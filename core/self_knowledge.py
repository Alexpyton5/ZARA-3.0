"""Deterministic, runtime-backed self-knowledge for ZARA."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join(
        "".join(ch for ch in normalized if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def detect_self_knowledge_topic(text: str) -> str | None:
    """Return a narrow self-knowledge topic, never a broad LLM intent guess."""
    value = _plain(text)
    if not value:
        return None
    if re.search(r"\b(por que|porque).*(falhou|nao funcionou|deu erro)\b|\bultima falha\b", value):
        return "failure"
    component_match = re.search(
        r"\b(?:o que e|quem e) (hermes|codex|mentor|supercerebro|lab)\b", value
    )
    if component_match:
        return component_match.group(1)
    if re.search(r"\b(qual|quais).*(provider|provedor)|\bproviders? disponiveis\b", value):
        return "providers"
    if re.search(r"\bqual (modelo|motor)\b|\bmodelo (esta|voce esta) usando\b", value):
        return "model"
    if re.search(r"\b(onde voce esta instalada|qual (e )?(seu )?(root|source|runtime)|onde fica sua instalacao)\b", value):
        return "runtime"
    if re.search(
        r"\b(o que voce consegue fazer|quais (sao )?(suas )?(funcoes|capacidades)|"
        r"o que esta funcionando|o que esta indisponivel|catalogo de capacidades)\b",
        value,
    ):
        return "capabilities"
    if re.search(r"\bquem e voce\b|\bo que e a? ?zara\b|\bse apresente\b", value):
        return "identity"
    return None


def _component(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(snapshot.get("components", {}).get(name, {}))


def _state_line(label: str, item: dict[str, Any]) -> str:
    state = str(item.get("status") or "UNKNOWN")
    detail = str(item.get("detail") or "").strip()
    return f"{label}: {state}" + (f" — {detail}" if detail else "")


def render_self_knowledge(topic: str, snapshot: dict[str, Any]) -> str:
    """Render a concise answer from observed runtime state."""
    if topic == "identity":
        return (
            "Eu sou ZARA, a assistente local deste computador. "
            "Modelo e provider são motores que eu uso; não são minha identidade."
        )

    if topic == "model":
        policy = str(snapshot.get("engine_policy") or "não informada")
        model = snapshot.get("effective_model")
        if isinstance(model, dict) and model:
            return (
                f"Eu sou ZARA. Meu motor efetivo mais recente foi {model.get('name') or model.get('id')} "
                f"({model.get('provider')}, modelo {model.get('api_model') or model.get('id')}). "
                f"Política atual: {policy}."
            )
        return (
            f"Eu sou ZARA. Política atual: {policy}. "
            "Ainda não há um motor efetivamente usado registrado nesta sessão."
        )

    if topic == "providers":
        providers = snapshot.get("providers") or []
        if not providers:
            return "Nenhum provider gratuito está configurado e disponível neste runtime."
        rows = [
            f"{item['name']}: {item['status']} ({item['models']} modelo(s))"
            for item in providers
        ]
        return "Providers configurados agora: " + "; ".join(rows) + "."

    if topic == "runtime":
        runtime = snapshot.get("runtime", {})
        mode = "empacotado" if runtime.get("frozen") else "source"
        return (
            f"Estou executando em modo {mode}. Source/root: {runtime.get('source_root')}. "
            f"Runtime: {runtime.get('executable')}. Dados locais: {runtime.get('data_root')}."
        )

    if topic in {"hermes", "codex", "mentor", "supercerebro", "lab"}:
        explanations = {
            "hermes": "Hermes é a integração local de execução e o gateway usado pelo Supercérebro.",
            "codex": "Codex é o agente de desenvolvimento que trabalha no código da ZARA.",
            "mentor": "Mentor é o conselheiro do projeto e orienta decisões importantes.",
            "supercerebro": "Supercérebro é o modo explícito que conecta o gateway Hermes e libera o gate de controle do PC; ele não remove confirmações de risco.",
            "lab": "LAB é o coordenador local de propostas, tarefas e workers da ZARA.",
        }
        return explanations[topic] + " " + _state_line("Estado atual", _component(snapshot, topic))

    if topic == "failure":
        failure = snapshot.get("last_failure")
        if not isinstance(failure, dict) or not failure:
            return "Ainda não há falha operacional registrada nesta sessão."
        return (
            f"Última falha operacional: {failure.get('action', 'ação desconhecida')} — "
            f"{failure.get('reason', 'motivo não registrado')} "
            f"(etapa: {failure.get('stage', 'desconhecida')})."
        )

    capabilities = snapshot.get("capabilities") or []
    if not capabilities:
        return "Meu catálogo de capacidades ainda não está disponível neste runtime."
    lines = [_state_line(str(item.get("label")), item) for item in capabilities]
    counts = snapshot.get("action_counts", {})
    header = (
        f"Catálogo vivo: {counts.get('registered', 0)} ações registradas; "
        f"Supercérebro {'ON' if snapshot.get('pc_control_allowed') else 'OFF'}."
    )
    return header + "\n" + "\n".join(f"- {line}" for line in lines)
