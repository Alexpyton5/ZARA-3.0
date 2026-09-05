"""
Engine de voz 100% Local — faster-whisper (STT) + Kokoro/Piper (TTS) + Silero VAD + Pipecat (orquestração).
Zero nuvem, zero cota, roda offline no seu hardware.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

from .voice_manager import VoiceConfig, VoiceEngine


class LocalVoiceEngine(VoiceEngine):
    """Engine de voz totalmente local usando faster-whisper + Kokoro/Piper + Silero VAD."""

    def __init__(self):
        self.is_listening = False
        self.is_speaking_flag = False
        self._on_transcript: Callable[[str], None] | None = None
        self._on_speech_start: Callable[[], None] | None = None
        self._config: VoiceConfig | None = None
        self._tasks: list[asyncio.Task] = []

        # Componentes lazy-loaded
        self._whisper_model = None
        self._kokoro_model = None
        self._piper_voice = None
        self._vad_model = None
        self._audio_stream = None
        self._vad_iterator = None

    async def initialize(self, config: VoiceConfig) -> bool:
        self._config = config

        try:
            # Verifica dependências
            if config.tts_engine == "kokoro":
                await self._init_kokoro()
            elif config.tts_engine == "piper":
                await self._init_piper()

            await self._init_whisper()

            if config.vad_enabled:
                await self._init_vad()

            print(f"[LocalVoice] Inicializado: STT={config.stt_model}, TTS={config.tts_engine}, VAD={config.vad_enabled}")
            return True

        except Exception as e:
            print(f"[LocalVoice] Erro ao inicializar: {e}")
            return False

    async def _init_whisper(self):
        """Inicializa faster-whisper."""
        try:
            from faster_whisper import WhisperModel

            device = self._config.stt_device
            compute_type = self._config.stt_compute_type

            # Ajusta compute_type para CPU
            if device == "cpu" and compute_type == "float16":
                compute_type = "int8"

            self._whisper_model = WhisperModel(
                self._config.stt_model,
                device=device,
                compute_type=compute_type
            )
            print(f"[LocalVoice] faster-whisper '{self._config.stt_model}' carregado ({device}/{compute_type})")
        except ImportError:
            print("[LocalVoice] faster-whisper não instalado: pip install faster-whisper")
            raise
        except Exception as e:
            print(f"[LocalVoice] Erro ao carregar Whisper: {e}")
            raise

    async def _init_kokoro(self):
        """Inicializa Kokoro-TTS (ONNX)."""
        try:
            # Kokoro via onnxruntime
            import onnxruntime as ort

            # Baixa modelo se não existir
            model_path = Path.home() / ".cache" / "kokoro" / "kokoro-v1.0.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if not model_path.exists():
                print("[LocalVoice] Baixando modelo Kokoro...")
                import urllib.request
                url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v1.0.onnx"
                urllib.request.urlretrieve(url, model_path)

            self._kokoro_model = ort.InferenceSession(str(model_path))

            # Baixa voz se não existir
            voices_dir = Path.home() / ".cache" / "kokoro" / "voices"
            voices_dir.mkdir(parents=True, exist_ok=True)
            voice_path = voices_dir / f"{self._config.tts_voice}.bin"

            if not voice_path.exists():
                print(f"[LocalVoice] Baixando voz Kokoro: {self._config.tts_voice}")
                voice_url = f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices/{self._config.tts_voice}.bin"
                urllib.request.urlretrieve(voice_url, voice_path)

            self._kokoro_voice_data = voice_path.read_bytes()
            print(f"[LocalVoice] Kokoro-TTS pronto (voz: {self._config.tts_voice})")

        except ImportError:
            print("[LocalVoice] onnxruntime não instalado: pip install onnxruntime")
            raise
        except Exception as e:
            print(f"[LocalVoice] Erro ao inicializar Kokoro: {e}")
            raise

    async def _init_piper(self):
        """Inicializa Piper TTS."""
        try:
            from piper import PiperVoice

            model_path = Path.home() / ".cache" / "piper" / f"{self._config.tts_voice}.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if not model_path.exists():
                print(f"[LocalVoice] Baixando modelo Piper: {self._config.tts_voice}")
                import urllib.request
                # URLs do Piper variam, usa huggingface
                base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
                urllib.request.urlretrieve(f"{base_url}/{self._config.tts_voice}/{self._config.tts_voice}.onnx", model_path)
                urllib.request.urlretrieve(f"{base_url}/{self._config.tts_voice}/{self._config.tts_voice}.onnx.json", model_path.with_suffix(".onnx.json"))

            self._piper_voice = PiperVoice.load(str(model_path))
            print(f"[LocalVoice] Piper TTS pronto (voz: {self._config.tts_voice})")

        except ImportError:
            print("[LocalVoice] piper-tts não instalado: pip install piper-tts")
            raise
        except Exception as e:
            print(f"[LocalVoice] Erro ao inicializar Piper: {e}")
            raise

    async def _init_vad(self):
        """Inicializa Silero VAD para detecção de voz e barge-in."""
        try:
            import torch
            self._vad_model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            self._vad_iterator = utils[3]  # VADIterator
            print("[LocalVoice] Silero VAD carregado")
        except Exception as e:
            print(f"[LocalVoice] Erro ao carregar Silero VAD: {e}")
            self._config.vad_enabled = False

    async def start_listening(self, on_transcript: Callable[[str], None], on_speech_start: Callable[[], None]) -> None:
        self._on_transcript = on_transcript
        self._on_speech_start = on_speech_start
        self.is_listening = True

        if self._config.pipecat_enabled:
            await self._start_pipecat_pipeline()
        else:
            await self._start_simple_loop()

    async def _start_pipecat_pipeline(self):
        """Inicia pipeline completo via Pipecat (streaming real)."""
        try:
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineTask
            from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
            from pipecat.services.kokoro import KokoroTTSService
            from pipecat.services.whisper import WhisperSTTService
            from pipecat.transports.local.audio import LocalAudioTransport
            from pipecat.vad.silero import SileroVADAnalyzer

            # Configura transporte de áudio local
            transport = LocalAudioTransport(
                sample_rate=16000,
                num_channels=1,
            )

            # STT
            stt = WhisperSTTService(
                model=self._config.stt_model,
                device=self._config.stt_device,
                compute_type=self._config.stt_compute_type,
                language="pt"
            )

            # TTS
            if self._config.tts_engine == "kokoro":
                tts = KokoroTTSService(
                    voice=self._config.tts_voice,
                    sample_rate=24000
                )
            else:
                # Piper via Pipecat (se disponível)
                from pipecat.services.piper import PiperTTSService
                tts = PiperTTSService(voice=self._config.tts_voice)

            # VAD
            vad = SileroVADAnalyzer()

            # Pipeline
            pipeline = Pipeline([
                transport.input(),
                vad,
                stt,
                # LLM context aggregator seria conectado aqui
                tts,
                transport.output(),
            ])

            task = PipelineTask(pipeline)
            runner = PipelineRunner()

            self._pipecat_task = task
            self._pipecat_runner = runner

            # Callback para transcrição
            @stt.event_handler("on_transcript")
            async def on_transcript(transcript):
                if self._on_transcript:
                    self._on_transcript(transcript)

            # Inicia
            await runner.run(task)

        except ImportError:
            print("[LocalVoice] Pipecat não instalado, caindo para modo simples")
            await self._start_simple_loop()
        except Exception as e:
            print(f"[LocalVoice] Erro no Pipecat: {e}")
            await self._start_simple_loop()

    async def _start_simple_loop(self):
        """Loop simples de captura -> transcrição (fallback sem Pipecat)."""
        import numpy as np
        import pyaudio

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        try:
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        except Exception as e:
            # Microphone missing, access denied, or device unavailable
            print(f"[LocalVoice] Microphone initialization failed: {e}")
            if self._on_transcript:
                self._on_transcript("")  # Signal failure
            return

        print("[LocalVoice] Escutando (modo simples)...")

        audio_buffer = bytearray()
        silence_chunks = 0
        speech_started = False
        VAD_THRESHOLD = 500  # Ajustar conforme necessário

        async def process_audio():
            nonlocal audio_buffer, silence_chunks, speech_started

            while self.is_listening:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    audio_buffer.extend(data)

                    # VAD simples baseado em energia
                    audio_np = np.frombuffer(data, dtype=np.int16)
                    energy = np.abs(audio_np).mean()

                    if energy > VAD_THRESHOLD:
                        if not speech_started:
                            speech_started = True
                            if self._on_speech_start:
                                self._on_speech_start()
                        silence_chunks = 0
                    else:
                        if speech_started:
                            silence_chunks += 1
                            if silence_chunks > 30:  # ~2 segundos de silêncio
                                # Processa áudio acumulado
                                await self._transcribe_buffer(bytes(audio_buffer))
                                audio_buffer = bytearray()
                                speech_started = False
                                silence_chunks = 0

                    await asyncio.sleep(0.01)

                except Exception as e:
                    print(f"[LocalVoice] Erro no loop de áudio: {e}")
                    await asyncio.sleep(0.1)

        task = asyncio.create_task(process_audio())
        self._tasks.append(task)

    async def _transcribe_buffer(self, audio_data: bytes):
        """Transcreve buffer de áudio usando faster-whisper."""
        if not self._whisper_model or not audio_data:
            return

        try:
            # Salva temporário
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wf = wave.open(f, 'wb')
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
                wf.close()
                temp_path = f.name

            # Transcreve
            segments, info = self._whisper_model.transcribe(
                temp_path,
                language="pt",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            text = " ".join([seg.text for seg in segments]).strip()

            # Limpa temp
            os.unlink(temp_path)

            if text and self._on_transcript:
                self._on_transcript(text)

        except Exception as e:
            print(f"[LocalVoice] Erro na transcrição: {e}")

    async def stop_listening(self) -> None:
        self.is_listening = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        if hasattr(self, '_audio_stream') and self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except:
                pass

    async def speak(self, text: str, interruptible: bool = True) -> None:
        if not text.strip():
            return

        self.is_speaking_flag = True

        try:
            if self._config.tts_engine == "kokoro":
                await self._speak_kokoro(text)
            elif self._config.tts_engine == "piper":
                await self._speak_piper(text)
        except Exception as e:
            print(f"[LocalVoice] Erro ao falar: {e}")
        finally:
            self.is_speaking_flag = False

    async def _speak_kokoro(self, text: str):
        """Gera e toca áudio via Kokoro ONNX."""
        import numpy as np
        import sounddevice as sd

        # Prepara inputs
        # Kokoro espera: input_ids, style, speed
        # Simplificado - usa tokenização básica
        tokens = self._text_to_tokens(text)

        inputs = {
            "input_ids": np.array([tokens], dtype=np.int64),
            "style": np.array(self._kokoro_voice_data, dtype=np.float32).reshape(1, -1),
            "speed": np.array([self._config.tts_speed], dtype=np.float32)
        }

        # Inferência
        outputs = self._kokoro_model.run(None, inputs)
        audio = outputs[0].squeeze()

        # Normaliza e toca
        audio = np.clip(audio, -1, 1)
        audio_int16 = (audio * 32767).astype(np.int16)

        try:
            sd.play(audio_int16, samplerate=24000)
            sd.wait()
        except Exception as e:
            print(f"[LocalVoice] Audio playback failed: {e}")

    async def _speak_piper(self, text: str):
        """Gera e toca áudio via Piper."""
        import numpy as np
        import sounddevice as sd

        # Piper sintetiza
        audio_chunks = []
        for chunk in self._piper_voice.synthesize(text):
            audio_chunks.append(chunk)

        audio = np.concatenate(audio_chunks)
        audio = np.clip(audio, -1, 1)
        audio_int16 = (audio * 32767).astype(np.int16)

        try:
            sd.play(audio_int16, samplerate=self._piper_voice.config.sample_rate)
            sd.wait()
        except Exception as e:
            print(f"[LocalVoice] Audio playback failed: {e}")

    def _text_to_tokens(self, text: str) -> list:
        """Tokenização simples para Kokoro (placeholder - usar tokenizer real)."""
        # Placeholder - na prática usar tokenizer do Kokoro
        # Por ora retorna IDs básicos
        return [ord(c) for c in text[:512]]  # Limite de tokens

    async def interrupt(self) -> None:
        self.is_speaking_flag = False
        try:
            import sounddevice as sd
            sd.stop()
        except:
            pass

    def is_speaking(self) -> bool:
        return self.is_speaking_flag

    async def shutdown(self) -> None:
        self.is_listening = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        try:
            import sounddevice as sd
            sd.stop()
        except:
            pass
