"""ZARA-RACIOCINIO-LIVRE ETAPA 2 — classificador de intencao por modelo.

Contexto (Alex, 2026-08-27/28): ele nao quer ter que falar sempre do mesmo
jeito. Hoje a cadeia e 100% deterministica (regex em core/pc_voice_intent.py),
o que e rapido e de graca, mas rigido: fora do padrao esperado, a Zara recusa
honestamente ("ainda nao sei fazer isto").

Esta e a ETAPA 2 do plano em docs/audits/PROPOSTA_RACIOCINIO_LIVRE_2026-08-28.md:
construir o classificador como peca ISOLADA e testavel, SEM plugar na cadeia.
Nada em core/ipc_handlers.py chama este modulo ainda -- de proposito. Plugar e
a Etapa 3, atras de flag, e so no caminho de texto primeiro.

Desenho (as tres regras que importam):

1. NUNCA inventa acao. O modelo escolhe DENTRO de uma lista fechada de acoes
   ja registradas no ActionRegistry, passada como catalogo. Qualquer nome
   fora da lista e descartado aqui, nao vira execucao.
2. FALHA FECHADA. Sem chave, sem rede, timeout, JSON quebrado, confianca
   baixa ou acao desconhecida -> devolve None. Quem chamar deve seguir com a
   recusa honesta de hoje. Nunca "chuta" uma acao pra parecer inteligente.
3. NAO toca o caminho quente. So faz sentido ser chamado DEPOIS que toda a
   cadeia deterministica ja tentou e falhou, entao a latencia dele nunca
   entra no comando do dia a dia que ja funciona por regex.

Modelo: usa os endpoints gratuitos da NVIDIA (Nemotron/GLM) que ja estao no
MODEL_REGISTRY e cuja chave o Alex ja tem. Escolha deliberada por custo: o
fallback roda em toda frase que a Zara nao entende, entao nao pode ser um
modelo pago por chamada.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Ordem de preferencia: o menor/mais rapido primeiro. Classificar intencao e
# tarefa simples -- nao precisa do modelo de 550B, precisa de resposta curta e
# rapida. Se o primeiro estiver indisponivel, cai pro proximo.
_PREFERRED_MODEL_IDS = (
    "nvidia_nemotron_super",
    "nvidia_glm52",
    "nvidia_nemotron_ultra",
)

# MEDIDO em 2026-08-28 contra o endpoint gratuito da NVIDIA (Nemotron 3
# Super), nao estimado: com 120 tokens o modelo gastava o orcamento inteiro
# "pensando em voz alta" e era cortado ANTES de escrever o JSON -- a
# classificacao estava certa e se perdia na saida. Com 800 ele conclui.
_MAX_OUTPUT_TOKENS = 800

_MAX_TEXT_CHARS = 400
_MIN_CONFIDENCE = 0.6
# MEDIDO em 2026-08-28, mesma frase, endpoint gratuito da NVIDIA: 6.4s, 9.8s
# e 16.0s em tentativas diferentes -- lento e MUITO variavel. O timeout de 6s
# que estava aqui antes teria estourado na maioria das chamadas, transformando
# classificacao correta em recusa. Como este caminho so roda quando a Zara ja
# ia recusar de qualquer forma, esperar mais vale mais a pena do que desistir
# cedo. Isto NAO entra no comando do dia a dia, que continua no regex local.
_DEFAULT_TIMEOUT_S = 20.0


@dataclass(frozen=True, slots=True)
class IntentGuess:
    """Palpite do modelo, ja validado contra a lista fechada de acoes."""
    action: str
    param: str | None
    confidence: float


def build_action_catalog(allowed_actions: list[str]) -> list[dict[str, str]]:
    """Monta o catalogo (nome + descricao) das acoes que o modelo pode escolher.

    A descricao vem do proprio ActionSpec registrado, entao o catalogo nunca
    diverge do que a Zara realmente sabe fazer -- se uma action sumir do
    registry, ela some do catalogo automaticamente.
    """
    try:
        from core.action_registry import get_registry
        registry = get_registry()
    except Exception:
        return []

    catalog: list[dict[str, str]] = []
    for name in allowed_actions:
        spec = registry.get_spec(name)
        if spec is None:
            continue
        catalog.append({
            "name": name,
            "description": str(getattr(spec, "description", "") or "").strip()[:200],
        })
    return catalog


def _build_prompt(text: str, catalog: list[dict[str, str]]) -> str:
    linhas = "\n".join(f"- {item['name']}: {item['description']}" for item in catalog)
    return (
        "Voce interpreta pedidos falados em portugues do Brasil para um assistente "
        "de computador chamada ZARA.\n\n"
        "Escolha UMA acao da lista abaixo que corresponda ao pedido do usuario. "
        "Voce NAO executa nada, apenas classifica.\n\n"
        f"ACOES DISPONIVEIS:\n{linhas}\n\n"
        f"PEDIDO DO USUARIO:\n{text}\n\n"
        "Responda APENAS com um JSON, sem texto antes ou depois, no formato:\n"
        '{\"action\": \"<nome exato da lista>\", \"param\": \"<parametro ou null>\", '
        '\"confidence\": <0.0 a 1.0>}\n\n'
        "REGRAS DURAS:\n"
        "- Use SOMENTE um nome que esta na lista acima. Nunca invente nome de acao.\n"
        "- Se o pedido nao corresponder claramente a nenhuma acao da lista, "
        'responda {\"action\": null, \"param\": null, \"confidence\": 0.0}.\n'
        "- Se for conversa/pergunta (nao um comando de computador), responda "
        "action null tambem.\n"
        "- Prefira responder null a chutar. Chute errado faz a ZARA executar a "
        "coisa errada no computador do usuario."
    )


def _resolve_model() -> Any | None:
    """Primeiro modelo preferido que tem chave configurada. None se nenhum."""
    try:
        from core.model_router import get_model_config
    except Exception:
        return None

    for model_id in _PREFERRED_MODEL_IDS:
        config = get_model_config(model_id)
        if config is None:
            continue
        if str(os.environ.get(config.api_key_env) or "").strip():
            return config
    return None


def _call_nvidia(config: Any, prompt: str, timeout_s: float) -> str | None:
    """Chamada crua ao endpoint OpenAI-compativel da NVIDIA.

    Caminho proprio e enxuto de proposito: a proposta (Etapa 4) marca
    core/model_router.py como area de outro dono, que exigiria trava nomeada.
    Aqui so LEMOS a config dele, nunca alteramos o roteador.
    """
    try:
        import httpx
    except Exception:
        return None

    api_key = str(os.environ.get(config.api_key_env) or "").strip()
    if not api_key:
        return None

    try:
        response = httpx.post(
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": config.api_model,
                "messages": [
                    # Convencao do Nemotron: reduz a cadeia de raciocinio antes
                    # da resposta. MEDIDO: 16.0s -> 9.8s na mesma frase.
                    # Modelo que ignora esta linha simplesmente a trata como
                    # instrucao inofensiva, entao e seguro manter sempre.
                    {"role": "system", "content": "detailed thinking off"},
                    {"role": "user", "content": prompt},
                ],
                # Classificacao quer resposta determinista e curta, nao criatividade.
                "temperature": 0,
                "max_tokens": _MAX_OUTPUT_TOKENS,
            },
            timeout=timeout_s,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"])
    except Exception:
        return None


def _parse_response(raw: str, allowed_actions: list[str]) -> IntentGuess | None:
    """Extrai e VALIDA o JSON do modelo contra a lista fechada de acoes."""
    if not raw:
        return None

    # Modelos as vezes embrulham o JSON em cerca de codigo ou texto solto.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    action = data.get("action")
    if not isinstance(action, str) or not action.strip():
        return None
    action = action.strip()

    # A trava que impede o modelo de inventar capacidade que a Zara nao tem.
    if action not in allowed_actions:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None
    if confidence < _MIN_CONFIDENCE:
        return None

    param = data.get("param")
    if param is not None:
        if not isinstance(param, (str, int, float)):
            return None
        param = str(param).strip() or None

    return IntentGuess(action=action, param=param, confidence=confidence)


def classify_intent_with_llm(
    text: str,
    allowed_actions: list[str],
    *,
    call_model: Callable[[str], str | None] | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> IntentGuess | None:
    """Tenta entender um pedido que a cadeia deterministica NAO entendeu.

    Devolve None sempre que nao houver certeza suficiente -- quem chama deve
    seguir com a recusa honesta de hoje. `call_model` existe para teste:
    injetando uma funcao, o classificador roda inteiro sem tocar a rede.
    """
    clean = " ".join(str(text or "").split())[:_MAX_TEXT_CHARS]
    if not clean or not allowed_actions:
        return None

    catalog = build_action_catalog(allowed_actions)
    if not catalog:
        return None

    prompt = _build_prompt(clean, catalog)

    if call_model is None:
        config = _resolve_model()
        if config is None:
            return None
        raw = _call_nvidia(config, prompt, timeout_s)
    else:
        try:
            raw = call_model(prompt)
        except Exception:
            return None

    if not raw:
        return None
    # allowed_actions e a fonte da verdade, nao o catalogo (que pode ter
    # perdido entradas sem spec registrado).
    return _parse_response(raw, allowed_actions)
