"""
Voice TTS — Kokoro ONNX local neural text-to-speech.
High-quality, offline, multi-language. Fallback to Gemini Live when online.
"""
from __future__ import annotations

import asyncio
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

# Optional imports
try:
    import kokoro_onnx
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    kokoro_onnx = None

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    sd = None

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from core.paths import user_data_dir


@dataclass
class TTSConfig:
    """TTS configuration."""
    # Kokoro
    kokoro_model_path: str = ""
    kokoro_voices_path: str = ""
    default_voice: str = "pf_dora"  # Portuguese (Brazil), female
    sample_rate: int = 24000

    # Gemini Live fallback
    gemini_api_key: str = ""
    gemini_voice: str = "Puck"  # Puck, Charon, Kore, Fenrir, Aoede
    gemini_model: str = "gemini-1.5-flash"

    # Audio output
    output_device: int | None = None

    # Behavior
    prefer_local: bool = True
    interruptible: bool = True


class KokoroTTS:
    """Local neural TTS using Kokoro ONNX."""

    # Available voices (Kokoro v0.19+)
    VOICES = {
        # US English Female
        "af_heart": {"lang": "en-us", "gender": "f", "desc": "Warm, natural"},
        "af_bella": {"lang": "en-us", "gender": "f", "desc": "Clear, professional"},
        "af_nicole": {"lang": "en-us", "gender": "f", "desc": "Soft, gentle"},
        "af_sarah": {"lang": "en-us", "gender": "f", "desc": "Bright, energetic"},
        "af_sky": {"lang": "en-us", "gender": "f", "desc": "Airy, ethereal"},

        # US English Male
        "am_michael": {"lang": "en-us", "gender": "m", "desc": "Deep, authoritative"},
        "am_adam": {"lang": "en-us", "gender": "m", "desc": "Casual, friendly"},
        "am_liam": {"lang": "en-us", "gender": "m", "desc": "Young, modern"},

        # British English
        "bf_emma": {"lang": "en-gb", "gender": "f", "desc": "British, polished"},
        "bf_isabella": {"lang": "en-gb", "gender": "f", "desc": "British, warm"},
        "bm_george": {"lang": "en-gb", "gender": "m", "desc": "British, distinguished"},
        "bm_lewis": {"lang": "en-gb", "gender": "m", "desc": "British, casual"},

        # Portuguese (Brazil)
        "pf_dora": {"lang": "pt-br", "gender": "f", "desc": "Portuguese BR, natural"},
        "pm_alex": {"lang": "pt-br", "gender": "m", "desc": "Portuguese BR, clear"},

        # Other languages
        "jf_alpha": {"lang": "ja", "gender": "f", "desc": "Japanese"},
        "jm_kumo": {"lang": "ja", "gender": "m", "desc": "Japanese"},
        "zf_xiaobei": {"lang": "zh", "gender": "f", "desc": "Chinese"},
        "zm_yunjian": {"lang": "zh", "gender": "m", "desc": "Chinese"},
        "ff_siwis": {"lang": "fr", "gender": "f", "desc": "French"},
        "hf_alpha": {"lang": "hi", "gender": "f", "desc": "Hindi"},
        "if_sara": {"lang": "id", "gender": "f", "desc": "Indonesian"},
        "ef_dora": {"lang": "es", "gender": "f", "desc": "Spanish"},
        "em_alex": {"lang": "es", "gender": "m", "desc": "Spanish"},
    }

    def __init__(self, config: TTSConfig):
        if not KOKORO_AVAILABLE:
            raise RuntimeError("Kokoro ONNX not installed. Run: uv pip install kokoro-onnx")

        self.config = config
        self.model: kokoro_onnx.Kokoro | None = None
        self._load_model()

    def _load_model(self):
        """Load or download Kokoro model."""
        model_dir = user_data_dir() / "models" / "kokoro"
        model_dir.mkdir(parents=True, exist_ok=True)

        if self.config.kokoro_model_path and Path(self.config.kokoro_model_path).exists():
            model_path = self.config.kokoro_model_path
            voices_path = self.config.kokoro_voices_path or str(model_dir / "voices.json")
        else:
            model_path = str(model_dir / "kokoro-v0.19.onnx")
            voices_path = str(model_dir / "voices.json")

            # Download if not exists
            if not Path(model_path).exists():
                print("[Kokoro] Downloading model...")
                import urllib.request
                url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0.19.onnx"
                urllib.request.urlretrieve(url, model_path)

            if not Path(voices_path).exists():
                print("[Kokoro] Downloading voices...")
                url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json"
                urllib.request.urlretrieve(url, voices_path)

        self.model = kokoro_onnx.Kokoro(model_path, voices_path)
        print(f"[Kokoro] Model loaded: {model_path}")

    def synthesize(self, text: str, voice: str = None, speed: float = 1.0) -> tuple[np.ndarray, int]:
        """
        Synthesize text to audio.
        Returns (audio_array, sample_rate).
        """
        if self.model is None:
            raise RuntimeError("Kokoro model not loaded")

        voice = voice or self.config.default_voice
        if voice not in self.VOICES:
            print(f"[Kokoro] Unknown voice '{voice}', using default")
            voice = self.config.default_voice

        # Generate audio
        audio = self.model.generate(
            text=text,
            voice=voice,
            speed=speed,
            lang=self.VOICES[voice]["lang"],
        )

        return audio, self.config.sample_rate

    def synthesize_to_file(self, text: str, output_path: str, voice: str = None, speed: float = 1.0):
        """Synthesize and save to WAV file."""
        audio, sr = self.synthesize(text, voice, speed)

        # Convert to int16
        if NUMPY_AVAILABLE:
            audio_int16 = (audio * 32767).astype(np.int16)
        else:
            audio_int16 = [int(max(-32768, min(32767, s * 32767))) for s in audio]

        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            if NUMPY_AVAILABLE:
                wf.writeframes(audio_int16.tobytes())
            else:
                import struct
                wf.writeframes(struct.pack(f"<{len(audio_int16)}h", *audio_int16))

        return output_path

    def play(self, text: str, voice: str = None, speed: float = 1.0, blocking: bool = True):
        """Synthesize and play audio directly."""
        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError("sounddevice not installed for playback")

        audio, sr = self.synthesize(text, voice, speed)

        if NUMPY_AVAILABLE:
            audio_data = (audio * 32767).astype(np.int16)
        else:
            audio_data = [int(max(-32768, min(32767, s * 32767))) for s in audio]

        if blocking:
            sd.play(audio_data, sr, device=self.config.output_device)
            sd.wait()
        else:
            sd.play(audio_data, sr, device=self.config.output_device)

    @classmethod
    def list_voices(cls) -> dict:
        """List all available voices."""
        return cls.VOICES.copy()


class GeminiTTS:
    """Gemini Live TTS fallback (requires API key and internet)."""

    def __init__(self, config: TTSConfig):
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")

        if not config.gemini_api_key:
            raise ValueError("Gemini API key required for Gemini TTS")

        self.config = config
        self.client = httpx.AsyncClient(timeout=60.0)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def synthesize(self, text: str, voice: str = None) -> bytes:
        """Synthesize using Gemini TTS API. Returns WAV bytes."""
        voice = voice or self.config.gemini_voice

        # Use Gemini's native audio output (requires specific model)
        url = f"{self.base_url}/models/{self.config.gemini_model}:generateContent"

        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice}
                    }
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.config.gemini_api_key,
        }

        resp = await self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # Extract audio data (base64 encoded)
        import base64
        audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return base64.b64decode(audio_b64)

    async def play(self, text: str, voice: str = None):
        """Synthesize and play."""
        audio_bytes = await self.synthesize(text, voice)

        # Save to temp file and play
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            if SOUNDDEVICE_AVAILABLE:
                import soundfile as sf
                data, sr = sf.read(tmp_path)
                sd.play(data, sr, device=self.config.output_device)
                sd.wait()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def close(self):
        await self.client.aclose()


class TTSManager:
    """
    Unified TTS manager with automatic fallback.
    Prefers local (Kokoro), falls back to Gemini Live.
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self.kokoro: KokoroTTS | None = None
        self.gemini: GeminiTTS | None = None
        self._current_playback = None
        self._interrupt_event = threading.Event()

    def initialize(self):
        """Initialize available TTS engines."""
        # Try Kokoro first (local)
        if self.config.prefer_local:
            try:
                self.kokoro = KokoroTTS(self.config)
                print("[TTS] Kokoro initialized (local)")
            except Exception as e:
                print(f"[TTS] Kokoro init failed: {e}")
                self.kokoro = None

        # Try Gemini as fallback
        if self.config.gemini_api_key:
            try:
                self.gemini = GeminiTTS(self.config)
                print("[TTS] Gemini TTS initialized (cloud fallback)")
            except Exception as e:
                print(f"[TTS] Gemini init failed: {e}")
                self.gemini = None

        if not self.kokoro and not self.gemini:
            raise RuntimeError("No TTS engine available. Install kokoro-onnx or set Gemini API key.")

    def speak(self, text: str, voice: str = None, speed: float = 1.0, blocking: bool = True):
        """Speak text using best available engine."""
        self._interrupt_event.clear()

        # Try Kokoro first
        if self.kokoro:
            try:
                if blocking:
                    self.kokoro.play(text, voice, speed, blocking=True)
                else:
                    # Run in thread for non-blocking
                    t = threading.Thread(
                        target=self.kokoro.play,
                        args=(text, voice, speed, True),
                        daemon=True
                    )
                    t.start()
                    self._current_playback = t
                return
            except Exception as e:
                print(f"[TTS] Kokoro failed, trying fallback: {e}")

        # Fallback to Gemini
        if self.gemini:
            asyncio.run(self._gemini_speak(text, voice))
            return

        raise RuntimeError("No TTS engine available")

    async def _gemini_speak(self, text: str, voice: str = None):
        """Speak via Gemini (async)."""
        await self.gemini.play(text, voice)

    def interrupt(self):
        """Interrupt current playback."""
        self._interrupt_event.set()
        if SOUNDDEVICE_AVAILABLE:
            sd.stop()
        if self._current_playback and self._current_playback.is_alive():
            # Thread will check interrupt event
            pass
        print("[TTS] Interrupted")

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        if SOUNDDEVICE_AVAILABLE:
            return sd.get_stream().active if sd.get_stream() else False
        return self._current_playback is not None and self._current_playback.is_alive()

    def cleanup(self):
        """Cleanup resources."""
        self.interrupt()
        if self.gemini:
            asyncio.run(self.gemini.close())


# Factory
def create_tts_manager(
    prefer_local: bool = True,
    gemini_api_key: str = "",
    default_voice: str = "pf_dora",
) -> TTSManager:
    """Create TTS manager with config."""
    config = TTSConfig(
        prefer_local=prefer_local,
        gemini_api_key=gemini_api_key,
        default_voice=default_voice,
    )
    manager = TTSManager(config)
    manager.initialize()
    return manager
