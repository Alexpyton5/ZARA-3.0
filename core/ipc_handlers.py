"""
ZARA 3.0 - Python IPC Handlers
Handles all IPC communication between Electron frontend and Python backend.
"""

import asyncio
import json
import os
import re
import sys
import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _sanitize_observation(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)\b(?:bearer\s+)?(?:sk-|api[_-]?key[=: ]+|token[=: ]+)[^\s,;]+", "<redacted>", text)
    text = re.sub(r"(?i)(?:[A-Z]:\\|/)[^\s,;]+", "<path>", text)
    return " ".join(text.split())[:180]


_WAKE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:ei|hey)\s+)?(?:zara|sara)\b[\s,;:!.-]*(.*)$",
    flags=re.IGNORECASE,
)


def _canonical_request(value: object) -> str:
    """Normalize voice and text into the same deterministic request shape."""
    text = str(value or "").strip()
    wake = _WAKE_PREFIX_RE.match(text)
    if wake:
        return str(wake.group(1) or "").strip()
    return text


def _looks_like_unhandled_local_action(text: str) -> bool:
    """Fail closed for PC-action language that no deterministic handler claimed."""
    return bool(re.match(
        r"^\s*(?:abra|abre|abrir|feche|fecha|fechar|minimize|maximize|restaure|"
        r"aumente|aumentar|diminua|diminuir|ative|ativar|desative|desativar|"
        r"ligue|ligar|desligue|desligar|mova|mover|copie|copiar|cole|colar|"
        r"digite|digitar|escreva|escrever|pesquise|pesquisar|procure|buscar)\b",
        text,
        flags=re.IGNORECASE,
    ))


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
    from comtypes import CoInitialize, CoUninitialize
    import comtypes.client

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
    from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
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
        self.current_engine: str = "auto_smart"
        self.supercerebro_active: bool = False
        self._set_supercerebro_state(False)
        self.voice_active: bool = False

        # Voice pipeline
        self.voice_pipeline: VoicePipeline | None = None
        self.tts_manager: TTSManager | None = None
        self._voice_level: float = 0.0
        self._voice_tone: float = 0.5
        self._voice_speaking: bool = False
        self._voice_last_error: str | None = None
        self._voice_loop_task: asyncio.Task | None = None
        self._voice_start_lock = asyncio.Lock()
        self._tts_initialized: bool = False
        self.gemini_live_voice: GeminiLiveVoice | None = None
        self.voice_mode: str = "off"
        self._gemini_wake_armed_until: float = 0.0
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

    async def _try_self_knowledge(self, text: str) -> str | None:
        from core.self_knowledge import detect_self_knowledge_topic, render_self_knowledge

        topic = detect_self_knowledge_topic(text)
        if topic is None:
            return None
        snapshot = await self._build_self_knowledge_snapshot(probe_hardware=topic == "capabilities")
        return render_self_knowledge(topic, snapshot)

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
            self.current_engine = engine or "auto_smart"
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

        print("[IPC] Backend components initialized")

    async def _prepare_voice_components(self):
        """Prepare voice objects without loading/downloading models at startup.

        Vosk/Kokoro are intentionally lazy. The desktop interface must become
        ready even on a fresh machine where voice models have not been cached.
        """
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if GEMINI_LIVE_MODULE_AVAILABLE and GeminiLiveVoice and GeminiLiveVoiceConfig and gemini_key:
            try:
                self.gemini_live_voice = GeminiLiveVoice(
                    GeminiLiveVoiceConfig(api_key=gemini_key, voice_name="Kore"),
                    on_state=self._on_gemini_live_state,
                    on_level=self._on_gemini_live_level,
                    on_turn=self._on_gemini_live_turn,
                    on_interrupt=self._on_gemini_live_interrupt,
                    on_error=self._on_gemini_live_error,
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
            self._gemini_wake_armed_until = time.monotonic() + 8.0
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

    async def _on_gemini_live_turn(self, user_text: str, model_text: str) -> None:
        del model_text  # Remote draft is never trusted as proof of a PC action.
        spoken = str(user_text or "").strip()
        if not spoken:
            return

        wake = _WAKE_PREFIX_RE.match(spoken)
        if wake:
            command = str(wake.group(1) or "").strip()
            if not command:
                self._gemini_wake_armed_until = time.monotonic() + 8.0
                print("[VOICE_TRACE] stage=WAKE_EVENT result=PASS", flush=True)
                await self.send_event('state-change', 'LISTENING')
                return
        elif time.monotonic() <= self._gemini_wake_armed_until:
            command = spoken
        else:
            print("[VOICE_TRACE] stage=WAKE_GATE result=IGNORED_NO_WAKE", flush=True)
            return

        self._gemini_wake_armed_until = 0.0
        print(f"[VOICE_TRACE] stage=STT_RESULT result=PASS chars={len(command)}", flush=True)
        print(f"[VOICE_TRACE] stage=NORMALIZED_TEXT result=PASS chars={len(command.strip())}", flush=True)
        if re.fullmatch(r"(?:pare|parar|interrompa|interromper|chega)", command, flags=re.IGNORECASE):
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.gemini_live_voice.interrupt_speech()
            await self._on_gemini_live_interrupt()
            return
        await self._append_conversation_message("user", command, "gemini_live_stt")
        await self.send_event('message', {
            'role': 'user', 'content': command, 'engine': 'gemini_live_stt',
            'timestamp': datetime.now().isoformat(),
        })
        await self._process_voice_message(command)

    async def _on_gemini_live_interrupt(self) -> None:
        """Reflect a real server-side barge-in in ZARA's session state."""
        self._voice_speaking = False
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

    async def _append_conversation_message(
        self, role: str, content: str, engine: str = ""
    ) -> dict[str, Any] | None:
        """Persist renderer history without making chat availability depend on disk I/O."""
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

    async def _try_pc_intent(self, text: str) -> str | None:
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
            if res.action == "os_volume":
                if res.param in ("up", "down"):
                    current = (
                        self._last_volume_level
                        if res.contextual
                        else _read_windows_volume()
                    )
                    if current is None:
                        return "Não consegui ler o volume do sistema."
                    params["level"] = max(0, min(100, current + (10 if res.param == "up" else -10)))
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
            result = await execute_action(res.action, **params)
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
                return "Pronto."
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
            print("[VOICE_TRACE] stage=INTENT_MATCH result=START", flush=True)
            pc_reply = await self._try_compound_pc_intent(text)
            if not pc_reply:
                pc_reply = await self._try_pc_intent(text)
            if pc_reply:
                print("[VOICE_TRACE] stage=ACTION_DISPATCH result=COMPLETED", flush=True)
                await self._append_conversation_message("assistant", pc_reply, "pc_control")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': pc_reply,
                    'engine': 'pc_control',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(pc_reply)
                print("[VOICE_TRACE] stage=FINAL_RESPONSE result=PASS", flush=True)
                return
            if _looks_like_unhandled_local_action(text):
                reply = "Não encontrei um executor local verificado para esse comando; nenhuma ação foi realizada."
                await self._append_conversation_message("assistant", reply, "local_action_guard")
                await self.send_event('message', {
                    'role': 'assistant', 'content': reply, 'engine': 'local_action_guard',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(reply)
                return
            # ZARA-USER-MEMORY-CONTEXT-001: enriquece com memorias relevantes
            text = await self._enrich_with_memory(text)
            # Supercérebro routes through the real Hermes gateway only while
            # explicitly enabled. Otherwise use ZARA's normal model router.
            if self.supercerebro_active and self.hermes and self.hermes.enabled and self.hermes.is_connected:
                response = await self.hermes.send_message(text, history=[], team="general")
                engine_used = "hermes_gateway"
            elif self.orchestrator:
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
        # Speak with TTS (best effort, non-blocking for the engine)
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
        await self.send_response(msg.request_id, {"success": True, "nodes": nodes,
            "count": len(nodes), "sources": sources, "read_only": True})

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
        await self.send_event('state-change', 'SPEAKING')
        await self.send_event('voice-level', {
            'level': 0.5,
            'tone': 0.5,
            'speaking': True,
            'state': 'SPEAKING'
        })

        try:
            print("[VOICE_TRACE] stage=TTS_START result=START", flush=True)
            spoken = False
            if live_voice_available and self.gemini_live_voice:
                spoken = await self.gemini_live_voice.speak(value)
            # Use Kokoro (local) if Live Kore was unavailable.
            if not spoken and self.tts_manager and self.tts_manager.kokoro:  # type: ignore[union-attr]
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.tts_manager.kokoro.play(value, blocking=True)  # type: ignore[union-attr]
                )
                spoken = True
            elif not spoken and self.tts_manager and self.tts_manager.gemini:  # type: ignore[union-attr]
                await self.tts_manager.gemini.play(value)  # type: ignore[union-attr]
                spoken = True
            if not spoken:
                await asyncio.to_thread(_speak_windows_sapi, value)
            print("[VOICE_TRACE] stage=TTS_START result=PASS", flush=True)
        except Exception as e:
            print(f"[Voice] TTS error: {e}")
        finally:
            self._voice_speaking = False
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

        print(f"[IPC] Processing message ({len(text)} chars, engine: {engine})")
        await self._append_conversation_message("user", text, engine)

        jarvis_reply = await self._try_jarvis_multi_action(text)
        if jarvis_reply:
            await self._append_conversation_message("assistant", jarvis_reply, "jarvis_plan")
            await self.send_response(msg.request_id, {
                'response': jarvis_reply,
                'engine': 'jarvis_plan',
            })
            return

        # ZARA-REMINDER-VOICE-BINDING-001: texto e voz usam o MESMO intent handler.
        reminder_reply = await self._try_reminder_intent(text)
        if reminder_reply:
            await self._append_conversation_message("assistant", reminder_reply, "reminder")
            await self.send_response(msg.request_id, {
                'response': reminder_reply,
                'engine': 'reminder',
            })
            return

        memory_reply = await self._try_operational_memory_intent(text)
        if memory_reply:
            await self._append_conversation_message("assistant", memory_reply, "operational_memory")
            await self.send_response(msg.request_id, {
                'response': memory_reply,
                'engine': 'operational_memory',
            })
            return

        # Autoconhecimento usa estado real e o mesmo caminho em texto e voz.
        self_reply = await self._try_self_knowledge(text)
        if self_reply:
            await self._append_conversation_message("assistant", self_reply, "self_knowledge")
            await self.send_response(msg.request_id, {
                'response': self_reply,
                'engine': 'self_knowledge',
            })
            return

        file_reply = await self._try_file_intent(text)
        if file_reply:
            await self._append_conversation_message("assistant", file_reply, "file_control")
            await self.send_response(msg.request_id, {
                'response': file_reply,
                'engine': 'file_control',
            })
            return

        # ZARA-COMPUTER-CONTROL-VOLUME-001: texto e voz usam o MESMO intent handler.
        pc_reply = await self._try_compound_pc_intent(text)
        if not pc_reply:
            pc_reply = await self._try_pc_intent(text)
        if pc_reply:
            await self._append_conversation_message("assistant", pc_reply, "pc_control")
            await self.send_response(msg.request_id, {
                'response': pc_reply,
                'engine': 'pc_control',
            })
            return

        if _looks_like_unhandled_local_action(text):
            reply = "Não encontrei um executor local verificado para esse comando; nenhuma ação foi realizada."
            await self._append_conversation_message("assistant", reply, "local_action_guard")
            await self.send_response(msg.request_id, {
                'response': reply,
                'engine': 'local_action_guard',
            })
            return

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

            # Text chat already returns this response to the invoking renderer.
            # Voice turns still use the asynchronous 'message' event path.

        except Exception as e:
            print(f"[IPC] Send message error: {e}")
            traceback.print_exc()
            await self._append_conversation_message(
                "system", "Backend indisponível para esta solicitação.", engine
            )
            await self.send_error(msg, str(e))

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

        try:
            result = await execute_action(action, **params)
            await self.send_response(msg.request_id, {'success': True, 'result': result})
        except Exception as e:
            print(f"[IPC] Action error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

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
                        GeminiLiveVoiceConfig(api_key=gemini_key, voice_name='Kore'),
                        on_state=self._on_gemini_live_state,
                        on_level=self._on_gemini_live_level,
                        on_turn=self._on_gemini_live_turn,
                        on_interrupt=self._on_gemini_live_interrupt,
                        on_error=self._on_gemini_live_error,
                    )
                status = await self.gemini_live_voice.start(timeout=12.0)
                self.voice_active = True
                self.voice_mode = 'gemini_live'
                print("[IPC] Gemini Live voice started (Kore, wake-gate)")
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

    async def handle_voice_stop(self, msg: IPCMessage):
        """Stop whichever voice transport is currently active."""
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.stop()
        if self.voice_pipeline:
            await asyncio.to_thread(self.voice_pipeline.stop)
        self.voice_active = False
        self.voice_mode = 'off'
        self._voice_speaking = False
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
            self.current_engine = 'auto_smart'
        available_ids = {engine['id'] for engine in engines}
        if self.current_engine not in available_ids:
            self.current_engine = 'auto_smart'

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
