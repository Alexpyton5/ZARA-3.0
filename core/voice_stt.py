"""
Voice STT — Vosk offline speech recognition + Porcupine wake word.
Thread-safe, async-friendly, designed for ZARA 3.0 neural interface.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Optional imports - gracefully handle missing deps
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    vosk = None

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    pvporcupine = None

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

from core.paths import user_data_dir


class VoiceNotConfiguredError(RuntimeError):
    """Local voice weights/backends are missing.

    Distinct from a runtime failure: nothing is broken, the feature simply has
    no model configured. ZARA never downloads weights on its own.
    """


@dataclass
class VoiceConfig:
    """Voice pipeline configuration."""
    # Vosk
    vosk_model_path: str = ""  # Auto-download if empty
    vosk_sample_rate: int = 16000

    # Porcupine
    porcupine_access_key: str = ""  # Required for Porcupine
    wake_words: list[str] = None  # ["ZARA", "SARA", "HEY ZARA"]
    porcupine_sensitivity: float = 0.6

    # Audio
    input_device: int | None = None
    channels: int = 1
    chunk_size: int = 4096

    # VAD (Voice Activity Detection)
    vad_threshold: float = 0.02
    vad_silence_chunks: int = 30  # ~0.5s at 16kHz/4096

    def __post_init__(self):
        if self.wake_words is None:
            self.wake_words = ["ZARA", "SARA"]


class VoskSTT:
    """Offline speech-to-text using Vosk."""

    def __init__(self, config: VoiceConfig):
        if not VOSK_AVAILABLE:
            raise VoiceNotConfiguredError("STT_BACKEND_NOT_CONFIGURED: vosk não instalado.")

        self.config = config
        self.model: vosk.Model | None = None
        self.recognizer: vosk.KaldiRecognizer | None = None
        self._load_model()

    def _load_model(self):
        """Load or download Vosk model."""
        if self.config.vosk_model_path and Path(self.config.vosk_model_path).exists():
            model_path = self.config.vosk_model_path
        else:
            # Default to user data dir
            model_dir = user_data_dir() / "models" / "vosk"
            model_dir.mkdir(parents=True, exist_ok=True)

            # Check for Portuguese model
            pt_model = model_dir / "vosk-model-small-pt-0.3"
            en_model = model_dir / "vosk-model-small-en-us-0.15"

            if pt_model.exists():
                model_path = str(pt_model)
            elif en_model.exists():
                model_path = str(en_model)
            else:
                # No weights on disk. Never download autonomously: report an
                # honest NOT_CONFIGURED state so the caller can surface it.
                raise VoiceNotConfiguredError(
                    "STT_MODEL_NOT_CONFIGURED: nenhum modelo Vosk encontrado em "
                    f"{model_dir}. Instale/aponte vosk_model_path manualmente."
                )

        self.model = vosk.Model(model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, self.config.vosk_sample_rate)
        self.recognizer.SetWords(True)
        print(f"[Vosk] Model loaded: {model_path}")

    def recognize(self, audio_data: bytes) -> str | None:
        """Recognize speech from audio bytes. Returns text or None."""
        if self.recognizer.AcceptWaveform(audio_data):
            result = json.loads(self.recognizer.Result())
            return result.get("text", "").strip()
        return None

    def partial_recognize(self, audio_data: bytes) -> str | None:
        """Get partial recognition result (for live feedback)."""
        self.recognizer.AcceptWaveform(audio_data)
        result = json.loads(self.recognizer.PartialResult())
        return result.get("partial", "").strip()

    def reset(self):
        """Reset recognizer for new utterance."""
        self.recognizer = vosk.KaldiRecognizer(self.model, self.config.vosk_sample_rate)
        self.recognizer.SetWords(True)


class PorcupineWakeWord:
    """Wake word detection using Porcupine."""

    def __init__(self, config: VoiceConfig):
        if not PORCUPINE_AVAILABLE:
            raise RuntimeError("Porcupine not installed. Run: uv pip install pvporcupine")

        if not config.porcupine_access_key:
            raise ValueError("Porcupine access key required. Get free key at https://console.picovoice.ai/")

        self.config = config
        self.handle: pvporcupine.Porcupine | None = None
        self._init_porcupine()

    def _init_porcupine(self):
        """Initialize Porcupine with built-in keywords."""
        # Map wake words to Porcupine built-in keywords
        keyword_map = {
            "ZARA": "jarvis",      # Closest built-in
            "SARA": "alexa",       # Closest built-in
            "HEY ZARA": "hey google",
            "OK ZARA": "ok google",
            "COMPUTER": "computer",
        }

        keywords = []
        sensitivities = []

        for ww in self.config.wake_words:
            kw = keyword_map.get(ww.upper(), "jarvis")
            if kw not in keywords:
                keywords.append(kw)
                sensitivities.append(self.config.porcupine_sensitivity)

        self.handle = pvporcupine.create(
            access_key=self.config.porcupine_access_key,
            keywords=keywords,
            sensitivities=sensitivities,
        )
        print(f"[Porcupine] Initialized with keywords: {keywords}")

    def process(self, pcm: bytes) -> int:
        """Process audio frame. Returns keyword index if detected, -1 otherwise."""
        if not NUMPY_AVAILABLE:
            # Convert bytes to int16 array manually
            import struct
            pcm_array = struct.unpack(f"{len(pcm)//2}h", pcm)
        else:
            pcm_array = np.frombuffer(pcm, dtype=np.int16)

        return self.handle.process(pcm_array)

    @property
    def frame_length(self) -> int:
        return self.handle.frame_length if self.handle else 512

    @property
    def sample_rate(self) -> int:
        return self.handle.sample_rate if self.handle else 16000

    def delete(self):
        if self.handle:
            self.handle.delete()
            self.handle = None


class AudioInput:
    """Cross-platform audio input using sounddevice."""

    def __init__(self, config: VoiceConfig):
        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError("sounddevice not installed. Run: uv pip install sounddevice")

        self.config = config
        self.stream: sd.RawInputStream | None = None
        self.queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self._running = False

    def start(self):
        """Start audio capture."""
        if self._running:
            return

        def callback(indata, frames, time, status):
            if status:
                print(f"[Audio] Status: {status}")
            if self._running:
                try:
                    self.queue.put_nowait(bytes(indata))
                except queue.Full:
                    pass  # Drop frame if queue full

        self._running = True
        try:
            self.stream = sd.RawInputStream(
                samplerate=self.config.vosk_sample_rate,
                blocksize=self.config.chunk_size,
                device=self.config.input_device,
                channels=self.config.channels,
                dtype="int16",
                callback=callback,
            )
            self.stream.start()
            print(f"[Audio] Started: {self.config.vosk_sample_rate}Hz, {self.config.channels}ch")
        except sd.PortAudioError as exc:
            self._running = False
            stream, self.stream = self.stream, None
            if stream is not None:
                for cleanup in (stream.stop, stream.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
            raise VoiceNotConfiguredError(f"AUDIO_INPUT_FAILED: {exc} permanent=True") from exc
        except Exception:
            self._running = False
            stream, self.stream = self.stream, None
            if stream is not None:
                for cleanup in (stream.stop, stream.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
            raise

    def stop(self):
        """Stop audio capture."""
        self._running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        print("[Audio] Stopped")

    def read(self, timeout: float = 0.1) -> bytes | None:
        """Read audio chunk from queue."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class VoicePipeline:
    """
    Complete voice pipeline: Wake word -> STT -> Callback.
    Designed to run in background thread with async callbacks.
    """

    def __init__(
        self,
        config: VoiceConfig,
        on_wake: Callable[[], None],
        on_speech: Callable[[str], None],
        on_partial: Callable[[str], None] = None,
        on_level: Callable[[float], None] = None,
    ):
        self.config = config
        self.on_wake = on_wake
        self.on_speech = on_speech
        self.on_partial = on_partial
        self.on_level = on_level

        self.vosk: VoskSTT | None = None
        self.porcupine: PorcupineWakeWord | None = None
        self.audio: AudioInput | None = None

        self._thread: threading.Thread | None = None
        self._running = False
        self._state = "SLEEPING"  # SLEEPING, LISTENING, PROCESSING, PAUSED
        # FRENTE2-ITEM4 (2026-09-29): contagem de referência do mute. O
        # _speak_response e o NarradorDeVoz pausam pelo mesmo funil; sem
        # refcount, um retomaria o mic com a outra fala ainda no ar.
        self._pause_depth = 0
        self._pause_lock = threading.Lock()
        self._silence_chunks = 0
        self._speech_buffer: list[bytes] = []
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def initialize(self):
        """Initialize all components."""
        print("[Voice] Initializing...")

        # Initialize Vosk STT
        self.vosk = VoskSTT(self.config)

        # Initialize Porcupine wake word (if access key provided)
        if self.config.porcupine_access_key:
            try:
                self.porcupine = PorcupineWakeWord(self.config)
            except Exception as e:
                print(f"[Voice] Porcupine init failed: {e}")
                self.porcupine = None

        # Initialize audio input
        self.audio = AudioInput(self.config)

        print("[Voice] Initialized")

    def start(self):
        """Start explicit microphone listening in a background thread."""
        if self._running:
            self._state = "LISTENING"
            return

        if not self.vosk or not self.audio:
            self.initialize()

        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            # start() may be intentionally moved to a worker thread so a bad
            # PortAudio driver cannot freeze the IPC loop. Preserve the loop
            # supplied by the async owner for callback dispatch.
            pass

        # When Porcupine is configured, the microphone starts behind the wake
        # gate. Push-to-talk/local fallback keeps the previous LISTENING mode.
        self._state = "SLEEPING" if self.porcupine else "LISTENING"
        self._speech_buffer = []
        self._silence_chunks = 0
        self._running = True
        try:
            self.audio.start()
        except VoiceNotConfiguredError as e:
            self._running = False
            try:
                self.audio.stop()
            except Exception:
                pass
            self._state = "ERROR"
            if hasattr(self, 'on_error') and self.on_error:
                try:
                    self.on_error(e)
                except Exception:
                    pass  # Ignore errors in error callback
            return
        except Exception as e:
            # Handle other unexpected errors during audio start
            self._running = False
            try:
                self.audio.stop()
            except Exception:
                pass
            self._state = "ERROR"
            if hasattr(self, 'on_error') and self.on_error:
                try:
                    self.on_error(e)
                except Exception:
                    pass  # Ignore errors in error callback
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="VoicePipeline")
        self._thread.start()
        print(f"[Voice] Pipeline started ({self._state})")

    def stop(self):
        """Stop the voice pipeline."""
        self._running = False
        if self.audio:
            self.audio.stop()
        if self._thread:
            self._thread.join(timeout=2)
        if self.porcupine:
            self.porcupine.delete()
        self._state = "STOPPED"
        self._pause_depth = 0
        print("[Voice] Pipeline stopped")

    def _dispatch(self, callback, *args) -> None:
        """Dispatch a callback safely onto the asyncio loop captured at start()."""
        if callback is None:
            return
        loop = self._event_loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._safe_call(callback, *args), loop)

    def pause_listening(self) -> None:
        """Discard microphone audio while ZARA is speaking.

        This is the local self-listening guard.  Audio continues to be drained
        by the worker thread, but it is never handed to Vosk while paused.

        FRENTE2-ITEM4: contagem de referência — a segunda pausa aproveita
        o mute já ativo; só a última retomada religa o microfone.
        """
        if not self._running:
            return
        with self._pause_lock:
            self._pause_depth += 1
            if self._pause_depth > 1:
                return
        self._state = "PAUSED"
        self._speech_buffer = []
        self._silence_chunks = 0
        if self.vosk:
            self.vosk.reset()

    def resume_listening(self, *, require_wake_word: bool = False) -> None:
        """Resume capture, optionally returning behind the wake-word gate.

        FRENTE2-ITEM4: só religa de verdade quando a última fala pendente
        terminar (contagem de referência do pause_listening).
        """
        if self._running:
            with self._pause_lock:
                self._pause_depth = max(0, self._pause_depth - 1)
                if self._pause_depth > 0:
                    return
            self._speech_buffer = []
            self._silence_chunks = 0
            if self.vosk:
                self.vosk.reset()
            self._state = "SLEEPING" if require_wake_word and self.porcupine else "LISTENING"

    def _run_loop(self):
        """Main processing loop (runs in background thread)."""
        print("[Voice] Loop started")

        while self._running:
            try:
                # Read audio chunk
                chunk = self.audio.read(timeout=0.1)
                if chunk is None:
                    continue

                # Process wake word (if Porcupine available)
                if self.porcupine and self._state == "SLEEPING":
                    keyword_idx = self.porcupine.process(chunk)
                    if keyword_idx >= 0:
                        print(f"[Voice] Wake word detected! (keyword {keyword_idx})")
                        self._state = "LISTENING"
                        self._speech_buffer = []
                        self._silence_chunks = 0
                        self.vosk.reset()
                        # Call wake callback in main thread
                        self._dispatch(self.on_wake)
                        continue

                # Process speech (when listening)
                if self._state == "LISTENING":
                    # Voice Activity Detection
                    if NUMPY_AVAILABLE:
                        audio_level = np.abs(np.frombuffer(chunk, dtype=np.int16)).mean() / 32768.0
                    else:
                        import struct
                        samples = struct.unpack(f"{len(chunk)//2}h", chunk)
                        audio_level = sum(abs(s) for s in samples) / len(samples) / 32768.0

                    # Normalize microphone energy for the renderer. Raw mean
                    # levels are usually small, so scale into a useful 0..1 range.
                    normalized_level = min(1.0, max(0.0, float(audio_level) * 10.0))
                    self._dispatch(self.on_level, normalized_level)

                    is_speech = audio_level > self.config.vad_threshold

                    if is_speech:
                        self._speech_buffer.append(chunk)
                        self._silence_chunks = 0

                        # Partial recognition for live feedback
                        if self.on_partial:
                            partial = self.vosk.partial_recognize(chunk)
                            if partial:
                                self._dispatch(self.on_partial, partial)
                    else:
                        self._silence_chunks += 1
                        self._speech_buffer.append(chunk)

                        # End of utterance detected
                        if self._silence_chunks >= self.config.vad_silence_chunks:
                            self._process_utterance()

            except Exception as e:
                print(f"[Voice] Loop error: {e}")
                import traceback
                traceback.print_exc()

        print("[Voice] Loop ended")

    def _process_utterance(self):
        """Process collected speech buffer."""
        if not self._speech_buffer:
            return

        # Combine all chunks
        audio_data = b"".join(self._speech_buffer)
        self._speech_buffer = []
        # Zera o contador de silêncio junto com o buffer: sem isto, no modo
        # push-to-talk (sem Porcupine) cada chunk silencioso seguinte
        # re-disparava _process_utterance — ~4 chamadas ao Vosk por segundo
        # de silêncio puro, para sempre.
        self._silence_chunks = 0

        # Final recognition
        text = self.vosk.recognize(audio_data)

        # If no final result, try partial
        if not text:
            text = self.vosk.partial_recognize(audio_data)

        if text and len(text) > 1:
            print(f"[Voice] Recognized: {text}")
            self._state = "PROCESSING"
            # Call speech callback in main thread
            self._dispatch(self.on_speech, text)
        else:
            print("[Voice] No speech recognized")
            if self._running:
                self._state = "SLEEPING" if self.porcupine else "LISTENING"

    async def _safe_call(self, callback, *args):
        """Safely call async callback."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            print(f"[Voice] Callback error: {e}")

    @property
    def state(self) -> str:
        return self._state

    def interrupt(self):
        """Interrupt current listening (e.g., user pressed stop)."""
        self._state = "SLEEPING"
        self._speech_buffer = []
        self._silence_chunks = 0
        if self.vosk:
            self.vosk.reset()
        print("[Voice] Interrupted")


# Factory function for easy creation
def create_voice_pipeline(
    on_wake: Callable[[], None],
    on_speech: Callable[[str], None],
    on_partial: Callable[[str], None] = None,
    on_level: Callable[[float], None] = None,
    access_key: str = "",
) -> VoicePipeline:
    """Create voice pipeline with default config."""
    config = VoiceConfig()
    if access_key:
        config.porcupine_access_key = access_key
    return VoicePipeline(config, on_wake, on_speech, on_partial, on_level)
