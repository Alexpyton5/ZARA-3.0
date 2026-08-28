"""
Sistema de Voz Dual para Zara — Gemini Live Kore (nuvem) OU Local (faster-whisper + Kokoro/Piper).
Selecionável na UI junto com o modelo de IA.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class VoiceMode(Enum):
    GEMINI_LIVE_KORE = "gemini_live_kore"   # Nuvem: Gemini Live API + voz Kore
    LOCAL = "local"                          # Local: faster-whisper + Kokoro/Piper + qwen3:4b


@dataclass
class VoiceConfig:
    mode: VoiceMode = VoiceMode.LOCAL
    # Gemini Live Kore
    gemini_api_key: str = ""
    gemini_voice: str = "Kore"               # Kore, Puck, Charon, etc.
    gemini_language: str = "pt-BR"
    # Local
    stt_model: str = "small"                 # faster-whisper: tiny, base, small, medium, large-v3
    stt_device: str = "cpu"                  # cpu, cuda
    stt_compute_type: str = "int8"           # int8, float16
    tts_engine: str = "kokoro"               # kokoro, piper
    tts_voice: str = "pt-br"                 # voz do TTS
    tts_speed: float = 1.0
    vad_enabled: bool = True                 # Silero VAD para barge-in
    pipecat_enabled: bool = True             # Usar Pipecat para orquestração streaming

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "gemini_api_key": self.gemini_api_key,
            "gemini_voice": self.gemini_voice,
            "gemini_language": self.gemini_language,
            "stt_model": self.stt_model,
            "stt_device": self.stt_device,
            "stt_compute_type": self.stt_compute_type,
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "tts_speed": self.tts_speed,
            "vad_enabled": self.vad_enabled,
            "pipecat_enabled": self.pipecat_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceConfig:
        mode = VoiceMode(data.get("mode", "local"))
        return cls(
            mode=mode,
            gemini_api_key=data.get("gemini_api_key", ""),
            gemini_voice=data.get("gemini_voice", "Kore"),
            gemini_language=data.get("gemini_language", "pt-BR"),
            stt_model=data.get("stt_model", "small"),
            stt_device=data.get("stt_device", "cpu"),
            stt_compute_type=data.get("stt_compute_type", "int8"),
            tts_engine=data.get("tts_engine", "kokoro"),
            tts_voice=data.get("tts_voice", "pt-br"),
            tts_speed=data.get("tts_speed", 1.0),
            vad_enabled=data.get("vad_enabled", True),
            pipecat_enabled=data.get("pipecat_enabled", True),
        )


class VoiceEngine(ABC):
    """Interface base para engines de voz."""

    @abstractmethod
    async def initialize(self, config: VoiceConfig) -> bool:
        """Inicializa o engine. Retorna True se ok."""
        pass

    @abstractmethod
    async def start_listening(self, on_transcript: Callable[[str], None], on_speech_start: Callable[[], None]) -> None:
        """Inicia escuta contínua. Callbacks: on_transcript(texto), on_speech_start()."""
        pass

    @abstractmethod
    async def stop_listening(self) -> None:
        """Para escuta."""
        pass

    @abstractmethod
    async def speak(self, text: str, interruptible: bool = True) -> None:
        """Fala o texto. Se interruptible=True, pode ser cortado por fala do usuário."""
        pass

    @abstractmethod
    async def interrupt(self) -> None:
        """Interrompe fala atual (barge-in)."""
        pass

    @abstractmethod
    def is_speaking(self) -> bool:
        """Retorna se está falando no momento."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Desliga engine completamente."""
        pass


class VoiceManager:
    """Gerencia engines de voz e troca entre modos."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
        self.engine: VoiceEngine | None = None
        self.current_mode: VoiceMode = self.config.mode
        self._callbacks: dict[str, Callable] = {}

    def _load_config(self) -> VoiceConfig:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                return VoiceConfig.from_dict(data)
            except Exception:
                pass
        return VoiceConfig()

    def save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    async def initialize(self) -> bool:
        return await self._create_engine(self.config.mode)

    async def _create_engine(self, mode: VoiceMode) -> bool:
        if self.engine:
            await self.engine.shutdown()
            self.engine = None

        if mode == VoiceMode.GEMINI_LIVE_KORE:
            from voice.gemini_live_engine import GeminiLiveKoreEngine
            self.engine = GeminiLiveKoreEngine()
        elif mode == VoiceMode.LOCAL:
            from voice.local_engine import LocalVoiceEngine
            self.engine = LocalVoiceEngine()
        else:
            raise ValueError(f"Modo de voz desconhecido: {mode}")

        ok = await self.engine.initialize(self.config)
        if ok:
            self.current_mode = mode
            self.config.mode = mode
            self.save_config()
        return ok

    async def switch_mode(self, mode: VoiceMode) -> bool:
        """Troca modo de voz (ex: LOCAL -> GEMINI_LIVE_KORE)."""
        return await self._create_engine(mode)

    def get_available_modes(self) -> list[dict]:
        return [
            {
                "id": VoiceMode.LOCAL.value,
                "name": "Local (Offline, Grátis)",
                "description": "faster-whisper + Kokoro/Piper + qwen3:4b — 100% offline, sem cota",
                "requires_api_key": False,
                "current": self.current_mode == VoiceMode.LOCAL,
            },
            {
                "id": VoiceMode.GEMINI_LIVE_KORE.value,
                "name": "Gemini Live + Kore (Nuvem)",
                "description": "Gemini Live API nativo com voz Kore — ultra-baixa latência, emoção, streaming real",
                "requires_api_key": True,
                "current": self.current_mode == VoiceMode.GEMINI_LIVE_KORE,
            },
        ]

    def get_config_for_ui(self) -> dict:
        return {
            "current_mode": self.current_mode.value,
            "modes": self.get_available_modes(),
            "gemini_voices": ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr"],
            "local_tts_engines": ["kokoro", "piper"],
            "local_stt_models": ["tiny", "base", "small", "medium", "large-v3"],
            "config": self.config.to_dict(),
        }

    # Delegação para engine atual
    async def start_listening(self, on_transcript: Callable[[str], None], on_speech_start: Callable[[], None]) -> None:
        if self.engine:
            await self.engine.start_listening(on_transcript, on_speech_start)

    async def stop_listening(self) -> None:
        if self.engine:
            await self.engine.stop_listening()

    async def speak(self, text: str, interruptible: bool = True) -> None:
        if self.engine:
            await self.engine.speak(text, interruptible)

    async def interrupt(self) -> None:
        if self.engine:
            await self.engine.interrupt()

    def is_speaking(self) -> bool:
        return self.engine and self.engine.is_speaking()

    async def shutdown(self) -> None:
        if self.engine:
            await self.engine.shutdown()
            self.engine = None
