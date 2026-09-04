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
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from core.pc_voice_intent import RESPOSTA_NAO_SEI


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
    r"(?:(?:ei|hey)\s+)?(?:zara|sara)\b[\s,;:!.-]*(.*)$",
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
    from integrations.hermes.integration import HermesIntegration
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


class IPCHandler:
    """Base handler for IPC messages"""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self.orchestrator: ZaraOrchestrator | None = None
        self.model_router: ModelRouter | None = None
        self.memory: MemoryManager | None = None
        self.hermes: HermesIntegration | None = None
        # ZARA-VELOCIDADE-001 (Alex, 2026-08-28 noite): resposta por voz tem
        # que ser rápida por padrão -- não é mais preciso pedir "modo rápido".
        self.current_engine: str = "auto_fast"
        self.supercerebro_active: bool = False
        self._set_supercerebro_state(False)
        # ZARA-TELEGRAM-GRUPO-001: ponte do grupo, em paralelo com a privada.
        self._telegram_grupo = None
        self._telegram_adapter = None
        self.voice_active: bool = False

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
        # ZARA-VOICE-LATENCY-OBSERVABILITY-001: start of the current voice turn.
        self._voice_turn_started: float = 0.0
        # ZARA-VOICE-ECO-001: ultima resposta falada, para nao se ouvir.
        self._last_spoken_text: str = ""
        # ZARA-CONFIRMACAO-VAZIA-001: a ultima frase dele que ela REALMENTE
        # processou, para citar em vez de afirmar que entendeu.
        self._ultimo_pedido_entendido: str = ""
        self.lab = None
        self._lab_background_tasks: set[asyncio.Task] = set()
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

    def _remember_action_failure(self, action: str, stage: str, reason: object) -> None:
        self._last_action_failure = {
            "action": str(action or "unknown"),
            "stage": str(stage or "unknown"),
            "reason": _sanitize_observation(reason) or "motivo não informado",
            "at": datetime.now().isoformat(),
        }

    async def _build_self_knowledge_snapshot(self, *, probe_hardware: bool = False) -> dict[str, Any]:
        """Observe current runtime state without exposing keys or inventing availability."""
        self._revoke_stale_pc_control()
        from core.action_registry import get_registry
        from core.model_router import get_model_config
        from core.paths import project_root, user_data_dir

        registry = get_registry()
        specs = [registry.get_spec(name) for name in registry.list_actions()]
        specs = [spec for spec in specs if spec is not None]
        gate_open = bool(registry.pc_control_allowed and self.supercerebro_active)

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
        elif last_engine == "hermes_gateway":
            effective_model = {
                "id": "hermes_gateway",
                "name": "Hermes Gateway",
                "provider": "hermes",
                "api_model": "runtime local",
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

        hermes_connected = bool(self.hermes and self.hermes.enabled and self.hermes.is_connected)
        components = {
            "hermes": component(
                "AVAILABLE" if hermes_connected else "OFFLINE",
                "gateway conectado" if hermes_connected else "gateway não conectado",
            ),
            "codex": component("NOT_CONFIGURED", "sem canal direto dentro do runtime da ZARA"),
            "mentor": component(
                "LIMITED" if getattr(self, "mentor_context", "") else "OFFLINE",
                "Context Sync local carregado" if getattr(self, "mentor_context", "") else "sem contexto local carregado",
            ),
            "supercerebro": component(
                "AVAILABLE" if gate_open and hermes_connected else "OFFLINE",
                "ativo e conectado" if gate_open and hermes_connected else "desativado ou sem gateway",
            ),
            "lab": component("AVAILABLE" if self.lab else "OFFLINE", "coordenador inicializado" if self.lab else "coordenador não inicializado"),
            "voice": component(
                "AVAILABLE" if (self.voice_active or self.voice_pipeline or self.gemini_live_voice) else ("NOT_CONFIGURED" if VOICE_AVAILABLE else "UNSUPPORTED"),
                f"modo {self.voice_mode}" if self.voice_active else "pipeline disponível, inativo" if (self.voice_pipeline or self.gemini_live_voice) else "pipeline não preparado",
            ),
        }

        spec_map = {spec.name: spec for spec in specs}

        def action_state(*names: str) -> str:
            selected = [spec_map.get(name) for name in names]
            if not selected or any(spec is None for spec in selected):
                return "UNSUPPORTED"
            local_domains = {"READ_ONLY", "LOCAL_PC_CONTROL"}
            if any(spec.capability not in local_domains for spec in selected) and not gate_open:
                return "BLOCKED_SUPERCEREBRO"
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
            {"label": "HERMES", **components["hermes"]},
            {"label": "MENTOR", **components["mentor"]},
        ]
        available_actions = sum(
            1 for spec in specs if spec.capability in {"READ_ONLY", "LOCAL_PC_CONTROL"} or gate_open
        )
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
            "pc_control_allowed": gate_open,
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

        from core.self_knowledge import detect_self_knowledge_topic, render_self_knowledge

        topic = detect_self_knowledge_topic(text)
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

    def _load_runtime_preferences(self) -> None:
        """Load non-secret runtime preferences from the existing config file."""
        try:
            from core.paths import api_keys_path
            path = api_keys_path()
            if not path.exists():
                return
            with open(path, encoding="utf-8") as f:
                config = json.load(f)
            engine = str(config.get("ai_engine") or "auto_smart").strip()
            if engine in {"auto", "auto_router"}:
                engine = "auto_smart"
            self.current_engine = engine or "auto_fast"
        except Exception as exc:
            print(f"[IPC] Could not load runtime preferences: {exc}")

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
        Hermes and voice are optional and may stay offline without preventing
        the desktop interface from opening.
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
            # the central action registry even when Hermes is offline.
            import core.actions  # noqa: F401
        except Exception as exc:
            essential_errors.append(f"actions: {exc}")
            traceback.print_exc()

        if essential_errors:
            raise RuntimeError("; ".join(essential_errors))

        try:
            self.hermes = HermesIntegration()
            await self.hermes.initialize()
        except Exception as exc:
            self.hermes = None
            print(f"[IPC] Hermes optional integration unavailable: {exc}")

        if LAB_AVAILABLE and LabCoordinator:
            try:
                worker_runtime = LabWorkerRuntime() if LabWorkerRuntime else None
                self.lab = LabCoordinator(orchestrator=self.orchestrator, hermes=self.hermes, worker_runtime=worker_runtime)
                await self.lab.initialize()
                print("[IPC] ZARA Lab Core initialized")
            except Exception as exc:
                self.lab = None
                print(f"[IPC] ZARA Lab optional module unavailable: {exc}")

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

    async def handle_voice_mic_chunk(self, msg: IPCMessage):
        """Microfone vindo do renderer, ja limpo pelo AEC. ZARA-AEC-RENDERER-001."""
        voice = self.gemini_live_voice
        if voice is None or not voice.usa_renderer:
            return None
        dados = (msg.payload or {}).get('pcm') or ''
        if not dados:
            return None
        try:
            voice.push_mic_pcm(base64.b64decode(dados))
        except Exception as exc:
            print(f"[IPC] chunk de microfone invalido: {exc}", flush=True)
        return None

    async def _prepare_voice_components(self):
        """Prepare voice objects without loading/downloading models at startup.

        Vosk/Kokoro are intentionally lazy. The desktop interface must become
        ready even on a fresh machine where voice models have not been cached.
        """
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
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
            from core.self_knowledge import detect_self_knowledge_topic
            if detect_self_knowledge_topic(text) is not None:
                return True

            from core.file_voice_intent import detect_file_intent
            if detect_file_intent(text) is not None:
                return True

            from core.pc_voice_intent import PcVoiceIntentDetector
            # pc_control_allowed=True DE PROPOSITO. A pergunta aqui e "isto e um
            # comando?", nao "posso executar?". Com False o detector devolveria
            # is_pc_intent=False para as acoes gateadas, elas cairiam em
            # CONVERSA e o modelo ficaria livre para dizer que executou. A
            # autorizacao real continua em _try_pc_intent, com o gate de
            # verdade (self.supercerebro_active).
            if PcVoiceIntentDetector(pc_control_allowed=True).detect(text).is_pc_intent:
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

    def _voice_can_answer_directly(self, user_text: str) -> bool:
        """A Kore pode responder este turno direto, sem passar pelo executor?

        ZARA-VOICE-FLUIDEZ-001. Chamado pelo transporte do Gemini Live antes de
        tocar o audio gerado, entao precisa ser sincrono e barato.

        So devolve True quando as DUAS coisas valem:
          1. o turno esta autorizado pelo wake gate (mesma regra de
             _on_gemini_live_turn, so que em leitura pura — nao arma nem
             desarma a janela de continuacao aqui);
          2. o turno e CONVERSA, nunca ACAO.
        """
        spoken = str(user_text or "").strip()
        if not spoken:
            return False
        # ZARA-VOICE-ECO-001 tem de ser conferido AQUI, nao so em
        # _on_gemini_live_turn. Naquele ponto a resposta direta ja teria saido
        # pelo alto-falante: a ZARA responderia ao proprio eco em voz alta e
        # realimentaria o loop que Alex relatou.
        if self._looks_like_own_echo(spoken):
            return False
        wake = _WAKE_PREFIX_RE.match(spoken)
        if wake:
            command = str(wake.group(1) or "").strip()
            if not command:
                return False  # so "Zara": arma o gate, nao responde nada
        elif time.monotonic() <= self._gemini_wake_armed_until:
            command = spoken
        else:
            return False  # sem wake a ZARA nao fala, nem para conversar
        if self._STOP_WORD_RE.fullmatch(command):
            return False  # "pare" e barge-in, tratado a parte
        return not self._voice_turn_needs_executor(command)

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
        elif time.monotonic() <= self._gemini_wake_armed_until:
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
        await self._append_conversation_message("user", command, "gemini_live_stt")
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

        # ZARA-VOICE-FLUIDEZ-001 — turno de CONVERSA.
        # A Kore ja falou, em streaming, enquanto o turno acontecia. Aqui so
        # resta registrar o que foi dito. `model_text` e usado como
        # TRANSCRICAO do que a voz realmente falou, nunca como prova de que
        # alguma acao aconteceu — turno de conversa, por definicao, nao
        # executou nada.
        if direct:
            print("[VOICE_TRACE] stage=ROUTE result=DIRECT_CONVERSATION", flush=True)
            said = str(model_text or "").strip()
            if said:
                self._last_spoken_text = said  # ZARA-VOICE-ECO-001
                await self._append_conversation_message(
                    "assistant", said, "gemini_live_direct"
                )
                await self.send_event('message', {
                    'role': 'assistant', 'content': said,
                    'engine': 'gemini_live_direct',
                    'timestamp': datetime.now().isoformat(),
                })
            print("[VOICE_TRACE] stage=FINAL_RESPONSE result=SPOKEN_BY_LIVE", flush=True)
            return

        # Turno de ACAO: o rascunho remoto morre aqui, como sempre.
        print("[VOICE_TRACE] stage=ROUTE result=EXECUTOR", flush=True)
        del model_text  # Remote draft is never trusted as proof of a PC action.
        await self._process_voice_message(command)

    async def _on_gemini_live_interrupt(self) -> None:
        """Reflect a real server-side barge-in in ZARA's session state."""
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

        await self._append_conversation_message("user", text, self.current_engine)
        await self.send_event('message', {
            'role': 'user',
            'content': text,
            'engine': self.current_engine,
            'timestamp': datetime.now().isoformat(),
        })

        # Process the recognized text through the message handler
        await self._process_voice_message(text)

    async def _enrich_with_memory(self, text: str) -> str:
        """Prepend ONLY relevant user memories (top-K) to the user message.

        ZARA-USER-MEMORY-CONTEXT-001: never dump the whole store; irrelevant
        memories are excluded by the relevance gate.
        """
        try:
            if not self.user_memory or not (text or "").strip():
                return text
            from memory.memory_context import build_memory_context
            ctx = build_memory_context(self.user_memory, text, top_k=4)
            if not ctx:
                return text
            return f"{ctx}\n\nMensagem de Alex:\n{text}"
        except Exception:
            return text

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

    async def _try_reminder_intent(self, text: str) -> str | None:
        """Deterministic reminder intent (ZARA-REMINDER-VOICE-BINDING-001).

        Returns the ZARA reply when the message is a reminder intent, or
        None so the normal brain handles it. Never an LLM decision.
        """
        try:
            if not self.reminder_engine or not (text or "").strip():
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

    async def _executar_intent_de_pc(self, text: str) -> str | None:
        """Deterministic PC intent (ZARA-COMPUTER-CONTROL-VOLUME-001).

        Maps voice/text PC commands to existing os_volume action through
        the existing capability gate (Supercérebro). Returns the ZARA reply
        or None so the normal brain handles it. Never an LLM decision.
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
                pc_control_allowed=bool(self.supercerebro_active),
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
                return res.reply or "Para controlar o computador, ative o Supercérebro."
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
                if self._last_window_hwnd is not None:
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
        if not raw or not re.search(r"[,;]|\be\s+depois\b|\bdepois\b", raw, re.IGNORECASE):
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
        if not 2 <= len(parts) <= 5:
            return None

        from core.pc_voice_intent import PcVoiceIntentDetector

        detector = PcVoiceIntentDetector(
            pc_control_allowed=bool(self.supercerebro_active),
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
        return "Resultado por etapa: " + " ".join(outcomes)

    @staticmethod
    def _jarvis_reply_status(reply: str | None) -> str:
        """Classify a primitive readback without turning dispatch into success."""
        clean = str(reply or "").strip()
        folded = clean.casefold()
        if not clean or folded.startswith(("não ", "nao ", "esse comando", "para executar")):
            return "FALHOU"
        if folded in {"que horas?", "quando?"} or "qual horário" in folded or "qual horario" in folded:
            return "PENDENTE"
        return "OK"

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
        if not self.supercerebro_active:
            return "Para executar um pedido com várias etapas, ative o Supercérebro."

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
        if intent.mutating and not self.supercerebro_active:
            return "Para alterar arquivos, ative o Supercérebro e repita o comando explícito."
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
            elif intent.action in {"files_write", "files_text_summary", "files_rename"}:
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

    async def _process_voice_message(self, text: str):
        """Process voice message through orchestrator/model router"""
        text = _canonical_request(text)
        if not text:
            return
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
                await self._speak_response(jarvis_reply)
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
                await self._speak_response(reminder_reply)
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
                await self._speak_response(memory_reply)
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
                await self._speak_response(self_reply)
                return
            file_reply = await self._try_file_intent(text)
            if file_reply:
                await self._append_conversation_message("assistant", file_reply, "file_control")
                await self.send_event('message', {
                    'role': 'assistant', 'content': file_reply, 'engine': 'file_control',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(file_reply)
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
                await self._speak_response(pc_reply)
                print(
                    f"[VOICE_TRACE] stage=FINAL_RESPONSE result=PASS route=pc_control "
                    f"total_ms={self._voice_elapsed_ms():.0f}",
                    flush=True,
                )
                return
            if _looks_like_unhandled_local_action(text):
                _log_intent_telemetry("refused_local_action", "voice", text)
                reply = RESPOSTA_NAO_SEI
                await self._append_conversation_message("assistant", reply, "local_action_guard")
                await self.send_event('message', {
                    'role': 'assistant', 'content': reply, 'engine': 'local_action_guard',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(reply)
                return
            # ETAPA 1 (raciocinio livre): guarda a frase original, antes do
            # enriquecimento de memoria, so para o log de telemetria abaixo.
            _telemetry_raw_text = text
            # ZARA-USER-MEMORY-CONTEXT-001: enriquece com memorias relevantes
            text = await self._enrich_with_memory(text)
            # Supercérebro routes through the real Hermes gateway only while
            # explicitly enabled. Otherwise use ZARA's normal model router.
            if self.supercerebro_active and self.hermes and self.hermes.enabled and self.hermes.is_connected:
                response = await self.hermes.send_message(text, history=[], team="general")
                engine_used = "hermes_gateway"
            elif self.orchestrator:
                if _has_broad_action_language_signal(_telemetry_raw_text):
                    _log_intent_telemetry("escaped_to_orchestrator", "voice", _telemetry_raw_text)
                response = await self.orchestrator.process_message(text, engine=self.current_engine)
                engine_used = self.orchestrator.last_engine_used or self.current_engine
            else:
                raise RuntimeError("No model backend is available")

            # Store in memory
            if self.memory:
                await self.memory.add_conversation(text, str(response), engine_used)

            await self._append_conversation_message("assistant", str(response), engine_used)

            # Send response as message event
            await self.send_event('message', {
                'role': 'assistant',
                'content': response,
                'engine': engine_used,
                'timestamp': datetime.now().isoformat()
            })

            # Speak response via TTS
            await self._speak_response(response)

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
            if self.voice_active and self.voice_pipeline:
                self.voice_pipeline.resume_listening(require_wake_word=True)
                await self.send_event('state-change', 'LISTENING')
            else:
                await self.send_event('state-change', 'STANDBY')

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
        if not self.project_memory:
            await self.send_error(msg, "Project Memory indisponível")
            return
        try:
            keys = self.project_memory.list_docs()
            await self.send_response(msg.request_id, {'success': True, 'keys': keys})
        except Exception as exc:
            await self.send_error(msg, f"project-memory-list: {exc}")

    async def handle_memory_galaxy_list(self, msg: IPCMessage):
        """Return a bounded, read-only view of the real memory stores."""
        nodes: list[dict] = []
        sources = {"project": "OFFLINE", "user": "OFFLINE", "context": "OFFLINE"}
        if self.project_memory:
            try:
                for key in self.project_memory.list_docs()[:50]:
                    doc = self.project_memory.get_doc(key)
                    if not doc or not str(doc.get("content", "")).strip():
                        continue
                    nodes.append({"id": f"project:{key}", "kind": "project",
                        "title": str(doc.get("title") or key)[:120],
                        "content": str(doc.get("content", ""))[:12_000],
                        "source": f"Project Memory · {key}", "updated_at": doc.get("updated_at")})
                sources["project"] = "AVAILABLE"
                context = self.project_memory.load_mentor_context().strip()
                if context:
                    nodes.append({"id": "context:mentor-latest", "kind": "context",
                        "title": "Contexto mais recente do Mentor", "content": context[:12_000],
                        "source": "Context Sync · mentor_context_latest.md", "updated_at": None})
                sources["context"] = "AVAILABLE"
            except Exception as exc:
                print(f"[IPC] Memory Galaxy project read failed: {type(exc).__name__}")
                sources["project"] = sources["context"] = "ERROR"
        if self.user_memory:
            try:
                for fact in self.user_memory.list()[:100]:
                    if fact.get("status") == "forgotten" or not str(fact.get("fact", "")).strip():
                        continue
                    nodes.append({"id": f"user:{fact.get('id', '')}", "kind": "user",
                        "title": str(fact.get("category") or "Memória do usuário")[:120],
                        "content": str(fact.get("fact", ""))[:12_000],
                        "source": f"User Memory · {fact.get('source') or 'local'}",
                        "updated_at": fact.get("updated_at")})
                sources["user"] = "AVAILABLE"
            except Exception as exc:
                print(f"[IPC] Memory Galaxy user read failed: {type(exc).__name__}")
                sources["user"] = "ERROR"
        if self.conversation_history:
            try:
                messages = await asyncio.to_thread(self.conversation_history.list_recent, 30)
                for item in messages:
                    content = str(item.get("content", "")).strip()
                    if content:
                        nodes.append({"id": f"history:{item.get('id', '')}", "kind": "history",
                            "title": "Conversa · " + str(item.get("role", "mensagem")),
                            "content": content[:12_000], "source": "Conversation History · SQLite local",
                            "updated_at": item.get("timestamp")})
                sources["context"] = "AVAILABLE"
            except Exception as exc:
                print(f"[IPC] Memory Galaxy history read failed: {type(exc).__name__}")
                if sources["context"] != "AVAILABLE": sources["context"] = "ERROR"
        try:
            links = _extract_memory_links(nodes)
        except Exception as exc:
            print(f"[IPC] Memory Galaxy links extraction failed: {type(exc).__name__}: {exc}")
            links = []
        await self.send_response(msg.request_id, {"success": True, "nodes": nodes,
            "count": len(nodes), "sources": sources, "read_only": True, "links": links})

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

    async def _speak_response(self, text: str):
        """Speak response using TTS, loading the local model only on first use."""
        value = str(text or "").strip()
        if not value:
            return

        live_voice_available = bool(self.gemini_live_voice and self.gemini_live_voice.active)
        if self.tts_manager and not self._tts_initialized and not live_voice_available:
            try:
                await asyncio.to_thread(self.tts_manager.initialize)
                self._tts_initialized = True
            except Exception as exc:
                self._tts_initialized = False
                print(f"[Voice] TTS lazy initialization failed: {exc}")

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
            print("[VOICE_TRACE] stage=TTS_START result=START", flush=True)
            # ZARA-LATENCIA-MEDIDA-001: aqui a ação já aconteceu. Tudo que vier
            # depois é a segunda viagem — o custo de FALAR uma frase que já
            # estava pronta. É a suspeita principal, e agora ela é medida.
            _crono = getattr(self, "_cronometro", None)
            if _crono is not None:
                _crono.marcar("antes_de_falar")
            spoken = False
            engine_used = "none"
            # ZARA-VOZ-UNICA-002: cada fala começa com a folha limpa.
            self._fala_interrompida = False
            if live_voice_available and self.gemini_live_voice:
                spoken = await self.gemini_live_voice.speak(value)
                if not spoken and self.gemini_live_voice.active:
                    # ZARA-VOZ-UNICA-001: uma segunda chance antes de trocar de
                    # voz. Alex reconhece a Kore e detesta a voz do Windows;
                    # trocar de voz no meio da conversa é pior do que esperar
                    # mais um instante.
                    print("[VOICE_TRACE] stage=TTS_RETRY result=KORE_SEGUNDA_TENTATIVA", flush=True)
                    spoken = await self.gemini_live_voice.speak(value)
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
            if getattr(self, "_fala_interrompida", False):
                print("[VOICE_TRACE] stage=TTS_ABORT result=INTERROMPIDO_POR_ALEX", flush=True)
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
            elif not spoken and self.tts_manager and self.tts_manager.gemini:  # type: ignore[union-attr]
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
            self._voice_speaking = False
            self._finish_assistant_output()
            if self.voice_active and self.voice_pipeline:
                self.voice_pipeline.resume_listening(require_wake_word=True)
            await self.send_event('voice-level', {
                'level': 0.0,
                'tone': 0.5,
                'speaking': False,
                'state': 'STANDBY'
            })
            await self.send_event('state-change', 'STANDBY')

    async def handle_message(self, msg: IPCMessage):
        """Route message to appropriate handler"""
        handler_map = {
            'engine-change': self.handle_engine_change,
            'engine-list': self.handle_engine_list,
            'supercerebro-toggle': self.handle_supercerebro_toggle,
            'supercerebro-status': self.handle_supercerebro_status,
            'send-message': self.handle_send_message,
            'interrupt': self.handle_interrupt,
            # ZARA-BOTAO-MUDO-001: calar a boca dela sem desligar o resto.
            'voice-mute': self.handle_voice_mute,
            # ZARA-AEC-RENDERER-001: microfone limpo pelo AEC do Chromium.
            'voice-mic-chunk': self.handle_voice_mic_chunk,
            'action-execute': self.handle_action_execute,
            'action-confirm': self.handle_action_confirm,
            'action-confirm-cancel': self.handle_action_confirm_cancel,
            'action-list': self.handle_action_list,
            'self-status': self.handle_self_status,
            'system-metrics': self.handle_system_metrics,
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
            'reminder-create': self.handle_reminder_create,
            'reminder-list': self.handle_reminder_list,
            'reminder-cancel': self.handle_reminder_cancel,
            'memory-user-add': self.handle_memory_user_add,
            'memory-user-search': self.handle_memory_user_search,
            'memory-user-list': self.handle_memory_user_list,
            'memory-user-forget': self.handle_memory_user_forget,
            'project-memory-get': self.handle_project_memory_get,
            'project-memory-list': self.handle_project_memory_list,
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
        elif event_type == 'supercerebro-change':
            active = data.get('active') if isinstance(data, dict) else data
            await self.send(IPCMessage(type=event_type, active=bool(active)))
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
            await self.send_response(msg.request_id, await self.lab.get_state())
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

    async def handle_engine_change(self, msg: IPCMessage):
        engine = str(msg.payload.get('engine') if msg.payload else '').strip()
        if not engine:
            await self.send_error(msg, "Engine not specified")
            return

        if engine in {'auto', 'auto_router'}:
            engine = 'auto_smart'

        if engine not in {'auto_smart', 'auto_economy'}:
            if not self.model_router:
                await self.send_error(msg, "Model router unavailable")
                return
            available_ids = {model.id for model in self.model_router.get_available_models(include_hermes=False)}
            # Native Gemini Live is a voice transport, not a text-chat engine.
            available_ids.discard('gemini_live')
            available_ids.discard('hermes_gateway')  # controlled only by Supercérebro
            if engine not in available_ids:
                await self.send_error(msg, f"Engine unavailable or API key missing: {engine}")
                return

        self.current_engine = engine
        self._persist_engine_preference(engine)
        print(f"[IPC] Engine changed to: {engine}")
        await self.send_response(msg.request_id, {'success': True, 'engine': engine})

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
            connection_proven = bool(
                connected and self.hermes.enabled and self.hermes.is_connected
            )
            if not connection_proven:
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

    async def handle_send_message(self, msg: IPCMessage):
        payload = msg.payload or {}
        text = _canonical_request(payload.get('text', '') or payload.get('message', ''))
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
            await self.send_response(msg.request_id, {
                'response': reminder_reply,
                'engine': 'reminder',
            })
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
        pc_reply = await self._try_compound_pc_intent(text)
        if not pc_reply:
            pc_reply = await self._try_pc_intent(text)
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
            await self.send_response(msg.request_id, {
                'response': pc_reply,
                'engine': 'pc_control',
                'selo': selo,
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
            reply = fallback_reply if fallback_reply is not None else RESPOSTA_NAO_SEI
            engine_usado = 'raciocinio_livre_texto' if fallback_reply is not None else 'local_action_guard'
            await self._append_conversation_message("assistant", reply, engine_usado)
            await self.send_response(msg.request_id, {
                'response': reply,
                'engine': engine_usado,
            })
            await self.send_event('state-change', 'STANDBY')
            return

        # ETAPA 1 (raciocinio livre): guarda a frase original, antes do
        # enriquecimento de memoria e do contexto do mentor, so para o log de
        # telemetria abaixo.
        _telemetry_raw_text = text

        # ZARA-USER-MEMORY-CONTEXT-001: enriquece com memorias relevantes (top-K)
        text = await self._enrich_with_memory(text)

        # CONTEXT SYNC: prepend mentor context if available
        if getattr(self, 'mentor_context', '') and self.mentor_context.strip():
            text = f"[CONTEXTO DO MENTOR - Carregado do mentor_context_latest.md]\n{self.mentor_context}\n\n---\nMensagem de Alex:\n{text}"

        try:
            history = payload.get('history', [])
            if self.supercerebro_active and self.hermes and self.hermes.enabled and self.hermes.is_connected:
                response = await self.hermes.send_message(text, history=history, team="general")
                engine_used = "hermes_gateway"
            elif self.orchestrator:
                if _has_broad_action_language_signal(_telemetry_raw_text):
                    _log_intent_telemetry("escaped_to_orchestrator", "text", _telemetry_raw_text)
                response = await self.orchestrator.process_message(
                    text, engine=engine, history=history
                )
                engine_used = self.orchestrator.last_engine_used or engine
            else:
                raise RuntimeError("No model backend is available")

            response = str(response)

            # Store the turn in episodic memory, not in compact fact memory.
            if self.memory:
                await self.memory.add_conversation(text, response, engine_used)

            await self._append_conversation_message("assistant", response, engine_used)

            await self.send_response(msg.request_id, {
                'response': response,
                'engine': engine_used
            })
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

        # The remote capability session may disappear between toggle and use.
        self._revoke_stale_pc_control()
        # Parameters may contain credentials or private content; never log them.
        print(f"[IPC] Executing action: {action}")

        # ZARA-CORE-STATE-ACAO-001: mesmo gap do handle_send_message -- o Core
        # nunca mostrava EXECUTANDO/ERRO durante uma acao real (clique de
        # botao na Home, ex. os_wifi_status, os_power_plan_set). Result.success
        # False sem excecao (ex. _failure()) tambem conta como erro visual.
        await self.send_event('state-change', 'EXECUTING')
        try:
            result = await execute_action(action, **params)
            await self.send_response(msg.request_id, {'success': True, 'result': result})
            result_ok = getattr(result, 'success', True)
            await self.send_event('state-change', 'SUCCESS' if result_ok else 'ERROR')
        except Exception as e:
            print(f"[IPC] Action error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))
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

        self._revoke_stale_pc_control()
        print(f"[IPC] Confirming HIGH-risk action: {action}")
        try:
            result = await execute_confirmed_action(
                action,
                confirmation_id,
                action_fingerprint,
                **params,
            )
            await self.send_response(msg.request_id, {'success': True, 'result': result})
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
        if self.voice_active:
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.send_response(msg.request_id, {
                    'success': True, 'state': 'LISTENING', **self.gemini_live_voice.status()
                })
                return

        gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
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
                await self.send_response(msg.request_id, {
                    'success': True,
                    'state': status.get('session_state', 'LISTENING'),
                    'wake_mode': bool(status.get('wake_detector_ready')),
                    **status
                })
                return
            except Exception as exc:
                self.voice_active = False
                self.voice_mode = 'off'
                print(f"[IPC] Gemini Live start error: {exc}")
                traceback.print_exc()
                # Fall through to local Vosk. A Gemini Live failure must not
                # turn the microphone button into a dead end.

        # Backward-compatible local path for machines without a Gemini key.
        if not VOICE_AVAILABLE or not self.voice_pipeline:
            await self.send_error(msg, "Gemini API key missing and local voice pipeline unavailable")
            return

        try:
            if not self.voice_pipeline.vosk or not self.voice_pipeline.audio:
                await asyncio.to_thread(self.voice_pipeline.initialize)
            self.voice_pipeline._event_loop = asyncio.get_running_loop()
            await asyncio.to_thread(self.voice_pipeline.start)
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
            self._voice_last_error = str(e).split(':', 1)[0][:120]
            print(f"[IPC] Voice start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

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
                if arquivo.exists():
                    token = str(
                        json.loads(arquivo.read_text(encoding="utf-8")).get("telegram_bot_token") or ""
                    ).strip()
                if token:
                    ponte = PonteTelegram(token, self._executar_do_celular)
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

    async def _executar_do_celular(self, destino: str, texto: str) -> str:
        """Uma ordem vinda do Telegram. Devolve o que responder a ele.

        ZARA-TELEGRAM-001. Reaproveita exatamente os mesmos caminhos da voz —
        nenhum atalho novo, nenhuma regra de segurança contornada porque a
        mensagem veio de fora.
        """
        from core.action_registry import execute_action

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

        # ZARA-TELEGRAM-HERMES-001
        #
        # O prefixo "hermes:" já existia no roteamento da ponte, mas o
        # despachante não tinha branch para ele — a mensagem caía na própria
        # ZARA. O Supercérebro (Hermes Agent via gateway local) é um destino
        # de verdade, então aqui ele é tratado direto, tanto pelo celular
        # privado quanto pelo grupo.
        if destino == "hermes":
            try:
                from integrations.hermes.client import HermesClient

                client = HermesClient()
                result = await asyncio.to_thread(client.send_message, texto)
                if result["success"]:
                    return f"Hermes:\n\n{result['text']}"
                return f"Hermes não veio: {result['error']}"
            except Exception as exc:
                return f"Hermes não veio: {type(exc).__name__}"

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

            try:
                from integrations.hermes.client import HermesClient

                client = HermesClient()
                result = await asyncio.to_thread(client.send_message, texto)
                partes.append(f"Hermes: {result['text']}" if result["success"] else f"Hermes não veio: {result['error']}")
            except Exception as exc:
                partes.append(f"Hermes não veio: {type(exc).__name__}")

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
            enriquecido = await self._enrich_with_memory(texto)
        except Exception:
            enriquecido = texto

        try:
            if self.orchestrator:
                resposta = await self.orchestrator.process_message(
                    enriquecido, engine="auto_smart", history=[]
                )
                return str(resposta).strip() or "Tô aqui."
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
        """Avisa Alex quando o Claude ou o Codex terminam de responder.

        ZARA-VIGIA-001. Sem isto ele fica olhando a tela para saber se chegou
        resposta — o desgaste que a ponte inteira existe para acabar.
        """
        try:
            if getattr(self, "_vigia", None) is not None:
                return
            from core.vigia_das_respostas import VigiaDasRespostas

            def pode_avisar() -> bool:
                # Nunca por cima da fala dela nem da fala do Alex.
                voz = self.gemini_live_voice
                if voz is not None and getattr(voz, "speaking_now", False):
                    return False
                return not self._voice_speaking

            async def avisar(texto: str, conteudo: str = "") -> None:
                # ZARA-TELEGRAM-001: o aviso vai para os dois lugares. Se ele
                # estiver longe do computador, é no celular que ele precisa
                # saber que chegou resposta.
                #
                # ZARA-VIGIA-CONTEUDO-001. Alex: "porque nao ta aparecendo o que
                # voces tao conversando aqui la no telegram?". Porque ela só
                # dizia "o Codex respondeu" — o aviso, nunca a resposta. No
                # computador isso basta, ele vira a cabeça e lê. No celular não:
                # saber que existe uma resposta que ele não pode ler é pior do
                # que não ser avisado.
                #
                # A voz continua curta de propósito. Ouvir a resposta inteira
                # sem pedir é justamente o que o botão vermelho existe para
                # evitar; ler no celular é escolha dele, no tempo dele.
                await self._speak_response(texto)
                ponte = getattr(self, "_telegram", None)
                if ponte is None:
                    return

                # ZARA-VIGIA-LONGE-001
                #
                # Alex: "suas respostas tao saindo aqui e la ainda no telegram".
                #
                # Mandar o texto inteiro para o celular resolveu um problema
                # ("porque nao aparece o que voces tao conversando la?") e criou
                # outro: com ele sentado lendo a resposta na tela, o celular
                # apitava a mesma coisa. Aviso repetido vira aviso ignorado.
                #
                # O critério não é uma opção a mais para ele configurar: é o
                # teclado e o mouse dele. Mexendo no computador, ele já está
                # lendo — vai só o aviso curto. Longe, vai o texto inteiro,
                # porque a tela não serve para nada nesse caso.
                # ZARA-RESPOSTA-VOLTA-POR-ONDE-VEIO-001
                #
                # A regra de "só manda se ele estiver longe" estava certa para
                # aviso que ninguém pediu, e ERRADA para resposta a pergunta.
                #
                # O que aconteceu, no histórico de hoje às 20h43: ele escreveu
                # "ta ai" pelo Telegram, a ZARA entregou para mim e respondeu a
                # ele "te aviso quando responder". Eu respondi — no computador.
                # A resposta ficou presa aqui porque ele estava perto do PC, e
                # do lado dele foi silêncio. Ele passou vinte minutos perguntando
                # à ZARA o que tinha acontecido comigo.
                #
                # Ele mesmo resumiu: "voce quebrou meu fluxo de trabalho, sem
                # voce nao consegui fazer nada".
                #
                # A regra certa é a mais velha do mundo: **resposta volta por
                # onde a pergunta veio**. Se ele perguntou pelo celular, a
                # resposta vai ao celular, esteja ele onde estiver. A distância
                # só decide o que fazer com aviso que ele NÃO pediu.
                esperando = bool(getattr(self, "_pergunta_veio_do_celular", False))
                if conteudo and (esperando or self._alex_esta_longe()):
                    await ponte.avisar(f"{texto}\n\n{conteudo}".strip())
                    self._pergunta_veio_do_celular = False
                else:
                    await ponte.avisar(texto)

            self._vigia = VigiaDasRespostas(avisar, pode_avisar=pode_avisar)
            await self._vigia.iniciar()
        except Exception as exc:
            self._vigia = None
            print(f"[IPC] vigia das respostas nao ligou: {exc}", flush=True)

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

    async def handle_voice_mute(self, msg: IPCMessage):
        """Liga/desliga a fala dela. ZARA-BOTAO-MUDO-001.

        Muda ela CALA, não desliga: continua ouvindo, entendendo e executando
        no PC, e continua avisando pelo Telegram. Só a voz sai de cena.

        Sem `mudo` no pedido, só responde como está — é assim que o botão
        descobre a cor certa quando o app abre.
        """
        pedido = (msg.payload or {}).get('mudo')
        if pedido is None:
            atual = bool(getattr(self, "_silenciada", False))
            await self.send_response(msg.request_id, {'success': True, 'mudo': atual})
            return

        self._silenciada = bool(pedido)
        self._gravar_silenciada(self._silenciada)

        if self._silenciada:
            # Cala o que já estiver saindo neste instante.
            if self.tts_manager:
                self.tts_manager.interrupt()
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.gemini_live_voice.interrupt_speech()
            self._voice_speaking = False

        print(f"[IPC] voz {'silenciada' if self._silenciada else 'liberada'}", flush=True)
        await self.send_response(msg.request_id, {'success': True, 'mudo': self._silenciada})
        await self.send_event('voice-mute-change', {'mudo': self._silenciada})

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
        config = {
            'current_engine': self.current_engine,
            'supercerebro_active': self.supercerebro_active,
            'voice_active': self.voice_active,
        }
        await self.send_response(msg.request_id, config)

    async def handle_self_status(self, msg: IPCMessage):
        """Return structured runtime truth for UI/LAB consumers."""
        snapshot = await self._build_self_knowledge_snapshot(probe_hardware=True)
        await self.send_response(msg.request_id, snapshot)

    async def handle_config_set(self, msg: IPCMessage):
        payload = msg.payload or {}
        key = payload.get('key')
        value = payload.get('value')
        if key == 'engine':
            self.current_engine = value
        elif key == 'supercerebro':
            await self.send_error(msg, "Use supercerebro-toggle so Hermes Gateway connectivity is verified")
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
        """Return zero-cost text engines and AUTO policies without exposing keys."""
        engines: list[dict[str, Any]] = [
            {
                # ZARA-VELOCIDADE-001 (Alex, 2026-08-28 noite): padrão agora.
                # Primeiro na lista de propósito -- é a opção recomendada.
                'id': 'auto_fast',
                'name': 'AUTO • RÁPIDO',
                'provider': 'zara',
                'free_tier': 'Prioriza o motor mais rápido disponível + fallback R$0',
                'status': 'READY',
            },
            {
                'id': 'auto_smart',
                'name': 'AUTO • INTELIGENTE',
                'provider': 'zara',
                'free_tier': 'Qualidade + tarefa + saúde + fallback R$0',
                'status': 'READY',
            },
            {
                'id': 'auto_economy',
                'name': 'AUTO • ECONÔMICO',
                'provider': 'zara',
                'free_tier': 'Prioriza modelos leves/rápidos e preserva cotas',
                'status': 'READY',
            },
        ]
        health: list[dict[str, Any]] = []
        if self.model_router:
            health = self.model_router.configured_model_status(include_paid=False)
            for model in self.model_router.get_available_models(include_hermes=False, include_paid=False):
                engines.append({
                    'id': model.id,
                    'name': model.name,
                    'provider': model.provider.value,
                    'free_tier': model.free_tier_limit,
                    'status': self.model_router.health_for(model.id).get('state', 'AVAILABLE'),
                })

        if self.current_engine in {'auto', 'auto_router'}:
            self.current_engine = 'auto_fast'
        available_ids = {engine['id'] for engine in engines}
        if self.current_engine not in available_ids:
            self.current_engine = 'auto_fast'

        await self.send_response(msg.request_id, {
            'current': self.current_engine,
            'engines': engines,
            'health': health,
            'last_engine_used': self.orchestrator.last_engine_used if self.orchestrator else None,
            'voice': {
                'id': 'gemini_live',
                'name': 'Gemini 3.1 Flash Live',
                'voice': 'Kore',
                'available': bool(os.environ.get('GEMINI_API_KEY')),
            },
        })

    async def handle_supercerebro_status(self, msg: IPCMessage):
        """Return supercerebro status"""
        self._revoke_stale_pc_control()
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
        # Agent status is descriptive only. Reassert the fail-closed local gate
        # after the health read so stale remote fields cannot claim SC is ON.
        self._revoke_stale_pc_control()
        status.update({
            'active': self.supercerebro_active,
            'connected': bool(self.hermes and self.hermes.is_connected),
            'enabled': bool(self.hermes and self.hermes.enabled),
        })
        await self.send_response(msg.request_id, status)

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
