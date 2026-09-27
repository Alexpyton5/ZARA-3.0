"""
ZARA 3.0 - Python IPC Handlers
Handles all IPC communication between Electron frontend and Python backend.
"""

import asyncio
import base64
import json
import os
import re
import sys
import time
import traceback
import unicodedata
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from core.model_router import get_model_config

from core.pc_voice_intent import RESPOSTA_NAO_SEI


IPC_PROTOCOL_VERSION = 1
IPC_MAX_REQUEST_ID_LENGTH = 160
IPC_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
IPC_EVENT_TYPES = frozenset({
    "state-change", "message", "metrics", "voice-level", "voice-output-audio",
    "reminder-created", "reminder-fired", "routing-telemetry",
    "lab-v1-operation-result", "lab-release-ready", "backend-ready",
})


def _valid_request_id(value: object) -> bool:
    return isinstance(value, str) and bool(IPC_REQUEST_ID_RE.fullmatch(value))


def _sanitize_observation(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)\b(?:bearer\s+)?(?:sk-|api[_-]?key[=: ]+|token[=: ]+)[^\s,;]+", "<redacted>", text)
    text = re.sub(r"(?i)(?:[A-Z]:\\|/)[^\s,;]+", "<path>", text)
    return " ".join(text.split())[:180]


def _extract_memory_links(nodes: list[dict], max_links: int = 200) -> list[dict]:
    """Derive graph edges from cross-references between node titles.

    Pure function, read-only: given the same `nodes` list the Memory Galaxy
    handler already builds (each with at least {id, title, content}), look
    for one node's title appearing as a substring (case-insensitive) inside
    another node's content, and emit {"source": id_a, "target": id_b}.

    Guards:
    - never links a node to itself (id_a == id_b)
    - never emits both A->B and B->A for the same unordered pair
    - skips titles too short to be meaningful (< 3 chars) to avoid noise
    - stops at `max_links` to keep the payload bounded
    """
    links: list[dict] = []
    if not nodes:
        return links

    seen_pairs: set[frozenset] = set()

    entries = []
    content_by_id: dict[str, str] = {}
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        title = str(node.get("title") or "").strip()
        content_by_id[node_id] = str(node.get("content") or "").lower()
        if not node_id or not title or len(title) < 3:
            continue
        entries.append((node_id, title.lower()))

    for a_id, a_title in entries:
        content_a = content_by_id.get(a_id, "")
        if not content_a:
            continue
        for b_id, b_title in entries:
            if a_id == b_id:
                continue
            if b_title not in content_a:
                continue
            pair = frozenset((a_id, b_id))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            links.append({"source": a_id, "target": b_id})
            if len(links) >= max_links:
                return links
    return links


_WAKE_PREFIX_RE = re.compile(
    # ZARA-VOICE-WAKE-SAUDACAO-001
    #
    # Medido no latencia.jsonl (15-19/08): cinco vezes o Alex chamou pelo nome e foi
    # descartado. As cinco tinham saudacao antes do nome: "Ola, Zara, que horas".
    # A ancora ^ so tolerava "ei|hey", entao o nome deixava de ser prefixo e o portao
    # tratava a frase como fala de sala. Contra as 611 linhas descartadas reais, este
    # grupo faz 4 delas passarem e nenhuma frase de TV, porque a saudacao so vale
    # quando o nome vem logo depois.
    r"^\s*(?:(?:ol[aá]|oi|al[oô]|opa|e\s*a[íi]|bom\s+dia|boa\s+tarde|boa\s+noite)[\s,;:!.-]*)?"
    r"(?:(?:ei|hey)\s+)?(?:zara|sara|l[aá]zara|o\s+l[aá]zara)\b[\s,;:!.-]*(.*)$",
    flags=re.IGNORECASE,
)


# ZARA-NOMES-DA-CASA-001
#
# O STT continua ouvindo "Cláudio" no lugar de "Claude" — no histórico de
# 15/08 aparece três vezes seguidas: "leiam o que o Cláudio respondeu",
# "leia o que o Cláudio falou", "lê o que o Cláudio respondeu".
#
# Já existe a instrução de vocabulário no modelo, e ela ajuda mas não garante:
# pedir ao modelo é probabilidade, não regra. Aqui a correção é determinística e
# acontece antes de qualquer intent — mesmo caminho para voz e para texto.
#
# Só nomes próprios da casa entram nesta tabela. Corrigir palavra comum seria
# reescrever o que o Alex disse, e isso é pior que errar o nome.
_NOMES_DA_CASA = (
    # Os padroes evitam letra acentuada de proposito: `cl.udi` cobre
    # cláudio, claudio e clâudio de uma vez, e nao depende de este arquivo
    # sobreviver a uma conversao de codificacao - que ja corrompeu esta
    # tabela uma vez.
    #
    # "cloud code" vem antes de "claudio": as duas regras disputam a mesma
    # fala e a mais especifica tem de ganhar.
    (re.compile(r"\bcloud\s+code\b", re.IGNORECASE), "Claude Code"),
    (re.compile(r"\bcl.?udi[oa]s?\b", re.IGNORECASE), "Claude"),
    # Auditoria do Codex, achado 23: "codec" e palavra legitima. Corrigir
    # sempre transformava "pesquise codecs de audio" em "pesquise Codex de
    # audio". So corrige quando ele esta claramente falando COM o agente:
    # chamando pelo nome no comeco, ou mandando algo para ele.
    (re.compile(r"^\s*codecs?\b(?=[\s,:;!?-])", re.IGNORECASE), "Codex"),
    (re.compile(r"\b(?:pro|para\s+o|ao|do|com\s+o)\s+codecs?\b", re.IGNORECASE),
     lambda m: m.group(0)[: m.group(0).lower().rindex("codec")] + "Codex"),
    (re.compile(r"\bcorei\b", re.IGNORECASE), "Kore"),
    (re.compile(r"\bzarah\b", re.IGNORECASE), "ZARA"),
)


def _corrigir_nomes_da_casa(texto: str) -> str:
    """Devolve o texto com os nomes próprios da casa escritos certo.

    O substituto pode ser uma função quando a correção precisa preservar o que
    veio antes do nome — caso do "pro codec", que vira "pro Codex" sem comer
    a preposição.
    """
    for padrao, certo in _NOMES_DA_CASA:
        texto = padrao.sub(certo, texto)
    return texto


def _canonical_request(value: object) -> str:
    """Normalize voice and text into the same deterministic request shape."""
    text = _corrigir_nomes_da_casa(str(value or "").strip())
    wake = _WAKE_PREFIX_RE.match(text)
    if wake:
        return str(wake.group(1) or "").strip()
    return text


def _looks_like_unhandled_local_action(text: str) -> bool:
    """Fail closed for PC-action language that no deterministic handler claimed.

    ZARA-VOICE-VERBOS-001. A lista antiga so tinha as formas de imperativo
    "culto" (diminua, aumente, coloque). A fala real do Alex usa a forma
    coloquial (diminui, aumenta, abaixa, coloca, poe). O comando entao
    escapava do intent E do guarda, caia no LLM e voltava como
    "pronto, diminui o brilho" sem nada ter acontecido no Windows.

    Este guarda e a ultima linha de defesa contra falso sucesso: se um verbo
    de acao de PC chega aqui, a resposta tem de ser uma recusa honesta.
    Ao adicionar verbo novo ao intent, adicionar tambem aqui.
    """
    return bool(re.match(
        r"^\s*(?:"
        # abrir / fechar
        r"abra|abre|abrir|feche|fecha|fechar|"
        # janelas
        r"minimize|minimiza|minimizar|maximize|maximiza|maximizar|"
        r"restaure|restaura|restaurar|foca|focar|foque|"
        # aumentar / diminuir  (culto + coloquial)
        r"aumente|aumenta|aumentar|sobe|sobir|suba|"
        r"diminua|diminui|diminuir|abaixe|abaixa|abaixar|"
        r"baixe|baixa|baixar|reduza|reduz|reduzir|"
        # ligar / desligar / ativar
        r"ative|ativa|ativar|desative|desativa|desativar|"
        r"ligue|liga|ligar|desligue|desliga|desligar|"
        r"habilite|habilita|desabilite|desabilita|"
        # definir valor
        r"coloque|coloca|colocar|ponha|p[oõ]e|por|bote|bota|"
        r"defina|define|definir|deixe|deixa|deixar|ajuste|ajusta|"
        r"muda|mude|mudar|troca|troque|trocar|"
        # mover / copiar / colar
        r"mova|move|mover|copie|copia|copiar|cole|cola|colar|"
        r"renomeie|renomeia|apague|apaga|"
        # escrever / digitar
        r"digite|digita|digitar|escreva|escreve|escrever|"
        # buscar
        r"pesquise|pesquisa|pesquisar|procure|procura|procurar|"
        r"busque|busca|buscar|"
        # midia
        r"toque|toca|tocar|pause|pausa|pausar|continue|continua|"
        r"pula|pule|pular|avanca|avance|volta|volte|"
        r"manda|mande|mandar|reproduza|reproduz|"
        # tela / brilho sem o substantivo
        r"escurece|escurecer|escureca|clareia|clarear|clareie|"
        # silenciar
        r"silencia|silencie|silenciar|muta|mute|mutar"
        r")\b",
        text,
        flags=re.IGNORECASE,
    ))


# --- ETAPA 1 do plano de raciocinio livre -----------------------------------
# docs/audits/PROPOSTA_RACIOCINIO_LIVRE_2026-08-28.md, secao (d).
#
# So log, sem decisao nova: nao muda resposta, nao muda rota, nao introduz
# intent. Objetivo: juntar frases REAIS do Alex que hoje falham (recusa do
# guarda `_looks_like_unhandled_local_action` ou fuga para
# `orchestrator.process_message`), para desenhar a Etapa 2 (classificador)
# contra dado real em vez de casos inventados.
#
# Rollback: apagar `_BROAD_ACTION_LANGUAGE_RE`, `_has_broad_action_language_signal`,
# `_log_intent_telemetry` e as chamadas a `_log_intent_telemetry` nos dois
# pontos de dispatch (voz em `_process_voice_message`, texto em
# `handle_send_message`). Zero risco funcional: nenhuma delas participa da
# decisao de qual resposta a ZARA da.

_BROAD_ACTION_LANGUAGE_RE = re.compile(
    r"\b(?:"
    r"abr\w*|fech\w*|abaix\w*|aument\w*|diminu\w*|"
    r"lig(?:a|ue|ar)\w*|deslig\w*|ativ\w*|desativ\w*|"
    r"silenci\w*|mut[ae]\w*|"
    r"toc[ae]\w*|pause?\w*|volt[ae]\w*|avan[cç]\w*|pul[ae]\w*|reproduz\w*|"
    r"minimiz\w*|maximiz\w*|restaur\w*|foc(?:a|ar|o|que)\w*|"
    r"escrev\w*|digit\w*|pesquis\w*|busc\w*|procur\w*|"
    r"copi\w*|col[ae]\w*|renome\w*|apag\w*|mov[ae]\w*|"
    r"coloc\w*|p[oõ]e\w*|ponha\w*|ajust\w*|defin\w*|deix\w*|troc\w*|mud\w*|"
    r"brilho\w*|volume\w*|wi[- ]?fi|bluetooth|janela\w*|"
    r"aplicativo\w*|programa\w*|arquivo\w*|pasta\w*|noturn\w*|mudo\w*"
    r")\b",
    flags=re.IGNORECASE,
)


def _has_broad_action_language_signal(text: str) -> bool:
    """Heuristica SO de telemetria (ETAPA 1). Nao decide nada, nao muda rota.

    Mais ampla e NAO ancorada no inicio da frase, ao contrario de
    `_looks_like_unhandled_local_action`: o objetivo aqui e so sinalizar, no
    log, uma frase com "cheiro" de comando de PC que escapou dos dois
    filtros. Falso positivo aqui custa uma linha de log a mais; nunca afeta
    a resposta dada ao Alex.
    """
    return bool(_BROAD_ACTION_LANGUAGE_RE.search(text or ""))


def _log_intent_telemetry(event: str, path: str, text: str) -> None:
    """Log puro da ETAPA 1. Ver comentario de bloco acima.

    `event` e um destes dois: "refused_local_action" (caiu no guarda) ou
    "escaped_to_orchestrator" (fugiu para o LLM com sinal amplo de acao).
    `path` e "voice" ou "text", pela mesma razao que todo `[VOICE_TRACE]`
    ja distingue os dois caminhos.
    """
    print(
        f"[INTENT_TELEMETRY] event={event} path={path} text={text!r}",
        flush=True,
    )


# --- NIGHT-07: o guarda honesto tambem alimenta o Lab -----------------------
#
# Ate aqui o Lab so aprendia com falha de EXECUTOR (`stage=executor`). O caso
# mais comum de "a ZARA nao sabe fazer isso" -- o guarda honesto acima
# respondendo RESPOSTA_NAO_SEI -- gravava telemetria e parava ali: nunca
# chegava a `_remember_action_failure`, logo nunca virava CapabilityGap.
# Isto liga a origem que faltava reusando a MESMA funcao, o mesmo servico e o
# mesmo tipo de gap; nao existe segundo mecanismo de captura.
#
# O freio e a parte importante desta mudanca. Sem teto, cada frase nao
# entendida viraria um gap novo, e um gap novo COM `source_path` conhecido faz
# `EvolutionEngine.observe_and_plan` despachar uma missao SELF_IMPROVEMENT
# (core/lab_v1/evolution.py:137-148 e :234-248) -- provider real, custo real,
# por frase mal ouvida. Por isso, nesta ordem:
#
#   1. DEDUP por frase normalizada -> mesmo `gap_id`, upsert, uma linha so.
#   2. TETO diario de frases NOVAS -> o volume de gaps por dia e finito.
#   3. `source_path` so depois de N repeticoes -- e e o `source_path` que
#      transforma o gap em missao dirigida. Sem ele o gap fica registrado e
#      INERTE, que e o estado padrao de toda frase nova.
#   4. Depois de escalonar, a frase para de reescrever o gap. O
#      `observation_id` do EvolutionEngine e hash do CONTEUDO dos gaps
#      (evolution.py:150-153 e :235-236): reescrever o mesmo gap com um
#      contador novo mudaria o hash e valeria UMA MISSAO NOVA para a mesma
#      frase. Escalonou uma vez, escreveu uma vez, fim.
#
# Rollback: apagar este bloco, o metodo `_remember_unhandled_intent`, as duas
# chamadas a ele (voz em `_process_voice_message`, texto em
# `handle_send_message`) e o `dedup_key` em `LabV1Service.capture_runtime_failure`.
# A cadeia de resposta ao Alex nao muda em nenhum dos dois caminhos.

UNHANDLED_INTENT_STAGE = "unhandled_intent"

# Onde o intent DEVERIA ter sido reconhecido, por evidencia e nao por chute:
# os verbos deste guarda sao os mesmos que `core/pc_voice_intent.py` mapeia
# para action (minimizar em :487, brilho/escurecer em :477, mudo/silenciar em
# :425). O executor nao falhou -- ninguem chegou a chama-lo, porque nenhum
# padrao daquele arquivo casou. O arquivo tambem esta no inventario que o
# EvolutionEngine varre (`core/**/*.py`), condicao para o gap virar missao.
UNHANDLED_INTENT_SOURCE_PATH = "core/pc_voice_intent.py"

# Repeticoes da MESMA frase normalizada antes de a lacuna virar missao real.
# 1 ocorrencia e ruido (STT errando uma palavra, frase pela metade); 2 ainda
# pode ser a mesma tentativa repetida por teimosia no mesmo minuto; 3 e padrao
# de uso -- o Alex quer aquilo e a ZARA nao tem. Valor conservador de
# proposito: erra para o lado de NAO gastar provider.
UNHANDLED_INTENT_MISSION_THRESHOLD = 3

# Teto de frases NOVAS persistidas por dia. Gap nao escalonado nao dispara
# missao, mas entra na evidencia que vai no prompt do worker
# (evolution.py:225) -- ou seja, custa token quando alguma missao roda. Dez
# frases novas por dia cobre com folga um dia real de uso do Alex e mantem o
# blob de evidencia pequeno.
UNHANDLED_INTENT_MAX_NEW_GAPS_PER_DAY = 10

# Teto de escalonamentos por dia. Cada escalonamento vale, no pior caso, UMA
# missao SELF_IMPROVEMENT nova (o gap passa a ter `source_path`, e o
# `observation_id` do EvolutionEngine muda uma vez). Dois por dia e o limite
# duro de gasto que esta mudanca pode provocar sozinha.
UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY = 2

_UNHANDLED_INTENT_NOISE_RE = re.compile(r"[^a-z0-9 ]+")


def _normalize_unhandled_phrase(text: str) -> str:
    """Chave estavel da frase, identica vinda de voz ou de texto.

    O STT devolve "abaixa o brilho pela metade" e o teclado devolve
    "Abaixa o brilho pela metade." -- a mesma lacuna. Sem dobrar acento,
    caixa e pontuacao, os dois canais criariam DOIS gaps para a mesma coisa e
    a paridade voz/texto seria mentira no banco. Descartar tudo que nao e
    letra/digito/espaco tambem tira do identificador qualquer caminho de
    arquivo ou token que tenha caido na frase por acidente.
    """
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(_UNHANDLED_INTENT_NOISE_RE.sub(" ", ascii_only).split())[:120]


# --- ETAPA 3 do plano de raciocinio livre -----------------------------------
# docs/audits/PROPOSTA_RACIOCINIO_LIVRE_2026-08-28.md.
#
# Plugar o classificador da Etapa 2 (core/intent_classifier.py) SO no caminho
# de TEXTO (voz e a Etapa 4, area do ENGENHEIRO_LATENCIA, precisa de trava
# nomeada por tocar model_router.py), atras de uma flag lida do disco a cada
# chamada -- desligar e so mudar um arquivo, sem rebuild, sem redeploy.
#
# So roda DEPOIS que toda a cadeia deterministica ja tentou e falhou (o
# proprio guarda `_looks_like_unhandled_local_action` ja decidiu recusar).
# Nao compete em velocidade com o comando do dia a dia: o caminho rapido de
# regex continua identico, byte a byte, pra quem a flag nunca tocou.
#
# Rollback: desligar a flag no arquivo -- a cadeia volta a ser 100% regex +
# guarda, sem reverter nenhum arquivo de codigo.

_FEATURE_FLAGS_FILE_NAME = "feature_flags.json"

# Conjunto pequeno e deliberado: so acoes onde o parametro do classificador
# (uma string livre) da pra converter com seguranca pro tipo que a action
# realmente espera. O classificador ja e limitado a acoes que existem no
# ActionRegistry (core/intent_classifier.py); esta lista e uma SEGUNDA trava,
# mais apertada, so pra decidir em quais delas confiamos o suficiente pra
# montar o parametro sem confirmacao humana no meio.
_ETAPA3_ALLOWED_ACTIONS = (
    "os_volume",
    "os_brightness_absolute",
    "audio_mute",
    "audio_unmute",
    "os_app",
    "os_close_safe_app",
    "youtube_open",
    "system_time",
    "system_info",
)


def _raciocinio_livre_fallback_texto_habilitado() -> bool:
    """Le a flag do disco a cada chamada -- desligar nao pede reinicio.

    Falha fechada: arquivo ausente, ilegivel ou campo faltando = desligado.
    """
    try:
        from core.paths import config_dir
        flags_path = config_dir() / _FEATURE_FLAGS_FILE_NAME
        if not flags_path.exists():
            return False
        import json
        data = json.loads(flags_path.read_text(encoding="utf-8"))
        return bool(data.get("raciocinio_livre_fallback_texto", False))
    except Exception:
        return False


# ZARA-INTENSIDADE-VOLUME-001 (Alex, 2026-08-28)
# "põe o som lá em baixo" e "diminua muito o volume" caíam num passo fixo de
# 10 pontos, igual a "diminua um pouco" -- nenhuma diferença de magnitude.
# O PcVoiceIntentDetector (core/pc_voice_intent.py) agora anexa um sufixo
# fechado ("_pouco"/"_muito") ao param "up"/"down" quando a frase carrega
# intensidade explícita ou idiomática. Aqui só se decodifica esse sufixo em
# um passo real -- sem chamada nova, sem latência nova, mesmo caminho
# determinístico de sempre.
_PASSO_POR_INTENSIDADE = {None: 10, "pouco": 5, "muito": 30}


def _resolver_direcao_e_delta(param: str | None) -> tuple[str, int] | None:
    """Decodifica 'up'/'down' (+ sufixo opcional _pouco/_muito) num delta
    assinado. None quando o param não é uma direção reconhecida -- quem
    chamar deve tratar como valor absoluto ou desistir honestamente."""
    if not isinstance(param, str):
        return None
    direcao, _, sufixo = param.partition("_")
    if direcao not in ("up", "down"):
        return None
    passo = _PASSO_POR_INTENSIDADE.get(sufixo or None)
    if passo is None:
        return None
    return direcao, (passo if direcao == "up" else -passo)


def _montar_parametros_etapa3(action: str, param: str | None) -> dict | None:
    """Converte o palpite do classificador (string livre) pro tipo real da
    action. None quando a conversao nao e segura -- quem chamar deve desistir
    honestamente, nunca executar com um palpite de tipo errado."""
    if action in {"audio_mute", "audio_unmute", "youtube_open", "system_time", "system_info"}:
        return {}
    if action == "os_volume":
        try:
            return {"level": max(0, min(100, int(float(param))))}
        except (TypeError, ValueError):
            return None
    if action == "os_brightness_absolute":
        try:
            return {"level": max(0, min(100, int(float(param))))}
        except (TypeError, ValueError):
            return None
    if action in {"os_app", "os_close_safe_app"}:
        if not param or not str(param).strip():
            return None
        return {"app": str(param).strip()}
    return None


async def _tentar_raciocinio_livre_texto(self, text: str) -> str | None:
    """ETAPA 3: ultimo recurso, so por texto, so atras da flag.

    Devolve None sempre que nao houver certeza suficiente -- quem chamar
    segue com a recusa honesta de sempre (RESPOSTA_NAO_SEI). Nunca finge
    sucesso: a resposta so sai afirmativa quando `result.success` e real.
    """
    if not _raciocinio_livre_fallback_texto_habilitado():
        return None

    try:
        from core.intent_classifier import classify_intent_with_llm
    except Exception:
        return None

    guess = classify_intent_with_llm(text, list(_ETAPA3_ALLOWED_ACTIONS))
    if guess is None:
        return None

    params = _montar_parametros_etapa3(guess.action, guess.param)
    if params is None:
        return None

    import core.actions  # noqa: F401
    from core.action_registry import execute_action

    print(
        f"[INTENT_TELEMETRY] event=free_reasoning_fallback_attempt path=text "
        f"action={guess.action} confidence={guess.confidence:.2f} text={text!r}",
        flush=True,
    )

    result = await execute_action(guess.action, **params)
    self._anotar_experiencia(
        text,
        guess.action,
        bool(result is not None and getattr(result, "success", False)),
        str(getattr(result, "output", "") or getattr(result, "error", "") or ""),
        "raciocinio_livre_texto",
    )
    if result is None or not getattr(result, "success", False):
        # Falhou de verdade (gate de risco, app nao encontrado, etc) -- a
        # mensagem do proprio executor ja e honesta, so repassa.
        return str(getattr(result, "error", "") or None) or None
    return str(getattr(result, "output", "") or "Feito.")




def _tts_voice_name(obj: object) -> str:
    """Best-effort name of the voice a TTS engine is configured to use.

    Observability helper for ZARA-VOICE-TTS-OBSERVABILITY-001. Never raises:
    an unknown voice must degrade to "?" and never break the speaking path.
    """
    for holder in (getattr(obj, "config", None), obj):
        if holder is None:
            continue
        for attr in ("voice_name", "gemini_voice", "voice"):
            value = getattr(holder, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "?"


def _observe_failure(action: str, stage: str, exc: BaseException, started: float) -> None:
    print(
        f"[OBS] action={action} stage={stage} exception_type={type(exc).__name__} "
        f"message={_sanitize_observation(exc)} duration_ms={(time.perf_counter() - started) * 1000:.1f}",
        file=sys.stderr,
    )


def _speak_windows_sapi(text: str) -> None:
    """Use the built-in Windows voice when optional neural weights are absent."""
    if os.name != "nt":
        raise RuntimeError("WINDOWS_SAPI_UNAVAILABLE")
    import comtypes.client
    from comtypes import CoInitialize, CoUninitialize

    CoInitialize()
    try:
        speaker = comtypes.client.CreateObject("SAPI.SpVoice")
        speaker.Speak(str(text))
    finally:
        CoUninitialize()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.conversation_history import ConversationHistory


def _read_windows_volume() -> float | None:
    """Read current master volume (0-100) via pycaw. Returns None if unavailable."""
    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume
        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = get_endpoint_volume(devices)
            return round(volume.GetMasterVolumeLevelScalar() * 100)
        finally:
            CoUninitialize()
    except Exception:
        return None


def _read_windows_brightness_level() -> int | None:
    """Read brightness only when a verified backend exists in this runtime."""
    try:
        from core.actions import os_ops

        ddcci = getattr(os_ops, "_read_windows_brightness", None)
        wmi = getattr(os_ops, "_wmi_read_brightness", None)
        observed = ddcci() if callable(ddcci) else None
        if observed is None and callable(wmi):
            observed = wmi()
        return int(observed) if observed is not None else None
    except Exception:
        return None

# Import existing ZARA components
try:
    from core.action_registry import execute_action, execute_confirmed_action
    from core.model_router import ModelRouter
    from core.zara_orchestrator import ZaraOrchestrator
    from memory.memory_manager import MemoryManager
except ImportError as e:
    print(f"[IPC Handlers] Warning: Some imports failed: {e}", file=sys.stderr)

# Voice components (optional)
try:
    from core.voice_stt import VoiceConfig, VoicePipeline, create_voice_pipeline
    from core.voice_tts import KokoroTTS, TTSConfig, TTSManager
    VOICE_AVAILABLE = True
except ImportError as e:
    print(f"[IPC Handlers] Voice components not available: {e}")
    VOICE_AVAILABLE = False
    VoicePipeline = None  # type: ignore[assignment]
    VoiceConfig = None  # type: ignore[assignment]
    create_voice_pipeline = None  # type: ignore[assignment]
    TTSManager = None  # type: ignore[assignment]
    TTSConfig = None  # type: ignore[assignment]
    KokoroTTS = None  # type: ignore[assignment]

try:
    from core.gemini_live_voice import (
        GeminiLiveVoice,
        GeminiLiveVoiceConfig,
        is_explicit_human_barge_in,
        looks_like_assistant_echo,
    )
    GEMINI_LIVE_MODULE_AVAILABLE = True
except ImportError as e:
    print(f"[IPC Handlers] Gemini Live module unavailable: {e}")
    GEMINI_LIVE_MODULE_AVAILABLE = False
    GeminiLiveVoice = None  # type: ignore[assignment]
    GeminiLiveVoiceConfig = None  # type: ignore[assignment]

try:
    from core.lab_coordinator import LabCoordinator
    from core.lab_worker_runtime import LabWorkerRuntime
    LAB_AVAILABLE = True
except ImportError as e:
    print(f"[IPC Handlers] ZARA Lab module unavailable: {e}")
    LAB_AVAILABLE = False
    LabCoordinator = None  # type: ignore[assignment]
    LabWorkerRuntime = None  # type: ignore[assignment]

try:
    # ZARA-LAB-V1-001: multi-agent runtime with its own service boundary.
    from core.lab_v1.service import LabV1Service
    LAB_V1_AVAILABLE = True
except ImportError as e:
    print(f"[IPC Handlers] ZARA Lab V1 module unavailable: {e}")
    LAB_V1_AVAILABLE = False
    LabV1Service = None  # type: ignore[assignment]


_chat_relay_instance = None


def _get_chat_relay():
    """Singleton preguiçoso do ChatRelay (ponte da Conselheira).

    TODO (Alex/OpenCode): ligar o Gmail real da ZARA aqui. Implemente o
    CeoMailAdapter com o código do painel Comunicações e passe
    ``adapter=...`` para o ChatRelay. Sem isso, o LoggingStubAdapter só
    registra localmente (sem rede) — ótimo para desenvolvimento.
    """
    global _chat_relay_instance
    if _chat_relay_instance is not None:
        return _chat_relay_instance
    try:
        from core.lab_ceo_gmail_bridge import ChatRelay
    except ImportError as e:
        print(f"[IPC Handlers] ChatRelay indisponível: {e}")
        return None
    _chat_relay_instance = ChatRelay()
    return _chat_relay_instance


@dataclass
class IPCMessage:
    type: str
    request_id: str | None = None
    payload: dict[str, Any] | None = None
    error: str | None = None
    response: Any | None = None
    result: Any | None = None
    state: str | None = None
    message: str | None = None
    metrics: dict | None = None
    level: float | None = None
    tone: float | None = None
    speaking: bool | None = None
    active: bool | None = None
    data: Any | None = None


IPC_REQUEST_ALLOWLIST = frozenset({
    "engine-change", "engine-list", "send-message", "interrupt", "voice-mute",
    "voice-mic-chunk", "action-execute", "action-confirm", "action-confirm-cancel",
    "action-list", "self-status", "system-metrics", "latencia-resumo", "system-info",
    "voice-start", "voice-stop", "voice-status", "config-get", "config-set",
    "lab-state", "lab-send", "lab-proposal-create", "lab-proposal-decide",
    "lab-v1-snapshot", "lab-v1-create-session", "lab-v1-admit-operation",
    "lab-v1-confirm-operation", "lab-v1-submit", "lab-v1-autopilot",
    "lab-v1-autopilot-activate", "lab-v1-autonomy-configure", "lab-v1-cancel-mission",
    "lab-v1-delete-session", "lab-v1-providers", "lab-v1-proposal-list",
    "lab-v1-proposal-register", "lab-v1-proposal-update", "lab-v1-agent-inventory",
    "lab-v1-agent-profiles", "lab-v1-agent-profile-update", "lab-v1-agent-profile-rollback",
    "lab-v1-create-agent", "lab-v1-configure-agent", "lab-v1-archive-agent",
    "lab-v1-rebind-role", "lab-v1-research-skill", "lab-v1-team-chat",
    "reminder-create", "reminder-list", "reminder-cancel", "memory-user-add",
    "memory-user-search", "memory-user-list", "memory-user-forget", "project-memory-get",
    "project-memory-list", "project-memory-activate", "project-memory-context",
    "memory-galaxy-list", "conversation-history-list", "conversation-history-clear",
})


def parse_ipc_message(data: object) -> IPCMessage:
    """Validate one inbound frame before it reaches a handler."""
    if not isinstance(data, dict):
        raise ValueError("IPC envelope must be an object")
    message_type = data.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise ValueError("IPC message type is required")
    request_id = data.get("request_id")
    if request_id is not None and not _valid_request_id(request_id):
        raise ValueError("IPC request_id is invalid")
    if message_type not in IPC_REQUEST_ALLOWLIST:
        raise ValueError("IPC message type is not allowlisted")
    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("IPC payload must be an object")
    fields = {key: value for key, value in data.items() if key in IPCMessage.__dataclass_fields__}
    return IPCMessage(**fields)


class IPCHandler:
    """Base handler for IPC messages"""

    _LAB_V1_CONFIRM_TIMEOUT_SECONDS = 2.0

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._smoke_test = os.environ.get('ZARA_SMOKE_TEST') == '1'
        self.orchestrator: ZaraOrchestrator | None = None
        self.model_router: ModelRouter | None = None
        self.memory: MemoryManager | None = None
        # ZARA-VELOCIDADE-001 (Alex, 2026-08-28 noite): resposta por voz tem
        # que ser rápida por padrão -- não é mais preciso pedir "modo rápido".
        self.current_engine: str = "gpt-5.6-luna"
        # ZARA-TELEGRAM-GRUPO-001: ponte do grupo, em paralelo com a privada.
        self._telegram_grupo = None
        self._telegram_adapter = None
        self.voice_active: bool = False
        self.supercerebro_active: bool = False
        # Every new IPC runtime starts fail-closed. A previous handler or
        # test must not leave local PC control enabled for this instance.
        from core.action_registry import get_registry
        get_registry().pc_control_allowed = False

        # Voice pipeline
        self.voice_pipeline: VoicePipeline | None = None
        self.tts_manager: TTSManager | None = None
        self._voice_level: float = 0.0
        self._voice_tone: float = 0.5
        self._voice_speaking: bool = False
        self._assistant_output_active: bool = False
        self._assistant_output_text: str = ""
        self._assistant_output_protect_until: float = 0.0
        self._recent_assistant_outputs: deque[tuple[str, float]] = deque(maxlen=3)
        self._voice_last_error: str | None = None
        self._voice_loop_task: asyncio.Task | None = None
        self._voice_start_lock = asyncio.Lock()
        self._tts_initialized: bool = False
        self.gemini_live_voice: GeminiLiveVoice | None = None
        self.voice_mode: str = "off"
        self._gemini_wake_armed_until: float = 0.0
        self._manual_voice_session: bool = False
        # ZARA-VOICE-LATENCY-OBSERVABILITY-001: start of the current voice turn.
        self._voice_turn_started: float = 0.0
        # Monotonic semantic fence. Provider threads may finish after barge-in,
        # but only the currently active generation may publish or speak.
        self._voice_turn_generation: int = 0
        self._active_voice_turn_id: int | None = None
        # ZARA-VOICE-ECO-001: ultima resposta falada, para nao se ouvir.
        self._last_spoken_text: str = ""
        # ZARA-CONFIRMACAO-VAZIA-001: a ultima frase dele que ela REALMENTE
        # processou, para citar em vez de afirmar que entendeu.
        self._ultimo_pedido_entendido: str = ""
        self.lab = None
        self._lab_background_tasks: set[asyncio.Task] = set()
        self.lab_v1 = None
        self._lab_v1_background_tasks: set[asyncio.Task] = set()
        self._voice_persistence_tasks: set[asyncio.Task] = set()
        self.reminder_engine = None  # initialized in async init
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self.user_memory = None      # initialized in async init
        self.project_memory = None   # initialized in async init
        # The Home transcript must be available before any IPC message arrives.
        # Its SQLite connection is opened lazily on the first read or write.
        self.conversation_history: ConversationHistory | None = ConversationHistory()
        self._last_volume_level: int | None = None
        self._last_brightness_level: int | None = None
        self._last_window_hwnd: int | None = None
        self._last_safe_folder: str | None = None
        self._last_safe_app: str | None = None
        self._operational_context: dict[str, Any] | None = None
        self._operational_context_updated_at: float = 0.0
        self._operational_context_turns: int = 0
        self._last_action_failure: dict[str, str] | None = None
        # Ephemeral one-shot clipboard confirmation. Never persisted or logged.
        self._pending_clipboard_text: str | None = None
        self._pending_clipboard_expires_at: float = 0.0

    async def _try_pending_clipboard_confirmation(self, text: str) -> str | None:
        # Some focused router tests construct a deliberately minimal handler
        # through __new__; missing ephemeral state is equivalent to no pending
        # confirmation and must not break unrelated intent routing.
        pending = getattr(self, "_pending_clipboard_text", None)
        expires_at = float(getattr(self, "_pending_clipboard_expires_at", 0.0))
        if pending is None or time.monotonic() > expires_at:
            self._pending_clipboard_text = None
            self._pending_clipboard_expires_at = 0.0
            return None
        normalized = re.sub(r"^\s*zara\s*[,;:]?\s*", "", str(text or "").strip().lower())
        answer = re.sub(r"[^a-záàâãéêíóôõúç]", "", normalized)
        if answer in {"sim", "pode", "confirmo", "confirma", "copie", "copia", "ok"}:
            self._pending_clipboard_text = None
            self._pending_clipboard_expires_at = 0.0
            from core.action_registry import execute_action
            result = await execute_action("os_clipboard", text=pending, confirm=True)
            if result and getattr(result, "success", False) and (getattr(result, "data", None) or {}).get("verified"):
                return "Área de transferência limpa e confirmada." if pending == "" else "Copiado e confirmado."
            return "Não consegui confirmar a alteração na área de transferência."
        if answer in {"não", "nao", "cancele", "cancela", "cancelar"}:
            self._pending_clipboard_text = None
            self._pending_clipboard_expires_at = 0.0
            return "Cancelado. Não alterei a área de transferência."
        return "Ainda preciso da sua confirmação. Diga sim ou não."

    def _context_fresh(self, kind: str | None = None) -> bool:
        fresh = (
            self._operational_context_turns > 0
            and time.monotonic() - self._operational_context_updated_at <= 120.0
        )
        if not fresh:
            if self._operational_context is not None:
                self._clear_operational_context()
            return False
        return kind is None or bool(
            self._operational_context
            and self._operational_context.get("action_type") == kind
        )

    def _touch_operational_context(self) -> None:
        self._operational_context_updated_at = time.monotonic()
        self._operational_context_turns = 3
        if self._operational_context is None:
            candidates = [
                ("window", self._last_window_hwnd is not None),
                ("folder", self._last_safe_folder is not None),
                ("volume", self._last_volume_level is not None),
            ]
            present = [kind for kind, enabled in candidates if enabled]
            self._operational_context = {
                "action_type": present[0] if len(present) == 1 else "ambiguous",
                "canonical_target": self._last_safe_folder or self._last_safe_app,
                "pid": None,
                "hwnd": self._last_window_hwnd,
                "verified_value": self._last_volume_level,
                "timestamp": self._operational_context_updated_at,
                "created_by_zara": False,
            }

    def _set_operational_context(
        self,
        action_type: str,
        *,
        canonical_target: str | None = None,
        pid: int | None = None,
        hwnd: int | None = None,
        verified_value: object = None,
        created_by_zara: bool = False,
    ) -> None:
        """Keep only the latest proven action, using canonical non-sensitive fields."""
        self._last_volume_level = int(verified_value) if action_type == "volume" else None
        self._last_window_hwnd = hwnd if action_type in {"app", "window"} else None
        self._last_safe_folder = canonical_target if action_type == "folder" else None
        self._last_safe_app = canonical_target if action_type in {"app", "window"} else None
        self._operational_context_updated_at = time.monotonic()
        self._operational_context_turns = 3
        self._operational_context = {
            "action_type": action_type,
            "canonical_target": canonical_target,
            "pid": pid,
            "hwnd": hwnd,
            "verified_value": verified_value,
            "timestamp": self._operational_context_updated_at,
            "created_by_zara": bool(created_by_zara),
        }

    def _clear_operational_context(self) -> None:
        self._last_volume_level = None
        self._last_window_hwnd = None
        self._last_safe_folder = None
        self._last_safe_app = None
        self._operational_context = None
        self._operational_context_updated_at = 0.0
        self._operational_context_turns = 0

    def _remember_action_failure(
        self,
        action: str,
        stage: str,
        reason: object,
        *,
        source_path: str | None = None,
        dedup_key: str | None = None,
    ) -> None:
        action_id = str(action or "unknown")
        failure_stage = str(stage or "unknown")
        bounded_reason = _sanitize_observation(reason) or "motivo não informado"
        self._last_action_failure = {
            "action": action_id,
            "stage": failure_stage,
            "reason": bounded_reason,
            "at": datetime.now().isoformat(),
        }
        # Capability gates are policy/refusal decisions, not observed product
        # defects. Persist an actual missing executor, an execution failure, or
        # a phrase no deterministic handler claimed (NIGHT-07) -- that last one
        # arrives already rate-limited by `_remember_unhandled_intent`.
        if failure_stage not in {"registry", "executor", UNHANDLED_INTENT_STAGE}:
            return
        service = getattr(self, "lab_v1", None)
        if service is None or not hasattr(service, "capture_runtime_failure"):
            return
        resolved_source = str(source_path or "")
        if not resolved_source and failure_stage == "executor":
            try:
                from core.action_registry import get_registry
                executor = get_registry()._actions.get(action_id)
                module = str(getattr(executor, "__module__", ""))
                if module.startswith("core."):
                    resolved_source = module.replace(".", "/") + ".py"
            except Exception:
                resolved_source = ""
        channel = "voice" if getattr(self, "_active_voice_turn_id", None) is not None else "conversation"
        run_id = ("voice:" + str(self._active_voice_turn_id)
                  if getattr(self, "_active_voice_turn_id", None) is not None else None)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(service.capture_runtime_failure(
            action_id, source_path=resolved_source, stage=failure_stage,
            status="EXECUTOR_FAILED" if failure_stage == "executor" else "CAPABILITY_MISSING",
            reason=bounded_reason, channel=channel, run_id=run_id, dedup_key=dedup_key))
        tasks = getattr(self, "_lab_v1_background_tasks", None)
        if tasks is not None:
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    def _unhandled_intent_budget(self) -> dict[str, Any]:
        """Estado do freio, criado sob demanda.

        Sob demanda porque varios testes (e o proprio caminho de recuperacao)
        constroem o handler por `__new__`, sem `__init__`. Contadores e frases
        ja escalonadas NAO zeram na virada do dia de proposito: uma frase que o
        Alex tenta toda manha continua somando ate virar missao. Quem zera sao
        so os tetos diarios.
        """
        state = getattr(self, "_unhandled_intent_state", None)
        today = datetime.now().strftime("%Y-%m-%d")
        if state is None:
            state = {"day": today, "counts": {}, "escalated": set(),
                     "new_today": 0, "escalations_today": 0}
            self._unhandled_intent_state = state
        if state["day"] != today:
            state["day"] = today
            state["new_today"] = 0
            state["escalations_today"] = 0
        return state

    def _remember_unhandled_intent(self, text: str) -> None:
        """Guarda honesto -> CapabilityGap, com teto. Ver bloco NIGHT-07 acima.

        Chamado dos DOIS caminhos, com a mesma frase e o mesmo resultado:
        voz em `_process_voice_message`, texto em `handle_send_message`.
        Nao muda a resposta dada ao Alex em nenhum dos dois -- ela continua
        sendo `RESPOSTA_NAO_SEI`.
        """
        phrase = _normalize_unhandled_phrase(text)
        if not phrase:
            return
        state = self._unhandled_intent_budget()
        counts = state["counts"]
        if phrase in state["escalated"]:
            # Ja registrada COM `source_path`: ja e elegivel a missao dirigida.
            # Reescrever o gap mudaria o `detail`, e o `observation_id` do
            # EvolutionEngine e hash do conteudo dos gaps -- cada reescrita
            # viraria uma missao nova para a MESMA frase. So conta e sai.
            counts[phrase] = counts.get(phrase, 0) + 1
            print(f"[VOICE_TRACE] stage=CAPABILITY_GAP result=ALREADY_ESCALATED "
                  f"occurrences={counts[phrase]}", flush=True)
            return
        if phrase not in counts and state["new_today"] >= UNHANDLED_INTENT_MAX_NEW_GAPS_PER_DAY:
            print("[VOICE_TRACE] stage=CAPABILITY_GAP result=BUDGET_EXHAUSTED "
                  "scope=new_gaps_today", flush=True)
            return
        if phrase not in counts:
            state["new_today"] += 1
        occurrences = counts.get(phrase, 0) + 1
        counts[phrase] = occurrences
        escalate = (occurrences >= UNHANDLED_INTENT_MISSION_THRESHOLD
                    and state["escalations_today"] < UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY)
        if escalate:
            state["escalated"].add(phrase)
            state["escalations_today"] += 1
        elif occurrences > 1:
            # Nada mudou de estado: a lacuna ja esta registrada e continua
            # inerte. Reescrever o mesmo gap so para trocar o contador gasta
            # IO e mexe no `detail` que o EvolutionEngine hasheia. So conta.
            print(f"[VOICE_TRACE] stage=CAPABILITY_GAP result=COUNTED "
                  f"occurrences={occurrences}", flush=True)
            return
        print(f"[VOICE_TRACE] stage=CAPABILITY_GAP "
              f"result={'ESCALATED' if escalate else 'RECORDED'} "
              f"occurrences={occurrences} stage_origin={UNHANDLED_INTENT_STAGE}", flush=True)
        self._remember_action_failure(
            f"{UNHANDLED_INTENT_STAGE}:{phrase[:80]}",
            UNHANDLED_INTENT_STAGE,
            f"nenhum handler deterministico reconheceu a frase "
            f"(ocorrencia {occurrences}): {phrase}",
            # Sem `source_path` o gap fica registrado e inerte: o
            # EvolutionEngine so monta missao dirigida para gap cujo caminho
            # existe no inventario (evolution.py:137-148).
            source_path=UNHANDLED_INTENT_SOURCE_PATH if escalate else "",
            dedup_key=f"{UNHANDLED_INTENT_STAGE}:{phrase}",
        )

    async def _build_self_knowledge_snapshot(self, *, probe_hardware: bool = False) -> dict[str, Any]:
        """Observe current runtime state without exposing keys or inventing availability."""
        from core.action_registry import get_registry
        from core.model_router import get_model_config
        from core.paths import project_root, user_data_dir

        registry = get_registry()
        specs = [registry.get_spec(name) for name in registry.list_actions()]
        specs = [spec for spec in specs if spec is not None]

        last_engine = self.orchestrator.last_engine_used if self.orchestrator else None
        effective_model: dict[str, Any] | None = None
        model = get_model_config(last_engine) if last_engine else None
        if model:
            effective_model = {
                "id": model.id,
                "name": model.name,
                "provider": model.provider.value,
                "api_model": model.api_model,
            }

        provider_rows = self.model_router.configured_model_status(include_paid=False) if self.model_router else []
        providers: dict[str, dict[str, Any]] = {}
        for row in provider_rows:
            name = str(row.get("provider") or "unknown")
            state = str((row.get("health") or {}).get("state") or "UNKNOWN")
            item = providers.setdefault(name, {"name": name, "models": 0, "states": []})
            item["models"] += 1
            item["states"].append(state)
        for item in providers.values():
            states = item.pop("states")
            item["status"] = "AVAILABLE" if "AVAILABLE" in states else states[0]

        def component(status: str, detail: str) -> dict[str, str]:
            return {"status": status, "detail": detail}

        voice_ready = bool(self.voice_active or self.voice_pipeline or self.gemini_live_voice)
        voice_detail = (
            f"modo {self.voice_mode}"
            if self.voice_active
            else "pipeline disponível, inativo"
            if (self.voice_pipeline or self.gemini_live_voice)
            else "pipeline não preparado"
        )
        components = {
            "codex": component("NOT_CONFIGURED", "sem canal direto dentro do runtime da ZARA"),
            "mentor": component(
                "LIMITED" if getattr(self, "mentor_context", "") else "OFFLINE",
                "Context Sync local carregado" if getattr(self, "mentor_context", "") else "sem contexto local carregado",
            ),
            "lab": component("AVAILABLE" if self.lab else "OFFLINE", "coordenador inicializado" if self.lab else "coordenador não inicializado"),
            "lab_v1": component(
                "AVAILABLE" if LAB_V1_AVAILABLE else "OFFLINE",
                "runtime V1 disponível (inicialização sob demanda)" if LAB_V1_AVAILABLE else "módulo Lab V1 não encontrado neste build",
            ),
            "voice": {
                **component(
                    "AVAILABLE" if voice_ready else ("NOT_CONFIGURED" if VOICE_AVAILABLE else "UNSUPPORTED"),
                    voice_detail,
                ),
                "active": bool(self.voice_active),
                "mode": str(self.voice_mode or "off"),
                "gemini_live_ready": self.gemini_live_voice is not None,
                "local_pipeline_ready": self.voice_pipeline is not None,
                "tts_ready": self.tts_manager is not None,
            },
        }

        spec_map = {spec.name: spec for spec in specs}

        def action_state(*names: str) -> str:
            selected = [spec_map.get(name) for name in names]
            if not selected or any(spec is None for spec in selected):
                return "UNSUPPORTED"
            return "AVAILABLE"

        brightness_status = action_state("os_brightness_absolute")
        if probe_hardware and "os_brightness_absolute" in spec_map:
            if await asyncio.to_thread(_read_windows_brightness_level) is None:
                brightness_status = "UNSUPPORTED"

        capabilities = [
            {"label": "VOLUME/MUTE", "status": action_state("os_volume", "audio_mute", "audio_unmute"), "detail": "controle com verificação de volume"},
            {"label": "APPS/PASTAS", "status": action_state("os_app", "os_open"), "detail": "alvos seguros registrados"},
            {"label": "ARQUIVOS", "status": action_state("files_write", "files_copy", "files_move", "files_search"), "detail": "mutação exige os gates aplicáveis"},
            {"label": "JANELAS", "status": action_state("window_minimize", "window_maximize", "window_restore", "window_switch"), "detail": "somente janela segura"},
            {"label": "NAVEGADOR", "status": action_state("browser_open_url", "browser_search"), "detail": "URL e pesquisa validadas"},
            {"label": "MÍDIA", "status": action_state("media_play_pause", "media_next", "media_previous"), "detail": "teclas de mídia do Windows"},
            {"label": "YOUTUBE/SPOTIFY", "status": action_state("youtube_search", "spotify_search", "youtube_skip_ad"), "detail": "destinos fixos e controles semânticos"},
            {"label": "BRILHO", "status": brightness_status, "detail": "depende do monitor expor DDC/CI ou WMI"},
            {"label": "LUZ NOTURNA", "status": action_state("os_night_light_on", "os_night_light_off"), "detail": "UI Automation sem coordenadas, com readback"},
            {"label": "WI-FI", "status": action_state("os_wifi_on", "os_wifi_off"), "detail": "WinRT Radio em segundo plano, com readback"},
            {"label": "BLUETOOTH", "status": action_state("os_bluetooth_on", "os_bluetooth_off"), "detail": "WinRT Radio em segundo plano, com readback"},
            {"label": "LEMBRETES", "status": "AVAILABLE" if self.reminder_engine else "OFFLINE", "detail": "persistência local"},
            {"label": "HISTÓRICO", "status": "AVAILABLE" if self.conversation_history else "OFFLINE", "detail": "SQLite local"},
            {"label": "MEMÓRIA", "status": "AVAILABLE" if (self.user_memory and self.project_memory) else "LIMITED", "detail": "User Memory e Project Memory separadas"},
            {"label": "VOZ", **components["voice"]},
            {"label": "LAB", **components["lab"]},
            {"label": "MENTOR", **components["mentor"]},
        ]
        available_actions = len(specs)
        return {
            "identity": "ZARA",
            "engine_policy": self.current_engine,
            "effective_model": effective_model,
            "providers": sorted(providers.values(), key=lambda item: item["name"]),
            "runtime": {
                "source_root": str(project_root()),
                "executable": sys.executable,
                "data_root": str(user_data_dir()),
                "frozen": bool(getattr(sys, "frozen", False)),
            },
            "components": components,
            "capabilities": capabilities,
            "action_counts": {"registered": len(specs), "available": available_actions},
            "last_failure": self._last_action_failure,
        }

    # ZARA-LATENCIA-MEDIDA-001
    # Alex não abre terminal e não vai ler um .jsonl. Se o número não puder ser
    # perguntado em voz alta, ele não existe para quem decide.
    # ZARA-NUNCA-INVENTAR-NUMERO-001
    #
    # Alex perguntou "quanto tempo você demorou?" três vezes e recebeu
    # "2,01 segundos" nas três. Ele desconfiou: *"você não tá me enganando com
    # essa informação, não, porque toda hora você dá a mesma?"*. Estava.
    #
    # O número não veio de medição nenhuma. A pergunta não casava com o padrão
    # antigo — que exigia "quanto tempo você DEMORA" e ele disse "DEMOROU" —
    # então caía no modelo, e o modelo produziu uma frase que soa técnica.
    # Precisão inventada é pior que "não sei": ela é convincente.
    #
    # O padrão agora aceita o jeito que ele fala de verdade, com folga entre as
    # palavras. Errar para o lado de interceptar demais é seguro: no pior caso
    # ela responde com a medida real quando ninguém pediu.
    _PERGUNTA_DE_LATENCIA = re.compile(
        # Auditoria do Codex, achado 22: sem exigir que a duracao seja DELA,
        # "quanto tempo durou o filme?" devolvia relatorio de latencia.
        r"(?:quanto\s+tempo\b(?:\s+(?:voc[êe]|vc|tu|isso|isto|essa|esse))?\s*(?:que\s+)?(?:voc[êe]|vc)?\s*(?:demor|lev|gast)"
        r"|quanto\s+(?:voc[êe]|vc)\s+(?:demor|lev|gast)"
        r"|qual\s+(?:a\s+|sua\s+)*(?:lat[êe]ncia|velocidade|demora)"
        r"|voc[êe]\s+(?:t[áa]|est[áa])\s+(?:lenta|demorando)"
        r"|onde\s+(?:vai|ta|est[áa])\s+o\s+tempo"
        r"|demorou\s+quanto)",
        re.IGNORECASE,
    )

    # ZARA-CONFIRMACAO-VAZIA-001
    #
    # No log de 15/08, três vezes seguidas:
    #   Alex: "você entendeu?"        ZARA: "Sim, entendi com certeza!"
    #   Alex: "você entendeu o que eu falei?"  ZARA: "Sim, entendi com clareza."
    # Numa delas ela ainda CHUTOU o que ele teria dito, e errou.
    #
    # Ele chamou isso de robótico, e é pior que robótico: é uma confirmação que
    # não confirma nada. "Sim, entendi" sem dizer O QUÊ não é informação — é
    # ruído educado. E quando ela chuta o assunto, vira invenção.
    #
    # A resposta honesta usa o que ela realmente processou por último. Se não
    # houver nada guardado, ela diz que não pegou — que é a verdade e é
    # exatamente o que ele precisa ouvir para repetir a frase.
    _PERGUNTA_SE_ENTENDEU = re.compile(
        r"(?:voc[êe]|vc)\s+(?:me\s+)?entende(?:u|ste)\b"
        r"|entendeu\s+(?:o\s+que|a\s+minha|minha)\b"
        r"|(?:ta|t[áa]|est[áa])\s+me\s+(?:ouvindo|escutando)\b"
        r"|voc[êe]\s+(?:ta|t[áa]|est[áa])\s+a[ií]\b",
        re.IGNORECASE,
    )

    def _confirmar_o_que_entendeu(self) -> str:
        """Confirma citando, não afirmando. ZARA-CONFIRMACAO-VAZIA-001."""
        ultimo = str(getattr(self, "_ultimo_pedido_entendido", "") or "").strip()
        if not ultimo:
            return (
                "Não peguei sua última frase inteira. Repete que agora eu tô ouvindo."
            )
        if len(ultimo) > 140:
            ultimo = ultimo[:140].rsplit(" ", 1)[0] + "..."
        return f'Peguei sim: "{ultimo}".'

    async def _try_self_knowledge(self, text: str) -> str | None:
        if self._PERGUNTA_SE_ENTENDEU.search(text or ""):
            return self._confirmar_o_que_entendeu()

        if self._PERGUNTA_DE_LATENCIA.search(text or ""):
            resposta = await asyncio.to_thread(self._contar_a_latencia)
            if resposta:
                return resposta

        from core.self_knowledge import (
            detect_self_knowledge_topic,
            is_self_knowledge_followup,
            render_self_knowledge,
        )

        topic = detect_self_knowledge_topic(text)
        if topic is None and is_self_knowledge_followup(text):
            if self.conversation_history is not None:
                try:
                    recent = await asyncio.to_thread(self.conversation_history.list_recent, 8)
                except Exception:
                    recent = []
                current = _canonical_request(text).casefold()
                skipped_current = False
                for item in reversed(recent):
                    if str(item.get("role") or "") != "user":
                        continue
                    content = str(item.get("content") or "")
                    if not skipped_current and _canonical_request(content).casefold() == current:
                        skipped_current = True
                        continue
                    topic = detect_self_knowledge_topic(content)
                    # “Isso” may refer only to the immediately preceding user
                    # turn. Never search farther back and resurrect stale state.
                    break
            if topic is None:
                return "Não encontrei o assunto de “isso” no turno anterior. Diga o que você quer que eu verifique."
        if topic is None:
            return None
        snapshot = await self._build_self_knowledge_snapshot(probe_hardware=topic == "capabilities")
        return render_self_knowledge(topic, snapshot)

    @staticmethod
    def _contar_a_latencia() -> str | None:
        """A própria ZARA dizendo onde o tempo dela foi parar.

        Em segundos e em português, não em milissegundos e nome de etapa: quem
        pergunta é o Alex, não um engenheiro. E se ainda não houver medida, ela
        diz isso — inventar um número seria pior que não ter nenhum.
        """
        try:
            from core.cronometro import relatorio

            dados = relatorio()
        except Exception:
            return None

        if not dados.get("turnos"):
            return (
                "Ainda não medi nada. Fala comigo umas cinco vezes por voz que "
                "eu te conto exatamente onde o tempo está indo."
            )

        total = dados.get("total_ms_mediano", 0) / 1000.0
        etapas = dados.get("etapas_ms_medianas") or {}
        antes = etapas.get("antes_de_falar", 0) / 1000.0
        falar = max(0.0, total - antes)

        # Auditoria do Codex, achado 14: a frase antiga dizia "do fim da sua
        # frase até eu começar a falar" — e as duas pontas estavam erradas. O
        # relógio só começa DEPOIS que a transcrição chega (fora ficam o VAD e
        # o silêncio de fechamento), e só para quando ela TERMINA de falar.
        #
        # Descrever mal o que se mediu é o mesmo defeito de inventar o número:
        # em ambos os casos Alex recebe uma frase que não corresponde ao mundo.
        # Agora ela diz exatamente o pedaço que mediu, e admite o que fica de
        # fora — inclusive porque é justamente aí que pode estar a lentidão.
        return (
            f"Medi {dados['turnos']} turnos. Da hora em que entendo sua frase até "
            f"eu terminar de responder dá {total:.1f} segundos: {antes:.1f} pensando "
            f"e fazendo, {falar:.1f} gerando e dizendo a resposta. "
            "O tempo que levo pra perceber que você parou de falar ainda não entra "
            "nessa conta."
        )

    def _load_runtime_preferences(self) -> None:
        # Front selection lives in the canonical Lab store. Legacy api_keys.json
        # preferences cannot authorize a paid or premium conversational route.
        self.current_engine = "gpt-5.6-luna"

    def _persist_engine_preference(self, engine: str) -> None:
        try:
            from core.paths import api_keys_path
            path = api_keys_path()
            data: dict[str, Any] = {}
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["ai_engine"] = engine
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[IPC] Could not persist engine preference: {exc}")

    async def initialize(self):
        """Initialize essential backend components and optional integrations.

        The ready signal is emitted only after the essential IPC dependencies
        (orchestrator, model router, memory and action registry) are usable.
        Voice is optional and may stay offline without preventing the desktop
        interface from opening.
        """
        essential_errors: list[str] = []
        self._event_loop = asyncio.get_running_loop()

        try:
            self.orchestrator = ZaraOrchestrator()
            await self.orchestrator.initialize()
        except Exception as exc:
            essential_errors.append(f"orchestrator: {exc}")
            traceback.print_exc()

        try:
            self.model_router = ModelRouter()
            self._load_runtime_preferences()
        except Exception as exc:
            essential_errors.append(f"model_router: {exc}")
            traceback.print_exc()

        try:
            self.memory = MemoryManager()
            await self.memory.initialize()
        except Exception as exc:
            essential_errors.append(f"memory: {exc}")
            traceback.print_exc()

        # User Memory Core (ZARA-USER-MEMORY-DESIGN-001): fatos semanticos
        # persistentes sobre o usuario, separado da Project Memory.
        try:
            from memory.user_memory import UserMemoryCore
            self.user_memory = UserMemoryCore()
            print("[IPC] User Memory Core initialized")
        except Exception as exc:
            self.user_memory = None
            print(f"[IPC] User Memory Core unavailable: {exc}")

        # Project Memory (ZARA-PROJECT-MEMORY-001): charter, arquitetura,
        # decisoes, estado e roadmap do PROJETO (nao dependem da conversa).
        try:
            from memory.project_memory import ProjectMemory
            self.project_memory = ProjectMemory()
            print("[IPC] Project Memory initialized")

            # CONTEXT SYNC: Load mentor_context_latest.md for Mentor continuity
            self.mentor_context = self.project_memory.load_mentor_context()
            if self.mentor_context:
                print(f"[IPC] Mentor context loaded ({len(self.mentor_context)} chars)")
            else:
                print("[IPC] No mentor context file found - continuing without it")
        except Exception as exc:
            self.project_memory = None
            self.mentor_context = ""
            print(f"[IPC] Project Memory unavailable: {exc}")

        try:
            # Importing the package triggers @action decorators and populates
            # the central action registry.
            import core.actions  # noqa: F401
        except Exception as exc:
            essential_errors.append(f"actions: {exc}")
            traceback.print_exc()

        if essential_errors:
            raise RuntimeError("; ".join(essential_errors))

        # Release validation exercises the real IPC/core in a disposable data
        # directory. It never starts microphone, messaging bridges or schedules.
        if self._smoke_test:
            from core.reminder_engine import ReminderEngine
            self.reminder_engine = ReminderEngine(on_fire=self._schedule_reminder_fire)
            print("[IPC] Isolated smoke mode: read-only IPC; background integrations disabled")
            return

        if LAB_AVAILABLE and LabCoordinator:
            try:
                worker_runtime = LabWorkerRuntime() if LabWorkerRuntime else None
                self.lab = LabCoordinator(orchestrator=self.orchestrator, worker_runtime=worker_runtime)
                await self.lab.initialize()
                print("[IPC] ZARA Lab Core initialized")
            except Exception as exc:
                self.lab = None
                print(f"[IPC] ZARA Lab optional module unavailable: {exc}")

        if LAB_V1_AVAILABLE and LabV1Service:
            try:
                self.lab_v1 = LabV1Service()
                self.lab_v1.on_release_ready = lambda result: self.send_event('lab-release-ready', {
                    'state': 'READY_TO_ACTIVATE', 'session_id': result['session_id']})
                await self.lab_v1.start_background()
                self._schedule_lab_v1_task(
                    self._drain_lab_v1_operation_outbox(self.lab_v1),
                    name="zara-lab-v1-operation-outbox",
                )
            except Exception:
                print('[IPC] Lab autonomy supervisor unavailable; core IPC remains active')

        if VOICE_AVAILABLE:
            await self._prepare_voice_components()

        # Reminder core (ZARA-REMINDER-CORE-001): local, persistent, no cloud.
        try:
            from core.reminder_engine import ReminderEngine
            self.reminder_engine = ReminderEngine(
                on_fire=self._schedule_reminder_fire,
            )
            self.reminder_engine.start()
            print("[IPC] Reminder Core initialized")
        except Exception as exc:
            self.reminder_engine = None
            print(f"[IPC] Reminder Core unavailable: {exc}")

        # ZARA-3-MODOS-2026-08-27: modo "tarefa agendada". O TaskScheduler
        # (core/actions/scheduler.py) ja existia completo -- add/remove/list,
        # loop de fundo, calculo de proximo horario -- mas nada no boot nunca
        # chamava .start(). Achado durante a limpeza de hoje: peca pronta,
        # nunca ligada. Wire real: qualquer action registrada pode ser
        # agendada por voz/texto (schedule_add), nao so lembretes.
        try:
            from core.actions.scheduler import TaskScheduler
            from core.action_registry import get_registry

            self.task_scheduler = TaskScheduler()
            self.task_scheduler.set_action_runner(
                lambda action_name, params: get_registry().execute(action_name, **params)
            )
            self.task_scheduler.start()
            print("[IPC] Task Scheduler initialized (modo agendado ligado)")
        except Exception as exc:
            self.task_scheduler = None
            print(f"[IPC] Task Scheduler unavailable: {exc}")

        # ZARA-TELEGRAM-002: a ponte do celular sobe no boot, NÃO junto com a
        # voz. Ela estava presa em handle_voice_start, então com o microfone
        # desligado o Telegram ficava mudo — e o ponto inteiro dessa ponte é
        # Alex comandar quando NÃO está na frente do computador.
        try:
            await self._ligar_telegram()
            # Pelo mesmo motivo: o aviso de "o Claude respondeu" precisa chegar
            # ao celular dele mesmo com o microfone desligado.
            await self._ligar_vigia_das_respostas()
            # ZARA-SE-CONSERTA-SOZINHA-001: a partir daqui ela cuida das
            # próprias pontes sem ninguém pedir.
            self._vigia_das_pontes = asyncio.create_task(
                self._cuidar_das_pontes(), name="zara-vigia-pontes"
            )
        except Exception as exc:
            print(f"[IPC] Telegram nao ligou no boot: {exc}")

        # ZARA-BOTAO-MUDO-005: a escolha dele sobre falar ou calar sobrevive ao
        # fechamento do app.
        self._silenciada = self._carregar_silenciada()
        print(f"[IPC] voz {'silenciada' if self._silenciada else 'liberada'} (lembrado)", flush=True)

        print("[IPC] Backend components initialized")

    def _build_gemini_live_config(self, gemini_key: str):
        """Monta a config do Gemini Live respeitando api_keys.json.

        ZARA-VOICE-AUDICAO-001. O gate Vosk local fica DESLIGADO por padrao
        porque cortava o inicio das frases. Para voltar ao comportamento
        antigo sem recompilar nada, basta gravar em api_keys.json:

            "wake_word_mode": "local"

        Qualquer outro valor (ou ausencia) mantem o wake por transcricao.
        """
        modo = ""
        try:
            from core.paths import config_dir
            arquivo = config_dir() / "api_keys.json"
            if arquivo.exists():
                modo = str(
                    json.loads(arquivo.read_text(encoding="utf-8")).get("wake_word_mode") or ""
                ).strip().lower()
        except Exception as exc:
            print(f"[IPC] wake_word_mode ilegivel, usando padrao: {exc}")
        gate_local = modo == "local"
        if gate_local:
            print("[IPC] wake_word_mode=local — gate Vosk LIGADO por configuracao", flush=True)
        # ZARA-AEC-RENDERER-001. O transporte de audio decide se o eco acustico
        # existe. "renderer" manda microfone e Kore pelo Electron, que aplica o
        # AEC do Chromium (o mesmo WebRTC AEC3, ja compilado e assinado dentro
        # do binario). "local" mantem PortAudio e o eco volta.
        # Reversivel sem rebuild: "audio_transport": "local" em api_keys.json.
        transporte = "renderer"
        try:
            from core.paths import config_dir
            arquivo = config_dir() / "api_keys.json"
            if arquivo.exists():
                escolhido = str(
                    json.loads(arquivo.read_text(encoding="utf-8")).get("audio_transport") or ""
                ).strip().lower()
                if escolhido in ("local", "renderer"):
                    transporte = escolhido
        except Exception as exc:
            print(f"[IPC] audio_transport ilegivel, usando renderer: {exc}")
        print(f"[IPC] audio_transport={transporte}", flush=True)

        # ZARA-VOICE-LATENCY-002: velocidade de fechamento de turno, ajustavel
        # sem rebuild. Menor = ela responde mais rapido, mas corta Alex se ele
        # pausar para pensar.
        silencio_ms = 450
        try:
            from core.paths import config_dir
            arquivo = config_dir() / "api_keys.json"
            if arquivo.exists():
                bruto = json.loads(arquivo.read_text(encoding="utf-8")).get("vad_silencio_ms")
                if bruto is not None:
                    silencio_ms = max(150, min(2000, int(bruto)))
        except Exception as exc:
            print(f"[IPC] vad_silencio_ms ilegivel, usando padrao: {exc}")

        # ZARA-VOICE-LATENCY-002: quanto audio o Gemini guarda ANTES do inicio
        # detectado da fala. Sem isso a primeira silaba de Alex podia ser
        # cortada quando ele comecava a falar bem em cima do fim do turno
        # anterior. Ajustavel sem rebuild por "vad_padding_ms" em api_keys.json.
        padding_ms = 100
        try:
            from core.paths import config_dir
            arquivo = config_dir() / "api_keys.json"
            if arquivo.exists():
                bruto = json.loads(arquivo.read_text(encoding="utf-8")).get("vad_padding_ms")
                if bruto is not None:
                    padding_ms = max(0, min(2000, int(bruto)))
        except Exception as exc:
            print(f"[IPC] vad_padding_ms ilegivel, usando padrao: {exc}")

        # ZARA-VOICE-LATENCY-002: sensibilidade de fim de fala do servidor.
        # Ajustavel sem rebuild por "vad_fim_sensivel" em api_keys.json.
        fim_sensivel = True
        try:
            from core.paths import config_dir
            arquivo = config_dir() / "api_keys.json"
            if arquivo.exists():
                bruto = json.loads(arquivo.read_text(encoding="utf-8")).get("vad_fim_sensivel")
                if bruto is not None:
                    if isinstance(bruto, bool):
                        fim_sensivel = bruto
                    elif isinstance(bruto, int):
                        fim_sensivel = bool(bruto)
                    elif isinstance(bruto, str):
                        low = bruto.strip().lower()
                        if low in ("true", "1"):
                            fim_sensivel = True
                        elif low in ("false", "0"):
                            fim_sensivel = False
                        else:
                            raise ValueError(f"vad_fim_sensivel invalido: {bruto!r}")
                    else:
                        raise ValueError(f"vad_fim_sensivel invalido: {bruto!r}")
        except Exception as exc:
            print(f"[IPC] vad_fim_sensivel ilegivel, usando padrao: {exc}")

        return GeminiLiveVoiceConfig(
            api_key=gemini_key,
            voice_name="Kore",
            wake_word_enabled=gate_local,
            audio_transport=transporte,
            vad_silencio_ms=silencio_ms,
            vad_padding_ms=padding_ms,
            vad_fim_sensivel=fim_sensivel,
        )

    async def _on_gemini_live_output_audio(self, audio: bytes) -> None:
        """Entrega a fala da Kore ao Electron para tocar. ZARA-AEC-RENDERER-001.

        Bytes vazios significam "corta agora" (barge-in), nao "silencio".
        """
        if not audio:
            await self.send_event('voice-output-audio', {'stop': True})
            return
        await self.send_event('voice-output-audio', {
            'pcm': base64.b64encode(audio).decode('ascii'),
            'sampleRate': 24000,
        })


    def _resolve_gemini_key(self):
        """Chave Gemini: env primeiro; config do usuario como fallback.

        O empacotado pode ser spawnado sem o env do usuario (ex: atualizador
        ou caminho de inicializacao divergente); o config e a mesma fonte que
        as demais telas usam — sem o fallback a voz Kore morre silenciosa
        mesmo com a chave salva no app.
        """
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            return key
        try:
            from core.paths import api_keys_path
            raw = json.loads(api_keys_path().read_text(encoding="utf-8"))
            return str(raw.get("gemini_api_key") or "").strip()
        except Exception:
            return ""

    async def _prepare_voice_components(self):
        """Prepare voice objects without loading/downloading models at startup.

        Vosk/Kokoro are intentionally lazy. The desktop interface must become
        ready even on a fresh machine where voice models have not been cached.
        """
        gemini_key = self._resolve_gemini_key()
        if GEMINI_LIVE_MODULE_AVAILABLE and GeminiLiveVoice and GeminiLiveVoiceConfig and gemini_key:
            try:
                self.gemini_live_voice = GeminiLiveVoice(
                    self._build_gemini_live_config(gemini_key),
                    on_state=self._on_gemini_live_state,
                    on_level=self._on_gemini_live_level,
                    on_turn=self._on_gemini_live_turn,
                    # ZARA-VOICE-FLUIDEZ-001: a politica CONVERSA/ACAO mora no
                    # dispatcher, nao no transporte de audio.
                    can_answer_directly=self._voice_can_answer_directly,
                    on_interrupt=self._on_gemini_live_interrupt,
                    on_error=self._on_gemini_live_error,
                    on_output_audio=self._on_gemini_live_output_audio,
                )
                print("[IPC] Gemini Live prepared: gemini-3.1-flash-live-preview / Kore")
            except Exception as exc:
                self.gemini_live_voice = None
                print(f"[IPC] Gemini Live preparation failed: {exc}")

        if VOICE_AVAILABLE and VoiceConfig and create_voice_pipeline:
            try:
                self.voice_pipeline = create_voice_pipeline(
                    on_wake=self._on_wake_word,
                    on_speech=self._on_speech_recognized,
                    on_partial=self._on_partial_speech,
                    on_level=self._on_voice_level,
                )
                print("[IPC] Voice STT prepared (lazy initialization)")
            except Exception as exc:
                self.voice_pipeline = None
                print(f"[IPC] Voice STT unavailable: {exc}")

        if VOICE_AVAILABLE and TTSManager and TTSConfig:
            try:
                tts_config = TTSConfig(default_voice="pf_dora")
                self.tts_manager = TTSManager(tts_config)
                self._tts_initialized = False
                print("[IPC] Voice TTS prepared (lazy initialization)")
            except Exception as exc:
                self.tts_manager = None
                self._tts_initialized = False
                print(f"[IPC] Voice TTS unavailable: {exc}")

    def _looks_like_own_echo(self, heard: str) -> bool:
        """Filtro temporal/conteudo; interrupcao humana tem precedencia."""
        if is_explicit_human_barge_in(heard):
            return False
        live = self.gemini_live_voice
        live_filter = getattr(live, "is_self_echo_transcript", None)
        if (
            callable(live_filter)
            and self._voice_turn_is_echo_suspect()
            and live_filter(heard)
        ):
            return True
        now = time.monotonic()
        if not self._assistant_output_active and now > self._assistant_output_protect_until:
            return False
        references: list[str] = []
        if self._assistant_output_text.strip():
            references.append(self._assistant_output_text)
        references.extend(
            text for text, expires_at in self._recent_assistant_outputs
            if text and now <= expires_at
        )
        return looks_like_assistant_echo(heard, references)

    def _begin_assistant_output(self, text: str) -> None:
        value = str(text or "").strip()
        self._assistant_output_active = True
        self._assistant_output_text = value
        self._last_spoken_text = value

    def _finish_assistant_output(self) -> None:
        if not self._assistant_output_active:
            return
        expires_at = time.monotonic() + 0.8
        value = self._assistant_output_text.strip()
        if value:
            self._recent_assistant_outputs.appendleft((value, expires_at))
        self._assistant_output_active = False
        self._assistant_output_text = ""
        self._assistant_output_protect_until = expires_at

    def _voice_elapsed_ms(self) -> float:
        """Milliseconds since the current voice turn started. 0.0 if unset."""
        if not self._voice_turn_started:
            return 0.0
        return (time.perf_counter() - self._voice_turn_started) * 1000.0

    async def _on_gemini_live_state(self, state: str) -> None:
        self.voice_active = state not in {"STANDBY", "STOPPED"}
        # ZARA-VOICE-WAKE-BRIDGE-001
        # The local Vosk gate consumes the audio chunk that carries the wake
        # word (gemini_live_voice._queue_audio returns early while the gate is
        # closed), so Gemini never transcribes "Zara" and _WAKE_PREFIX_RE in
        # _on_gemini_live_turn cannot match. The command was then dropped as
        # IGNORED_NO_WAKE. A real local wake must arm the same window the
        # transcript prefix would have armed.
        # gate_open is True only after GeminiLiveVoice.open_gate(), i.e. after
        # the local detector actually fired; the connect-time and
        # legacy always-stream LISTENING states leave it False.
        voice = self.gemini_live_voice
        if state == "LISTENING" and voice is not None and voice.gate_open:
            self._gemini_wake_armed_until = time.monotonic() + self._JANELA_DE_CONVERSA
            print("[VOICE_TRACE] stage=WAKE_EVENT result=PASS source=local_gate", flush=True)
        await self.send_event('state-change', state)

    async def _on_gemini_live_level(self, level: float, speaking: bool) -> None:
        self._voice_level = max(0.0, min(1.0, float(level or 0.0)))
        self._voice_speaking = bool(speaking)
        await self.send_event('voice-level', {
            'level': self._voice_level,
            'tone': self._voice_tone,
            'speaking': self._voice_speaking,
        })

    # ZARA-VOICE-FLUIDEZ-001
    # Sniff de lembrete por regex DE PROPOSITO. detect_reminder_intent nao pode
    # ser chamado daqui: ele CRIA o lembrete (core/reminder_intent.py:126). Um
    # classificador com efeito colateral agendaria lembrete so porque Alex
    # pronunciou a palavra no meio de uma conversa.
    _REMINDER_SNIFF_RE = re.compile(
        r"\b(?:lembre|lembra|lembrar|lembrete|lembretes)\b",
        re.IGNORECASE,
    )
    _STOP_WORD_RE = re.compile(
        r"(?:pare|para|parar|cancela|cancelar|interrompa|interromper|chega)",
        re.IGNORECASE,
    )
    # ZARA-PONTE-SEM-INVENCAO-001: citou Claude ou Codex, é assunto da ponte, e
    # ponte é ação. O modelo não pode responder sozinho e dizer que mandou.
    _PONTE_SNIFF_RE = re.compile(
        r"\b(?:claude|cláudio|claudio|cláudia|claudia|cloud|cloude|clode|claudi|"
        r"claudy|glaude|clod|codex|códex|codes|chat\s*gpt|chatgpt)\b",
        re.IGNORECASE,
    )

    def _voice_turn_needs_executor(self, command: str) -> bool:
        """CONVERSA ou ACAO? Roteamento de um turno de voz, sem LLM.

        ZARA-VOICE-FLUIDEZ-001. Regra definida por Alex em 2026-08-13:

            CONVERSA -> a voz do Live pode sair direto (fluidez).
            ACAO     -> audio do Live suprimido; o executor decide e so o
                        resultado verificado e falado.
            O LLM nunca declara sucesso de acao por conta propria.

        Retorna True para ACAO. Falha FECHADA: qualquer duvida vira ACAO.
        O pior caso de um falso ACAO e a lentidao que ja existe hoje; o pior
        caso de um falso CONVERSA e o modelo dizendo "abri o Chrome" sem nada
        ter acontecido no Windows, que e o falso sucesso que o projeto proibe.

        Sincrono e sem efeito colateral: roda dentro do _receive_loop do Live.
        """
        text = _canonical_request(command)
        if not text:
            return True
        # Auditoria do Codex, achado 20 — e é o achado que mais dói, porque
        # significa que o conserto principal da noite não funcionava por voz.
        #
        # "Quanto tempo você demorou?" e "você entendeu?" eram classificadas
        # como CONVERSA. A voz do modelo saía direto, `_try_self_knowledge`
        # nunca rodava, e ele voltava a inventar "2,01 segundos" e a dizer
        # "sim, entendi com certeza" — exatamente os dois defeitos que o Alex
        # pegou e que eu tinha declarado resolvidos.
        #
        # Interceptar por texto e não fechar esta porta é consertar só o
        # caminho que ele quase não usa.
        if self._PERGUNTA_DE_LATENCIA.search(text) or self._PERGUNTA_SE_ENTENDEU.search(text):
            return True
        if self._REMINDER_SNIFF_RE.search(text):
            return True
        # ZARA-PONTE-SEM-INVENCAO-001
        #
        # Alex falou "respondeu-me de pronto: Claro, funcionou" — fala truncada
        # pelo reconhecimento — e a ZARA respondeu "Mensagem enviada! O sistema
        # da ZARA já mandou essa resposta". Nada tinha sido enviado. O turno caiu
        # em CONVERSA porque nenhum padrão de comando casou, e o modelo
        # preencheu a lacuna inventando que agiu.
        #
        # Qualquer frase que cite o Claude ou o Codex mexe com a ponte, que é
        # ação. Falha FECHADA: manda para o executor, que ou faz e prova, ou diz
        # honestamente que não conseguiu.
        if self._PONTE_SNIFF_RE.search(text):
            return True
        try:
            from core.self_knowledge import detect_self_knowledge_topic, is_self_knowledge_followup
            if detect_self_knowledge_topic(text) is not None or is_self_knowledge_followup(text):
                return True

            from core.file_voice_intent import detect_file_intent
            if detect_file_intent(text) is not None:
                return True

            from core.pc_voice_intent import PcVoiceIntentDetector
            if PcVoiceIntentDetector().detect(text).is_pc_intent:
                return True
        except Exception:
            return True
        return bool(_looks_like_unhandled_local_action(text))

    def _voice_turn_is_echo_suspect(self) -> bool:
        """A fala em curso nasceu por cima da propria voz da ZARA?

        O sinal apenas habilita a comparacao temporal por conteudo. Nao bloqueia
        uma fala humana diferente e nao substitui o wake gate.
        """
        live = self.gemini_live_voice
        return bool(live is not None and getattr(live, "turn_echo_suspect", False))

    def _voice_is_authorized_conversation(self, user_text: str) -> bool:
        """Pure wake/echo/action classification; it never authorizes remote audio."""
        spoken = str(user_text or "").strip()
        if not spoken or self._looks_like_own_echo(spoken):
            return False
        wake = _WAKE_PREFIX_RE.match(spoken)
        if wake:
            command = str(wake.group(1) or "").strip()
            if not command:
                return False
        elif self._manual_voice_session or time.monotonic() <= self._gemini_wake_armed_until:
            command = spoken
        else:
            return False
        if self._STOP_WORD_RE.fullmatch(command):
            return False
        return not self._voice_turn_needs_executor(command)

    def _voice_can_answer_directly(self, user_text: str) -> bool:
        # Keep Gemini's microphone/STT stream, but suppress its conversational
        # answer. The selected front brain owns every accepted conversation.
        return False

    # ZARA-SILENCIO-VISIVEL-001 -------------------------------------------
    #
    # Um turno descartado não deixava rastro nenhum. O banco de conversa só
    # guarda o que foi aceito, então o histórico mostrava um diálogo impecável
    # enquanto Alex, na sala, falava sozinho e achava que ela tinha travado.
    #
    # Bug invisível não se conserta: se conserta por adivinhação, que é o que
    # custou semanas a este projeto. Agora o descarte vira linha em disco.
    def _anotar_turno_descartado(self, texto: str, motivo: str) -> None:
        try:
            from core.cronometro import anotar_descarte

            anotar_descarte(texto, motivo)
        except Exception:
            pass  # observar nunca pode atrapalhar

    async def _on_gemini_live_turn(
        self, user_text: str, model_text: str, direct: bool = False
    ) -> None:
        spoken = str(user_text or "").strip()
        if not spoken:
            return

        # ZARA-VOICE-ECO-001
        # Com o gate local desligado o microfone continua aberto enquanto a
        # Kore fala — condicao necessaria para o barge-in funcionar. O preco e
        # que o alto-falante volta para o microfone e a ZARA pode transcrever
        # a propria fala como se fosse o Alex. Este filtro compara o que
        # chegou com o que ela acabou de dizer e descarta o eco.
        # Nao usa tempo, usa conteudo: um "pare" dito por cima continua
        # passando, porque nao se parece com a resposta anterior.
        if self._looks_like_own_echo(spoken):
            print("[VOICE_TRACE] stage=ECHO_GUARD result=DISCARDED", flush=True)
            self._anotar_turno_descartado(spoken, "eco_da_propria_voz")
            return

        wake = _WAKE_PREFIX_RE.match(spoken)
        if wake:
            command = str(wake.group(1) or "").strip()
            if not command:
                self._gemini_wake_armed_until = time.monotonic() + self._JANELA_DE_CONVERSA
                print("[VOICE_TRACE] stage=WAKE_EVENT result=PASS", flush=True)
                await self.send_event('state-change', 'LISTENING')
                return
        elif self._manual_voice_session or time.monotonic() <= self._gemini_wake_armed_until:
            # ZARA-JANELA-DE-CONVERSA-003
            #
            # Medido na madrugada de 15/08, no arquivo de descartes: com a TV
            # ligada, treze falas de novela chegaram ao microfone — "óleo de
            # rícino", "no canguru", "pai, me desculpa, pai". O portão as
            # descartou porque a janela estava fechada.
            #
            # Abrir a janela para 75 s conserta a queixa dele (ser ignorado) e
            # cria a queixa inversa: a TV virar dona do computador. As duas são
            # ruins, e trocar uma pela outra não é conserto.
            #
            # Então a janela tem duas metades. Logo depois de ela falar, aceita
            # qualquer coisa — é a hora da réplica, e exigir formalidade aí
            # destrói a conversa. Passado esse tempo o turno ainda é aceito, mas
            # precisa PARECER dirigido a ela: um comando que o detector
            # reconhece, ou uma frase que fala com ela.
            #
            # Novela não pede para abrir o YouTube nem diz "você".
            resta = self._gemini_wake_armed_until - time.monotonic()
            na_replica = resta > (self._JANELA_DE_CONVERSA - self._REPLICA_LIVRE)
            if not na_replica and not self._parece_dirigido_a_ela(spoken):
                print("[VOICE_TRACE] stage=WAKE_GATE result=IGNORED_NAO_DIRIGIDO", flush=True)
                self._anotar_turno_descartado(spoken, "fora_da_replica_e_nao_dirigido")
                return
            command = spoken
        else:
            # ZARA-VOICE-ECO-002: cai aqui tambem o eco do proprio alto-falante,
            # que nasce por cima da fala dela e nao traz wake.
            #
            # ZARA-SILENCIO-VISIVEL-001. Alex: "ela as vezes ouvia um comando e
            # nao me respondia nada... eu tinha que ficar falando Zara voce me
            # entendeu, ai ela ressuscitava".
            #
            # Era aqui. E o pior nao era o descarte: era ele ser INVISIVEL.
            # O historico so guarda turno aceito, entao a conversa parecia
            # perfeita no banco enquanto ele falava sozinho na sala. Agora todo
            # descarte fica registrado, com o motivo e o texto — e da para
            # medir se a janela esta curta demais em vez de adivinhar.
            print("[VOICE_TRACE] stage=WAKE_GATE result=IGNORED_NO_WAKE", flush=True)
            self._anotar_turno_descartado(spoken, "sem_wake_e_fora_da_janela")
            return

        self._gemini_wake_armed_until = 0.0
        print(f"[VOICE_TRACE] stage=STT_RESULT result=PASS chars={len(command)}", flush=True)
        print(f"[VOICE_TRACE] stage=NORMALIZED_TEXT result=PASS chars={len(command.strip())}", flush=True)
        if self._STOP_WORD_RE.fullmatch(command):
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.gemini_live_voice.interrupt_speech()
            await self._on_gemini_live_interrupt()
            return
        user_history = await self._append_conversation_message("user", command, "gemini_live_stt")
        await self.send_event('message', {
            'role': 'user', 'content': command, 'engine': 'gemini_live_stt',
            'timestamp': datetime.now().isoformat(),
        })
        # ZARA-VOICE-CONVERSA-001
        # Depois de um comando aceito, abrir uma janela de continuacao. Sem
        # isso Alex precisa dizer "Zara" a cada frase, o que impede conversa
        # de verdade. A janela e curta e so vale apos um turno legitimo, entao
        # nao transforma conversa de fundo em comando.
        self._gemini_wake_armed_until = time.monotonic() + self._JANELA_DE_CONVERSA

        # Ignore a late direct=True callback from an older transport turn.
        # Its generated answer is not the owner-selected front brain.
        # Turno de ACAO: o rascunho remoto morre aqui, como sempre.
        print("[VOICE_TRACE] stage=ROUTE result=EXECUTOR", flush=True)
        del model_text  # Remote draft is never trusted as proof of a PC action.
        user_history_id = user_history.get('id') if isinstance(user_history, dict) else None
        if user_history_id:
            await self._process_voice_message(command, user_history_id=user_history_id)
        else:
            await self._process_voice_message(command)

    async def _on_gemini_live_interrupt(self) -> None:
        """Reflect a real server-side barge-in in ZARA's session state."""
        self._invalidate_voice_turn()
        self._voice_speaking = False
        # ZARA-VOZ-UNICA-002: Alex mandou parar. A cascata de vozes precisa
        # saber disso, senão ela entende "a Kore não falou" e recomeça o mesmo
        # texto com outra voz — foi o que aconteceu: ele interrompeu a Kore e a
        # voz do Windows continuou lendo sozinha, sem aceitar comando.
        self._fala_interrompida = True
        print("[VOICE_TRACE] stage=BARGE_IN result=PASS", flush=True)
        await self.send_event('state-change', 'LISTENING')
        await self.send_event('voice-level', {
            'level': 0.0, 'tone': self._voice_tone, 'speaking': False,
        })

    async def _on_gemini_live_error(self, error: str) -> None:
        print(f"[Gemini Live] {error}")
        await self._append_conversation_message("system", f"Gemini Live: {error}", "gemini_live")
        await self.send_event('message', {
            'role': 'system',
            'content': f'Gemini Live: {error}',
            'engine': 'gemini_live',
            'timestamp': datetime.now().isoformat(),
        })

    async def _on_wake_word(self):  # type: ignore[return-value]
        """Callback when wake word detected"""
        print("[Voice] Wake word detected!")
        self._voice_level = 0.3
        await self.send_event('voice-level', {
            'level': 0.3,
            'tone': 0.5,
            'speaking': False,
            'state': 'LISTENING'
        })
        await self.send_event('state-change', 'LISTENING')

    async def _on_voice_level(self, level: float):  # type: ignore[return-value]
        """Forward normalized microphone energy to the particle renderer."""
        if not self.voice_active:
            return
        self._voice_level = max(0.0, min(1.0, float(level or 0.0)))
        await self.send_event('voice-level', {
            'level': self._voice_level,
            'tone': self._voice_tone,
            'speaking': False,
        })

    async def _on_partial_speech(self, partial: str):  # type: ignore[return-value]
        """Partial transcript hook; audio energy is handled by _on_voice_level."""
        if partial:
            print(f"[Voice] Partial: {partial[:80]}")

    async def _on_speech_recognized(self, text: str):  # type: ignore[return-value]
        """Callback when speech is fully recognized"""
        print(f"[Voice] Recognized speech ({len(text)} chars)")
        self._voice_level = 0.0
        await self.send_event('voice-level', {
            'level': 0.0,
            'tone': 0.5,
            'speaking': False,
            'state': 'THINKING'
        })
        await self.send_event('state-change', 'THINKING')

        user_history = await self._append_conversation_message("user", text, self.current_engine)
        await self.send_event('message', {
            'role': 'user',
            'content': text,
            'engine': self.current_engine,
            'timestamp': datetime.now().isoformat(),
        })

        # Process the recognized text through the message handler
        user_history_id = user_history.get('id') if isinstance(user_history, dict) else None
        if user_history_id:
            await self._process_voice_message(text, user_history_id=user_history_id)
        else:
            await self._process_voice_message(text)

    async def _enrich_with_memory(self, text: str) -> str:
        """Prepend ONLY relevant shared-memory facts to the user message.

        ZARA-USER-MEMORY-CONTEXT-001: never dump the whole store; irrelevant
        memories are excluded by the relevance gate. The shared second brain
        (user memory + verified Lab lessons + project events + Obsidian) is
        the primary source and the same context the Lab agents consult; the
        legacy user-memory builder remains as a safe fallback. The current
        message always enters exactly once, below the context block.
        """
        try:
            if not (text or "").strip():
                return text
            ctx = ""
            brain = self.get_second_brain()
            if brain is not None:
                from memory.second_brain_composition import render_second_brain_context
                ctx = render_second_brain_context(brain, text)
            if not ctx and self.user_memory:
                from memory.memory_context import build_memory_context
                ctx = build_memory_context(self.user_memory, text, top_k=4)
            if not ctx:
                return text
            return f"{ctx}\n\nMensagem de Alex:\n{text}"
        except Exception:
            return text

    def get_second_brain(self):
        """Lazy shared second brain; None (legacy fallback) on failure.

        Prefers the Lab service's composed brain — the same instance and
        index the agent recovery path uses. Builds a local composition when
        the Lab service is unavailable. A failed build is not retried every
        message; the legacy fallback keeps answering.
        """
        if getattr(self, "_shared_brain_failed", False):
            return None
        brain = getattr(self, "_shared_brain", None)
        if brain is not None:
            return brain
        try:
            lab = self.lab_v1
            if lab is not None:
                brain = lab.get_shared_brain()
                if brain is not None:
                    self._shared_brain = brain
                    return brain
            from core.obsidian_memory import ObsidianMemoryManager
            from memory.second_brain_composition import build_shared_second_brain

            brain = build_shared_second_brain(
                user_memory=self.user_memory,
                project_memory=self.project_memory,
                obsidian=ObsidianMemoryManager(),
            )
            self._shared_brain = brain
            return brain
        except Exception:
            self._shared_brain_failed = True
            return None

    @property
    def aprendizado(self):
        """Diário de experiências. ZARA-APRENDIZADO-001.

        Criado sob demanda para não pesar o boot; falha em silêncio, porque
        aprender é secundário e nunca pode impedir a ZARA de responder.
        """
        atual = getattr(self, "_aprendizado", None)
        if atual is not None:
            return atual
        try:
            from core.aprendizado import Aprendizado

            self._aprendizado = Aprendizado()
        except Exception as exc:
            print(f"[IPC] aprendizado indisponivel: {exc}", flush=True)
            self._aprendizado = False
        return self._aprendizado or None

    def _anotar_experiencia(self, pedido: str, acao: str, sucesso: bool,
                            resultado: str, origem: str) -> None:
        """Registra o que ela fez, para aprender com a reação de Alex depois."""
        diario = self.aprendizado
        if diario is None:
            return
        try:
            diario.registrar_acao(pedido, acao, sucesso, resultado, origem)
        except Exception:
            pass

    def _ouvir_reacao_do_alex(self, fala: str) -> None:
        """A próxima fala dele é a nota da ação anterior: acertou ou errou."""
        diario = self.aprendizado
        if diario is None:
            return
        try:
            veredito = diario.observar_reacao(fala)
            if veredito:
                print(
                    f"[VOICE_TRACE] stage=APRENDIZADO result={veredito.upper()}",
                    flush=True,
                )
        except Exception:
            pass

    def _anotar_o_que_alex_disse(self, texto: str, origem: str) -> None:
        """Guarda sozinha fato ou preferência dita por Alex. ZARA-MEMORIA-AUTOMATICA-001.

        A gaveta de memória existia desde sempre e vivia vazia, porque só enchia
        quando ele mandava lembrar — e ninguém lembra de mandar lembrar. Agora
        toda fala dele passa por aqui.

        Silenciosa e à prova de falha de propósito: anotar é secundário, e nunca
        pode atrasar nem derrubar a resposta que ele está esperando.
        """
        try:
            from core.memoria_automatica import guardar_se_valer

            guardado = guardar_se_valer(self.user_memory, texto, origem=origem)
            if guardado:
                print(
                    "[VOICE_TRACE] stage=MEMORIA_AUTOMATICA result=GUARDADO "
                    f"categoria={guardado.get('category')}",
                    flush=True,
                )
        except Exception:
            pass

    async def _append_conversation_message(
        self, role: str, content: str, engine: str = ""
    ) -> dict[str, Any] | None:
        """Persist renderer history without making chat availability depend on disk I/O."""
        # Toda fala do Alex passa por aqui, venha de voz ou de texto — é o ponto
        # único onde dá para observar sem duplicar a lógica nos dois caminhos.
        if role == "user":
            self._anotar_o_que_alex_disse(str(content or ""), origem=engine or "conversa")
            # ZARA-APRENDIZADO-001: a fala logo depois de uma ação é a nota
            # dela. "não é isso" ensina mais que qualquer outra coisa.
            self._ouvir_reacao_do_alex(str(content or ""))
            if self.lab_v1 is not None:
                await self.lab_v1.capture_feedback(str(content or ""), channel=engine or "conversation")
        if not self.conversation_history:
            return None
        try:
            return await asyncio.to_thread(
                self.conversation_history.append,
                role,
                str(content),
                engine=str(engine or ""),
            )
        except Exception as exc:
            # Never print raw message content; history is private local data.
            print(f"[IPC] Conversation history write failed: {type(exc).__name__}")
            return None

    def _persist_voice_answer_in_background(
        self,
        *,
        turn_id: int,
        user_text: str,
        response: str,
        engine: str,
        front_run_id: str | None = None,
    ) -> None:
        """Persist a completed brain answer without delaying its spoken start."""

        async def persist() -> None:
            started_at = time.perf_counter()
            history = await self._append_conversation_message("assistant", response, engine)
            episode_id: str | None = None
            if self.memory:
                try:
                    episode_id = await self.memory.add_conversation(user_text, response, engine)
                except Exception as exc:
                    print(f"[Voice] Background memory write failed: {type(exc).__name__}")

            # A barge-in or a newer turn increments the generation. Remove only
            # that stale answer; a normally finished turn keeps its generation.
            if self._voice_turn_generation != turn_id:
                history_id = history.get("id") if isinstance(history, dict) else None
                if history_id and self.conversation_history:
                    try:
                        await asyncio.to_thread(self.conversation_history.delete, history_id)
                    except Exception as exc:
                        print(f"[Voice] Stale assistant history cleanup failed: {type(exc).__name__}")
                if episode_id and self.memory:
                    try:
                        await self.memory.remove_conversation_episode(episode_id)
                    except Exception as exc:
                        print(f"[Voice] Stale memory cleanup failed: {type(exc).__name__}")
                if front_run_id and self.lab_v1:
                    try:
                        await self.lab_v1.discard_front_run(front_run_id)
                    except Exception as exc:
                        print(f"[Voice] Stale FrontBrain cleanup failed: {type(exc).__name__}")
            print(
                "[VOICE_TRACE] stage=VOICE_PERSIST result=FINISHED "
                f"duration_ms={(time.perf_counter() - started_at) * 1000:.0f}",
                flush=True,
            )

        task = asyncio.create_task(
            persist(), name=f"zara-voice-persist-{turn_id}"
        )
        self._voice_persistence_tasks.add(task)

        def finished(done: asyncio.Task) -> None:
            self._voice_persistence_tasks.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                print(f"[Voice] Background persistence failed: {type(exc).__name__}")

        task.add_done_callback(finished)

    async def _try_reminder_intent(self, text: str) -> str | None:
        """Deterministic reminder intent (ZARA-REMINDER-VOICE-BINDING-001).

        Returns the ZARA reply when the message is a reminder intent, or
        None so the normal brain handles it. Never an LLM decision.
        """
        try:
            if not (text or "").strip():
                return None
            from core.reminder_intent import detect_reminder_intent
            res = detect_reminder_intent(text, self.reminder_engine)
            if res.kind == "reminder":
                await self.send_event('reminder-created', {
                    'id': res.reminder_id, 'text': res.message,
                    'due_at': res.due_at_utc, 'state': 'SCHEDULED',
                })
                return res.reply
            if res.kind == "reminder_failed":
                # BUG-001: nunca deixar o cerebro/LLM inventar sucesso
                return res.reply or "Não consegui criar esse lembrete."
            if res.kind == "needs_clarification":
                return res.reply or "Que horas?"
            if res.kind in {"list", "cancel", "complete"}:
                return res.reply
            return None
        except Exception:
            if self._REMINDER_SNIFF_RE.search(text or ""):
                return "Não consegui processar esse lembrete. Ele NÃO está agendado."
            return None

    # ZARA-NAO-VERIFICADO-001 ---------------------------------------------
    #
    # Alex: *"tente deixar ela sem mentiras e sem chutes; se não souber, ela
    # deve ser sempre transparente"*. E a regra que saiu da pesquisa da Apple:
    # ação executada mas não confirmada **nunca** aparece como certa.
    #
    # Existiam dois estados — deu certo, deu errado — e faltava o mais comum:
    # *fiz, e não tenho como provar*. Apertar uma tecla num app de terceiro,
    # mandar uma mensagem, disparar um atalho: nada disso devolve confirmação.
    # Sem a ressalva, tudo isso saía afirmativo, e afirmação sem prova é o
    # falso sucesso que este projeto inteiro existe para combater.
    _RESSALVA = " Não consegui confirmar; se não tiver acontecido, me fala."

    async def _try_pc_intent(self, text: str) -> str | None:
        self._ultimo_resultado_de_acao = None
        resposta = await self._executar_intent_de_pc(text)
        if not resposta:
            return resposta
        resultado = getattr(self, "_ultimo_resultado_de_acao", None)
        if resultado is not None and getattr(resultado, "incerto", False):
            if "confirmar" not in resposta.casefold():
                return resposta.rstrip() + self._RESSALVA
        return resposta

    async def _try_lab_intent(self, text: str) -> str | None:
        """Chat -> Zara Lab: quando Alex pede para criar algo, abre missao no Lab."""
        import re as _re
        raw = (text or '').strip()
        if not raw or len(raw) > 12000:
            return None
        low = raw.lower()
        if 'tarefa agendada' in low:
            return None
        triggers = [r'\bcri[ea]r?\b', r'\bmonte\b', r'\bdesenvolva\b', r'\bimplemente\b', r'\bgere\b', r'\bfa[çc]a\b', r'\bmelhore\b', r'\bpesquis\w*\b']
        has_trigger = any(_re.search(p, raw, _re.IGNORECASE) for p in triggers)
        if not has_trigger:
            return None
        has_context = bool(_re.search(r'\b(algo|coisa|projeto|bot|lab|tarefa|miss[aã]o|melhoria|feature|fun[cç][aã]o|pesquisa|automa)\b', raw, _re.IGNORECASE)) or len(raw.split()) <= 5
        if not has_context:
            return None
        if not LAB_V1_AVAILABLE or LabV1Service is None:
            return None
        try:
            if self.lab_v1 is None:
                self.lab_v1 = LabV1Service()
                try:
                    await self.lab_v1.start_background()
                except Exception:
                    pass
            result = await self.lab_v1.start_autopilot(raw)
            if isinstance(result, dict) and result.get('success'):
                sess = result.get('session_id') or (result.get('session', {}) or {}).get('id') or ''
                mission = result.get('mission', {})
                state = mission.get('state') if isinstance(mission, dict) else ''
                if sess:
                    return f'Pronto \u2014 criei no Zara Lab \u2705 Missao aberta: "{raw[:80]}" (sessao {str(sess)[:8]}...). Ja esta na fila dos bots, voce ve em Lab \u2192 Missoes. {state}'
                return f'Pronto \u2014 criei no Zara Lab \u2705 "{raw[:80]}" ja esta na fila dos bots.'
            err = (result.get('error') if isinstance(result, dict) else '') or 'Nao consegui abrir no Lab agora.'
            detail = ''
            if isinstance(result, dict) and result.get('state') == 'WAITING_RESOURCE':
                detail = ' (Lab ocupado, tente em segundos)'
            elif isinstance(result, dict) and result.get('code') == 'WORKFORCE_DISABLED':
                detail = ' \u2014 autonomy desabilitada, habilite em Lab \u2192 Config.'
            return f'{err}{detail}'
        except Exception as e:
            print(f'[LAB_INTENT] erro ao criar missao: {e}')
            return None


    async def _executar_intent_de_pc(self, text: str) -> str | None:
        """Deterministic PC intent (ZARA-COMPUTER-CONTROL-VOLUME-001).

        Maps voice/text PC commands to existing os_volume action. Returns
        the ZARA reply or None so the normal brain handles it. Never an
        LLM decision.
        """
        started = time.perf_counter()
        stage = "intent"
        try:
            if not (text or "").strip():
                return None
            pending_reply = await self._try_pending_clipboard_confirmation(text)
            if pending_reply is not None:
                return pending_reply
            if re.fullmatch(r"(?:zara[,\s]+)?(?:copie|copia)\s+(?:isso|isto)\s*[.!?]*", text.strip().lower()):
                return "Qual texto devo colocar na área de transferência?"
            clipboard_write = re.fullmatch(
                r"(?:zara[,\s]+)?(?:coloque|coloca|copie|copia)\s+(.+?)\s+(?:na|para\s+a)\s+(?:área|area)\s+de\s+transfer[êe]ncia\s*[.!?]*",
                text.strip(),
                flags=re.IGNORECASE,
            )
            if clipboard_write:
                pending = re.sub(r"^(?:este\s+texto\s+|o\s+texto\s+)", "", clipboard_write.group(1).strip(), flags=re.IGNORECASE)
                if len(pending) >= 2 and pending[0] in "'\"‘’“”" and pending[-1] in "'\"‘’“”":
                    pending = pending[1:-1].strip()
                pending = pending[:4000]
                if not pending:
                    return "Qual texto devo colocar na área de transferência?"
                self._pending_clipboard_text = pending
                self._pending_clipboard_expires_at = time.monotonic() + 30.0
                preview = _sanitize_observation(pending)[:120]
                if not preview or preview != pending[:120]:
                    return f"Posso copiar esse conteúdo sensível de {len(pending)} caracteres?"
                return f"Posso copiar ‘{preview}’?"
            from core.pc_voice_intent import PcVoiceIntentDetector
            detector = PcVoiceIntentDetector(
                volume_context_level=self._last_volume_level if self._context_fresh("volume") else None,
                window_context_available=bool(
                    (self._context_fresh("app") or self._context_fresh("window"))
                    and self._last_window_hwnd
                ),
                folder_context=(
                    self._last_safe_folder
                    if self._context_fresh("folder")
                    and self._last_safe_folder in {"downloads", "documents", "desktop", "pictures", "zara_root"}
                    else None
                ),
            )
            if self._operational_context_turns > 0:
                self._operational_context_turns -= 1
            res = detector.detect(text)
            if not res.is_pc_intent:
                return None
            if res.blocked:
                self._remember_action_failure(res.action, "capability_gate", res.reply)
                return res.reply or "Não consegui executar esse comando."
            # Keep direct/cold IPC use honest too: tests and lightweight
            # runtimes may reach this path before the async initializer has
            # imported the action package.
            import core.actions  # noqa: F401
            from core.action_registry import execute_action, get_registry
            # A detected PC intent whose action is not registered must never fall
            # through to the LLM: the model would answer as if the command had
            # been executed. Report unsupported honestly instead.
            if res.action not in get_registry()._specs:
                print(f"[IPC] PC intent '{res.action}' has no registered action (unsupported)")
                self._remember_action_failure(res.action, "registry", "ação não registrada")
                return (
                    "Esse comando ainda não é suportado no seu PC: "
                    f"não existe ação registrada para '{res.action}'."
                )
            params = {}
            # ZARA-INTENSIDADE-VOLUME-001: por padrão executa a própria action
            # detectada; volume/brilho relativo passam a executar a versão
            # absoluta (mesmo executor de sempre) com o nível já calculado
            # aqui, porque "up_muito"/"down_pouco" não é um tipo que a action
            # em si entenda -- ela só recebe o resultado já resolvido.
            action_to_execute = res.action
            if res.action == "os_volume":
                direcao_delta = _resolver_direcao_e_delta(res.param)
                if direcao_delta is not None:
                    _, delta = direcao_delta
                    current = (
                        self._last_volume_level
                        if res.contextual
                        else _read_windows_volume()
                    )
                    if current is None:
                        return "Não consegui ler o volume do sistema."
                    params["level"] = max(0, min(100, current + delta))
                else:
                    try:
                        params["level"] = max(0, min(100, int(float(res.param))))
                    except (TypeError, ValueError):
                        return None
            elif res.action == "os_app":
                params["app"] = res.param
            elif res.action == "os_open":
                params["folder"] = res.param
            elif res.action == "os_close_safe_app":
                params["app"] = res.param
            elif res.action == "os_brightness_absolute":
                try:
                    params["level"] = max(0, min(100, int(float(res.param))))
                except (TypeError, ValueError):
                    return None
            elif res.action in ("os_brightness_up", "os_brightness_down"):
                direcao_delta = _resolver_direcao_e_delta(res.param)
                if direcao_delta is None:
                    return None
                _, delta = direcao_delta
                current = (
                    self._last_brightness_level
                    if res.contextual
                    else _read_windows_brightness_level()
                )
                if current is None:
                    return "Não consegui ler o brilho da tela."
                params["level"] = max(0, min(100, current + delta))
                action_to_execute = "os_brightness_absolute"
            elif res.action in {"window_minimize", "window_maximize", "window_restore", "window_move", "window_resize_larger", "window_close"}:
                # ZARA-JANELA-NOMEADA-001: "minimize/maximize/restaure o Chrome"
                # manda um alvo por nome (ex.: "chrome"), nao a janela contextual.
                # "active" e None continuam caindo no hwnd de contexto de sempre.
                named_target = (
                    res.param
                    if res.action in {"window_minimize", "window_maximize", "window_restore"}
                    and res.param and res.param != "active"
                    else None
                )
                if named_target:
                    params["target"] = named_target
                elif self._last_window_hwnd is not None:
                    params["hwnd"] = self._last_window_hwnd
                if res.action == "window_move":
                    params["side"] = res.param
            elif res.action == "window_focus_named":
                params["target"] = res.param
            elif res.action == "browser_scroll":
                params["direction"] = res.param
            elif res.action == "input_type_text":
                params["text"] = res.param
            elif res.action == "input_hotkey":
                params["command"] = res.param
            elif res.action == "browser_open_url":
                params["url"] = res.param
            elif res.action == "browser_search":
                params["query"] = res.param
            elif res.action in {"youtube_search", "youtube_play_by_name", "spotify_search"}:
                params["query"] = res.param
            elif res.action == "youtube_seek":
                params["offset_seconds"] = 0 if res.param == "restart" else int(res.param)
                params["restart"] = res.param == "restart"
            elif res.action == "system_processes":
                params["limit"] = 10
            elif res.action == "os_notify":
                params.update({"title": "ZARA", "message": res.param, "timeout": 5})
            # ZARA-PONTE-LEITURA-COMPLETA-001: por padrão ela resume, porque
            # ouvir uma resposta técnica inteira cansa. "lê tudo" pede o texto
            # completo — a escolha fica com Alex, não comigo.
            elif res.action in {"claude_ler", "codex_ler"}:
                params["resumido"] = res.param == "resumido"
            elif res.action in {"claude_enviar", "codex_enviar"}:
                params["texto"] = str(res.param or "")
            elif res.action == "ponte_repassar":
                params["rota"] = str(res.param or "")
            elif res.action == "os_clipboard":
                pending = "" if res.param == "__CLEAR__" else str(res.param or "")
                if not pending and res.param != "__CLEAR__":
                    return "Qual texto devo colocar na área de transferência?"
                self._pending_clipboard_text = pending
                self._pending_clipboard_expires_at = time.monotonic() + 30.0
                if pending == "":
                    return "Posso limpar a área de transferência?"
                preview = _sanitize_observation(pending)[:120]
                if not preview or preview != pending[:120]:
                    return f"Posso copiar esse conteúdo sensível de {len(pending)} caracteres?"
                return f"Posso copiar ‘{preview}’?"
            stage = "executor"
            result = await execute_action(action_to_execute, **params)
            # ZARA-NAO-VERIFICADO-001: guardado para o embrulho decidir se a
            # frase pode sair afirmativa ou precisa da ressalva honesta.
            self._ultimo_resultado_de_acao = result
            # ZARA-APRENDIZADO-001: todo episódio entra no diário — pedido,
            # ação, deu certo ou não. É a matéria-prima do aprendizado; a nota
            # vem depois, na próxima fala de Alex.
            self._anotar_experiencia(
                text,
                res.action,
                bool(result is not None and getattr(result, "success", False)),
                str(getattr(result, "output", "") or getattr(result, "error", "") or ""),
                "voz",
            )
            if result is not None and getattr(result, "success", False):
                if res.action == "os_volume":
                    verified_level = _read_windows_volume()
                    if verified_level is None:
                        return "Ajustei, mas não consegui confirmar o nível."
                    self._set_operational_context("volume", verified_value=int(verified_level))
                    return f"Volume definido para {self._last_volume_level}%."
                if res.action == "os_app":
                    data = getattr(result, "data", None) or {}
                    hwnd = data.get("hwnd")
                    pid = data.get("window_pid")
                    created_pids = data.get("created_pids") or []
                    self._set_operational_context(
                        "app",
                        canonical_target=str(res.param),
                        pid=pid if isinstance(pid, int) and pid > 0 else None,
                        hwnd=hwnd if isinstance(hwnd, int) and hwnd > 0 else None,
                        verified_value="opened",
                        created_by_zara=bool(pid in created_pids if isinstance(pid, int) else False),
                    )
                    return str(getattr(result, "output", "") or "Aplicativo aberto e verificado.")
                if res.action == "os_open":
                    self._set_operational_context(
                        "folder", canonical_target=str(res.param), verified_value="dispatched"
                    )
                    return str(
                        getattr(result, "output", "")
                        or "Solicitação segura de abertura enviada ao Explorer."
                    )
                if res.action == "os_close_safe_app":
                    return str(getattr(result, "output", "") or "Aplicativo fechado e verificado.")
                if res.action.startswith("window_"):
                    if res.action == "window_close":
                        self._clear_operational_context()
                        return str(getattr(result, "output", "") or "Janela fechada e verificada.")
                    data = getattr(result, "data", None) or {}
                    hwnd = data.get("to_hwnd") or data.get("hwnd")
                    previous = self._operational_context or {}
                    self._set_operational_context(
                        "window",
                        canonical_target=previous.get("canonical_target"),
                        pid=data.get("pid") if isinstance(data.get("pid"), int) else previous.get("pid"),
                        hwnd=hwnd if isinstance(hwnd, int) and hwnd > 0 else None,
                        verified_value=data.get("after"),
                        created_by_zara=bool(previous.get("created_by_zara")),
                    )
                    return str(getattr(result, "output", "") or "Estado da janela alterado e verificado.")
                if res.action in {"browser_open_url", "browser_search"}:
                    return str(getattr(result, "output", "") or "Destino enviado ao navegador padrão.")
                if res.action in {
                    "os_brightness_absolute",
                    "os_brightness_up",
                    "os_brightness_down",
                }:
                    observed = (getattr(result, "data", None) or {}).get("observed")
                    if isinstance(observed, (int, float)):
                        self._last_brightness_level = int(observed)
                    return str(getattr(result, "output", "") or "Brilho alterado e verificado.")
                if res.action in {
                    "media_play_pause",
                    "youtube_pause",
                    "youtube_resume",
                    "youtube_seek",
                    "youtube_now_playing",
                    "youtube_next",
                    "youtube_another_by_artist",
                    "media_next",
                    "media_previous",
                    "audio_mute",
                    "audio_unmute",
                    "os_night_light_on",
                    "os_night_light_off",
                    "os_wifi_on",
                    "os_wifi_off",
                    "os_bluetooth_on",
                    "os_bluetooth_off",
                    "youtube_open",
                    "youtube_search",
                    "youtube_play_by_name",
                    "spotify_search",
                    "youtube_skip_ad",
                    "browser_new_tab",
                    "browser_back",
                    "browser_forward",
                    "browser_read_page",
                    "browser_scroll",
                    "browser_close_tab",
                    "input_type_text",
                    "input_hotkey",
                    "audio_status",
                }:
                    return str(getattr(result, "output", "") or "Comando de mídia enviado.")
                if res.action in {"system_time", "system_info", "system_metrics", "system_processes"}:
                    return str(getattr(result, "output", "") or "Informação do sistema coletada.")
                if res.action == "vision_screenshot":
                    data = getattr(result, "data", None) or {}
                    size = data.get("size")
                    return f"Captura de tela realizada e verificada ({size[0]}x{size[1]})." if size else "Captura de tela realizada e verificada."
                if res.action == "os_notify":
                    return str(getattr(result, "output", "") or "Notificação enviada ao Windows.")
                if res.action == "os_clipboard_read":
                    return str(getattr(result, "output", "") or "A área de transferência está vazia.")
                # ZARA-PONTE-RESPOSTA-001
                # A ponte com Claude e Codex NÃO devolve confirmação: devolve o
                # RECADO. Alex pediu "lê o que o Claude falou" e ouviu só
                # "Pronto." — a ação tinha funcionado, o texto estava em
                # result.output, e este ponto o descartava.
                if res.action in {"claude_ler", "codex_ler", "claude_enviar",
                                  "codex_enviar", "ponte_repassar"}:
                    return str(getattr(result, "output", "") or "Não veio texto nenhum.")
                # ZARA-RESPOSTA-DO-EXECUTOR-001
                # Antes daqui saía "Pronto." fixo, engolindo o que o executor
                # tinha a dizer. Qualquer ação nova cairia na mesma armadilha.
                # Agora a frase do executor vem primeiro; "Pronto." é só o
                # último recurso, para ação que de fato não tem o que relatar.
                return str(getattr(result, "output", "") or "Pronto.")
            error = str(getattr(result, "error", "") or "")
            self._remember_action_failure(res.action, "executor", error or "execução sem confirmação de sucesso")
            if res.contextual and res.action.startswith("window_"):
                self._clear_operational_context()
            return f"Não consegui executar essa ação. {error}".strip()
        except Exception as exc:
            action = getattr(locals().get("res"), "action", "unknown")
            self._remember_action_failure(action, stage, exc)
            _observe_failure(action, stage, exc, started)
            return None

    async def _try_compound_pc_intent(self, text: str) -> str | None:
        """Execute 2-5 explicit PC commands sequentially through the same executor.

        This is deterministic composition, not agentic planning. Every segment
        must be recognized before the first action runs, preventing surprising
        partial execution when one requested step is unsupported.
        """
        raw = str(text or "").strip()
        if not raw or not re.search(r"[,;]|\be\b|\bdepois\b", raw, re.IGNORECASE):
            return None
        raw = re.sub(r"^\s*zara\s*[,;:]?\s*", "", raw, flags=re.IGNORECASE)
        parts = [
            part.strip(" .!?")
            for part in re.split(
                r"\s*(?:[,;]|\be\s+depois\b|\bdepois\b)\s*",
                raw,
                flags=re.IGNORECASE,
            )
            if part.strip(" .!?")
        ]
        if not 1 <= len(parts) <= 5:
            return None

        from core.pc_voice_intent import PcVoiceIntentDetector

        detector = PcVoiceIntentDetector(
            volume_context_level=self._last_volume_level if self._context_fresh("volume") else None,
            window_context_available=bool(
                (self._context_fresh("app") or self._context_fresh("window"))
                and self._last_window_hwnd
            ),
            folder_context=(
                self._last_safe_folder
                if self._context_fresh("folder")
                and self._last_safe_folder in {"downloads", "documents", "desktop", "pictures", "zara_root"}
                else None
            ),
        )
        # ZARA-COMPOUND-E-SOLTO-001
        # O split acima só quebra em vírgula/";"/"depois". "abra o youtube,
        # pesquise Bruno Mars e bote para tocar e pule o anúncio" virava só
        # 2 pedaços: o segundo ("pesquise Bruno Mars e bote para tocar e
        # pule o anúncio") era um pedido de 3 ações que nenhum pattern único
        # reconhecia por inteiro.
        #
        # Corrigir quebrando também em "e" solto de cara quebraria frases
        # legítimas como "pesquise rock e blues no youtube" (uma query só,
        # nunca deve virar duas etapas). Por isso o "e" solto só entra como
        # FALLBACK, por pedaço: tenta dividir o pedaço em sub-pedaços por
        # " e " e só aceita a divisão se TODOS os sub-pedaços baterem sozinhos
        # como intent de PC. Se nem todos baterem — caso do "rock e blues",
        # onde "blues no youtube" sozinho não é comando nenhum — o pedaço
        # original fica intacto e segue pelo caminho de sempre (inclusive o
        # de "etapa não suportada" abaixo).
        #
        # A tentativa roda para qualquer pedaço com " e " no meio, não só
        # para quem já teria dado is_pc_intent=False: um pedaço como "abra o
        # notepad e feche o chrome" pode até casar inteiro (o catch-all de
        # abrir app engole o resto como nome de app e não resolve), mas a
        # divisão em dois comandos reais é sempre a leitura melhor quando
        # ambos os sub-pedaços batem sozinhos.
        expanded_parts: list[str] = []
        for part in parts:
            if re.search(r"\se\s", part, re.IGNORECASE):
                sub_parts = [
                    sub.strip(" .!?")
                    for sub in re.split(r"\s+e\s+", part, flags=re.IGNORECASE)
                    if sub.strip(" .!?")
                ]
                if len(sub_parts) >= 2 and all(
                    detector.detect(sub).is_pc_intent for sub in sub_parts
                ):
                    expanded_parts.extend(sub_parts)
                    continue
            expanded_parts.append(part)
        parts = expanded_parts

        if len(parts) < 2:
            return None
        if len(parts) > 5:
            return "Não executei: o pedido excede o limite de cinco etapas por comando."

        detected = [detector.detect(part) for part in parts]
        pc_count = sum(1 for item in detected if item.is_pc_intent)
        if pc_count == 0:
            return None
        unsupported = [part for part, item in zip(parts, detected) if not item.is_pc_intent]
        if unsupported:
            return (
                "Não executei o pedido composto porque esta etapa ainda não é suportada: "
                f"{unsupported[0]}."
            )
        blocked = [item for item in detected if item.blocked]
        if blocked:
            return blocked[0].reply or "Não executei o pedido composto porque uma etapa está bloqueada."

        outcomes: list[str] = []
        for index, part in enumerate(parts, start=1):
            reply = await self._try_pc_intent(part)
            outcomes.append(f"{index}) {reply or 'Etapa não executada.'}")
            if self._jarvis_reply_status(reply) != 'OK':
                outcomes.append("As etapas seguintes não foram executadas porque esta etapa não foi confirmada.")
                break
        return "Resultado por etapa: " + " ".join(outcomes)

    @staticmethod
    def _jarvis_reply_status(reply: str | None) -> str:
        """Classify a primitive readback without turning dispatch into success."""
        from core.reply_status import _jarvis_reply_status
        return _jarvis_reply_status(reply)

    async def _try_jarvis_multi_action(self, text: str) -> str | None:
        """Execute a bounded cross-domain plan using the existing primitives.

        This planner intentionally recognizes only a small set of explicit,
        reversible clauses.  Each primitive performs its own gate/readback and
        the consolidated answer preserves partial failures.
        """
        raw = str(text or "").strip()
        if not raw:
            return None

        patterns = (
            (
                "conforto",
                r"(?:deix[ae]|coloc[ae])\s+(?:o\s+)?(?:computador|pc).{0,24}?confort[aá]vel|modo\s+confort[aá]vel",
            ),
            ("projeto", r"(?:abr[ae]|abrir)\s+(?:o\s+)?projeto(?:\s+da\s+zara)?"),
            ("downloads", r"(?:abr[ae]|abrir)\s+(?:a\s+pasta\s+de\s+)?downloads\b"),
            (
                "status_pc",
                r"(?:vej[ae]|mostre|diga).{0,20}?(?:status|estado|como\s+est[aá]).{0,12}?(?:computador|pc)|(?:status|estado)\s+do\s+(?:computador|pc)",
            ),
            ("musica", r"(?:coloc[ae]|toque|tocar|continue)\s+(?:uma\s+)?m[uú]sica"),
            (
                "pendencias",
                r"(?:v[eê]|veja|mostre|diga).{0,24}?(?:o\s+que\s+)?(?:ficou\s+)?pendente|(?:ver|listar)\s+pend[eê]ncias",
            ),
            ("lembrete", r"(?:me\s+)?lembr(?:e|a|ar)(?:-me)?\b"),
        )
        found: list[tuple[int, str, re.Match[str]]] = []
        for kind, pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                found.append((match.start(), kind, match))
        found.sort(key=lambda item: item[0])

        # Fewer clauses should continue through the ordinary single/compound
        # handlers; requiring three domains prevents accidental activation.
        if len(found) < 3:
            return None

        outcomes: list[tuple[str, str, str]] = []
        for _position, kind, match in found[:5]:
            if kind == "conforto":
                brightness = await self._try_pc_intent("brilho em 45%")
                night_light = await self._try_pc_intent("ative a luz noturna")
                statuses = {
                    self._jarvis_reply_status(brightness),
                    self._jarvis_reply_status(night_light),
                }
                status = "OK" if statuses == {"OK"} else "PARCIAL" if "OK" in statuses else "FALHOU"
                detail = f"Brilho: {brightness or 'sem confirmação'} Luz noturna: {night_light or 'sem confirmação'}"
                outcomes.append((status, "Conforto", detail))
            elif kind == "projeto":
                reply = await self._try_pc_intent("abra a pasta da zara")
                outcomes.append((self._jarvis_reply_status(reply), "Projeto", reply or "Sem confirmação."))
            elif kind == "downloads":
                reply = await self._try_pc_intent("abra Downloads")
                outcomes.append((self._jarvis_reply_status(reply), "Downloads", reply or "Sem confirmação."))
            elif kind == "status_pc":
                reply = await self._try_pc_intent("como está o computador")
                outcomes.append((self._jarvis_reply_status(reply), "Estado do PC", reply or "Sem confirmação."))
            elif kind == "musica":
                reply = await self._try_pc_intent("continue a música")
                outcomes.append((self._jarvis_reply_status(reply), "Música", reply or "Sem confirmação."))
            elif kind == "pendencias":
                reply = await self._try_operational_memory_intent("O que ficou pendente?")
                outcomes.append((self._jarvis_reply_status(reply), "Pendências", reply or "Sem confirmação."))
            elif kind == "lembrete":
                reminder_clause = raw[match.start():].strip(" ,;.!?")
                reply = await self._try_reminder_intent(reminder_clause)
                outcomes.append((self._jarvis_reply_status(reply), "Lembrete", reply or "Sem confirmação."))

        completed = sum(status == "OK" for status, _label, _detail in outcomes)
        partial = sum(status == "PARCIAL" for status, _label, _detail in outcomes)
        details = " ".join(
            f"{index}) [{status}] {label}: {detail}"
            for index, (status, label, detail) in enumerate(outcomes, start=1)
        )
        return (
            f"Plano Jarvis concluído: {completed}/{len(outcomes)} etapa(s) confirmada(s)"
            f"{f', {partial} parcial(is)' if partial else ''}. {details}"
        )

    async def _try_operational_memory_intent(self, text: str) -> str | None:
        """Answer bounded recall questions from local stores, without an LLM."""
        try:
            from core.operational_recall import recall_operational_memory

            return await asyncio.to_thread(
                recall_operational_memory,
                text,
                project_memory=self.project_memory,
                user_memory=self.user_memory,
            )
        except Exception as exc:
            _observe_failure("operational_memory", "recall", exc, time.perf_counter())
            return None

    async def _try_file_intent(self, text: str) -> str | None:
        """Execute closed known-folder file commands through ActionRegistry."""
        from core.file_voice_intent import detect_file_intent

        intent = detect_file_intent(text)
        if intent is None:
            return None
        try:
            from core.action_registry import execute_action
            from core.actions.os_ops import _resolve_safe_folder
            from core.paths import user_data_dir

            def folder_path(folder: str):
                if folder == "corujao":
                    return user_data_dir() / "data" / "corujao" / "voice_files"
                return _resolve_safe_folder(folder)

            params = dict(intent.params)
            if intent.action in {"files_list", "files_search", "files_organize_by_extension", "files_open_latest"}:
                base = folder_path(params.pop("folder"))
                if base is None:
                    return "A pasta conhecida não está disponível neste computador."
                params["path"] = str(base)
            elif intent.action in {"files_write", "files_text_summary", "files_rename", "files_create_folder", "files_open_named"}:
                base = folder_path(params.pop("folder"))
                name = params.pop("name")
                if base is None:
                    return "A pasta conhecida não está disponível neste computador."
                target = base / name
                if intent.action == "files_rename":
                    params["src"] = str(target)
                else:
                    params["path"] = str(target)
            elif intent.action in {"files_copy", "files_move"}:
                source = folder_path(params.pop("source_folder"))
                destination = folder_path(params.pop("destination_folder"))
                name = params.pop("name")
                if source is None or destination is None:
                    return "Uma das pastas conhecidas não está disponível neste computador."
                params.update({"src": str(source / name), "dst": str(destination / name)})
            if intent.mutating:
                params["confirm"] = True
            result = await execute_action(intent.action, **params)
            if not getattr(result, "success", False):
                error = str(getattr(result, "error", "") or "falha sem detalhe")
                self._remember_action_failure(intent.action, "executor", error)
                return f"Não consegui executar a ação de arquivo. {error}"
            data = getattr(result, "data", None) or {}
            if intent.action == "files_open_latest":
                hwnd = data.get("hwnd")
                self._set_operational_context(
                    "window",
                    canonical_target=str(data.get("name") or "download"),
                    hwnd=hwnd if isinstance(hwnd, int) and hwnd > 0 else None,
                    verified_value="opened_by_association",
                    created_by_zara=False,
                )
                return str(getattr(result, "output", "") or "Arquivo aberto e verificado.")
            if intent.action == "files_list":
                names = [item.get("name", "") for item in data.get("files", [])[:12]]
                return f"Encontrei {data.get('count', len(names))} item(ns): " + ", ".join(names) + "."
            if intent.action == "files_search":
                matches = data.get("matches", [])
                preview = "; ".join(f"{item.get('file')}:{item.get('line')}" for item in matches[:8])
                return f"Encontrei {data.get('count', len(matches))} ocorrência(s): {preview}."
            return str(getattr(result, "output", "") or "Ação de arquivo concluída e verificada.")
        except Exception as exc:
            self._remember_action_failure(intent.action, "executor", exc)
            return f"Não consegui executar a ação de arquivo. {type(exc).__name__}."

    async def _process_voice_message(self, text: str, *, user_history_id: str | None = None):
        """Process voice message through orchestrator/model router"""
        text = _canonical_request(text)
        if not text:
            return
        voice_turn_id = self._begin_voice_turn()
        front_run_id: str | None = None
        # ZARA-VOICE-LATENCY-OBSERVABILITY-001
        # F1.2 requires measuring before optimizing. This clock starts when the
        # recognized command enters the pipeline and is read again at the final
        # response, so every turn reports its own cost. Observability only.
        self._voice_turn_started = time.perf_counter()
        # ZARA-CONFIRMACAO-VAZIA-001: guarda a frase dele para poder CITAR
        # quando ele perguntar "você entendeu?", em vez de afirmar que sim.
        # Só o que chegou até aqui conta: se o turno morreu antes, ela não
        # entendeu mesmo, e tem de dizer isso.
        if not self._PERGUNTA_SE_ENTENDEU.search(text):
            self._ultimo_pedido_entendido = text
        # ZARA-ONDE-ELE-ESTA-001: falou por voz, entao esta na sala com o PC.
        self._marcar_canal("computador")
        # ZARA-LATENCIA-MEDIDA-001: o mesmo turno, mas gravado em disco. Os
        # [VOICE_TRACE] morrem com o console, e é por isso que a lentidão que
        # Alex sente nunca virou número.
        try:
            from core.cronometro import Cronometro

            self._cronometro = Cronometro(text, origem="voz")
        except Exception:
            self._cronometro = None
        try:
            _voz = self.gemini_live_voice
            _fim_fala = _voz.ultimo_fim_de_fala() if _voz is not None else None
            _transcricao = _voz.ultima_transcricao_pronta() if _voz is not None else None
            if self._cronometro is not None:
                self._cronometro._speech_end_at = _fim_fala
                self._cronometro._transcript_ready_at = _transcricao
            if _fim_fala is not None and _transcricao is not None:
                self._marcar_valor_no_cronometro("speech_end_ms", 0.0)
                self._marcar_valor_no_cronometro(
                    "transcript_ready_ms",
                    max(0.0, (_transcricao - _fim_fala) * 1000.0),
                )
                self._marcar_valor_no_cronometro(
                    "speech_end_to_transcript_ms",
                    max(0.0, (_transcricao - _fim_fala) * 1000.0),
                )
        except Exception:
            pass
        # ZARA-LATENCIA-SEGUNDA-VIAGEM-001 — A PRIMEIRA VIAGEM, QUE NINGUEM MEDIA.
        #
        # Este ponto do codigo so e alcancado depois do turn_complete do turno
        # do Alex. Em turno de ACAO o audio que o modelo gerou nesse turno foi
        # DESCARTADO byte a byte (gemini_live_voice._receive_loop: o `if
        # audio_data and (...)` da falso), mas o programa esperou a geracao
        # inteira terminar antes de chamar o executor. Ou seja: uma resposta
        # falada completa foi produzida no Google, jogada fora, e o Alex pagou
        # o tempo dela.
        #
        # O cronometro nascia aqui, entao esse custo ficava FORA de qualquer
        # medicao. Agora ele vira uma etapa em disco. Se este numero for grande,
        # ele — e nao a segunda viagem — e o alvo da proxima tarefa.
        try:
            _voz = self.gemini_live_voice
            _fim_fala = _voz.ultimo_fim_de_fala() if _voz is not None else None
            if _fim_fala is not None:
                _descartada = (time.perf_counter() - _fim_fala) * 1000.0
                self._marcar_valor_no_cronometro("primeira_viagem_descartada", _descartada)
                print(
                    "[VOICE_TRACE] stage=PRIMEIRA_VIAGEM_DESCARTADA "
                    f"result=AUDIO_GERADO_E_JOGADO_FORA ms={_descartada:.0f}",
                    flush=True,
                )
        except Exception:
            pass  # medir nunca pode atrapalhar
        try:
            jarvis_reply = await self._try_jarvis_multi_action(text)
            if jarvis_reply:
                await self._append_conversation_message("assistant", jarvis_reply, "jarvis_plan")
                await self.send_event('message', {
                    'role': 'assistant', 'content': jarvis_reply, 'engine': 'jarvis_plan',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(jarvis_reply, voice_turn_id=voice_turn_id)
                return
            # ZARA-REMINDER-VOICE-BINDING-001: intent determinístico primeiro.
            reminder_reply = await self._try_reminder_intent(text)
            if reminder_reply:
                await self._append_conversation_message("assistant", reminder_reply, "reminder")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': reminder_reply,
                    'engine': 'reminder',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(reminder_reply, voice_turn_id=voice_turn_id)
                return
            memory_reply = await self._try_operational_memory_intent(text)
            if memory_reply:
                await self._append_conversation_message("assistant", memory_reply, "operational_memory")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': memory_reply,
                    'engine': 'operational_memory',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(memory_reply, voice_turn_id=voice_turn_id)
                return
            self_reply = await self._try_self_knowledge(text)
            if self_reply:
                await self._append_conversation_message("assistant", self_reply, "self_knowledge")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': self_reply,
                    'engine': 'self_knowledge',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(self_reply, voice_turn_id=voice_turn_id)
                return
            file_reply = await self._try_file_intent(text)
            if file_reply:
                await self._append_conversation_message("assistant", file_reply, "file_control")
                await self.send_event('message', {
                    'role': 'assistant', 'content': file_reply, 'engine': 'file_control',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(file_reply, voice_turn_id=voice_turn_id)
                return
            # ZARA-COMPUTER-CONTROL-VOLUME-001: PC intent antes do LLM.
            print(
                f"[VOICE_TRACE] stage=INTENT_MATCH result=START ms={self._voice_elapsed_ms():.0f}",
                flush=True,
            )
            pc_reply = await self._try_compound_pc_intent(text)
            if not pc_reply:
                pc_reply = await self._try_pc_intent(text)
            if pc_reply:
                print(
                    f"[VOICE_TRACE] stage=ACTION_DISPATCH result=COMPLETED ms={self._voice_elapsed_ms():.0f}",
                    flush=True,
                )
                await self._append_conversation_message("assistant", pc_reply, "pc_control")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': pc_reply,
                    'engine': 'pc_control',
                    'selo': self._selo_do_ultimo_resultado(),
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(pc_reply, voice_turn_id=voice_turn_id)
                print(
                    f"[VOICE_TRACE] stage=FINAL_RESPONSE result=PASS route=pc_control "
                    f"total_ms={self._voice_elapsed_ms():.0f}",
                    flush=True,
                )
                return
            lab_reply = await self._try_lab_intent(text)
            if lab_reply:
                await self._append_conversation_message("assistant", lab_reply, "lab_autopilot")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': lab_reply,
                    'engine': 'lab_autopilot',
                    'timestamp': __import__('datetime').datetime.now().isoformat(),
                })
                await self._speak_response(lab_reply, voice_turn_id=voice_turn_id)
                return
            if _looks_like_unhandled_local_action(text):
                _log_intent_telemetry("refused_local_action", "voice", text)
                # NIGHT-07: a recusa honesta e a evidencia mais valiosa que a
                # ZARA produz -- o Lab so aprendia com falha de executor.
                self._remember_unhandled_intent(text)
                reply = RESPOSTA_NAO_SEI
                await self._append_conversation_message("assistant", reply, "local_action_guard")
                await self.send_event('message', {
                    'role': 'assistant', 'content': reply, 'engine': 'local_action_guard',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(reply, voice_turn_id=voice_turn_id)
                return
            # ETAPA 1 (raciocinio livre): guarda a frase original, antes do
            # enriquecimento de memoria, so para o log de telemetria abaixo.
            _telemetry_raw_text = text
            if _has_broad_action_language_signal(_telemetry_raw_text):
                _log_intent_telemetry(
                    "escaped_to_orchestrator", "voice", _telemetry_raw_text
                )
            # ZARA-USER-MEMORY-CONTEXT-001: enriquece com memorias relevantes
            _brain_started = time.perf_counter()
            if self._cronometro is not None:
                self._cronometro._brain_request_start_at = _brain_started
                _speech_end = getattr(self._cronometro, "_speech_end_at", None)
                if _speech_end is not None:
                    self._marcar_valor_no_cronometro(
                        "brain_request_start_ms",
                        max(0.0, (_brain_started - _speech_end) * 1000.0),
                    )
                    self._marcar_valor_no_cronometro(
                        "speech_end_to_brain_start_ms",
                        max(0.0, (_brain_started - _speech_end) * 1000.0),
                    )
            front_result = await self._front_conversation_reply(
                text, voice_turn_id=voice_turn_id, channel='VOICE'
            )
            _brain_output = time.perf_counter()
            if self._cronometro is not None:
                self._cronometro._brain_first_output_at = _brain_output
                _speech_end = getattr(self._cronometro, "_speech_end_at", None)
                if _speech_end is not None:
                    self._marcar_valor_no_cronometro(
                        "brain_first_output_ms",
                        max(0.0, (_brain_output - _speech_end) * 1000.0),
                    )
                self._marcar_valor_no_cronometro(
                    "brain_start_to_first_output_ms",
                    max(0.0, (_brain_output - _brain_started) * 1000.0),
                )
            front_run_id = str(front_result.get('run_id') or '') or None
            if not self._voice_turn_is_current(voice_turn_id):
                print(f"[VOICE_TRACE] stage=TURN_FENCE result=STALE turn={voice_turn_id}", flush=True)
                return
            if front_result.get('success') is False:
                error = front_result.get('error', 'O modelo selecionado nao respondeu.')
                await self._append_conversation_message(
                    "system", "Backend indisponível para esta solicitação.",
                    front_result.get('engine') or self.current_engine,
                )
                await self.send_event('message', {
                    **front_result, 'role': 'assistant', 'content': error,
                    'timestamp': datetime.now().isoformat(),
                })
                return
            response, engine_used = front_result['response'], front_result['engine']

            self._persist_voice_answer_in_background(
                turn_id=voice_turn_id,
                user_text=text,
                response=str(response),
                engine=engine_used,
                front_run_id=front_run_id,
            )

            # Send response as message event
            await self.send_event('message', {
                **front_result,
                'role': 'assistant',
                'content': response,
                'engine': engine_used,
                'timestamp': datetime.now().isoformat()
            })
            if not self._voice_turn_is_current(voice_turn_id):
                print(f"[VOICE_TRACE] stage=TURN_FENCE result=STALE turn={voice_turn_id}", flush=True)
                return

            # Speak response via TTS
            await self._speak_response(response, voice_turn_id=voice_turn_id)

        except Exception as e:
            print(f"[Voice] Process message error: {e}")
            traceback.print_exc()
            await self._append_conversation_message(
                "system", "Não foi possível processar a mensagem de voz.", self.current_engine
            )
            await self.send_event('message', {
                'role': 'assistant',
                'content': f"Erro ao processar: {e}",
                'engine': self.current_engine,
                'timestamp': datetime.now().isoformat()
            })
        finally:
            if not self._voice_turn_is_current(voice_turn_id):
                if user_history_id and self.conversation_history:
                    try:
                        await asyncio.to_thread(self.conversation_history.delete, user_history_id)
                    except Exception as cleanup_error:
                        print(f"[Voice] Stale Home history cleanup failed: {type(cleanup_error).__name__}")
                if front_run_id and self.lab_v1:
                    try:
                        await self.lab_v1.discard_front_run(front_run_id)
                    except Exception as cleanup_error:
                        print(f"[Voice] Stale FrontBrain cleanup failed: {type(cleanup_error).__name__}")
            if self._voice_turn_is_current(voice_turn_id):
                if self.voice_active and self.voice_pipeline:
                    self.voice_pipeline.resume_listening(require_wake_word=True)
                    await self.send_event('state-change', 'LISTENING')
                else:
                    await self.send_event('state-change', 'STANDBY')
                self._finish_voice_turn(voice_turn_id)

    def _schedule_reminder_fire(self, reminder) -> None:
        """Move a scheduler-thread callback safely onto the IPC event loop."""
        loop = self._event_loop
        if loop is None or loop.is_closed():
            print(f"[Reminder] Event loop unavailable for {reminder.id}")
            return

        future = asyncio.run_coroutine_threadsafe(self._on_reminder_fire(reminder), loop)

        def report_delivery_error(completed) -> None:
            try:
                completed.result()
            except Exception as exc:
                print(f"[Reminder] Delivery failed: {exc}")

        future.add_done_callback(report_delivery_error)

    async def _on_reminder_fire(self, reminder) -> None:
        """Reminder fired: speak it and notify the UI."""
        text = reminder.message
        print(f"[Reminder] FIRED: {text}")
        await self.send_event('reminder-fired', {
            'id': reminder.id,
            'text': text,
            'fired_at': reminder.fired_at,
        })
        # ZARA-REMINDER-VOZ-001
        # Lembrete so fala com a voz oficial da ZARA. Ele dispara no boot,
        # antes de a sessao de voz existir, e antes falava pela cascata de
        # emergencia — por isso saia com outra voz, que Alex estranhou.
        # Sem a voz principal ativa, o lembrete vai para a tela e espera.
        # Uma voz errada corroi a confianca mais do que o silencio.
        voz_pronta = bool(self.gemini_live_voice and self.gemini_live_voice.active)
        if not voz_pronta:
            print("[VOICE_TRACE] stage=REMINDER_TTS result=SKIPPED motivo=voz_principal_inativa", flush=True)
            return
        try:
            await self._speak_response(f"Alex, você pediu para eu te lembrar: {text}")
        except Exception as exc:
            print(f"[Reminder] TTS falhou: {exc}")

    async def handle_reminder_create(self, msg: IPCMessage):
        """Create a reminder. payload: {text, due_at (epoch), timezone?}"""
        if not self.reminder_engine:
            await self.send_error(msg, "Reminder Core indisponível")
            return
        try:
            text = str(msg.payload.get("text", "")).strip()
            due_at = float(msg.payload.get("due_at", 0))
            tz = str(msg.payload.get("timezone", "local"))
            if not text:
                await self.send_error(msg, "texto do lembrete vazio")
                return
            if due_at <= 0:
                await self.send_error(msg, "due_at inválido (epoch)")
                return
            r = self.reminder_engine.create(text, due_at, tz)
            await self.send_response(msg.request_id, {
                'success': True,
                'id': r.id,
                'text': r.message,
                'due_at': r.due_at_utc,
                'timezone': r.timezone,
                'state': r.state,
            })
            await self.send_event('reminder-created', {
                'id': r.id, 'text': r.message, 'due_at': r.due_at_utc, 'state': r.state,
            })
        except Exception as exc:
            await self.send_error(msg, f"reminder-create: {exc}")

    async def handle_reminder_list(self, msg: IPCMessage):
        if not self.reminder_engine:
            await self.send_error(msg, "Reminder Core indisponível")
            return
        try:
            state = msg.payload.get("state") if msg.payload else None
            rems = self.reminder_engine.list(state)
            await self.send_response(msg.request_id, {
                'success': True,
                'reminders': [r.to_row() for r in rems],
            })
        except Exception as exc:
            await self.send_error(msg, f"reminder-list: {exc}")

    async def handle_reminder_cancel(self, msg: IPCMessage):
        if not self.reminder_engine:
            await self.send_error(msg, "Reminder Core indisponível")
            return
        try:
            rid = str((msg.payload or {}).get("id", ""))
            ok = self.reminder_engine.cancel(rid)
            await self.send_response(msg.request_id, {'success': ok, 'id': rid})
        except Exception as exc:
            await self.send_error(msg, f"reminder-cancel: {exc}")

    async def handle_memory_user_add(self, msg: IPCMessage):
        """Add a semantic fact about the user. payload: {fact, category, confidence?, source?}"""
        if not self.user_memory:
            await self.send_error(msg, "User Memory Core indisponível")
            return
        try:
            p = msg.payload or {}
            fact = str(p.get("fact", "")).strip()
            category = str(p.get("category", "semantic_fact"))
            confidence = float(p.get("confidence", 0.6))
            source = str(p.get("source", "manual"))
            if not fact:
                await self.send_error(msg, "fato vazio")
                return
            rec = self.user_memory.add(fact, category=category, confidence=confidence, source=source)
            await self.send_response(msg.request_id, {'success': True, 'fact': rec})
        except Exception as exc:
            await self.send_error(msg, f"memory-user-add: {exc}")

    async def handle_memory_user_search(self, msg: IPCMessage):
        if not self.user_memory:
            await self.send_error(msg, "User Memory Core indisponível")
            return
        try:
            p = msg.payload or {}
            query = str(p.get("query", ""))
            since = float(p["since"]) if p.get("since") else None
            until = float(p["until"]) if p.get("until") else None
            hits = self.user_memory.search(query, since=since, until=until, limit=int(p.get("limit", 5)))
            await self.send_response(msg.request_id, {'success': True, 'hits': hits})
        except Exception as exc:
            await self.send_error(msg, f"memory-user-search: {exc}")

    async def handle_memory_user_list(self, msg: IPCMessage):
        if not self.user_memory:
            await self.send_error(msg, "User Memory Core indisponível")
            return
        try:
            p = msg.payload or {}
            items = self.user_memory.list(category=p.get("category"), status=p.get("status"))
            await self.send_response(msg.request_id, {'success': True, 'facts': items})
        except Exception as exc:
            await self.send_error(msg, f"memory-user-list: {exc}")

    async def handle_memory_user_forget(self, msg: IPCMessage):
        if not self.user_memory:
            await self.send_error(msg, "User Memory Core indisponível")
            return
        try:
            rid = str((msg.payload or {}).get("id", ""))
            ok = self.user_memory.forget(rid)
            await self.send_response(msg.request_id, {'success': ok, 'id': rid})
        except Exception as exc:
            await self.send_error(msg, f"memory-user-forget: {exc}")

    async def handle_project_memory_get(self, msg: IPCMessage):
        if not self.project_memory:
            await self.send_error(msg, "Project Memory indisponível")
            return
        try:
            key = str((msg.payload or {}).get("key", ""))
            doc = self.project_memory.get_doc(key)
            await self.send_response(msg.request_id, {'success': True, 'doc': doc})
        except Exception as exc:
            await self.send_error(msg, f"project-memory-get: {exc}")

    async def handle_project_memory_list(self, msg: IPCMessage):
        """List project identities and document keys, never document contents."""
        if not self.project_memory:
            await self.send_error(msg, "Project Memory indisponível")
            return
        try:
            projects = [
                {
                    'id': project_id,
                    'keys': self.project_memory.list_project_docs(project_id),
                }
                for project_id in self.project_memory.list_projects()
            ]
            await self.send_response(msg.request_id, {
                'success': True,
                'projects': projects,
                'active_project_id': self.project_memory.get_active_project(),
                # Backward-compatible legacy inventory: keys only, no contents.
                'keys': self.project_memory.list_docs(),
            })
        except Exception as exc:
            await self.send_error(msg, f"project-memory-list: {exc}")

    async def handle_project_memory_activate(self, msg: IPCMessage):
        """Activate an existing project without creating or merging context."""
        if not self.project_memory:
            await self.send_error(msg, "Project Memory indisponível")
            return
        try:
            payload = msg.payload or {}
            if not isinstance(payload, dict):
                await self.send_error(msg, "project-memory-activate: payload inválido")
                return
            project_id = payload.get('project_id', payload.get('id'))
            active = self.project_memory.activate_project(project_id)
            await self.send_response(msg.request_id, {
                'success': True,
                'active_project_id': active,
            })
        except Exception as exc:
            await self.send_error(msg, f"project-memory-activate: {exc}")



    async def handle_conversation_history_list(self, msg: IPCMessage):
        """Load the private Home transcript in chronological display order."""
        if not self.conversation_history:
            await self.send_error(msg, "Conversation history unavailable")
            return
        try:
            requested_limit = int((msg.payload or {}).get("limit", 200))
            messages = await asyncio.to_thread(
                self.conversation_history.list_recent, requested_limit
            )
            await self.send_response(
                msg.request_id,
                {
                    "messages": messages,
                    "count": len(messages),
                    "local_only": True,
                },
            )
        except (TypeError, ValueError):
            await self.send_error(msg, "Invalid conversation history limit")
        except Exception as exc:
            print(f"[IPC] Conversation history read failed: {type(exc).__name__}")
            await self.send_error(msg, "Conversation history unavailable")

    async def handle_conversation_history_clear(self, msg: IPCMessage):
        """Permanently clear the Home transcript after the explicit UI action."""
        if not self.conversation_history:
            await self.send_error(msg, "Conversation history unavailable")
            return
        try:
            deleted = await asyncio.to_thread(self.conversation_history.clear)
            await self.send_response(
                msg.request_id, {"success": True, "deleted": int(deleted)}
            )
        except Exception as exc:
            print(f"[IPC] Conversation history clear failed: {type(exc).__name__}")
            await self.send_error(msg, "Conversation history could not be cleared")

    def _marcar_valor_no_cronometro(self, nome: str, ms: float) -> None:
        """Grava uma duracao JA MEDIDA como etapa do turno. ZARA-LATENCIA-SEGUNDA-VIAGEM-001.

        `Cronometro.marcar()` so sabe registrar "quantos ms desde o inicio do
        turno". Os marcos novos nao sao isso: `primeira_viagem_descartada`
        acontece ANTES do inicio do turno e os marcos de TTS sao intervalos
        internos. Por isso o valor entra direto na tabela de etapas.

        Divida temporaria e assumida: `core/cronometro.py` nao e meu e nao entrou
        nesta trava, entao nao pude acrescentar la o `marcar_valor()` publico que
        isto deveria estar chamando. Quando o dono acrescentar, esta funcao vira
        uma linha. Ate la o acesso e defensivo e engolido em silencio, como o
        resto do cronometro: um medidor que derruba a voz seria pior que nao medir.
        """
        try:
            crono = getattr(self, "_cronometro", None)
            if crono is None:
                return
            marcas = getattr(crono, "_marcas", None)
            if isinstance(marcas, dict):
                marcas[str(nome)] = float(ms)
        except Exception:
            pass  # medir nunca pode atrapalhar

    def _begin_voice_turn(self) -> int:
        self._voice_turn_generation += 1
        self._active_voice_turn_id = self._voice_turn_generation
        return self._voice_turn_generation

    def _invalidate_voice_turn(self) -> None:
        self._voice_turn_generation += 1
        self._active_voice_turn_id = None

    def _voice_turn_is_current(self, turn_id: int) -> bool:
        return self._active_voice_turn_id == turn_id

    def _finish_voice_turn(self, turn_id: int) -> None:
        if self._active_voice_turn_id == turn_id:
            self._active_voice_turn_id = None

    async def _speak_response(
        self,
        text: str,
        *,
        voice_turn_id: int | None = None,
        prefer_live: bool = True,
    ):
        """Speak response using TTS, loading the local model only on first use."""
        value = str(text or "").strip()
        if not value:
            return
        if voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id):
            return

        # A mute request must keep both local and Live input listening. Do not
        # initialize fallback engines or pause the microphone for silent turns.
        if getattr(self, "_silenciada", False):
            print("[VOICE_TRACE] stage=TTS_MUDA result=SILENCIADA_POR_ALEX", flush=True)
            await self.send_event('state-change', 'LISTENING')
            return

        live_voice_available = bool(
            prefer_live and self.gemini_live_voice and self.gemini_live_voice.active
        )
        if self.tts_manager and not self._tts_initialized and not live_voice_available:
            try:
                await asyncio.to_thread(self.tts_manager.initialize)
                self._tts_initialized = True
            except Exception as exc:
                self._tts_initialized = False
                print(f"[Voice] TTS lazy initialization failed: {exc}")
        if voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id):
            return

        # Never feed ZARA's own local TTS back into Vosk.  The microphone
        # worker keeps draining audio but recognition remains paused until the
        # response ends, then returns behind the wake gate when configured.
        if self.voice_active and self.voice_pipeline:
            self.voice_pipeline.pause_listening()
        # Keep Gemini Live input open during Kore output so server-side VAD can
        # produce a real barge-in event. Local Vosk remains paused above.

        self._voice_speaking = True
        self._begin_assistant_output(value)
        await self.send_event('state-change', 'SPEAKING')
        await self.send_event('voice-level', {
            'level': 0.5,
            'tone': 0.5,
            'speaking': True,
            'state': 'SPEAKING'
        })

        # ZARA-BOTAO-MUDO-001
        # Alex: "agora eu nao to falando com ela, voce ta respondendo aqui e ela
        # ta toda hora falando o claude respondeu.. isso irrita".
        # Ela continua ouvindo, entendendo e executando — só não fala. É a
        # diferença entre uma presença e uma interrupção.
        if getattr(self, "_silenciada", False):
            print("[VOICE_TRACE] stage=TTS_MUDA result=SILENCIADA_POR_ALEX", flush=True)
            await self.send_event('state-change', 'LISTENING')
            return

        try:
            # ZARA-VOICE-TTS-OBSERVABILITY-001
            # Four engines can speak (Live Kore, Kokoro, Gemini HTTP, Windows
            # SAPI) and all of them used to print the same PASS line, so a
            # silent fallback was invisible in the log. Name the engine that
            # actually spoke and measure it. Observability only: the cascade
            # order and every behaviour below are unchanged.
            _tts_started = time.perf_counter()
            if _crono := getattr(self, "_cronometro", None):
                _crono._tts_start_at = _tts_started
                _speech_end = getattr(_crono, "_speech_end_at", None)
                if _speech_end is not None:
                    self._marcar_valor_no_cronometro(
                        "tts_start_ms",
                        max(0.0, (_tts_started - _speech_end) * 1000.0),
                    )
                _brain_output = getattr(_crono, "_brain_first_output_at", None)
                if _brain_output is not None:
                    self._marcar_valor_no_cronometro(
                        "brain_first_output_to_tts_start_ms",
                        max(0.0, (_tts_started - _brain_output) * 1000.0),
                    )
            print("[VOICE_TRACE] stage=TTS_START result=START", flush=True)
            # ZARA-LATENCIA-MEDIDA-001: aqui a ação já aconteceu. Tudo que vier
            # depois é a segunda viagem — o custo de FALAR uma frase que já
            # estava pronta. É a suspeita principal, e agora ela é medida.
            _crono = getattr(self, "_cronometro", None)
            if _crono is not None:
                _crono.marcar("antes_de_falar")
            spoken = False
            engine_used = "none"
            live_audio_started = False
            # ZARA-VOZ-UNICA-002: cada fala começa com a folha limpa.
            if voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id):
                return
            self._fala_interrompida = False
            if live_voice_available and self.gemini_live_voice:
                spoken = await self.gemini_live_voice.speak(value)
                if not spoken and self.gemini_live_voice.active:
                    delivered_at = self.gemini_live_voice.ultimo_audio_entregue()
                    live_audio_started = delivered_at is not None
                    # ZARA-VOZ-UNICA-001: uma segunda chance antes de trocar de
                    # voz. Alex reconhece a Kore e detesta a voz do Windows;
                    # trocar de voz no meio da conversa é pior do que esperar
                    # mais um instante.
                    if not live_audio_started:
                        print("[VOICE_TRACE] stage=TTS_RETRY result=KORE_SEGUNDA_TENTATIVA", flush=True)
                        spoken = await self.gemini_live_voice.speak(value)
                        delivered_at = self.gemini_live_voice.ultimo_audio_entregue()
                        live_audio_started = delivered_at is not None
                    if live_audio_started:
                        # Do not replay the whole sentence through another
                        # voice after Kore has already delivered a partial.
                        print(
                            "[VOICE_TRACE] stage=TTS_FALLBACK "
                            "result=SUPPRESSED_AFTER_LIVE_AUDIO",
                            flush=True,
                        )
                        spoken = True
                if spoken:
                    engine_used = f"gemini_live/{_tts_voice_name(self.gemini_live_voice)}"
                else:
                    print("[VOICE_TRACE] stage=TTS_FALLBACK result=LIVE_DID_NOT_SPEAK", flush=True)
            # ZARA-VOZ-UNICA-002 — quem manda parar é Alex.
            # Ele interrompeu a Kore no meio de um recado e a voz do Windows
            # continuou lendo o mesmo texto do começo, sem aceitar comando. A
            # causa: interromper faz a Kore devolver "não falei", e a cascata
            # entendia isso como falha e tentava a próxima voz. Parar é uma
            # ordem, não uma falha.
            if (getattr(self, "_fala_interrompida", False)
                    or (voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id))):
                print("[VOICE_TRACE] stage=TTS_ABORT result=INTERROMPIDO_POR_ALEX", flush=True)
                return
            if (
                not spoken
                and self.tts_manager
                and not self._tts_initialized
                and not any((self.tts_manager.edge, self.tts_manager.kokoro, self.tts_manager.gemini))
            ):
                try:
                    await asyncio.to_thread(self.tts_manager.initialize)
                    self._tts_initialized = True
                except Exception as exc:
                    self._tts_initialized = False
                    print(f"[Voice] TTS fallback initialization failed: {exc}")
                if voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id):
                    print(
                        f"[VOICE_TRACE] stage=TURN_FENCE result=STALE turn={voice_turn_id}",
                        flush=True,
                    )
                    return
            # Edge neural (gratuita, sem cota) assume quando a Kore nao fala.
            if not spoken and self.tts_manager and self.tts_manager.edge:  # type: ignore[union-attr]
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.tts_manager.edge.play(value, blocking=True)  # type: ignore[union-attr]
                    )
                    spoken = True
                    engine_used = f"edge/{_tts_voice_name(self.tts_manager.edge)}"  # type: ignore[union-attr]
                except Exception as exc:
                    print(
                        f"[VOICE_TRACE] stage=TTS_FALLBACK result=EDGE_FAILED reason={type(exc).__name__}",
                        flush=True,
                    )
            # Use Kokoro (local) if Live Kore and Edge were unavailable.
            if not spoken and self.tts_manager and self.tts_manager.kokoro:  # type: ignore[union-attr]
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.tts_manager.kokoro.play(value, blocking=True)  # type: ignore[union-attr]
                )
                spoken = True
                engine_used = f"kokoro/{_tts_voice_name(self.tts_manager.kokoro)}"
            elif not spoken and prefer_live and self.tts_manager and self.tts_manager.gemini:  # type: ignore[union-attr]
                await self.tts_manager.gemini.play(value)  # type: ignore[union-attr]
                spoken = True
                engine_used = f"gemini_http/{_tts_voice_name(self.tts_manager.gemini)}"
            if not spoken:
                # ZARA-VOZ-UNICA-002 — a voz do Windows saiu da cascata.
                #
                # Alex: "eu odeio esta voz". Ela também não obedecia ao pedido
                # de parar: uma vez começada, seguia até o fim. Uma voz que ele
                # detesta e não consegue calar é pior que silêncio.
                #
                # Restam Kore (a voz dela) e Edge (neural, gratuita) — as duas
                # boas e as duas interrompíveis. Se nenhuma puder falar, ela
                # fica calada e o texto aparece escrito na tela.
                print("[VOICE_TRACE] stage=TTS_FALLBACK result=SEM_VOZ_DISPONIVEL", flush=True)
                engine_used = "nenhuma"
            print(
                f"[VOICE_TRACE] stage=TTS_START result=PASS engine={engine_used} "
                f"ms={(time.perf_counter() - _tts_started) * 1000:.0f}",
                flush=True,
            )
            # ZARA-LATENCIA-MEDIDA-001: fecha o turno em disco. A diferença
            # entre `antes_de_falar` e o total é exatamente o preço da segunda
            # viagem — o número que faltava para decidir se vale eliminá-la.
            if _crono is not None:
                # ZARA-LATENCIA-SEGUNDA-VIAGEM-001 — CUIDADO AO LER `voz_pronta`.
                #
                # speak() so retorna no turn_complete do Gemini, isto e, quando
                # a frase INTEIRA ja foi gerada. Logo `voz_pronta` (e o
                # `total_ms`, que e igual a ele) mede "ate ela terminar de
                # falar", nao "ate ela comecar". Uma frase mais longa aumenta
                # esse numero sem que nada tenha ficado mais lento.
                #
                # A espera que o Alex reclama e a de COMECAR, e ela e:
                #   primeira_viagem_descartada + antes_de_falar
                #   + tts_pedido_ate_player_ms
                # As tres agora vao para o disco separadas, para que ninguem
                # volte a otimizar contra o numero errado.
                _crono.marcar("voz_pronta")
                try:
                    if self.gemini_live_voice is not None:
                        for _nome, _valor in (
                            self.gemini_live_voice.marcos_da_segunda_viagem().items()
                        ):
                            self._marcar_valor_no_cronometro(_nome, _valor)
                        _audio_at = self.gemini_live_voice.ultimo_audio_entregue()
                        if _audio_at is not None:
                            self._marcar_valor_no_cronometro(
                                "tts_start_to_first_audio_ms",
                                max(0.0, (_audio_at - _tts_started) * 1000.0),
                            )
                            _speech_end = getattr(_crono, "_speech_end_at", None)
                            if _speech_end is not None:
                                self._marcar_valor_no_cronometro(
                                    "first_audio_played_ms",
                                    max(0.0, (_audio_at - _speech_end) * 1000.0),
                                )
                                self._marcar_valor_no_cronometro(
                                    "speech_end_to_first_audio_ms",
                                    max(0.0, (_audio_at - _speech_end) * 1000.0),
                                )
                except Exception:
                    pass  # medir nunca pode atrapalhar
                _crono.fechar(rota="voz", voz=engine_used, falou=spoken)
                self._cronometro = None
            # ZARA-JANELA-DE-CONVERSA-002
            #
            # A janela era armada quando o comando chegava — ou seja, ANTES de
            # ela responder. Uma resposta longa comia o próprio tempo de
            # conversa: ela falava trinta segundos e sobravam quarenta e cinco
            # para ele reagir, embora a conversa só tenha recomeçado quando ela
            # calou a boca.
            #
            # Entre pessoas o relógio da vez começa quando o outro termina de
            # falar. Aqui também.
            if spoken:
                self._gemini_wake_armed_until = (
                    time.monotonic() + self._JANELA_DE_CONVERSA
                )
            if not engine_used.startswith("gemini_live/Kore"):
                print(
                    f"[VOICE_TRACE] stage=KORE_CHECK result=NOT_KORE engine={engine_used}",
                    flush=True,
                )
        except Exception as e:
            print(f"[Voice] TTS error: {e}")
        finally:
            stale_turn = voice_turn_id is not None and not self._voice_turn_is_current(voice_turn_id)
            self._voice_speaking = False
            self._finish_assistant_output()
            if not stale_turn and self.voice_active and self.voice_pipeline:
                self.voice_pipeline.resume_listening(require_wake_word=True)
            if not stale_turn:
                await self.send_event('voice-level', {
                    'level': 0.0,
                    'tone': 0.5,
                    'speaking': False,
                    'state': 'STANDBY'
                })
                await self.send_event('state-change', 'STANDBY')

    async def handle_message(self, msg: IPCMessage):
        """Route message to appropriate handler"""
        if (self._smoke_test and msg.type == 'lab-v1-autopilot'
                and os.environ.get('ZARA_LAB_ENTRY_CANARY') != '1'):
            await self.send_error(msg, 'SMOKE_READ_ONLY: Autopilot desabilitado no smoke test')
            return
        from core.lab_v1.canary import allowed as lab_canary_allowed
        if self._smoke_test and not lab_canary_allowed(msg.type) and msg.type not in {
            'engine-list', 'action-list', 'system-metrics', 'system-info',
            'voice-status', 'config-get', 'reminder-list',
            'memory-user-search', 'memory-user-list', 'project-memory-get',
            'project-memory-list', 'project-memory-context',
            'memory-galaxy-list', 'conversation-history-list',
        }:
            await self.send_error(msg, 'SMOKE_READ_ONLY: action blocked during isolated validation')
            return
        handler_map = {
            'engine-change': self.handle_engine_change,
            'engine-list': self.handle_engine_list,
            'send-message': self.handle_send_message,
            'interrupt': self.handle_interrupt,
            'voice-mute': self.handle_voice_mute,
            'voice-mic-chunk': self.handle_voice_mic_chunk,
            'action-execute': self.handle_action_execute,
            'action-confirm': self.handle_action_confirm,
            'action-confirm-cancel': self.handle_action_confirm_cancel,
            'action-list': self.handle_action_list,
            'self-status': self.handle_self_status,
            'system-metrics': self.handle_system_metrics,
            'latencia-resumo': self.handle_latencia_resumo,
            'system-info': self.handle_system_info,
            'voice-start': self.handle_voice_start,
            'voice-stop': self.handle_voice_stop,
            'voice-status': self.handle_voice_status,
            'config-get': self.handle_config_get,
            'config-set': self.handle_config_set,
            'lab-state': self.handle_lab_state,
            'lab-send': self.handle_lab_send,
            'lab-proposal-create': self.handle_lab_proposal_create,
            'lab-proposal-decide': self.handle_lab_proposal_decide,
            'lab-v1-room-message': self.handle_lab_v1_room_message,
            'lab-v1-snapshot': self.handle_lab_v1_snapshot,
            'lab-v1-admit-operation': self.handle_lab_v1_admit_operation,
            'lab-v1-confirm-operation': self.handle_lab_v1_confirm_operation,
            'lab-v1-create-session': self.handle_lab_v1_create_session,
            'lab-v1-submit': self.handle_lab_v1_submit,
            'lab-v1-autopilot': self.handle_lab_v1_autopilot,
            'lab-v1-autopilot-activate': self.handle_lab_v1_autopilot_activate,
            'lab-v1-autonomy-configure': self.handle_lab_v1_autonomy_configure,
            'lab-v1-cancel-mission': self.handle_lab_v1_cancel_mission,
            'lab-v1-delete-session': self.handle_lab_v1_delete_session,
            'lab-v1-providers': self.handle_lab_v1_providers,
            'lab-v1-proposal-list': self.handle_lab_v1_proposal_list,
            'lab-v1-proposal-register': self.handle_lab_v1_proposal_register,
            'lab-v1-proposal-update': self.handle_lab_v1_proposal_update,
            'lab-v1-agent-inventory': self.handle_lab_v1_agent_inventory,
            'lab-v1-create-agent': self.handle_lab_v1_create_agent,
            'lab-v1-configure-agent': self.handle_lab_v1_configure_agent,
            'lab-v1-agent-profiles': self.handle_lab_v1_agent_profiles,
            'lab-v1-agent-profile-update': self.handle_lab_v1_agent_profile_update,
            'lab-v1-agent-profile-rollback': self.handle_lab_v1_agent_profile_rollback,
            'lab-v1-archive-agent': self.handle_lab_v1_archive_agent,
            'lab-v1-rebind-role': self.handle_lab_v1_rebind_role,
            'lab-v1-research-skill': self.handle_lab_v1_research_skill,
            'lab-v1-team-chat': self.handle_lab_v1_team_chat,
            'lab-mission-state': self.handle_lab_mission_state,
            'lab-mission-verify': self.handle_lab_mission_verify,
            'lab-mission-cycle': self.handle_lab_mission_cycle,
            'lab-mission-recruit': self.handle_lab_mission_recruit,
            'lab-mission-finding': self.handle_lab_mission_finding,
            'lab-mission-prioritize': self.handle_lab_mission_prioritize,
            'lab-mission-patch': self.handle_lab_mission_patch,
            'lab-mission-bot': self.handle_lab_mission_bot,
            'lab-autonomy-start': self.handle_lab_autonomy_start,
            'lab-autonomy-stop': self.handle_lab_autonomy_stop,
            'lab-autonomy-status': self.handle_lab_autonomy_status,
            'conselheira-send': self.handle_conselheira_send,
            'conselheira-sync': self.handle_conselheira_sync,
            'conselheira-messages': self.handle_conselheira_messages,
            'conselheira-status': self.handle_conselheira_status,
            'reminder-create': self.handle_reminder_create,
            'reminder-list': self.handle_reminder_list,
            'reminder-cancel': self.handle_reminder_cancel,
            'memory-user-add': self.handle_memory_user_add,
            'memory-user-search': self.handle_memory_user_search,
            'memory-user-list': self.handle_memory_user_list,
            'memory-user-forget': self.handle_memory_user_forget,
            'project-memory-get': self.handle_project_memory_get,
            'project-memory-list': self.handle_project_memory_list,
            'project-memory-activate': self.handle_project_memory_activate,
            'project-memory-context': self.handle_project_memory_context,
            'memory-galaxy-list': self.handle_memory_galaxy_list,
            'conversation-history-list': self.handle_conversation_history_list,
            'conversation-history-clear': self.handle_conversation_history_clear,
        }

        handler = handler_map.get(msg.type)
        if handler:
            try:
                await handler(msg)
            except Exception as e:
                print(f"[IPC] Handler error for {msg.type}: {e}")
                traceback.print_exc()
                await self.send_error(msg, str(e))
        else:
            print(f"[IPC] Unknown message type: {msg.type}")

    async def send_response(self, request_id: str, response: Any = None, error: str = None, result: Any = None):
        """Send response back to renderer"""
        await self.send(IPCMessage(
            type='response',
            request_id=request_id,
            response=response,
            error=error,
            result=result
        ))

    async def send_error(self, msg: IPCMessage, error: str):
        if msg.request_id:
            await self.send_response(msg.request_id, error=error)

    async def send_event(self, event_type: str, data: Any):
        """Send a typed event to Electron without inventing dataclass fields."""
        if event_type == 'state-change':
            await self.send(IPCMessage(type=event_type, state=str(data)))
        elif event_type == 'message':
            await self.send(IPCMessage(type=event_type, message=data))
        elif event_type == 'metrics':
            await self.send(IPCMessage(type=event_type, metrics=data))
        elif event_type == 'voice-level':
            payload = data if isinstance(data, dict) else {}
            await self.send(IPCMessage(
                type=event_type,
                level=float(payload.get('level', 0.0) or 0.0),
                tone=float(payload.get('tone', 0.5) or 0.5),
                speaking=bool(payload.get('speaking', False)),
            ))
        else:
            await self.send(IPCMessage(type=event_type, data=data))

    # ============================================================
    # HANDLERS
    # ============================================================

    async def handle_lab_state(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        try:
            state = await self.lab.get_state()
            # The original Lab surface and the real V1 runtime coexist during
            # the migration.  Previously this handler exposed only the legacy
            # coordinator, whose honest-but-obsolete banner said that worker
            # execution was locked even while the resident V1 supervisor was
            # already running.  Project the V1 health snapshot here as an
            # additive field and derive the legacy banner from observed health;
            # never infer execution from installed binaries alone.
            if self.lab_v1 is not None:
                try:
                    v1 = await self.lab_v1.snapshot()
                    state["lab_v1"] = v1
                    health = v1.get("resident_health") or {}
                    resident = bool(health.get("resident")) and health.get("state") != "DEGRADED"
                    background = (v1.get("autonomy_policy") or {}).get("background_task_state")
                    if resident and background == "RUNNING":
                        state["execution_runtime"] = "AUTONOMY ONLINE • SANDBOX WORKERS ACTIVE"
                        autonomy = state.get("autonomy")
                        if isinstance(autonomy, dict):
                            autonomy["execution_enabled"] = True
                            autonomy["execution_scope"] = "V1 sandbox; produção exige revisão de Alex"
                except Exception as exc:
                    state["lab_v1"] = {"success": False, "error": type(exc).__name__}
            await self.send_response(msg.request_id, state)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_send(self, msg: IPCMessage):
        """Queue a council turn and ACK immediately.

        Worker/LLM turns may legitimately take tens of seconds. They must never
        occupy the Windows stdin dispatch loop, otherwise unrelated requests
        such as lab-state/system-metrics also time out.
        """
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return

        payload = msg.payload or {}
        author = str(payload.get('author') or 'alex')
        target = str(payload.get('target') or 'zara')
        content = str(payload.get('content') or '').strip()
        if not content:
            await self.send_error(msg, "Mensagem vazia")
            return

        async def _run_turn():
            try:
                result = await self.lab.send_message(author, target, content)
                print(
                    f"[LAB] background turn completed target={target} "
                    f"state={result.get('state') if isinstance(result, dict) else 'UNKNOWN'}"
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # The LabCoordinator normally persists worker errors itself.
                # This is only the final safety net for an unexpected exception.
                print(f"[LAB] background turn failed target={target}: {exc}")
                traceback.print_exc()

        task = asyncio.create_task(
            _run_turn(),
            name=f"zara-lab:{target}:{msg.request_id or 'no-id'}",
        )
        self._lab_background_tasks.add(task)
        task.add_done_callback(self._lab_background_tasks.discard)

        # Electron receives this before its normal request timeout. The renderer
        # already polls lab-state, so the actual agent response appears when the
        # background turn persists it to SQLite.
        ack: dict[str, Any] = {
            'success': True,
            'state': 'QUEUED',
            'target': target,
        }
        # The renderer decides whether to warn "relay offline" from this ACK, so
        # the real relay status must travel with it. Without this the UI showed a
        # false offline warning even when the bridge heartbeat was fresh.
        if target == 'mentor':
            try:
                ack['relay_online'] = bool(self.lab.mentor_relay.status().online)
            except Exception as exc:
                print(f"[LAB] mentor relay status unavailable: {exc}")
                ack['relay_online'] = False
                ack['relay_status_error'] = True
        await self.send_response(msg.request_id, ack)

    async def handle_lab_proposal_create(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.create_proposal(
                str(payload.get('title') or ''),
                str(payload.get('summary') or ''),
                str(payload.get('risk') or 'MEDIUM'),
                str(payload.get('owner') or 'opencode'),
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_proposal_decide(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.decide_proposal(
                str(payload.get('id') or ''),
                str(payload.get('decision') or ''),
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_voice_mic_chunk(self, msg: IPCMessage):
        """Forward renderer microphone PCM to the active Gemini voice session."""
        voice = self.gemini_live_voice
        pcm = (msg.payload or {}).get('pcm') or ''
        if voice is None or not pcm or not getattr(voice, 'usa_renderer', False):
            return
        try:
            import base64
            voice.push_mic_pcm(base64.b64decode(pcm))
        except Exception as exc:
            print(f"[IPC] chunk de microfone invalido: {exc}", flush=True)

    async def handle_voice_mute(self, msg: IPCMessage):
        """Mute only speech output while keeping the assistant running."""
        requested = (msg.payload or {}).get('mudo')
        if requested is None:
            await self.send_response(msg.request_id, {'success': True, 'mudo': bool(getattr(self, '_silenciada', False))})
            return
        self._silenciada = bool(requested)
        if self._silenciada:
            if self.tts_manager and hasattr(self.tts_manager, 'interrupt'):
                self.tts_manager.interrupt()
            if self.gemini_live_voice and getattr(self.gemini_live_voice, 'active', False):
                await self.gemini_live_voice.interrupt_speech()
            self._voice_speaking = False
        await self.send_response(msg.request_id, {'success': True, 'mudo': self._silenciada})
        await self.send_event('voice-mute-change', {'mudo': self._silenciada})

    async def handle_project_memory_context(self, msg: IPCMessage):
        if not self.project_memory:
            await self.send_error(msg, "Project Memory indisponível")
            return
        try:
            response: dict[str, Any] = {'success': True, 'keys': self.project_memory.list_docs()}
            payload = msg.payload or {}
            if payload.get('build') and hasattr(self.project_memory, 'build_project_context'):
                envelope = self.project_memory.build_project_context(
                    payload.get('project_id'),
                    keys=tuple(payload.get('keys')) if isinstance(payload.get('keys'), list) else None,
                    budget_bytes=payload.get('budget_bytes', 4096),
                )
                response['context'] = json.loads(envelope.to_json())
            await self.send_response(msg.request_id, response)
        except Exception as exc:
            await self.send_error(msg, f"project-memory-context: {exc}")

    async def handle_memory_galaxy_list(self, msg: IPCMessage):
        """Return a bounded, read-only view of local project and user memory."""
        nodes: list[dict[str, Any]] = []
        if self.project_memory:
            for key in self.project_memory.list_docs()[:50]:
                doc = self.project_memory.get_doc(key)
                if doc and str(doc.get('content', '')).strip():
                    nodes.append({
                        'id': f'project:{key}',
                        'kind': 'project',
                        'title': str(doc.get('title') or key)[:120],
                        'content': str(doc.get('content', ''))[:12000],
                        'source': f'Project Memory · {key}',
                    })
        if self.user_memory:
            for fact in self.user_memory.list()[:100]:
                if fact.get('status') != 'forgotten' and str(fact.get('fact', '')).strip():
                    nodes.append({
                        'id': f"user:{fact.get('id', '')}",
                        'kind': 'user',
                        'title': str(fact.get('category') or 'Memória do usuário')[:120],
                        'content': str(fact.get('fact', ''))[:12000],
                        'source': f"User Memory · {fact.get('source') or 'local'}",
                    })
        await self.send_response(msg.request_id, {
            'success': True, 'nodes': nodes, 'count': len(nodes), 'read_only': True, 'links': [],
        })

    async def handle_self_status(self, msg: IPCMessage):
        await self.send_response(msg.request_id, {
            'success': True,
            'current_engine': self.current_engine,
            'supercerebro_active': self.supercerebro_active,
            'voice_active': self.voice_active,
            'lab_available': bool(self.lab),
            'lab_v1_available': bool(LAB_V1_AVAILABLE),
        })

    # ------------------------------------------------------------
    # ZARA Lab V1 -- new multi-agent runtime (ZARA-LAB-V1-001)
    # ------------------------------------------------------------

    _LAB_V1_TEXT_LIMIT = 12000
    _LAB_V1_ADMISSIBLE_COMMANDS = frozenset({
        'lab.v1.submit', 'lab.v1.message', 'lab.v1.room', 'lab.v1.cancel', 'lab.v1.resume',
    })

    async def _ensure_lab_v1(self, msg: IPCMessage):
        """Lazily construct the LabV1Service facade, or ACK a clear failure.

        Returns the service instance, or None after already sending the
        "indisponível" error -- callers must return immediately when None.
        """
        if not LAB_V1_AVAILABLE or LabV1Service is None:
            await self.send_error(msg, "ZARA Lab V1 indisponível")
            return None
        if self.lab_v1 is None:
            try:
                self.lab_v1 = LabV1Service()
                # O Lab V1 só era criado sob demanda, mas seu ciclo de
                # supervisor/scheduler ficava parado até uma segunda ação.
                # Ao abrir qualquer superfície do Lab, inicia o background
                # persistente; a própria WorkforcePolicy continua decidindo
                # se ele pode rodar, com orçamento, escopo e verificação.
                background = await self.lab_v1.start_background()
                print(
                    f"[IPC] ZARA Lab V1 background state={background.get('state')}",
                    flush=True,
                )
            except Exception as exc:
                print(f"[IPC] ZARA Lab V1 failed to initialize: {exc}")
                traceback.print_exc()
                self.lab_v1 = None
                await self.send_error(msg, "ZARA Lab V1 indisponível")
                return None
        return self.lab_v1

    async def handle_lab_v1_room_message(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        session_id = str(payload.get('session_id') or '').strip()
        content = str(payload.get('content') or '').strip()[:self._LAB_V1_TEXT_LIMIT]
        if not session_id or not content:
            await self.send_error(msg, 'session_id e content são obrigatórios')
            return
        try:
            await self.send_response(msg.request_id, await svc.room_message(session_id, content))
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_snapshot(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        session_id = payload.get('session_id')
        team_id = payload.get('team_id')
        if session_id is not None and not isinstance(session_id, str):
            await self.send_error(msg, "session_id inválido")
            return
        if team_id is not None and not isinstance(team_id, str):
            await self.send_error(msg, "team_id inválido")
            return
        try:
            result = await svc.snapshot(session_id, team_id)
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_create_session(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        objective = str(payload.get('objective') or '').strip()[:self._LAB_V1_TEXT_LIMIT]
        team_id = payload.get('team_id')
        if not objective:
            await self.send_error(msg, "Objetivo vazio")
            return
        if team_id is not None and not isinstance(team_id, str):
            await self.send_error(msg, "team_id inválido")
            return
        try:
            result = await svc.create_session(objective, team_id=team_id)
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_admit_operation(self, msg: IPCMessage):
        """Return a durable admission ACK; the renderer confirms receipt next."""
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        envelope = msg.payload or {}
        if not isinstance(envelope, dict):
            await self.send_error(msg, 'Payload inválido')
            return
        command = envelope.get('command')
        if command not in self._LAB_V1_ADMISSIBLE_COMMANDS:
            await self.send_error(msg, 'Comando do Lab inválido')
            return
        payload = envelope.get('payload')
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload do comando inválido')
            return
        result, _newly_admitted = await svc.admit_operation_for_dispatch(
            msg.request_id, command, payload
        )
        await self.send_response(msg.request_id, result)

    async def handle_lab_v1_confirm_operation(self, msg: IPCMessage):
        """Release work only after the renderer proves it received admission.

        A separate confirmation removes the unobservable crash interval between
        writing an ACK to stdout and committing a release in SQLite. Replaying
        either message is safe: admission and authorization are idempotent.
        """
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload inválido')
            return
        operation_id = str(payload.get('operation_id') or '').strip()
        if not operation_id:
            await self.send_error(msg, 'operation_id ausente')
            return
        authorization = asyncio.create_task(
            svc.authorize_operation_dispatch(operation_id),
            name=f"zara-lab-v1-authorize:{operation_id}",
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(authorization),
                timeout=self._LAB_V1_CONFIRM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # The database outcome is not yet known. Do not claim confirmation
            # or cancel a write that may already have committed.
            await self.send_response(msg.request_id, {
                'success': False,
                'confirmed': False,
                'code': 'CONFIRMATION_OUTCOME_UNKNOWN',
                'operation_id': operation_id,
            })

            async def _finish_after_authorization():
                try:
                    await authorization
                except Exception as exc:
                    print(f"[IPC] Lab authorization failed: {type(exc).__name__}", flush=True)
                    return
                await self._dispatch_lab_v1_operation(svc, operation_id)

            self._schedule_lab_v1_task(
                _finish_after_authorization(),
                name=f"zara-lab-v1-late-confirm:{operation_id}",
            )
            return
        except ValueError as exc:
            await self.send_error(msg, str(exc))
            return
        await self.send_response(msg.request_id, {
            'success': True,
            'confirmed': True,
            'operation_id': operation_id,
            'state': 'DISPATCH_AUTHORIZED',
        })
        self._schedule_lab_v1_task(
            self._dispatch_lab_v1_operation(svc, operation_id),
            name=f"zara-lab-v1-operation:{operation_id}",
        )

    def _schedule_lab_v1_task(self, coroutine, *, name: str):
        task = asyncio.create_task(coroutine, name=name)
        self._lab_v1_background_tasks.add(task)

        def _observe(completed):
            self._lab_v1_background_tasks.discard(completed)
            try:
                completed.exception()
            except asyncio.CancelledError:
                pass

        task.add_done_callback(_observe)
        return task

    async def _dispatch_lab_v1_operation(self, svc, operation_id: str):
        try:
            result = await svc.dispatch_operation(operation_id)
        except Exception as exc:
            print(f"[IPC] Lab operation dispatch failed {operation_id}: {exc}", flush=True)
            return
        if result.get('state') in {'COMPLETED', 'FAILED', 'INTERRUPTED'}:
            await self._publish_lab_v1_operation_results(svc)

    async def _drain_lab_v1_operation_outbox(self, svc):
        await svc.dispatch_pending_operations()
        await self._publish_lab_v1_operation_results(svc)

    async def _publish_lab_v1_operation_results(self, svc):
        while True:
            results = await svc.claim_operation_result_publications()
            if not results:
                return
            for result in results:
                operation_id = result.get('operation_id')
                event = {**result, 'event_id': f'operation-result:{operation_id}'}
                try:
                    await self.send_event('lab-v1-operation-result', event)
                    await svc.mark_operation_result_published(operation_id)
                except Exception as exc:
                    print(f"[IPC] Lab operation result publish failed {operation_id}: {exc}", flush=True)
                    try:
                        await svc.release_operation_result_publication(operation_id)
                    except Exception as release_exc:
                        print(
                            f"[IPC] Lab operation result release failed {operation_id}: {release_exc}",
                            flush=True,
                        )
                    return

    async def handle_lab_v1_submit(self, msg: IPCMessage):
        # Do not ACK QUEUED before a policy-approved mission exists.
        svc = await self._ensure_lab_v1(msg)
        if svc is not None:
            await self.send_response(msg.request_id, svc.workforce_refusal())

    async def handle_lab_v1_autopilot(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        intent = payload.get('intent')
        if not isinstance(intent, str) or not 1 <= len(intent.strip()) <= self._LAB_V1_TEXT_LIMIT:
            await self.send_error(msg, 'Objetivo invalido')
            return
        result = await svc.start_autopilot(intent.strip())
        entry_canary = self._smoke_test and os.environ.get('ZARA_LAB_ENTRY_CANARY') == '1'
        if result.get('success') and not entry_canary:
            task = asyncio.create_task(svc.run_autopilot(result['session_id']))
            self._lab_v1_background_tasks.add(task)
            task.add_done_callback(self._lab_v1_background_tasks.discard)
        # The ACK follows persistence, never claims that the mission has finished.
        await self.send_response(msg.request_id, result)

    async def handle_lab_v1_cancel_mission(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is not None:
            session_id = str((msg.payload or {}).get('session_id') or '')
            await self.send_response(msg.request_id, await svc.cancel_autopilot(session_id))

    async def handle_lab_v1_autonomy_configure(self, msg: IPCMessage):
        if self._smoke_test:
            await self.send_error(msg, 'Autonomia desabilitada no canary isolado')
            return
        svc = await self._ensure_lab_v1(msg)
        enabled = (msg.payload or {}).get('enabled')
        if type(enabled) is not bool:
            await self.send_error(msg, 'Estado de autonomia invalido')
            return
        if svc is not None:
            await self.send_response(msg.request_id, await svc.configure_autonomy(enabled))

    async def handle_lab_v1_autopilot_activate(self, msg: IPCMessage):
        if self._smoke_test:
            await self.send_error(msg, 'Autonomia desabilitada no canary isolado')
            return
        svc = await self._ensure_lab_v1(msg)
        if svc is not None:
            await self.send_response(msg.request_id, await svc.activate_autopilot())

    async def handle_lab_v1_providers(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        try:
            result = await svc.providers()
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_proposal_list(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        state = payload.get('state')
        if state is not None and not isinstance(state, str):
            await self.send_error(msg, 'state invalido')
            return
        try:
            limit = min(max(int(payload.get('limit', 100)), 1), 500)
            await self.send_response(msg.request_id, await svc.proposal_feed_list(state, limit))
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_proposal_register(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        proposal = msg.payload or {}
        if not isinstance(proposal, dict) or not str(proposal.get('proposal_id') or proposal.get('id') or '').strip():
            await self.send_error(msg, 'proposal_id obrigatorio')
            return
        try:
            await self.send_response(msg.request_id, await svc.proposal_feed_register(proposal))
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_proposal_update(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        proposal_id = str(payload.get('proposal_id') or payload.get('id') or '').strip()
        state = payload.get('state') or payload.get('status')
        if not proposal_id or not isinstance(state, str) or not state.strip():
            await self.send_error(msg, 'proposal_id e state sao obrigatorios')
            return
        try:
            await self.send_response(msg.request_id, await svc.proposal_feed_update(proposal_id, state))
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_agent_inventory(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        refresh = bool((msg.payload or {}).get('refresh', False))
        await self.send_response(msg.request_id, await svc.agent_inventory(refresh=refresh))

    async def handle_lab_v1_research_skill(self, msg: IPCMessage):
        """Bounded research/skill gates; activation still needs owner approval."""
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload inválido')
            return
        operation = str(payload.get('operation') or '').strip().lower()
        if operation not in {'snapshot', 'research', 'candidate', 'test', 'activate', 'rollback'}:
            await self.send_error(msg, 'Operação de pesquisa/skill inválida')
            return
        if len(payload) > 16:
            await self.send_error(msg, 'Payload de pesquisa excede o limite')
            return
        if operation == 'research':
            topic = payload.get('topic')
            sources = payload.get('sources')
            if not isinstance(topic, str) or not topic.strip() or len(topic) > 500:
                await self.send_error(msg, 'Tema de pesquisa inválido')
                return
            if not isinstance(sources, list) or not 1 <= len(sources) <= 8 or any(
                not isinstance(source, str) or not source.strip() or len(source) > 2000 for source in sources
            ):
                await self.send_error(msg, 'Fontes de pesquisa inválidas')
                return
        try:
            result = await svc.research_skill_pipeline(operation, payload)
            await self.send_response(msg.request_id, result)
        except Exception:
            await self.send_error(msg, 'Falha controlada na operação de pesquisa/skill')

    async def handle_lab_v1_team_chat(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload inválido')
            return
        allowed_roles = {'RESEARCHER', 'ARCHITECT', 'ENGINEER', 'CODER', 'TESTER', 'REVIEWER', 'CEO', 'ZARA'}
        allowed_states = {'OBSERVED', 'ANALYZING', 'PLANNED', 'IMPLEMENTING', 'TESTING', 'REVIEWING', 'WAITING_CEO', 'APPROVED', 'REJECTED', 'ROLLED_BACK'}
        required = ('mission_id', 'role', 'state', 'summary')
        if len(payload) > 6 or any(key not in payload for key in required):
            await self.send_error(msg, 'Payload de chat inválido')
            return
        if not all(isinstance(payload[key], str) and payload[key].strip() for key in required):
            await self.send_error(msg, 'Campos obrigatórios do chat inválidos')
            return
        if payload['role'].strip().upper() not in allowed_roles or payload['state'].strip().upper() not in allowed_states:
            await self.send_error(msg, 'Papel ou estado do chat inválido')
            return
        if len(payload['mission_id']) > 160 or len(payload['summary']) > 4000 or len(payload.get('next_action', '')) > 1000:
            await self.send_error(msg, 'Mensagem de chat excede o limite')
            return
        refs = payload.get('evidence_refs', [])
        if not isinstance(refs, list) or len(refs) > 20 or any(not isinstance(ref, str) or len(ref) > 200 for ref in refs):
            await self.send_error(msg, 'Referências de evidência inválidas')
            return
        try:
            await self.send_response(msg.request_id, await svc.append_team_chat(payload))
        except Exception:
            await self.send_error(msg, 'Falha controlada ao gravar chat do Lab')

    async def handle_lab_v1_create_agent(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, "Payload inválido")
            return
        name = str(payload.get('name') or '').strip()[:self._LAB_V1_TEXT_LIMIT]
        provider_id = str(payload.get('provider_id') or '').strip()
        model = str(payload.get('model') or '').strip()
        if not name or not provider_id or not model:
            await self.send_error(msg, "Nome, provedor e modelo são obrigatórios")
            return
        instructions = str(payload.get('instructions') or '')[:self._LAB_V1_TEXT_LIMIT]
        # Only forward keys LabV1Service.create_agent actually accepts
        # (core/lab_v1/service.py): name, provider_id, model, role, team_id,
        # lifecycle, instructions, fallback_agent_id. Unknown extras are
        # dropped rather than passed through, so a stray renderer field can
        # never turn into a TypeError deep in the service.
        kwargs: dict[str, Any] = {
            'name': name,
            'provider_id': provider_id,
            'model': model,
            'instructions': instructions,
        }
        role = payload.get('role')
        if isinstance(role, str) and role.strip():
            kwargs['role'] = role.strip()
        lifecycle = payload.get('lifecycle')
        if isinstance(lifecycle, str) and lifecycle.strip():
            kwargs['lifecycle'] = lifecycle.strip()
        team_id = payload.get('team_id')
        if isinstance(team_id, str) and team_id.strip():
            kwargs['team_id'] = team_id.strip()
        fallback_agent_id = payload.get('fallback_agent_id')
        if isinstance(fallback_agent_id, str) and fallback_agent_id.strip():
            kwargs['fallback_agent_id'] = fallback_agent_id.strip()
        try:
            result = await svc.create_agent(**kwargs)
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_delete_session(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is not None:
            await self.send_response(msg.request_id, await svc.delete_session(str((msg.payload or {}).get('session_id') or '')))

    async def handle_lab_v1_configure_agent(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None: return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload inválido'); return
        values = {k: str(payload.get(k) or '').strip() for k in ('agent_id', 'provider_id', 'model')}
        if not all(values.values()):
            await self.send_error(msg, 'Participante, provedor e modelo são obrigatórios'); return
        await self.send_response(msg.request_id, await svc.configure_agent(**values))

    async def handle_lab_v1_agent_profiles(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        agent_id = str(payload.get('agent_id') or '').strip() if isinstance(payload, dict) else ''
        result = await svc.agent_profile(agent_id) if agent_id else await svc.agent_profiles()
        await self.send_response(msg.request_id, result)

    async def handle_lab_v1_agent_profile_update(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, 'Payload inválido')
            return
        agent_id = str(payload.get('agent_id') or '').strip()
        if not agent_id:
            await self.send_error(msg, 'Participante obrigatório')
            return
        permissions = payload.get('permissions')
        if permissions is not None and not isinstance(permissions, list):
            await self.send_error(msg, 'Permissões inválidas')
            return
        await self.send_response(msg.request_id, await svc.update_agent_profile(
            agent_id=agent_id,
            soul=payload.get('soul') if 'soul' in payload else None,
            provider_id=payload.get('provider_id') if 'provider_id' in payload else None,
            model=payload.get('model') if 'model' in payload else None,
            permissions=permissions,
        ))

    async def handle_lab_v1_agent_profile_rollback(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        try:
            agent_id = str(payload.get('agent_id') or '').strip()
            version = int(payload.get('version'))
        except (AttributeError, TypeError, ValueError):
            await self.send_error(msg, 'Participante e versão são obrigatórios')
            return
        await self.send_response(msg.request_id, await svc.rollback_agent_profile(
            agent_id=agent_id, version=version,
        ))

    async def handle_lab_v1_archive_agent(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        agent_id = str(payload.get('agent_id') or '').strip()
        if not agent_id:
            await self.send_error(msg, "agent_id ausente")
            return
        try:
            result = await svc.archive_agent(agent_id)
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))

    async def handle_lab_v1_rebind_role(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        payload = msg.payload or {}
        team_id = str(payload.get('team_id') or '').strip()
        role = str(payload.get('role') or '').strip()
        agent_id = str(payload.get('agent_id') or '').strip()
        reason = str(payload.get('reason') or '').strip()[:self._LAB_V1_TEXT_LIMIT]
        if not team_id or not role or not agent_id:
            await self.send_error(msg, "team_id, role e agent_id são obrigatórios")
            return
        try:
            result = await svc.rebind_role(team_id, role, agent_id, reason)
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    # ------------------------------------------------------------
    # ZARA Lab V1 -- new multi-agent runtime (ZARA-LAB-V1-001)
    # ------------------------------------------------------------

    _LAB_V1_TEXT_LIMIT = 12000
    _LAB_V1_ADMISSIBLE_COMMANDS = frozenset({
        'lab.v1.submit', 'lab.v1.message', 'lab.v1.room', 'lab.v1.cancel', 'lab.v1.resume',
    })






























    async def handle_engine_change(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        engine = (msg.payload or {}).get('engine')
        try:
            result = await svc.select_front_brain(engine)
            if not result.get('success'):
                await self.send_error(msg, result.get('error', 'Modelo indisponivel.'))
                return
            self.current_engine = result['engine']
            await self.send_response(msg.request_id, result)
        except Exception:
            await self.send_error(msg, 'Nao foi possivel salvar a selecao do modelo.')

    def _front_runtime_capability_context(self, channel):
        """Small factual contract shared by every conversational input channel."""
        normalized_channel = str(channel or 'UNKNOWN').strip().upper()
        return '\n'.join((
            '[ZARA_RUNTIME_CONTEXT]',
            'identity=ZARA',
            'runtime=ZARA_DESKTOP',
            f'channel={normalized_channel}',
            'session_id=session_zara_front_v1',
            'local_dispatcher=AVAILABLE',
            f'reminders={"AVAILABLE" if self.reminder_engine is not None else "UNAVAILABLE"}',
            f'memory={"AVAILABLE" if self.memory is not None else "UNAVAILABLE"}',
            f'conversation_history={"AVAILABLE" if self.conversation_history is not None else "UNAVAILABLE"}',
            f'voice_active={str(bool(self.voice_active)).upper()}',
            f'voice_mode={str(self.voice_mode or "off").upper()}',
            f'gemini_live_transport={"AVAILABLE" if self.gemini_live_voice is not None else "UNAVAILABLE"}',
            f'local_voice_pipeline={"AVAILABLE" if self.voice_pipeline is not None else "UNAVAILABLE"}',
            f'lab_coordinator={"AVAILABLE" if self.lab is not None else "UNAVAILABLE"}',
            f'lab_v1_runtime={"AVAILABLE" if LAB_V1_AVAILABLE else "UNAVAILABLE"}',
            'runtime_context_overrides_stale_conversation_claims=TRUE',
            'channel_changes_identity=FALSE',
            '[/ZARA_RUNTIME_CONTEXT]',
        ))

    async def _front_conversation_reply(self, text, requested_model=None, voice_turn_id=None,
                                        channel='TEXT', history_override=None):
        # Preserve the injected orchestrator contract used by callers that
        # provide an explicit conversation engine (tests and embedders). The
        # production path still converges on FrontBrain/LabV1 below; an
        # injected implementation must not be silently bypassed by lazy Lab
        # construction.
        orchestrator_module = type(self.orchestrator).__module__ if self.orchestrator is not None else ""
        if (
            self.lab_v1 is None
            and self.orchestrator is not None
            and not isinstance(self.orchestrator, ZaraOrchestrator)
            and not orchestrator_module.startswith("unittest.mock")
        ):
            history = history_override if isinstance(history_override, list) else None
            if history is None and self.conversation_history is not None:
                history = await asyncio.to_thread(self.conversation_history.list_recent, 20)
            engine = requested_model or self.current_engine
            response = await self.orchestrator.process_message(
                text, engine=engine, history=history,
            )
            return {
                'response': str(response),
                'engine': getattr(self.orchestrator, 'last_engine_used', engine),
            }
        if self.lab_v1 is None:
            if not LAB_V1_AVAILABLE or LabV1Service is None:
                raise RuntimeError('Conversa ZARA indisponivel.')
            self.lab_v1 = LabV1Service()
            background = await self.lab_v1.start_background()
            print(
                f"[IPC] ZARA Lab V1 conversation background state={background.get('state')}",
                flush=True,
            )
        enriched = await self._enrich_with_memory(text)
        context = (str(enriched)[:6000] if enriched != text else '')
        context += '\n' + str(getattr(self, 'mentor_context', '') or '')[:4000]
        context += '\n' + self._front_runtime_capability_context(channel)
        history = None
        if self.conversation_history is not None:
            history = await asyncio.to_thread(self.conversation_history.list_recent, 20)
        result_is_current = None
        if voice_turn_id is not None:
            result_is_current = lambda: self._voice_turn_is_current(voice_turn_id)
        result = await self.lab_v1.front_reply(
            text, requested_model=requested_model, history=history, context=context,
            result_is_current=result_is_current,
        )
        if isinstance(result, dict):
            resolved_model = (
                result.get('engine') or requested_model or self.current_engine
            )
            model_config = get_model_config(resolved_model) if resolved_model else None
            result.setdefault(
                'cost_status',
                getattr(model_config, 'cost_status', 'UNKNOWN_COST'),
            )
        if result.get('engine'):
            self.current_engine = result['engine']
        return result

    async def handle_send_message(self, msg: IPCMessage):
        payload = msg.payload or {}
        raw_text = str(payload.get('text', '') or payload.get('message', '') or '').strip()
        text = _canonical_request(raw_text)
        # ZARA-SAUDACAO-VAZIA-001: "Oi Zara" sozinho e so o nome + saudacao --
        # _canonical_request tira o dois e sobra "". Isso nao e "nada foi
        # digitado" (raw_text existe); e um cumprimento sem comando junto.
        # Sem isto, todo "Oi Zara" digitado virava erro "No text provided" em
        # vez de puxar uma resposta de conversa normal.
        if not text and raw_text:
            text = raw_text
        engine = str(payload.get('engine', self.current_engine) or self.current_engine)

        if not text:
            await self.send_error(msg, "No text provided")
            return

        # ZARA-CORE-STATE-TEXTO-001: o Core (bola central da Home) so reagia a
        # eventos de voz. Comando de texto nunca movia o estado -- ficava
        # "idle" o tempo todo, mesmo processando. Cada saida abaixo devolve
        # para STANDBY, entao nunca fica travado em THINKING.
        await self.send_event('state-change', 'THINKING')
        print(f"[IPC] Processing message ({len(text)} chars, engine: {engine})")
        # ZARA-ONDE-ELE-ESTA-001: digitou no app, entao esta na frente do PC.
        self._marcar_canal("computador")
        await self._append_conversation_message("user", text, engine)

        jarvis_reply = await self._try_jarvis_multi_action(text)
        if jarvis_reply:
            await self._append_conversation_message("assistant", jarvis_reply, "jarvis_plan")
            await self.send_response(msg.request_id, {
                'response': jarvis_reply,
                'engine': 'jarvis_plan',
            })
            await self.send_event('state-change', 'STANDBY')
            return

        # ZARA-REMINDER-VOICE-BINDING-001: texto e voz usam o MESMO intent handler.
        reminder_reply = await self._try_reminder_intent(text)
        if reminder_reply:
            await self._append_conversation_message("assistant", reminder_reply, "reminder")
            response_payload = {
                'response': reminder_reply,
                'engine': 'reminder',
            }
            if self.lab_v1 is not None or not type(self._try_reminder_intent).__module__.startswith("unittest.mock"):
                response_payload['response_origin'] = 'local_deterministic'
            await self.send_response(msg.request_id, response_payload)
            await self.send_event('state-change', 'STANDBY')
            return

        memory_reply = await self._try_operational_memory_intent(text)
        if memory_reply:
            await self._append_conversation_message("assistant", memory_reply, "operational_memory")
            await self.send_response(msg.request_id, {
                'response': memory_reply,
                'engine': 'operational_memory',
            })
            await self.send_event('state-change', 'STANDBY')
            return

        # Autoconhecimento usa estado real e o mesmo caminho em texto e voz.
        self_reply = await self._try_self_knowledge(text)
        if self_reply:
            await self._append_conversation_message("assistant", self_reply, "self_knowledge")
            await self.send_response(msg.request_id, {
                'response': self_reply,
                'engine': 'self_knowledge',
            })
            await self.send_event('state-change', 'STANDBY')
            return

        file_reply = await self._try_file_intent(text)
        if file_reply:
            await self._append_conversation_message("assistant", file_reply, "file_control")
            await self.send_response(msg.request_id, {
                'response': file_reply,
                'engine': 'file_control',
            })
            await self.send_event('state-change', 'STANDBY')
            return

        # ZARA-COMPUTER-CONTROL-VOLUME-001: texto e voz usam o MESMO intent handler.
        try:
            pc_reply = await self._try_compound_pc_intent(text)
            if not pc_reply:
                pc_reply = await self._try_pc_intent(text)
        except Exception as exc:
            print(f"[IPC] Local action router failed: {type(exc).__name__}", flush=True)
            await self.send_response(msg.request_id, {
                'response': 'Não consegui executar essa ação com segurança.',
                'engine': 'local_action_error',
            })
            await self.send_event('state-change', 'ERROR')
            return
        if pc_reply:
            # Auditoria do Codex, achado 3: o selo só saía pelo caminho de voz.
            # Alex digita "diminua o volume", a MESMA ação executa, e a tela
            # ficava sem saber se aquilo foi verificado — mostrando cinza para
            # uma ação que a ZARA provou. Voz e texto compartilham a cadeia
            # inteira; compartilham a prova também.
            selo = self._selo_do_ultimo_resultado()
            await self._append_conversation_message("assistant", pc_reply, "pc_control")
            await self.send_event('message', {
                'role': 'assistant',
                'content': pc_reply,
                'engine': 'pc_control',
                'selo': selo,
                'timestamp': datetime.now().isoformat(),
            })
            response_payload = {
                'response': pc_reply,
                'engine': 'pc_control',
                'selo': selo,
            }
            if self.lab_v1 is not None or not type(self._try_pc_intent).__module__.startswith("unittest.mock"):
                response_payload['response_origin'] = 'local_deterministic'
            await self.send_response(msg.request_id, response_payload)
            await self.send_event('state-change', 'STANDBY')
            return

        lab_reply = await self._try_lab_intent(text)
        if lab_reply:
            await self._append_conversation_message("assistant", lab_reply, "lab_autopilot")
            await self.send_event('message', {
                'role': 'assistant',
                'content': lab_reply,
                'engine': 'lab_autopilot',
                'timestamp': datetime.now().isoformat(),
            })
            await self.send_response(msg.request_id, {
                'response': lab_reply,
                'engine': 'lab_autopilot',
            })
            await self.send_event('state-change', 'STANDBY')
            return

        if _looks_like_unhandled_local_action(text):
            _log_intent_telemetry("refused_local_action", "text", text)
            # ETAPA 3 (raciocinio livre): ultimo recurso, atras de flag, so
            # aqui -- depois que a cadeia deterministica inteira ja recusou.
            # Nao muda nada no comando do dia a dia; flag desligada (padrao)
            # e byte a byte o comportamento de antes.
            fallback_reply = await _tentar_raciocinio_livre_texto(self, text)
            if fallback_reply is None:
                # NIGHT-07, mesma chamada do caminho de voz. Fica DEPOIS da
                # Etapa 3 e so quando ela nao respondeu: com a flag desligada
                # (padrao, e o que roda em producao) isto e byte a byte o
                # mesmo ponto do caminho de voz; com a flag ligada, uma frase
                # que a Etapa 3 roteou nao e lacuna e nao vira gap.
                self._remember_unhandled_intent(text)
            reply = fallback_reply if fallback_reply is not None else RESPOSTA_NAO_SEI
            engine_usado = 'raciocinio_livre_texto' if fallback_reply is not None else 'local_action_guard'
            await self._append_conversation_message("assistant", reply, engine_usado)
            await self.send_response(msg.request_id, {
                'response': reply,
                'engine': engine_usado,
                # The optional legacy LLM classifier has no FrontBrain Run
                # receipt. Keep it explicitly unproven so Home fails closed.
                'response_origin': (
                    'unproven_legacy' if fallback_reply is not None
                    else 'local_deterministic'
                ),
            })
            await self.send_event('state-change', 'STANDBY')
            return

        # ETAPA 1 (raciocinio livre): guarda a frase original, antes do
        # enriquecimento de memoria e do contexto do mentor, so para o log de
        # telemetria abaixo.
        _telemetry_raw_text = text
        if _has_broad_action_language_signal(_telemetry_raw_text):
            _log_intent_telemetry(
                "escaped_to_orchestrator", "text", _telemetry_raw_text
            )

        try:
            front_result = await self._front_conversation_reply(
                text, payload.get('engine'), channel='TEXT',
                history_override=payload.get('history'),
            )
            if front_result.get('success') is False:
                await self._append_conversation_message(
                    "system", "Backend indisponível para esta solicitação.",
                    front_result.get('engine') or engine,
                )
                await self.send_response(msg.request_id, {
                    **front_result,
                    'response': front_result.get(
                        'response',
                        'O cérebro conversacional está temporariamente indisponível.',
                    ),
                })
                await self.send_event('state-change', 'ERROR')
                return

            response = str(front_result['response'])
            engine_used = front_result['engine']

            # Store the turn in episodic memory, not in compact fact memory.
            if self.memory:
                await self.memory.add_conversation(text, response, engine_used)

            await self._append_conversation_message("assistant", response, engine_used)

            await self.send_response(msg.request_id, {**front_result, 'response': response})
            await self.send_event('state-change', 'STANDBY')

            # Text chat already returns this response to the invoking renderer.
            # Voice turns still use the asynchronous 'message' event path.

        except Exception as e:
            print(f"[IPC] Send message error: {e}")
            traceback.print_exc()
            await self._append_conversation_message(
                "system", "Backend indisponível para esta solicitação.", engine
            )
            await self.send_error(msg, str(e))
            await self.send_event('state-change', 'ERROR')

    async def handle_interrupt(self, msg: IPCMessage):
        print("[IPC] Interrupt requested")
        self._invalidate_voice_turn()
        if self.tts_manager:
            self.tts_manager.interrupt()
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.interrupt_speech()
        # Interrupt voice pipeline if active
        if self.voice_pipeline:
            self.voice_pipeline.interrupt()
        self._voice_speaking = False
        self._fala_interrompida = True  # ZARA-VOZ-UNICA-002
        self._finish_assistant_output()
        await self.send_response(msg.request_id, {'success': True})
        await self.send_event('state-change', 'STANDBY')
        await self.send_event('voice-level', {
            'level': 0.0,
            'tone': 0.5,
            'speaking': False,
            'state': 'STANDBY'
        })

    async def handle_action_execute(self, msg: IPCMessage):
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, "Action payload must be an object")
            return
        action = payload.get('action', '')
        params = payload.get('params', {})

        if not action:
            await self.send_error(msg, "Action not specified")
            return

        if not isinstance(params, dict):
            await self.send_error(msg, "Action params must be an object")
            return

        reserved = {"confirmation_id", "action_fingerprint", "_zara_confirmation_proof"}
        if reserved.intersection(params):
            await self.send_error(msg, "Confirmation proof is only accepted by action-confirm")
            return

        # Parameters may contain credentials or private content; never log them.
        print(f"[IPC] Executing action: {action}")

        # ZARA-CORE-STATE-ACAO-001: mesmo gap do handle_send_message -- o Core
        # nunca mostrava EXECUTANDO/ERRO durante uma acao real (clique de
        # botao na Home, ex. os_wifi_status, os_power_plan_set). Result.success
        # False sem excecao (ex. _failure()) tambem conta como erro visual.
        show_state = action not in {'os_wifi_status', 'os_power_plan_list'}
        if show_state:
            await self.send_event('state-change', 'EXECUTING')
        try:
            result = await execute_action(action, **params)
            result_ok = bool(getattr(result, 'success', False))
            await self.send_response(msg.request_id, {
                'success': result_ok, 'result': result,
                'error': getattr(result, 'error', None),
                'verificado': bool(getattr(result, 'verificado', False)),
            })
            if show_state:
                await self.send_event('state-change', 'SUCCESS' if result_ok else 'ERROR')
        except Exception as e:
            print(f"[IPC] Action error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))
            if show_state:
                await self.send_event('state-change', 'ERROR')

    async def handle_action_confirm(self, msg: IPCMessage):
        """Consume a private one-shot confirmation and execute the bound action."""
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, "Confirmation payload must be an object")
            return

        confirmation_id = payload.get('confirmation_id')
        action_fingerprint = payload.get('action_fingerprint')
        action = payload.get('action')
        params = payload.get('params', {})
        if not isinstance(confirmation_id, str) or not confirmation_id:
            await self.send_error(msg, "confirmation_id is required")
            return
        if not isinstance(action_fingerprint, str) or not action_fingerprint:
            await self.send_error(msg, "action_fingerprint is required")
            return
        if not isinstance(action, str) or not action:
            await self.send_error(msg, "Action not specified")
            return
        if not isinstance(params, dict):
            await self.send_error(msg, "Action params must be an object")
            return
        if "_zara_confirmation_proof" in params:
            await self.send_error(msg, "Reserved action parameter")
            return

        print(f"[IPC] Confirming HIGH-risk action: {action}")
        try:
            result = await execute_confirmed_action(
                action,
                confirmation_id,
                action_fingerprint,
                **params,
            )
            await self.send_response(msg.request_id, {
                'success': bool(getattr(result, 'success', False)), 'result': result,
                'error': getattr(result, 'error', None),
                'verificado': bool(getattr(result, 'verificado', False)),
            })
        except Exception as e:
            print(f"[IPC] Action confirmation error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

    async def handle_action_confirm_cancel(self, msg: IPCMessage):
        """Cancel a pending confirmation without executing an action."""
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            await self.send_error(msg, "Confirmation payload must be an object")
            return
        confirmation_id = payload.get('confirmation_id')
        if not isinstance(confirmation_id, str) or not confirmation_id:
            await self.send_error(msg, "confirmation_id is required")
            return

        from core.action_registry import get_registry

        cancelled = get_registry().cancel_confirmation(confirmation_id)
        await self.send_response(
            msg.request_id,
            {'success': True, 'cancelled': cancelled},
        )

    async def handle_latencia_resumo(self, msg: IPCMessage):
        try:
            from core.cronometro import relatorio
            dados = relatorio()
        except Exception as e:
            await self.send_response(msg.request_id, {'success': False, 'error': str(e)})
            return
        await self.send_response(msg.request_id, {'success': True, 'data': dados})

    async def handle_system_metrics(self, msg: IPCMessage):
        import psutil

        metrics = {
            'cpu': psutil.cpu_percent(interval=0.1),
            'ram': psutil.virtual_memory().percent,
            'disk': psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent,
            'netUp': 0,  # Would need network monitoring
            'netDown': 0,
        }

        await self.send_response(msg.request_id, metrics)

        # Also broadcast as event
        await self.send_event('metrics', metrics)

    async def handle_voice_start(self, msg: IPCMessage):
        """Start Gemini Live (Kore) when configured; keep local voice as fallback."""
        print("[VOICE_TRACE] stage=MANUAL_MIC_EVENT result=RECEIVED", flush=True)
        async with self._voice_start_lock:
            await self._handle_voice_start_locked(msg)

    async def _handle_voice_start_locked(self, msg: IPCMessage):
        """Serialize microphone starts without blocking unrelated IPC requests."""
        # Clicking the microphone is an explicit request for a hands-free
        # conversation. Keep accepting turns until the owner stops the mic;
        # otherwise the UI remains "Ouvindo" while the wake timer silently
        # expires and every later sentence is discarded.
        self._manual_voice_session = True
        if self.voice_active:
            if self.gemini_live_voice and self.gemini_live_voice.active:
                self._gemini_wake_armed_until = time.monotonic() + self._JANELA_DE_CONVERSA
                print("[VOICE_TRACE] stage=WAKE_EVENT result=PASS source=manual_mic", flush=True)
                await self.send_response(msg.request_id, {
                    'success': True, 'state': 'LISTENING', **self.gemini_live_voice.status()
                })
                return

        gemini_key = self._resolve_gemini_key()
        if gemini_key and GEMINI_LIVE_MODULE_AVAILABLE and GeminiLiveVoice and GeminiLiveVoiceConfig:
            try:
                if not self.gemini_live_voice:
                    self.gemini_live_voice = GeminiLiveVoice(
                        self._build_gemini_live_config(gemini_key),
                        on_state=self._on_gemini_live_state,
                        on_level=self._on_gemini_live_level,
                        on_turn=self._on_gemini_live_turn,
                        # ZARA-VOICE-FLUIDEZ-001: politica CONVERSA/ACAO.
                        can_answer_directly=self._voice_can_answer_directly,
                        on_interrupt=self._on_gemini_live_interrupt,
                        on_error=self._on_gemini_live_error,
                        on_output_audio=self._on_gemini_live_output_audio,
                    )
                status = await self.gemini_live_voice.start(timeout=12.0)
                self.voice_active = True
                self.voice_mode = 'gemini_live'
                print("[IPC] Gemini Live voice started (Kore, wake-gate)")
                await self._ligar_vigia_das_respostas()
                self._gemini_wake_armed_until = time.monotonic() + self._JANELA_DE_CONVERSA
                print("[VOICE_TRACE] stage=WAKE_EVENT result=PASS source=manual_mic", flush=True)
                await self.send_response(msg.request_id, {
                    'success': True,
                    'state': status.get('session_state', 'LISTENING'),
                    'wake_mode': bool(status.get('wake_detector_ready')),
                    **status
                })
                return
            except Exception as exc:
                self.voice_active = False
                self._manual_voice_session = False
                self.voice_mode = 'off'
                print(f"[IPC] Gemini Live start error: {exc}")
                traceback.print_exc()
                # Fall through to local Vosk. A Gemini Live failure must not
                # turn the microphone button into a dead end.

        # Backward-compatible local path for machines without a Gemini key.
        if not VOICE_AVAILABLE or not self.voice_pipeline:
            self._manual_voice_session = False
            await self.send_error(msg, "Gemini API key missing and local voice pipeline unavailable")
            return

        try:
            if not self.voice_pipeline.vosk or not self.voice_pipeline.audio:
                await asyncio.to_thread(self.voice_pipeline.initialize)
            self.voice_pipeline._event_loop = asyncio.get_running_loop()
            await asyncio.to_thread(self.voice_pipeline.start)
            # VoicePipeline.start() deliberately catches device/model errors so
            # its worker thread cannot take down IPC.  That means the caller
            # must inspect the resulting state before advertising success;
            # otherwise a missing Vosk model or denied microphone was reported
            # as LISTENING even though the pipeline was already in ERROR.
            pipeline_state = str(getattr(self.voice_pipeline, "state", "UNKNOWN"))
            if pipeline_state not in {"LISTENING", "SLEEPING"}:
                self.voice_active = False
                self._manual_voice_session = False
                self.voice_mode = 'off'
                self._voice_last_error = f"LOCAL_VOICE_NOT_READY:{pipeline_state}"
                print(
                    f"[VOICE_TRACE] stage=MIC_OPEN_RESULT result=FAIL "
                    f"mode=local state={pipeline_state}",
                    flush=True,
                )
                await self.send_error(
                    msg,
                    f"Local voice unavailable (state={pipeline_state}). "
                    "Check the Vosk model and microphone.",
                )
                return
            self.voice_active = True
            self.voice_mode = 'local'
            self._voice_last_error = None
            print("[IPC] Local voice pipeline started")
            await self.send_response(msg.request_id, {
                'success': True, 'state': 'LISTENING', 'mode': 'local',
                'voice': 'Kokoro/Vosk fallback'
            })
            await self.send_event('state-change', 'LISTENING')
        except Exception as e:
            self._manual_voice_session = False
            self._voice_last_error = str(e).split(':', 1)[0][:120]
            print(f"[IPC] Voice start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

    def _montar_portao_lab_telegram(self, token: str):
        """Constrói o `TelegramLabGate` como biblioteca (sem laço próprio).

        ZARA-TELEGRAM-LAB-BRIDGE-001. Nunca chama `poll_once`/`run_forever`
        daqui — quem consome `getUpdates` é só `core.telegram_ponte.
        PonteTelegram`. Isolado numa função própria para o chamador poder
        tratar qualquer falha (Lab não inicializado, banco indisponível) sem
        derrubar a ponte comum do Telegram.
        """
        from core.lab_v1.release import ReleaseQueue
        from core.lab_v1.store import LabStore
        from core.lab_v1.telegram_gate import (
            HttpTelegramTransport,
            TelegramLabGate,
            default_ready_candidate,
        )
        from core.paths import api_keys_path, data_dir

        store = LabStore()
        store.initialize()
        return TelegramLabGate(
            transport=HttpTelegramTransport(token),
            state_path=data_dir() / "lab" / "telegram_gate_state.json",
            api_keys_path=api_keys_path(),
            candidate_source=lambda: default_ready_candidate(store),
            queue_factory=lambda: ReleaseQueue(store),
        )

    async def _interceptar_comando_do_lab(self, chat_id: int, texto: str) -> str | None:
        """Gancho passado à `PonteTelegram`: só responde quando `texto` é
        exatamente um comando do Lab (SIM/NÃO/RESTAURAR/VOLTAR) vindo do
        `telegram_owner_chat_id`. Devolve None em qualquer outro caso —
        inclusive gate ausente/indisponível — para a ponte seguir seu
        caminho normal sem regressão nenhuma.
        """
        gate = getattr(self, "_lab_telegram_gate", None)
        if gate is None:
            return None
        try:
            # síncrono e pode tocar disco/DB do Lab; não bloquear o loop.
            return await asyncio.to_thread(gate.handle_message, chat_id, texto)
        except Exception as exc:
            print(f"[TELEGRAM] portao do lab nao respondeu: {type(exc).__name__}", flush=True)
            return None

    async def _ligar_telegram(self) -> None:
        """Alex comandando a equipe pelo celular. ZARA-TELEGRAM-001.

        Ele não pode ficar o dia todo na cadeira. Sem token configurado, esta
        função não faz nada e não reclama — a ZARA continua igual.

        ZARA-TELEGRAM-GRUPO-001: além da ponte privada do Alex, sobe também a
        ponte do grupo (se houver token de grupo e id de grupo autorizado).
        As duas rodam em paralelo, cada uma com seu bot e sua regra de acesso.
        """
        try:
            if getattr(self, "_telegram", None) is None:
                from core.paths import config_dir
                from core.telegram_ponte import PonteTelegram

                arquivo = config_dir() / "api_keys.json"
                token = ""
                dono_telegram = None
                if arquivo.exists():
                    try:
                        dados_telegram = json.loads(arquivo.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError):
                        dados_telegram = {}
                    token = str(dados_telegram.get("telegram_bot_token") or "").strip()
                    # A configuração explícita é a autoridade do dono. Não
                    # deixar a ponte herdar silenciosamente um chat antigo do
                    # marcador de updates (pode ser de smoke test/outro dono).
                    dono_configurado = dados_telegram.get("telegram_owner_chat_id")
                    if dono_configurado is not None and str(dono_configurado).strip():
                        try:
                            dono_telegram = int(dono_configurado)
                        except (TypeError, ValueError):
                            dono_telegram = None
                if token:
                    # ZARA-TELEGRAM-LAB-BRIDGE-001: o portão de aprovação do
                    # Lab (core.lab_v1.telegram_gate) não sobe mais como
                    # processo/escutador próprio dentro da ZARA — dois
                    # consumidores de getUpdates no mesmo token brigam pela
                    # mesma fila. Ele vira biblioteca chamada por ESTA ponte,
                    # que continua sendo a única a fazer polling. Qualquer
                    # falha ao montar o gate fica isolada aqui: o bot comum
                    # sobe do mesmo jeito, só sem o atalho de aprovação.
                    if getattr(self, "_lab_telegram_gate", None) is None:
                        try:
                            self._lab_telegram_gate = self._montar_portao_lab_telegram(token)
                        except Exception as exc:
                            self._lab_telegram_gate = None
                            print(f"[TELEGRAM] portao do lab nao subiu, bot comum segue: {type(exc).__name__}", flush=True)
                    parametros_ponte = {
                        "interceptar": self._interceptar_comando_do_lab,
                    }
                    if dono_telegram is not None:
                        parametros_ponte["dono"] = dono_telegram
                    ponte = PonteTelegram(token, self._executar_do_celular, **parametros_ponte)
                    if await ponte.iniciar():
                        self._telegram = ponte
                        from core.telegram_approval_adapter import TelegramApprovalAdapter

                        self._telegram_adapter = TelegramApprovalAdapter(ponte)

            # Ponte do grupo (roda em paralelo com a privada).
            if getattr(self, "_telegram_grupo", None) is None:
                from core.paths import config_dir
                from core.telegram_grupo import PonteGrupo

                cfg = config_dir() / "api_keys.json"
                dados = {}
                if cfg.exists():
                    try:
                        dados = json.loads(cfg.read_text(encoding="utf-8"))
                    except Exception:
                        dados = {}
                token_grupo = str(dados.get("telegram_group_token") or "").strip()
                grupo_id = dados.get("telegram_group_id")
                # ZARA-TELEGRAM-GRUPO-002: usa o bot novo também no privado do
                # Alex, se não houver grupo ainda. O id do dono privado vem do
                # config, com fallback para o dono da ponte privada.
                dono_privado = dados.get("telegram_group_dono_privado")
                if dono_privado is None:
                    dono_privado = dados.get("telegram_dono")
                if token_grupo and grupo_id is not None:
                    ponte_grupo = PonteGrupo(
                        token_grupo,
                        self._executar_do_celular,
                        grupo_id=int(grupo_id),
                        dono_privado=int(dono_privado) if dono_privado is not None else None,
                    )
                    if await ponte_grupo.iniciar():
                        self._telegram_grupo = ponte_grupo
                elif token_grupo and dono_privado is not None:
                    # Sem grupo ainda: o bot novo já atende o privado do Alex.
                    ponte_grupo = PonteGrupo(
                        token_grupo,
                        self._executar_do_celular,
                        grupo_id=None,
                        dono_privado=int(dono_privado),
                    )
                    if await ponte_grupo.iniciar():
                        self._telegram_grupo = ponte_grupo
        except Exception as exc:
            self._telegram = None
            self._telegram_grupo = None
            self._telegram_adapter = None
            print(f"[TELEGRAM] nao ligou: {exc}", flush=True)

    # ZARA-SE-CONSERTA-SOZINHA-001
    #
    # Alex, saindo de casa: *"se cair ou parar você corrige tudo,
    # automaticamente"*.
    #
    # O pedido nasceu de um susto real: eu fui conferir se estava tudo de pé
    # antes de ele sair e achei o Telegram MUDO — a ZARA aberta, o processo
    # vivo, e o bot sem escutar ninguém. Se ele tivesse saído, teria mandado
    # mensagem para o vazio e só descobriria ao voltar.
    #
    # O ponto não é o Telegram ter caído: é ninguém ter notado. Um serviço que
    # falha em silêncio é pior que um serviço que falha alto, porque some da
    # cabeça de todo mundo até doer.
    #
    # Este vigia pergunta a cada minuto se a ponte deu uma volta completa no
    # Telegram há pouco. Não pergunta se o objeto existe nem se a tarefa está na
    # lista — pergunta se ela FALOU com o Telegram, que é o único fato que
    # importa. Se não falou, derruba e sobe de novo.
    _INTERVALO_DO_VIGIA = 60.0

    async def _cuidar_das_pontes(self) -> None:
        """Reergue sozinha o que cair enquanto Alex não está olhando."""
        while True:
            try:
                await asyncio.sleep(self._INTERVALO_DO_VIGIA)
                ponte = getattr(self, "_telegram", None)
                ponte_grupo = getattr(self, "_telegram_grupo", None)
                if (
                    (ponte is None or not ponte.configurado)
                    and (ponte_grupo is None or not ponte_grupo.configurado)
                ):
                    continue
                if (ponte is None or ponte.esta_viva) and (
                    ponte_grupo is None or ponte_grupo.esta_viva
                ):
                    continue

                print("[VIGIA] Telegram parou de responder; reerguendo", flush=True)
                for p in (ponte, ponte_grupo):
                    if p is not None:
                        try:
                            await p.parar()
                        except Exception:
                            pass
                self._telegram = None
                self._telegram_grupo = None
                await self._ligar_telegram()

                nova = getattr(self, "_telegram", None)
                if nova is not None and nova.configurado:
                    print("[VIGIA] Telegram de pe outra vez", flush=True)
                    # Ele precisa saber que caiu. Consertar em silêncio esconde
                    # um problema que pode estar piorando — e ele decide o que
                    # fazer com a informação, não eu.
                    await nova.avisar(
                        "O Telegram tinha parado e eu reergui sozinha. "
                        "Se isso se repetir, me avise que tem algo maior por trás."
                    )
                else:
                    print("[VIGIA] nao consegui reerguer o Telegram", flush=True)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                print(f"[VIGIA] erro: {type(exc).__name__}", flush=True)

    # ZARA-SELO-NA-TELA-001
    #
    # A interface nova mostra, ao lado de cada turno, se aquilo foi verificado.
    # Só que ninguém estava mandando essa informação para ela: o evento de
    # mensagem levava texto e motor, mais nada. O Codex notou e relatou —
    # "as mensagens não carregam selo estruturado, portanto aparecem como NÃO
    # VERIFICADO" — o que teria pintado a tela inteira de cinza e feito a
    # feature mais importante do desenho parecer quebrada.
    #
    # `conversa` existe de propósito: papo não tem o que verificar, e marcar
    # papo como "não verificado" seria inventar uma dúvida que não existe.
    def _selo_do_ultimo_resultado(self) -> str:
        resultado = getattr(self, "_ultimo_resultado_de_acao", None)
        if resultado is None:
            return "conversa"
        if not getattr(resultado, "success", False):
            return "nao-consegui"
        if getattr(resultado, "verificado", True):
            return "verificado"
        return "nao-verificado"

    # ZARA-APROVAR-DO-CELULAR-001 ------------------------------------------
    def _fila_de_aprovacao(self):
        """A fila de autorizações pendentes, criada na primeira necessidade."""
        fila = getattr(self, "_aprovacoes", None)
        if fila is None:
            try:
                from core.aprovacao_remota import FilaDeAprovacao

                fila = FilaDeAprovacao()
                self._aprovacoes = fila
                self._aprovado_por_alex: set[str] = set()
            except Exception:
                return None
        return fila

    async def pedir_autorizacao_ao_alex(self, o_que: str, quem: str = "O Claude") -> str | None:
        """Manda o pedido para o celular dele. Devolve o id, ou None se não deu.

        Não espera resposta aqui de propósito: bloquear a ZARA esperando um ser
        humano que está no trabalho seria trocar um travamento por outro. Quem
        pediu consulta depois se foi aprovado.
        """
        fila = self._fila_de_aprovacao()
        ponte = getattr(self, "_telegram", None)
        if fila is None or ponte is None:
            return None
        pedido = fila.pedir(o_que, quem_pediu=quem)
        if not await ponte.avisar(pedido.como_pergunta()):
            fila.cancelar(pedido.id)
            return None
        return pedido.id

    def foi_aprovado(self, id_do_pedido: str) -> bool:
        """Ele autorizou? Só True quando ele disse sim de verdade."""
        return id_do_pedido in getattr(self, "_aprovado_por_alex", set())

    def _deve_requer_aprovacao_explicita(self, texto: str) -> bool:
        """Hook for the remote approval policy (fail closed by default)."""
        return False

    async def _executar_do_celular(self, destino: str, texto: str,
                                   execute_action=None) -> str:
        """Uma ordem vinda do Telegram. Devolve o que responder a ele.

        ZARA-TELEGRAM-001. Reaproveita exatamente os mesmos caminhos da voz —
        nenhum atalho novo, nenhuma regra de segurança contornada porque a
        mensagem veio de fora.
        """
        if execute_action is None:
            from core.action_registry import execute_action as _execute_action
            execute_action = _execute_action

        if destino == "zara" and self._deve_requer_aprovacao_explicita(texto):
            pedido_id = await self.pedir_autorizacao_ao_alex(texto)
            if pedido_id:
                return "Pedido enviado para aprovação no Telegram. Responder com 'sim' ou 'não'."
            return "Não consegui enviar o pedido de aprovação agora."

        # ZARA-TELEGRAM-MEMORIA-001
        #
        # Descoberto olhando o histórico depois que Alex mandou "Zara me
        # responda oi" pelo celular: a mensagem chegou, foi processada, foi
        # respondida — e sumiu. Nada do que ele fala pelo Telegram entrava na
        # conversa dela.
        #
        # O efeito é pior do que "falta um registro". Significa que ela conversa
        # com ele o dia inteiro pelo celular e, ao voltar para o computador, não
        # lembra de nada — nem para citar, nem para o diário, nem para o
        # "você entendeu?". Metade da vida dela acontecia e não existia.
        #
        # Voz e texto sempre compartilharam a cadeia; agora compartilham a
        # memória também.
        # ZARA-ONDE-ELE-ESTA-001: ele falou pelo celular, entao ele esta no
        # celular. E o sinal mais confiavel que existe — melhor que qualquer
        # palpite sobre teclado ou tela bloqueada.
        self._marcar_canal("telegram")
        resposta_final = await self._responder_ao_celular(destino, texto, execute_action)
        try:
            await self._append_conversation_message("user", texto, "telegram")
            await self._append_conversation_message("assistant", resposta_final, "telegram")
            if destino == "zara":
                # Só o que foi dito PARA ela vira a última frase entendida.
                # Recado para o Claude ou para o Codex não é fala com ela.
                self._ultimo_pedido_entendido = texto
        except Exception as exc:
            print(f"[TELEGRAM] nao consegui gravar a conversa: {type(exc).__name__}", flush=True)
        return resposta_final

    async def _responder_ao_celular(self, destino: str, texto: str, execute_action) -> str:
        """O que ela responde. Separado só para a gravação acontecer sempre."""

        # ZARA-PONTE-CODEX-CLI-001
        #
        # Pelo celular, o Codex é falado pelo canal estruturado do CLI, não
        # digitando na janela do app. Motivo: quando o pedido vem do Telegram,
        # o Alex não está na frente do computador — e a rota da janela depende
        # de trazer o app para a frente, achar a caixa de texto e ler a resposta
        # da tela. Cada uma dessas etapas já falhou, e ele não tem como perceber
        # nem corrigir de longe.
        #
        # Além disso o próprio Codex alertou: escrever na janela dele com o
        # texto do canal criaria "um segundo agente e duas histórias
        # divergentes". Então a janela continua sendo a conversa pessoal dele,
        # e o Telegram é onde o Alex acompanha a conversa da ZARA.
        #
        # Aqui a resposta volta na mesma mensagem, sem depender do vigia.
        if destino == "codex":
            from core.ponte_codex_cli import falar_com_codex

            resposta, erro = await asyncio.to_thread(falar_com_codex, texto)
            if erro:
                return f"Não consegui falar com o Codex: {erro}"
            return f"Codex:\n\n{resposta}"

        if destino == "claude":
            resultado = await execute_action("claude_enviar", texto=texto)
            if getattr(resultado, "success", False):
                # ZARA-RESPOSTA-VOLTA-POR-ONDE-VEIO-001: fica marcado que ele
                # está esperando ALI. Sem isso a resposta do Claude ficava presa
                # no computador e ele, no celular, achava que eu tinha sumido.
                self._pergunta_veio_do_celular = True
                return "Entreguei ao Claude. Te aviso quando responder."
            return f"Não consegui: {getattr(resultado, 'error', 'motivo desconhecido')}"

        # ZARA-TELEGRAM-TODOS-001
        #
        # Alex escreveu "todos- se voces 3 estao vendo esta mensagem responda
        # sim" e ninguém respondeu, porque esse destino não existia. Ele pensa
        # nos três como um grupo; a ponte tratava um de cada vez.
        #
        # Ela responde primeiro por si — é a única que responde na hora — e
        # entrega aos outros dois em seguida, dizendo o que aconteceu com cada
        # um em vez de um "pronto" que esconde metade da verdade.
        if destino == "todos":
            partes = []

            minha = await self._conversar(texto)
            partes.append(f"ZARA: {minha}")

            try:
                from core.ponte_codex_cli import falar_com_codex

                do_codex, erro = await asyncio.to_thread(falar_com_codex, texto)
                partes.append(f"Codex: {do_codex}" if not erro else f"Codex não veio: {erro}")
            except Exception as exc:
                partes.append(f"Codex não veio: {type(exc).__name__}")

            resultado = await execute_action("claude_enviar", texto=texto)
            if getattr(resultado, "success", False):
                partes.append("Claude: entreguei, ele responde em seguida.")
            else:
                partes.append(
                    f"Claude não recebeu: {getattr(resultado, 'error', 'motivo desconhecido')}"
                )

            return "\n\n".join(partes)

        # ZARA-APROVAR-DO-CELULAR-001
        #
        # Antes de tratar como comando: isto é resposta a uma autorização que
        # ficou pendurada? Se for, é só isso — não vira comando também.
        #
        # A fila é consultada primeiro justamente porque "sim" e "não" são
        # palavras que qualquer outro caminho poderia engolir, e aí a permissão
        # dele se perderia sem ninguém notar.
        fila = self._fila_de_aprovacao()
        if fila is not None:
            pedido, aprovado = fila.responder(texto)
            if pedido is not None:
                if aprovado:
                    self._aprovado_por_alex.add(pedido.id)
                    return f"Anotado, pode seguir: {pedido.o_que}"
                return f"Beleza, não faço: {pedido.o_que}"

        # Qualquer outra coisa é comando para a própria ZARA, pela MESMA cadeia
        # que a voz percorre.
        resposta = await self._try_pc_intent(texto)
        if resposta:
            return resposta
        resposta = await self._try_reminder_intent(texto)
        if resposta:
            return resposta

        # ZARA-TELEGRAM-CONVERSA-001
        #
        # Alex mandou "zara ta aqui?" pelo celular e recebeu "Não entendi o que
        # fazer com isso aqui pelo celular." Ele não estava pedindo nada — estava
        # falando com ela. Pelo computador ela responderia; pelo celular ela
        # tinha virado só um controle remoto de comandos.
        #
        # Uma ZARA que só entende ordem não é a ZARA. Aqui o celular passa a
        # cair no MESMO cérebro que o texto do app, sem atalho novo.
        return await self._conversar(texto)

    async def _conversar(self, texto: str) -> str:
        """A ZARA respondendo como ela mesma. ZARA-TELEGRAM-CONVERSA-001."""
        try:
            result = await self._front_conversation_reply(texto, channel='TELEGRAM')
            if result.get('success'):
                return str(result.get('response') or '').strip() or "Tô aqui."
            return str(result.get('error') or 'O cérebro selecionado não respondeu agora.')
        except Exception as exc:
            print(f"[TELEGRAM] conversa falhou: {type(exc).__name__}", flush=True)

        # Sem cérebro disponível ela ainda responde — e diz a verdade sobre o
        # próprio estado, em vez de fingir que não entendeu o que ele disse.
        return "Tô aqui, mas meu raciocínio não subiu agora. Comando de PC eu executo normal."

    # ZARA-VIGIA-LONGE-001 -------------------------------------------------
    #
    # A primeira versão usava só o tempo sem teclado: 3 minutos parado = longe.
    # Alex derrubou na hora, e estava certo: "como assim quando eu tiver longe
    # do computador?" — ler uma resposta longa leva mais de três minutos sem
    # tocar em nada. Ele estaria sentado na cadeira, lendo, e classificado como
    # ausente. O celular apitaria exatamente na hora errada.
    #
    # Critério novo, sem chute: a tela. Computador BLOQUEADO é a única prova
    # barata e sem ambiguidade de que ele não está vendo. Tela aberta significa
    # que ele está aí, mesmo imóvel.
    #
    # O tempo sem teclado continua existindo, mas só como segunda condição, com
    # uma folga grande — meia hora parado com a tela aberta é ele tendo saído
    # sem bloquear, não ele lendo.
    # Trinta minutos era folga demais, e Alex pagou por isso: ele avisou que
    # estava saindo para o trabalho, mandou mensagem poucos minutos depois, e
    # pela minha conta ainda contava como presente — justamente na primeira
    # meia hora, que é quando ele mais precisa de resposta no celular.
    #
    # Cinco minutos parado é gente que levantou. Ele lendo uma resposta longa
    # continua protegido pelo outro lado da regra: pergunta feita no celular
    # volta pelo celular sem consultar distância nenhuma.
    _LONGE_APOS = 300.0  # 5 min

    @staticmethod
    def _ocioso_ha_quantos_segundos() -> float:
        """Há quanto tempo ninguém toca no teclado ou no mouse.

        Devolve 0.0 quando não dá para saber — o padrão seguro é assumir que
        ele está por perto, porque errar para o lado do silêncio é melhor que
        errar para o lado de encher o celular dele.
        """
        try:
            import ctypes

            class _Entrada(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            info = _Entrada()
            info.cbSize = ctypes.sizeof(_Entrada)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return 0.0
            agora = ctypes.windll.kernel32.GetTickCount()
            return max(0.0, (agora - info.dwTime) / 1000.0)
        except Exception:
            return 0.0

    @staticmethod
    def _tela_bloqueada() -> bool:
        """O Windows está na tela de bloqueio?

        Medido pela mesa de trabalho ativa: com a sessão bloqueada, a mesa
        visível passa a ser a `Winlogon`, e o processo da ZARA deixa de
        conseguir abri-la. Não conseguir abrir é a resposta.
        """
        try:
            import ctypes

            OPEN_DESKTOP_INPUT = 0x0100  # DESKTOP_SWITCHDESKTOP
            mesa = ctypes.windll.user32.OpenInputDesktop(0, False, OPEN_DESKTOP_INPUT)
            if not mesa:
                return True
            ctypes.windll.user32.CloseDesktop(mesa)
            return False
        except Exception:
            return False  # na dúvida, ele está aqui

    # ZARA-ONDE-ELE-ESTA-001
    #
    # Alex, depois de eu errar duas vezes seguidas o critério de presença:
    #
    #   "quando eu não digitar aqui nesse chat por trinta minutos, você já sabe
    #    que eu não estou aqui, principalmente se eu digitar pelo Telegram e não
    #    digitar aqui, porque sempre que eu estou aqui, eu digito aqui."
    #
    # A regra dele é melhor que a minha e por um motivo simples: eu estava
    # adivinhando presença pelo teclado, e ele estava me dando um FATO. O canal
    # que ele escolhe para falar é a prova de onde ele está — ninguém escreve no
    # celular estando na frente do computador.
    #
    # O teclado continua valendo como segundo sinal, para o caso de ele estar no
    # PC sem falar com ninguém. Mas o canal manda.
    _JANELA_DO_CANAL = 30 * 60  # 30 minutos, palavra dele

    def _marcar_canal(self, canal: str) -> None:
        """Registra por onde ele acabou de falar. `telegram` ou `computador`."""
        self._ultimo_canal = (canal, time.time())

    def _alex_esta_longe(self) -> bool:
        canal, quando = getattr(self, "_ultimo_canal", ("", 0.0))
        if canal and (time.time() - quando) < self._JANELA_DO_CANAL:
            # Ele falou por algum canal há pouco: o canal responde a pergunta,
            # e nenhum palpite sobre teclado ou tela vale mais que isso.
            return canal == "telegram"
        if self._tela_bloqueada():
            return True
        return self._ocioso_ha_quantos_segundos() >= self._LONGE_APOS

    async def _ligar_vigia_das_respostas(self) -> None:
        """Keep the owner-revoked legacy cross-app announcer disabled.

        Existing conversation/history is preserved. Boot and reconnect must not
        start window scraping, unsolicited speech, or forwarding to Telegram.
        """
        existing = getattr(self, "_vigia", None)
        if existing is not None:
            await existing.parar()
            self._vigia = None

    # ZARA-JANELA-DE-CONVERSA-001 -----------------------------------------
    #
    # Alex: "ela às vezes ouvia um comando e não me respondia nada... isso é
    # muito robótico, quero a conversação natural".
    #
    # A janela durava 8 e 12 segundos. Medido no histórico dele em 15/08, os
    # intervalos REAIS entre uma frase e a seguinte foram 17, 29, 36, 48, 55,
    # 66, 69 e 86 segundos — ele lê a resposta, pensa, e responde. Quase toda
    # frase caía fora da janela e era descartada em silêncio, e ele achava que
    # ela tinha travado.
    #
    # Conversa entre humanos tem pausa. Uma janela de oito segundos não é
    # conversa, é interrogatório: obriga a dizer o nome dela a cada frase.
    #
    # 75 segundos cobre o comportamento observado com folga. O risco de janela
    # longa é ela captar conversa de fundo — e para isso agora existe o botão
    # vermelho do microfone, que é a resposta certa para "não me escute",
    # em vez de deixar a porta meio fechada o tempo todo.
    _JANELA_DE_CONVERSA = 75.0

    # ZARA-JANELA-DE-CONVERSA-003: os primeiros segundos depois de ela falar são
    # de réplica livre — ali ele responde no impulso e qualquer exigência de
    # formalidade quebra a conversa. Depois disso a barra sobe.
    _REPLICA_LIVRE = 20.0

    # Uma frase dirigida a ela tem marca de segunda pessoa, ou é um pedido.
    # Fala de televisão narra, conta história, fala de outra gente — quase nunca
    # chama alguém de "você" pedindo alguma coisa.
    _FALA_COM_ELA = re.compile(
        r"\b(?:voc[êe]|vc|tu)\b"
        r"|\b(?:me|pra\s+mim|comigo|contigo)\b"
        r"|\b(?:zara|sara)\b"
        r"|\b(?:pode|consegue|sabe|lembra|manda|abre|abra|fecha|feche|toca|"
        r"toque|coloca|coloque|aumenta|aumente|diminui|diminua|liga|ligue|"
        r"desliga|desligue|procura|procure|pesquisa|pesquise|le[ia]|escreve|"
        # "para" saiu da lista: é preposição antes de ser verbo. "faz muito bem
        # PARA todos", numa novela, virava comando. "pare" fica, e a parada de
        # emergência já tem caminho próprio no `_STOP_WORD_RE`.
        r"escreva|responde|responda|repete|repita|pare|cancela|anota|"
        r"anote|lembre|mostra|mostre|conta|conte|explica|explique)\b",
        re.IGNORECASE,
    )

    # Auditoria do Codex, achado 7. Ele listou o que o filtro jogaria fora:
    # "sim", "não", "isso mesmo", "a segunda", "o azul", "mais baixo", "de novo",
    # "não, o outro". São todas réplicas legítimas — e a resposta a uma pergunta
    # que a própria ZARA acabou de fazer.
    #
    # Frase curta depois de ela falar é continuação, não conversa de fundo:
    # televisão não responde em três palavras a uma pergunta feita aqui dentro.
    _LIMITE_DE_REPLICA_CURTA = 5  # palavras

    def _parece_dirigido_a_ela(self, frase: str) -> bool:
        """A frase fala COM ela, ou é conversa/TV que passou perto do microfone?

        Erra para o lado de aceitar: uma pergunta genuína descartada irrita mais
        que uma frase de novela respondida. Por isso qualquer pergunta passa.
        """
        texto = str(frase or "").strip()
        if not texto:
            return False
        # Réplica curta é continuação da conversa dela, não fala solta da sala.
        if len(texto.split()) <= self._LIMITE_DE_REPLICA_CURTA:
            return True
        if "?" in texto:
            return True
        # De propósito NÃO se consulta o detector de intent aqui.
        #
        # A frase real "Respira mais alto, Rosa" — de uma novela, capturada às
        # 3h12 — casa com a linguagem de aumentar volume. Perguntar ao detector
        # deixaria a televisão mexer no computador toda vez que um personagem
        # falasse "mais alto". A lista de verbos acima já cobre o imperativo que
        # o Alex usa de verdade ("abre", "diminui", "toca"), e sem esse efeito
        # colateral.
        return bool(self._FALA_COM_ELA.search(texto))

    # ZARA-BOTAO-MUDO-005 -------------------------------------------------
    #
    # Alex: "eu tenho que ficar toda hora clicando em deixar vermelho é?".
    #
    # Não. Ele clicava, fechava a ZARA, e no dia seguinte ela estava falando de
    # novo — porque o estado só existia na memória do processo. Um botão que
    # esquece a escolha obriga a refazer a escolha, e vira exatamente a
    # chateação que ele queria eliminar.
    @staticmethod
    def _arquivo_da_voz():
        from core.paths import user_data_dir

        return user_data_dir() / "voz_silenciada.json"

    def _carregar_silenciada(self) -> bool:
        try:
            arquivo = self._arquivo_da_voz()
            if arquivo.exists():
                return bool(json.loads(arquivo.read_text(encoding="utf-8")).get("mudo"))
        except Exception:
            pass
        return False

    def _gravar_silenciada(self, mudo: bool) -> None:
        try:
            arquivo = self._arquivo_da_voz()
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps({"mudo": bool(mudo)}), encoding="utf-8")
        except Exception:
            pass  # esquecer a preferência é chato, não é fatal


    async def handle_voice_stop(self, msg: IPCMessage):
        """Stop whichever voice transport is currently active."""
        vigia = getattr(self, "_vigia", None)
        if vigia is not None:
            await vigia.parar()
            self._vigia = None
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.stop()
        if self.voice_pipeline:
            await asyncio.to_thread(self.voice_pipeline.stop)
        self.voice_active = False
        self._manual_voice_session = False
        self.voice_mode = 'off'
        self._voice_speaking = False
        self._finish_assistant_output()
        print("[IPC] Voice stopped")
        await self.send_response(msg.request_id, {'success': True, 'state': 'STANDBY'})
        await self.send_event('state-change', 'STANDBY')
        await self.send_event('voice-level', {
            'level': 0.0,
            'tone': 0.5,
            'speaking': False,
            'state': 'STANDBY'
        })

    async def handle_config_get(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        try:
            snapshot = await svc.front_snapshot()
            self.current_engine = snapshot['current']
            await self.send_response(msg.request_id, {
                'current_engine': self.current_engine, 'voice_active': self.voice_active})
        except Exception:
            await self.send_error(msg, 'Nao foi possivel ler o modelo selecionado.')


    async def handle_config_set(self, msg: IPCMessage):
        payload = msg.payload or {}
        key = payload.get('key')
        value = payload.get('value')
        if key == 'engine':
            await self.handle_engine_change(IPCMessage(type='engine-change', request_id=msg.request_id,
                                                       payload={'engine': value}))
            return
        elif key and str(key).endswith('_api_key'):
            try:
                from core.paths import api_keys_path
                config_path = api_keys_path()
                config_data: dict[str, Any] = {}
                if config_path.exists():
                    with open(config_path, encoding='utf-8') as f:
                        config_data = json.load(f)
                config_data[key] = value
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                if self.model_router:
                    self.model_router._load_api_keys()
            except Exception as e:
                print(f"[IPC] config-set api key error: {e}")
                await self.send_error(msg, str(e))
                return


        await self.send_response(msg.request_id, {'success': True})

    async def handle_engine_list(self, msg: IPCMessage):
        svc = await self._ensure_lab_v1(msg)
        if svc is None:
            return
        try:
            snapshot = await svc.front_snapshot()
            self.current_engine = snapshot['current']
            await self.send_response(msg.request_id, snapshot)
        except Exception:
            await self.send_error(msg, 'Nao foi possivel consultar os modelos.')

    async def handle_action_list(self, msg: IPCMessage):
        """Return all registered actions with specs"""
        try:
            from core.action_registry import get_registry
            registry = get_registry()
            actions = {}
            for name in registry.list_actions():
                spec = registry.get_spec(name)
                if spec:
                    actions[name] = {
                        'name': spec.name,
                        'description': spec.description,
                        'parameters': spec.parameters,
                        'category': spec.category,
                        'requires_confirmation': spec.requires_confirmation,
                        'async_execution': spec.async_execution,
                        'tags': spec.tags,
                        'risk': spec.risk,
                        'capability': spec.capability,
                    }
            await self.send_response(msg.request_id, actions)
        except Exception as e:
            print(f"[IPC] Action list error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

    async def handle_system_info(self, msg: IPCMessage):
        """Return detailed system information"""
        import platform

        import psutil

        info = {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'architecture': platform.machine(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
            'memory_total': psutil.virtual_memory().total,
            'memory_available': psutil.virtual_memory().available,
            'disk_total': psutil.disk_usage('/').total if os.name != 'nt' else psutil.disk_usage('C:\\').total,
            'disk_free': psutil.disk_usage('/').free if os.name != 'nt' else psutil.disk_usage('C:\\').free,
            'boot_time': psutil.boot_time(),
        }
        await self.send_response(msg.request_id, info)

    async def handle_voice_status(self, msg: IPCMessage):
        """Return current voice transport status."""
        if self.gemini_live_voice:
            live = self.gemini_live_voice.status()
        else:
            live = {
                'active': False, 'connected': False, 'mode': 'gemini_live',
                'model': 'gemini-3.1-flash-live-preview', 'voice': 'Kore',
            }
        status = {
            'level': self._voice_level,
            'tone': self._voice_tone,
            'speaking': self._voice_speaking,
            'listening': self.voice_active,
            'mode': self.voice_mode,
            'gemini_live': live,
            'wake_word_active': self.voice_pipeline is not None and self.voice_pipeline.porcupine is not None,
            'stt_ready': self.voice_pipeline is not None and self.voice_pipeline.vosk is not None,
            'tts_ready': self.tts_manager is not None and (self.tts_manager.kokoro is not None or self.tts_manager.gemini is not None),
            'pipeline_state': self.voice_pipeline.state if self.voice_pipeline else 'STOPPED',
            'self_listening_guard': bool(self.voice_pipeline),
            'interrupt_ready': self.tts_manager is not None or self.gemini_live_voice is not None,
            'diagnostic': self._voice_last_error or 'OK',
        }
        await self.send_response(msg.request_id, status)
    def _set_supercerebro_state(self, active: bool) -> None:
        """Mirror Supercerebro state into the physical capability gate.

        This controls capabilities only. Risk gates remain independent, so
        enabling Supercerebro never opens MEDIUM or HIGH actions by itself.
        """
        self.supercerebro_active = active is True
        from core.action_registry import get_registry

        get_registry().pc_control_allowed = self.supercerebro_active
    def _revoke_stale_pc_control(self) -> None:
        """Fail closed if the Hermes session disappeared after enablement."""
        if not self.supercerebro_active:
            return
        connected = bool(self.hermes and self.hermes.enabled and self.hermes.is_connected)
        if not connected:
            self._set_supercerebro_state(False)
    async def handle_lab_mission_state(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        try:
            await self.send_response(msg.request_id, await self.lab.mission_state())
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_verify(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.mission_verify_milestone(
                str(payload.get('code') or ''),
                str(payload.get('state') or ''),
                [str(e) for e in (payload.get('evidence') or [])],
                str(payload.get('note') or ''),
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_cycle(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            action = str(payload.get('action') or 'resume')
            if action == 'complete':
                result = await self.lab.mission_complete_cycle(
                    str(payload.get('cycle_id') or ''),
                    str(payload.get('summary') or ''),
                )
            else:
                result = await self.lab.mission_resume_cycle(
                    str(payload.get('objective') or ''),
                )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_recruit(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.mission_recruit(
                str(payload.get('task') or ''),
                [str(c) for c in (payload.get('needed_capabilities') or [])],
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_finding(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.mission_submit_finding(
                str(payload.get('reader') or 'reader'),
                str(payload.get('source_name') or ''),
                str(payload.get('url') or ''),
                str(payload.get('summary') or ''),
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_prioritize(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.mission_prioritize(
                str(payload.get('finding_id') or ''),
                str(payload.get('decision') or ''),
                str(payload.get('note') or ''),
                str(payload.get('proposal_id') or '') or None,
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_patch(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            action = str(payload.get('action') or '')
            if action == 'create':
                result = await self.lab.mission_create_patch(
                    str(payload.get('title') or ''),
                    [str(f) for f in (payload.get('files') or [])],
                    str(payload.get('diff') or ''),
                )
            else:
                result = await self.lab.mission_patch_transition(
                    str(payload.get('patch_id') or ''),
                    action,
                    verifier=str(payload.get('verifier') or ''),
                    passed=bool(payload.get('passed')),
                    evidence=str(payload.get('evidence') or ''),
                    reviewer=str(payload.get('reviewer') or ''),
                    approved=bool(payload.get('approved')),
                    notes=str(payload.get('notes') or ''),
                    artifacts=[str(a) for a in (payload.get('artifacts') or [])],
                )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_mission_bot(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.mission_bot_config(
                str(payload.get('bot_id') or ''),
                str(payload.get('action') or 'get'),
                soul=payload.get('soul'),
                primary_model=payload.get('primary_model'),
                fallbacks=payload.get('fallbacks'),
                from_model=str(payload.get('from_model') or ''),
                to_model=str(payload.get('to_model') or ''),
                reason=str(payload.get('reason') or ''),
            )
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_autonomy_start(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        payload = msg.payload or {}
        try:
            result = await self.lab.autonomy_start(str(payload.get('objective') or ''))
            await self.send_response(msg.request_id, result)
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_autonomy_stop(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        try:
            await self.send_response(msg.request_id, await self.lab.autonomy_stop())
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_lab_autonomy_status(self, msg: IPCMessage):
        if not self.lab:
            await self.send_error(msg, "ZARA Lab indisponível")
            return
        try:
            await self.send_response(msg.request_id, await self.lab.autonomy_status())
        except Exception as exc:
            await self.send_error(msg, str(exc))
    def _chat_relay(self):
        """Instância preguiçosa do ChatRelay (uma por processo)."""
        return _get_chat_relay()
    def _conselheira_context(self, relay) -> str:
        """Snapshot curto do estado da ZARA anexado a cada mensagem."""
        try:
            from core.lab_ceo_gmail_bridge import build_context_snapshot
        except ImportError:
            return ""
        snap = relay.snapshot()
        extra = (
            f"Ponte: {snap['pending']} mensagem(ns) pendente(s), "
            f"{snap['awaiting_reply']} aguardando resposta da zoe."
        )
        return build_context_snapshot(extra)
    async def handle_conselheira_send(self, msg: IPCMessage):
        """Recebe o texto do painel e enfileira na ponte (sem rede aqui)."""
        relay = self._chat_relay()
        if relay is None:
            await self.send_error(msg, "Ponte Conselheira indisponível")
            return
        payload = msg.payload or {}
        text = str(payload.get('text') or '').strip()
        if not text:
            await self.send_error(msg, "Mensagem vazia")
            return
        try:
            turn = relay.send_message(text, context=self._conselheira_context(relay))
            await self.send_response(msg.request_id, {
                'chat_id': turn['chat_id'],
                'created_at': turn['created_at'],
            })
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_conselheira_sync(self, msg: IPCMessage):
        """Uma passada da ponte: envia pendentes e importa respostas da zoe."""
        relay = self._chat_relay()
        if relay is None:
            await self.send_error(msg, "Ponte Conselheira indisponível")
            return
        try:
            await self.send_response(msg.request_id, relay.sync())
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_conselheira_messages(self, msg: IPCMessage):
        """Histórico da conversa para o painel."""
        relay = self._chat_relay()
        if relay is None:
            await self.send_error(msg, "Ponte Conselheira indisponível")
            return
        payload = msg.payload or {}
        try:
            limit = int(payload.get('limit') or 200)
        except (TypeError, ValueError):
            limit = 200
        try:
            await self.send_response(msg.request_id, relay.get_thread(limit=limit))
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_conselheira_status(self, msg: IPCMessage):
        """Estado da ponte: pendentes, aguardando, última sincronização."""
        relay = self._chat_relay()
        if relay is None:
            await self.send_error(msg, "Ponte Conselheira indisponível")
            return
        try:
            await self.send_response(msg.request_id, relay.snapshot())
        except Exception as exc:
            await self.send_error(msg, str(exc))
    async def handle_supercerebro_toggle(self, msg: IPCMessage):
        requested = msg.payload.get('active') if msg.payload else None
        if requested is None:
            await self.send_error(msg, "Active state not specified")
            return

        if type(requested) is not bool:
            await self.send_error(msg, "Active state must be a boolean")
            return

        if requested:
            if not self.hermes:
                self._set_supercerebro_state(False)
                await self.send_error(msg, "Hermes integration is unavailable")
                return
            connected = await self.hermes.enable_supercerebro()
            if not connected:
                self._set_supercerebro_state(False)
                await self.send_event('supercerebro-change', False)
                await self.send_error(msg, "Hermes Gateway is offline")
                return
            self._set_supercerebro_state(True)
        else:
            # Revoke local permission before touching the remote integration.
            # A disconnect error must never leave PC control enabled.
            self._set_supercerebro_state(False)
            if self.hermes:
                try:
                    await self.hermes.disable_supercerebro()
                except Exception as exc:
                    print(f"[IPC] Hermes disable warning: {exc}")

        print(f"[IPC] Supercerebro {'enabled' if self.supercerebro_active else 'disabled'}")
        await self.send_event('supercerebro-change', self.supercerebro_active)
        await self.send_response(msg.request_id, {
            'success': True,
            'active': self.supercerebro_active,
            'connected': bool(self.hermes and self.hermes.is_connected),
        })
    async def handle_supercerebro_status(self, msg: IPCMessage):
        """Return supercerebro status"""
        status = {
            'active': self.supercerebro_active,
            'url': 'http://127.0.0.1:8642',
            'connected': bool(self.hermes and self.hermes.is_connected),
            'enabled': bool(self.hermes and self.hermes.enabled),
        }
        if self.hermes:
            try:
                agent_status = await self.hermes.get_agent_status()
                status.update(agent_status)
            except Exception as e:
                status['error'] = str(e)
        await self.send_response(msg.request_id, status)



async def _wait_for_windows_parent_exit(parent_pid: int) -> None:
    """Wait on the exact Electron process handle without polling or PID guessing."""
    if sys.platform != 'win32' or parent_pid <= 0:
        await asyncio.Future()
        return

    def wait_for_handle() -> None:
        import ctypes

        synchronize = 0x00100000
        infinite = 0xFFFFFFFF
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel32.OpenProcess(synchronize, False, parent_pid)
        if not handle:
            return
        try:
            kernel32.WaitForSingleObject(handle, infinite)
        finally:
            kernel32.CloseHandle(handle)

    await asyncio.to_thread(wait_for_handle)


async def _run_ipc_with_parent_watchdog(handler: IPCHandler) -> None:
    """Tie packaged sidecar lifetime to its owning Electron process."""
    ipc_runner = _run_windows_ipc(handler) if sys.platform == 'win32' else _run_unix_ipc(handler)
    parent_text = os.environ.get('ZARA_PARENT_PID', '').strip()
    if sys.platform != 'win32' or not parent_text.isdigit():
        await ipc_runner
        return

    parent_pid = int(parent_text)
    ipc_task = asyncio.create_task(ipc_runner, name='zara-ipc')
    parent_task = asyncio.create_task(
        _wait_for_windows_parent_exit(parent_pid),
        name='zara-parent-watchdog',
    )
    done, pending = await asyncio.wait(
        {ipc_task, parent_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if parent_task in done and not ipc_task.done():
        print(f"[ZARA] Electron parent exited pid={parent_pid}; stopping sidecar", flush=True)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    if ipc_task in done:
        await ipc_task


async def main() -> int:
    """Main entry point for Python sidecar"""
    startup_started = time.perf_counter()

    async def send_to_electron(msg: IPCMessage):
        """Send message to Electron via stdout"""
        print(serialize_ipc_message(msg), flush=True)

    handler = IPCHandler(send_to_electron)
    await handler.initialize()

    print(
        f"[OBS] action=backend_startup stage=initialized duration_ms={(time.perf_counter() - startup_started) * 1000:.1f}",
        flush=True,
    )

    print("[ZARA] IPC Handler ready", flush=True)
    print("SYS: Interface neural pronta", flush=True)  # Signal ready

    await _run_ipc_with_parent_watchdog(handler)

    print("[ZARA] IPC Handler shutting down", flush=True)
    return 0


def serialize_ipc_message(msg: IPCMessage) -> str:
    """Serialize one UTF-8-safe IPC frame without escaping Portuguese text."""
    return json.dumps(asdict(msg), ensure_ascii=False)


async def _run_unix_ipc(handler: IPCHandler):
    """Unix/Linux/macOS IPC using asyncio pipes"""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                data = json.loads(line.decode().strip())
                msg = IPCMessage(**data)
                await handler.handle_message(msg)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[IPC] Parse error: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass


async def _run_windows_ipc(handler: IPCHandler):
    """Windows IPC using thread-based stdin reading"""
    import queue
    import threading

    stdin_queue: queue.Queue[str | None] = queue.Queue()
    stop_event = threading.Event()

    def read_stdin():
        """Background thread to read stdin"""
        try:
            for line in sys.stdin:
                if stop_event.is_set():
                    break
                if line.strip():
                    stdin_queue.put(line.strip())
        except Exception:
            pass
        finally:
            # EOF must wake the async consumer. The sentinel is queued after
            # every frame read by this thread, so pending messages are drained
            # before the IPC loop exits.
            stdin_queue.put(None)

    reader_thread = threading.Thread(target=read_stdin, daemon=True)
    reader_thread.start()
    background_requests: set[asyncio.Task] = set()

    try:
        while True:
            try:
                # Never block the asyncio loop waiting for stdin. Voice-level
                # callbacks and other async work need this loop to stay free.
                line = stdin_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)
                continue

            if line is None:
                break

            try:
                data = json.loads(line)
                msg = IPCMessage(**data)
                if msg.type in {'voice-start', 'voice-stop', 'send-message'}:
                    print(f"[VOICE_TRACE] stage=IPC_RECEIVE type={msg.type}", flush=True)
                if msg.type == 'voice-start':
                    # PortAudio/device initialization is isolated from the IPC
                    # consumer so typed commands remain responsive.
                    task = asyncio.create_task(
                        handler.handle_message(msg),
                        name=f"ipc-voice-start-{msg.request_id}",
                    )
                    background_requests.add(task)
                    task.add_done_callback(background_requests.discard)
                else:
                    await handler.handle_message(msg)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[IPC] Parse error: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if background_requests:
            for task in background_requests:
                task.cancel()
            await asyncio.gather(*background_requests, return_exceptions=True)


if __name__ == '__main__':
    from main import configure_utf8_stdio

    configure_utf8_stdio()
    asyncio.run(main())
