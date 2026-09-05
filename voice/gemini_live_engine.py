"""
Engine de voz Gemini Live API + Voz Kore (nuvem).
Requer API key do Gemini (gratuita no AI Studio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

try:
    import google.generativeai as genai
    from google.generativeai.types import Content, LiveConnectConfig, Part
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    LiveConnectConfig = None
    Content = None
    Part = None

from .voice_manager import VoiceConfig, VoiceEngine


class GeminiLiveKoreEngine(VoiceEngine):
    """Engine Gemini Live API com voz Kore nativa."""

    def __init__(self):
        self.session = None
        self.audio_queue = asyncio.Queue()
        self.is_listening = False
        self.is_speaking_flag = False
        self._on_transcript: Callable[[str], None] | None = None
        self._on_speech_start: Callable[[], None] | None = None
        self._config: VoiceConfig | None = None
        self._tasks: list[asyncio.Task] = []

    async def initialize(self, config: VoiceConfig) -> bool:
        if not GEMINI_AVAILABLE:
            print("[GeminiLive] google-generativeai não instalado. pip install google-generativeai")
            return False

        if not config.gemini_api_key:
            print("[GeminiLive] API key não configurada")
            return False

        self._config = config
        genai.configure(api_key=config.gemini_api_key)

        try:
            # Configuração da sessão Live
            live_config = LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config={
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": config.gemini_voice
                        }
                    },
                    "language_code": config.gemini_language,
                },
                system_instruction=Content(
                    parts=[Part(text="Você é a Zara, assistente virtual estilo JARVIS. Responda em português brasileiro de forma natural e concisa.")],
                    role="user"
                )
            )

            self.session = await genai.connect_live("gemini-2.0-flash-exp", live_config)
            print(f"[GeminiLive] Conectado com voz {config.gemini_voice}")
            return True

        except Exception as e:
            print(f"[GeminiLive] Erro ao inicializar: {e}")
            return False

    async def start_listening(self, on_transcript: Callable[[str], None], on_speech_start: Callable[[], None]) -> None:
        self._on_transcript = on_transcript
        self._on_speech_start = on_speech_start
        self.is_listening = True

        # Task para receber áudio do microfone e enviar pro Gemini
        task = asyncio.create_task(self._audio_sender())
        self._tasks.append(task)

        # Task para processar respostas do Gemini
        task = asyncio.create_task(self._response_handler())
        self._tasks.append(task)

    async def _audio_sender(self):
        """Captura áudio do microfone e envia pro Gemini Live."""
        try:
            import pyaudio
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000

            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

            while self.is_listening:
                data = stream.read(CHUNK, exception_on_overflow=False)
                if self.session:
                    await self.session.send_audio(data)
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"[GeminiLive] Erro no audio sender: {e}")
        finally:
            try:
                stream.stop_stream()
                stream.close()
                p.terminate()
            except:
                pass

    async def _response_handler(self):
        """Processa respostas do Gemini Live (áudio + transcrição)."""
        try:
            async for response in self.session.receive():
                # Transcrição do usuário
                if response.text and self._on_transcript:
                    self._on_transcript(response.text)

                # Detecção de início de fala do usuário (barge-in)
                if hasattr(response, 'speech_start') and response.speech_start and self._on_speech_start:
                    self._on_speech_start()
                    self.is_speaking_flag = False

                # Áudio de resposta - já tocado automaticamente via callback de áudio
                # O Gemini Live cuida do playback nativo

        except Exception as e:
            print(f"[GeminiLive] Erro no response handler: {e}")

    async def stop_listening(self) -> None:
        self.is_listening = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def speak(self, text: str, interruptible: bool = True) -> None:
        if not self.session:
            return

        self.is_speaking_flag = True
        try:
            # Envia texto pro Gemini falar (ele gera áudio nativamente)
            await self.session.send_text(text)
            # Aguarda um pouco pro áudio começar
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[GeminiLive] Erro ao falar: {e}")

    async def interrupt(self) -> None:
        if self.session and self.is_speaking_flag:
            # O Gemini Live detecta barge-in automaticamente via VAD nativo
            # Mas podemos forçar enviando áudio vazio ou cancelando
            self.is_speaking_flag = False

    def is_speaking(self) -> bool:
        return self.is_speaking_flag

    async def shutdown(self) -> None:
        self.is_listening = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self.session:
            try:
                await self.session.close()
            except:
                pass
            self.session = None
