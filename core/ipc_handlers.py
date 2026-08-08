"""
ZARA 3.0 - Python IPC Handlers
Handles all IPC communication between Electron frontend and Python backend.
"""

import asyncio
import json
import os
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_windows_volume() -> float | None:
    """Read current master volume (0-100) via pycaw. Returns None if unavailable."""
    try:
        from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            return round(volume.GetMasterVolumeLevelScalar() * 100)
        finally:
            CoUninitialize()
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
        self._voice_loop_task: asyncio.Task | None = None
        self._tts_initialized: bool = False
        self.gemini_live_voice: GeminiLiveVoice | None = None
        self.voice_mode: str = "off"
        self.lab = None
        self._lab_background_tasks: set[asyncio.Task] = set()
        self.reminder_engine = None  # initialized in async init
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self.user_memory = None      # initialized in async init
        self.project_memory = None   # initialized in async init
        self.conversation_history = None  # Home transcript; separate from model memory
        self._shutdown_requested = False
        self._shutdown_started = False
        self._shutdown_complete = False

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

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    async def _disable_supercerebro(self) -> None:
        """Revoke local permission first, then clean only ZARA-owned Hermes."""
        self._set_supercerebro_state(False)
        if self.hermes:
            try:
                await self.hermes.disable_supercerebro()
            except Exception as exc:
                print(f"[IPC] Hermes disable warning: {exc}")

    async def shutdown(self) -> None:
        """Deterministically release runtime resources; safe to call repeatedly."""
        self._shutdown_requested = True
        if self._shutdown_started:
            return
        self._shutdown_started = True

        # Fail closed synchronously before any cleanup that can await or fail.
        self._set_supercerebro_state(False)

        for task in list(self._lab_background_tasks):
            task.cancel()
        if self._lab_background_tasks:
            await asyncio.gather(*self._lab_background_tasks, return_exceptions=True)
        self._lab_background_tasks.clear()

        if self._voice_loop_task and not self._voice_loop_task.done():
            self._voice_loop_task.cancel()
            await asyncio.gather(self._voice_loop_task, return_exceptions=True)
        self._voice_loop_task = None

        if self.gemini_live_voice:
            try:
                await self.gemini_live_voice.stop()
            except Exception as exc:
                print(f"[IPC] Gemini Live shutdown warning: {exc}")
        if self.voice_pipeline:
            try:
                self.voice_pipeline.stop()
            except Exception as exc:
                print(f"[IPC] Voice pipeline shutdown warning: {exc}")
        self.voice_active = False
        self.voice_mode = "off"

        if self.tts_manager:
            try:
                self.tts_manager.interrupt()
                if self.tts_manager.gemini:
                    await self.tts_manager.gemini.close()
            except Exception as exc:
                print(f"[IPC] TTS shutdown warning: {exc}")

        if self.reminder_engine:
            try:
                await asyncio.to_thread(self.reminder_engine.stop)
            except Exception as exc:
                print(f"[IPC] Reminder shutdown warning: {exc}")

        if self.hermes:
            try:
                await self.hermes.shutdown()
            except Exception as exc:
                print(f"[IPC] Hermes shutdown warning: {exc}")

        self._shutdown_complete = True

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

        # The Home transcript is local UI state, not semantic/episodic memory.
        # Keeping it in its own bounded SQLite store prevents raw conversations
        # from being injected into prompts or appearing in Memory Galaxy.
        try:
            from core.conversation_history import ConversationHistory

            self.conversation_history = ConversationHistory()
            await asyncio.to_thread(self.conversation_history.list_recent, 1)
        except Exception as exc:
            essential_errors.append(f"conversation_history: {exc}")
            self.conversation_history = None
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
        except Exception as exc:
            self.project_memory = None
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
        if user_text:
            await self._append_conversation_message("user", user_text, "gemini_live")
            await self.send_event('message', {
                'role': 'user',
                'content': user_text,
                'engine': 'gemini_live',
                'timestamp': datetime.now().isoformat(),
            })
        if model_text:
            await self._append_conversation_message("assistant", model_text, "gemini_live")
            await self.send_event('message', {
                'role': 'assistant',
                'content': model_text,
                'engine': 'gemini_live',
                'timestamp': datetime.now().isoformat(),
            })
        if self.memory and (user_text or model_text):
            await self.memory.add_conversation(user_text, model_text, 'gemini_live')

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
            if res.kind == "needs_clarification":
                return "Que horas?"
            return None
        except Exception:
            return None

    async def _try_pc_intent(self, text: str) -> str | None:
        """Deterministic PC intent (ZARA-COMPUTER-CONTROL-VOLUME-001).

        Maps voice/text PC commands to existing os_volume action through
        the existing capability gate (Supercérebro). Returns the ZARA reply
        or None so the normal brain handles it. Never an LLM decision.
        """
        try:
            if not (text or "").strip():
                return None
            from core.pc_voice_intent import PcVoiceIntentDetector
            detector = PcVoiceIntentDetector(pc_control_allowed=bool(self.supercerebro_active))
            res = detector.detect(text)
            if not res.is_pc_intent:
                return None
            if res.blocked:
                return res.reply or "Para controlar o computador, ative o Supercérebro."
            from core.action_registry import execute_action
            params = {}
            if res.action == "os_volume":
                if res.param in ("up", "down"):
                    current = _read_windows_volume()
                    if current is None:
                        return "Não consegui ler o volume do sistema."
                    params["level"] = max(0, min(100, current + (10 if res.param == "up" else -10)))
                else:
                    try:
                        params["level"] = max(0, min(100, int(float(res.param))))
                    except (TypeError, ValueError):
                        return None
            result = await execute_action(res.action, **params)
            if result is not None and getattr(result, "success", False):
                level = params.get("level")
                return f"Volume definido para {level}%." if level is not None else "Pronto."
            error = str(getattr(result, "error", "") or "")
            return f"Não consegui executar essa ação. {error}".strip()
        except Exception:
            return None

    async def _process_voice_message(self, text: str):
        """Process voice message through orchestrator/model router"""
        try:
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
            # ZARA-COMPUTER-CONTROL-VOLUME-001: PC intent antes do LLM.
            pc_reply = await self._try_pc_intent(text)
            if pc_reply:
                await self._append_conversation_message("assistant", pc_reply, "pc_control")
                await self.send_event('message', {
                    'role': 'assistant',
                    'content': pc_reply,
                    'engine': 'pc_control',
                    'timestamp': datetime.now().isoformat(),
                })
                await self._speak_response(pc_reply)
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
                self.voice_pipeline.resume_listening()
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
        if not self.tts_manager:
            return

        if not self._tts_initialized:
            try:
                await asyncio.to_thread(self.tts_manager.initialize)
                self._tts_initialized = True
            except Exception as exc:
                self._tts_initialized = False
                print(f"[Voice] TTS lazy initialization failed: {exc}")
                return

        self._voice_speaking = True
        await self.send_event('state-change', 'SPEAKING')
        await self.send_event('voice-level', {
            'level': 0.5,
            'tone': 0.5,
            'speaking': True,
            'state': 'SPEAKING'
        })

        try:
            # Use Kokoro (local) if available
            if self.tts_manager and self.tts_manager.kokoro:  # type: ignore[union-attr]
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.tts_manager.kokoro.play(text, blocking=True)  # type: ignore[union-attr]
                )
            elif self.tts_manager and self.tts_manager.gemini:  # type: ignore[union-attr]
                await self.tts_manager.gemini.play(text)  # type: ignore[union-attr]
        except Exception as e:
            print(f"[Voice] TTS error: {e}")
        finally:
            self._voice_speaking = False
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
            'conversation-history-list': self.handle_conversation_history_list,
            'conversation-history-clear': self.handle_conversation_history_clear,
            'shutdown': self.handle_shutdown,
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
        await self.send_response(msg.request_id, {
            'success': True,
            'state': 'QUEUED',
            'target': target,
        })

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
            try:
                connected = await self.hermes.enable_supercerebro()
            except Exception as exc:
                connected = False
                print(f"[IPC] Hermes enable warning: {exc}")
            if not connected:
                await self._disable_supercerebro()
                await self.send_event('supercerebro-change', False)
                await self.send_error(msg, "Hermes Gateway is offline")
                return
            self._set_supercerebro_state(True)
        else:
            # Revoke local permission before touching the remote integration.
            # A disconnect error must never leave PC control enabled.
            await self._disable_supercerebro()

        print(f"[IPC] Supercerebro {'enabled' if self.supercerebro_active else 'disabled'}")
        await self.send_event('supercerebro-change', self.supercerebro_active)
        await self.send_response(msg.request_id, {
            'success': True,
            'active': self.supercerebro_active,
            'connected': bool(self.hermes and self.hermes.is_connected),
        })

    async def handle_shutdown(self, msg: IPCMessage):
        """Acknowledge Electron shutdown and make both IPC loops exit."""
        self._shutdown_requested = True
        await self._disable_supercerebro()
        await self.send_response(msg.request_id, {'success': True, 'shutting_down': True})

    async def handle_send_message(self, msg: IPCMessage):
        payload = msg.payload or {}
        text = str(payload.get('text', '') or payload.get('message', '')).strip()
        engine = str(payload.get('engine', self.current_engine) or self.current_engine)

        if not text:
            await self.send_error(msg, "No text provided")
            return

        print(f"[IPC] Processing message ({len(text)} chars, engine: {engine})")
        await self._append_conversation_message("user", text, engine)

        # ZARA-REMINDER-VOICE-BINDING-001: texto e voz usam o MESMO intent handler.
        reminder_reply = await self._try_reminder_intent(text)
        if reminder_reply:
            await self._append_conversation_message("assistant", reminder_reply, "reminder")
            await self.send_response(msg.request_id, {
                'response': reminder_reply,
                'engine': 'reminder',
            })
            return

        # ZARA-COMPUTER-CONTROL-VOLUME-001: texto e voz usam o MESMO intent handler.
        pc_reply = await self._try_pc_intent(text)
        if pc_reply:
            await self._append_conversation_message("assistant", pc_reply, "pc_control")
            await self.send_response(msg.request_id, {
                'response': pc_reply,
                'engine': 'pc_control',
            })
            return

        # ZARA-USER-MEMORY-CONTEXT-001: enriquece com memorias relevantes (top-K)
        text = await self._enrich_with_memory(text)

        try:
            history = payload.get('history', [])
            if self.supercerebro_active and self.hermes and self.hermes.enabled and self.hermes.is_connected:
                response = await self.hermes.send_message(text, history=history, team="general")
                engine_used = "hermes_gateway"
            elif self.orchestrator:
                response = await self.orchestrator.process_message(text, engine=engine)
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
                        on_error=self._on_gemini_live_error,
                    )
                status = await self.gemini_live_voice.start()
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
                await self.send_error(msg, f"Gemini Live/Kore indisponível: {exc}")
                return

        # Backward-compatible local path for machines without a Gemini key.
        if not VOICE_AVAILABLE or not self.voice_pipeline:
            await self.send_error(msg, "Gemini API key missing and local voice pipeline unavailable")
            return

        try:
            if not self.voice_pipeline.vosk or not self.voice_pipeline.audio:
                await asyncio.to_thread(self.voice_pipeline.initialize)
            self.voice_pipeline.start()
            self.voice_active = True
            self.voice_mode = 'local'
            print("[IPC] Local voice pipeline started")
            await self.send_response(msg.request_id, {
                'success': True, 'state': 'LISTENING', 'mode': 'local',
                'voice': 'Kokoro/Vosk fallback'
            })
            await self.send_event('state-change', 'LISTENING')
        except Exception as e:
            print(f"[IPC] Voice start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))

    async def handle_voice_stop(self, msg: IPCMessage):
        """Stop whichever voice transport is currently active."""
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.stop()
        if self.voice_pipeline:
            self.voice_pipeline.stop()
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
        }
        await self.send_response(msg.request_id, status)


async def main() -> int:
    """Main entry point for Python sidecar"""

    async def send_to_electron(msg: IPCMessage):
        """Send message to Electron via stdout"""
        print(serialize_ipc_message(msg), flush=True)

    handler = IPCHandler(send_to_electron)
    await handler.initialize()

    print("[ZARA] IPC Handler ready", flush=True)
    print("SYS: Interface neural pronta", flush=True)  # Signal ready

    try:
        # Windows-compatible stdin reading
        if sys.platform == 'win32':
            await _run_windows_ipc(handler)
        else:
            await _run_unix_ipc(handler)
    finally:
        # stdin EOF is also an ownership signal: Electron disappeared, so all
        # resources launched by this sidecar must be released.
        await handler.shutdown()

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
    transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    try:
        await _consume_ipc_reader(handler, reader)
    except KeyboardInterrupt:
        pass
    finally:
        transport.close()


async def _consume_ipc_reader(handler: IPCHandler, reader: asyncio.StreamReader) -> None:
    while not handler.shutdown_requested:
        line = await reader.readline()
        if not line:
            break
        try:
            data = json.loads(line.decode().strip())
            msg = IPCMessage(**data)
            await handler.handle_message(msg)
        except json.JSONDecodeError:
            continue
        except Exception as exc:
            print(f"[IPC] Parse error: {exc}", file=sys.stderr)


def _windows_stdin_is_pipe() -> bool:
    """Distinguish Electron's pipe from an interactive development console."""
    try:
        import ctypes
        import msvcrt

        file_type_pipe = 0x0003
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        return ctypes.windll.kernel32.GetFileType(handle) == file_type_pipe
    except (AttributeError, OSError, ValueError):
        return False


async def _run_windows_ipc(handler: IPCHandler):
    """Use non-blocking pipe polling in packaged mode; threads only for a console."""
    if _windows_stdin_is_pipe():
        await _run_windows_pipe_ipc(handler)
    else:
        await _run_windows_console_ipc(handler)


async def _run_windows_pipe_ipc(handler: IPCHandler) -> None:
    """Poll Electron's named pipe without any thread blocked in ``sys.stdin``.

    Both a blocked TextIO thread and Proactor ``connect_read_pipe`` prevent or
    break multiprocessing bootstrap in this PyInstaller onefile application.
    ``PeekNamedPipe`` tells us when a direct ``os.read`` is safe, allowing the
    event loop to remain responsive and making broken-pipe EOF deterministic.
    """
    import ctypes
    import msvcrt
    from ctypes import wintypes

    max_buffer_bytes = 1024 * 1024
    poll_interval_seconds = 0.02
    broken_pipe_errors = {6, 109, 232, 233}
    stdin_fd = sys.stdin.fileno()
    msvcrt.setmode(stdin_fd, os.O_BINARY)
    handle = msvcrt.get_osfhandle(stdin_fd)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    peek_named_pipe = kernel32.PeekNamedPipe
    peek_named_pipe.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    peek_named_pipe.restype = wintypes.BOOL
    buffer = bytearray()

    while not handler.shutdown_requested:
        available = wintypes.DWORD(0)
        ok = peek_named_pipe(handle, None, 0, None, ctypes.byref(available), None)
        if not ok:
            error = ctypes.get_last_error()
            if error in broken_pipe_errors:
                break
            raise OSError(error, "PeekNamedPipe failed for Electron stdin")

        if available.value == 0:
            await asyncio.sleep(poll_interval_seconds)
            continue

        chunk = os.read(stdin_fd, min(int(available.value), 64 * 1024))
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_buffer_bytes:
            raise ValueError("Electron IPC input exceeded the 1 MiB safety limit")

        while b"\n" in buffer and not handler.shutdown_requested:
            raw_line, _, remainder = buffer.partition(b"\n")
            buffer = bytearray(remainder)
            await _handle_ipc_bytes(handler, raw_line)


async def _handle_ipc_bytes(handler: IPCHandler, raw_line: bytes) -> None:
    if not raw_line.strip():
        return
    try:
        data = json.loads(raw_line.decode("utf-8").strip())
        await handler.handle_message(IPCMessage(**data))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    except Exception as exc:
        print(f"[IPC] Parse error: {exc}", file=sys.stderr)


async def _run_windows_console_ipc(handler: IPCHandler) -> None:
    """Interactive/source fallback where Proactor cannot wrap a console."""
    import queue
    import threading

    stdin_queue: queue.Queue[str] = queue.Queue()
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
            # Before this signal existed, a closed Electron pipe left the
            # Windows loop sleeping forever inside the PyInstaller child.
            stop_event.set()

    reader_thread = threading.Thread(target=read_stdin, daemon=True)
    reader_thread.start()

    try:
        while not stop_event.is_set() and not handler.shutdown_requested:
            try:
                # Never block the asyncio loop waiting for stdin. Voice-level
                # callbacks and other async work need this loop to stay free.
                line = stdin_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)
                continue

            try:
                data = json.loads(line)
                msg = IPCMessage(**data)
                await handler.handle_message(msg)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[IPC] Parse error: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


if __name__ == '__main__':
    asyncio.run(main())
