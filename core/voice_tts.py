"""
Voice TTS — cascata de vozes da ZARA.

Ordem de preferencia: Kore (Gemini Live, melhor entonacao, tem cota) ->
Edge Neural (gratuita, sem chave, sem cota, precisa de internet) ->
Kokoro ONNX (local, offline, sem limite) -> Gemini HTTP.

ZARA-VOZ-UNICA-002 removeu o Windows SAPI da cascata em definitivo. O teste
`test_a_voz_do_windows_nunca_mais_e_chamada` garante que `_speak_windows_sapi`
nunca e chamado. A regra de produto e simples: a ZARA nunca pode ficar muda.
"""
from __future__ import annotations

import asyncio
import ctypes
import itertools
import os
import sys
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
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    edge_tts = None

try:
    import miniaudio
    MINIAUDIO_AVAILABLE = True
except ImportError:
    MINIAUDIO_AVAILABLE = False
    miniaudio = None

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
from core.voice_stt import VoiceNotConfiguredError


@dataclass
class TTSConfig:
    """TTS configuration."""
    # Kokoro
    kokoro_model_path: str = ""
    kokoro_voices_path: str = ""
    default_voice: str = "pf_dora"  # Portuguese (Brazil), female
    sample_rate: int = 24000

    # Edge Neural (gratuita, sem chave, sem cota; exige internet)
    edge_voice: str = "pt-BR-FranciscaNeural"
    edge_timeout: float = 8.0

    # Gemini Live fallback
    gemini_api_key: str = ""
    gemini_voice: str = "Puck"  # Puck, Charon, Kore, Fenrir, Aoede
    gemini_model: str = "gemini-1.5-flash"

    # Audio output
    output_device: int | None = None

    # Behavior
    prefer_local: bool = True
    prefer_edge: bool = True
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

    # Pares (modelo, vozes) aceitos, do mais novo para o mais antigo.
    _VOICE_PACKS = (
        ("kokoro-v1.0.onnx", "voices-v1.0.bin"),
        ("kokoro-v0.19.onnx", "voices.json"),
    )

    def __init__(self, config: TTSConfig):
        if not KOKORO_AVAILABLE:
            raise VoiceNotConfiguredError("TTS_BACKEND_NOT_CONFIGURED: kokoro-onnx não instalado.")

        self.config = config
        self.model: kokoro_onnx.Kokoro | None = None
        self._load_model()

    def _load_model(self):
        """Load or download Kokoro model."""
        model_dir = user_data_dir() / "models" / "kokoro"
        model_dir.mkdir(parents=True, exist_ok=True)

        if self.config.kokoro_model_path and Path(self.config.kokoro_model_path).exists():
            model_path = self.config.kokoro_model_path
            voices_path = self.config.kokoro_voices_path or str(model_dir / self._VOICE_PACKS[0][1])
        else:
            # kokoro-onnx 0.5 le as vozes com np.load e so aceita o pacote
            # binario v1.0; o par v0.19 (voices.json) explodia em ValueError
            # dentro da biblioteca, o que aparecia como "voz local quebrada"
            # sem dizer que o problema era o par de arquivos.
            for modelo, vozes in self._VOICE_PACKS:
                if (model_dir / modelo).exists() and (model_dir / vozes).exists():
                    model_path = str(model_dir / modelo)
                    voices_path = str(model_dir / vozes)
                    break
            else:
                # Never download weights autonomously — report NOT_CONFIGURED.
                esperados = " ou ".join(f"{m} + {v}" for m, v in self._VOICE_PACKS)
                raise VoiceNotConfiguredError(
                    "TTS_MODEL_NOT_CONFIGURED: pesos Kokoro ausentes em "
                    f"{model_dir}. Esperado {esperados}."
                )

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

        # kokoro-onnx expoe `create` e devolve (audio, sample_rate). O nome
        # `generate` e de uma versao anterior da biblioteca: com a 0.5 esta
        # chamada morria em AttributeError, ou seja, a "voz local" nunca chegou
        # a falar uma frase. O sample_rate vem do modelo, nao de config.
        audio, sample_rate = self.model.create(
            text,
            voice=voice,
            speed=speed,
            lang=self.VOICES[voice]["lang"],
        )

        return audio, int(sample_rate)

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


class _EdgeChunkSource(miniaudio.StreamableSource if MINIAUDIO_AVAILABLE else object):
    """Fila de bytes MP3 que o decoder le enquanto a Microsoft ainda envia.

    O produtor (WebSocket da Edge) e o consumidor (decoder) vivem em threads
    diferentes; `read` bloqueia ate ter bytes, fim de stream ou barge-in.
    """

    def __init__(self):
        self._buffer = bytearray()
        self._condition = threading.Condition()
        self._finished = False
        self.closed = False

    def feed(self, data: bytes):
        with self._condition:
            self._buffer.extend(data)
            self._condition.notify_all()

    def finish(self):
        with self._condition:
            self._finished = True
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self.closed = True
            self._condition.notify_all()

    def read(self, num_bytes: int) -> bytes:
        """Devolve o que ja chegou, sem esperar encher `num_bytes`.

        Esperar o bloco cheio anulava o streaming: o decoder pedia mais bytes
        do que o MP3 inteiro tinha e so era servido no fim da sintese, ou seja,
        a ZARA voltava a so falar depois de gerar tudo. Leitura curta e
        legitima aqui; b"" fica reservado para fim de stream e barge-in.
        """
        with self._condition:
            while not self._buffer and not self._finished and not self.closed:
                self._condition.wait(timeout=0.25)
            if self.closed:
                return b""
            chunk = bytes(self._buffer[:num_bytes])
            del self._buffer[:num_bytes]
            return chunk


class EdgeTTS:
    """Voz neural feminina gratuita (Microsoft Edge). Sem chave, sem cota.

    Existe para tapar o buraco entre a Kore e a voz robotica do Windows: quando
    a cota do Gemini Live acaba, a ZARA continua com voz neural em vez de cair
    para o SAPI. Exige internet; quando nao ha rede, quem assume e o Kokoro
    local.

    A sintese sai em MP3, entao a reproducao usa MCI (winmm), que ja decodifica
    MP3 no proprio Windows. Isso evita depender de decoder externo que nao
    sobreviveria ao empacotamento PyInstaller.
    """

    VOICES = {
        "pt-BR-FranciscaNeural": {"lang": "pt-br", "gender": "f", "desc": "PT-BR, calorosa"},
        "pt-BR-ThalitaMultilingualNeural": {"lang": "pt-br", "gender": "f", "desc": "PT-BR, expressiva"},
        "pt-BR-BrendaNeural": {"lang": "pt-br", "gender": "f", "desc": "PT-BR, neutra"},
        "pt-BR-LeticiaNeural": {"lang": "pt-br", "gender": "f", "desc": "PT-BR, jovem"},
        "pt-BR-AntonioNeural": {"lang": "pt-br", "gender": "m", "desc": "PT-BR, masculina"},
    }

    _alias_seq = itertools.count(1)
    _STREAM_RATE = 24000
    _STREAM_FRAMES = 1200  # 50ms por bloco: barge-in corta rapido

    def __init__(self, config: TTSConfig):
        if not EDGE_TTS_AVAILABLE:
            raise VoiceNotConfiguredError("TTS_BACKEND_NOT_CONFIGURED: edge-tts nao instalado.")
        if not (MINIAUDIO_AVAILABLE and SOUNDDEVICE_AVAILABLE and NUMPY_AVAILABLE) and not sys.platform.startswith("win"):
            raise VoiceNotConfiguredError(
                "TTS_BACKEND_NOT_CONFIGURED: sem miniaudio/sounddevice e sem MCI do Windows."
            )

        # Deliberadamente `_config`: `_tts_voice_name` inspeciona `.config`
        # primeiro e encontraria `gemini_voice`, rotulando esta engine com o
        # nome da voz errada no [VOICE_TRACE].
        self._config = config
        self.voice_name = config.edge_voice
        self._lock = threading.Lock()
        self._alias: str | None = None
        self._source: _EdgeChunkSource | None = None
        self._stop_event = threading.Event()

    def _resolve_voice(self, voice: str | None) -> str:
        voice = voice or self.voice_name
        if voice not in self.VOICES:
            print(f"[EdgeTTS] Voz desconhecida '{voice}', usando {self._config.edge_voice}")
            voice = self._config.edge_voice
        return voice

    # -- sintese -------------------------------------------------------

    async def _save(self, text: str, output_path: str, voice: str, speed: float):
        rate = f"{round((speed - 1.0) * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_path)

    def synthesize_to_file(self, text: str, output_path: str, voice: str = None, speed: float = 1.0) -> str:
        """Sintetiza para MP3. Levanta se a rede falhar — quem decide o
        proximo degrau da cascata e o chamador, nunca esta classe."""
        voice = self._resolve_voice(voice)

        async def _run():
            await asyncio.wait_for(
                self._save(text, output_path, voice, speed),
                timeout=self._config.edge_timeout,
            )

        asyncio.run(_run())

        if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
            raise RuntimeError("EdgeTTS produziu audio vazio")
        return output_path

    # -- reproducao ----------------------------------------------------

    @staticmethod
    def _mci(command: str) -> str:
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(command, buf, 255, None)
        if err:
            raise RuntimeError(f"MCI erro {err}: {command}")
        return buf.value

    def play(self, text: str, voice: str = None, speed: float = 1.0, blocking: bool = True):
        """Sintetiza e toca. `blocking=False` devolve a thread que esta tocando."""
        if not blocking:
            t = threading.Thread(
                target=self.play, args=(text, voice, speed, True), daemon=True
            )
            t.start()
            return t

        if self._can_stream():
            self._play_streaming(text, voice, speed)
            return
        self._play_via_file(text, voice, speed)

    # -- caminho rapido: comeca a falar antes de terminar de sintetizar ----

    def _can_stream(self) -> bool:
        return MINIAUDIO_AVAILABLE and SOUNDDEVICE_AVAILABLE and NUMPY_AVAILABLE

    def _play_streaming(self, text: str, voice: str = None, speed: float = 1.0):
        """Toca o primeiro pedaco de audio assim que ele chega da Microsoft.

        Esperar o MP3 inteiro custava ~1,5s por frase — acima da meta de 1s.
        Aqui o audio e decodificado e tocado enquanto ainda esta chegando, e o
        que o Alex percebe passa a ser o tempo do primeiro pedaco.
        """
        voice = self._resolve_voice(voice)
        rate = f"{round((speed - 1.0) * 100):+d}%"
        source = _EdgeChunkSource()
        failure: list[BaseException] = []

        def _produce():
            async def _run():
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                async for chunk in communicate.stream():
                    if source.closed:
                        return
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        source.feed(chunk["data"])

            try:
                asyncio.run(asyncio.wait_for(_run(), timeout=self._config.edge_timeout))
            except BaseException as exc:  # noqa: BLE001 - repassado ao chamador
                failure.append(exc)
            finally:
                source.finish()

        producer = threading.Thread(target=_produce, daemon=True)
        producer.start()

        self._stop_event.clear()
        with self._lock:
            self._source = source

        # O dispositivo de saida e aberto agora, em paralelo com a ida ate a
        # Microsoft. Abrir so quando o audio chega somava ~200ms de espera
        # depois de o audio ja estar pronto.
        stream = sd.OutputStream(
            samplerate=self._STREAM_RATE,
            channels=1,
            dtype="int16",
            device=self._config.output_device,
        )
        stream.start()
        wrote_any = False
        try:
            frames = miniaudio.stream_any(
                source,
                miniaudio.FileFormat.MP3,
                miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=self._STREAM_RATE,
                frames_to_read=self._STREAM_FRAMES,
            )
            for samples in frames:
                if self._stop_event.is_set():
                    break
                stream.write(np.frombuffer(memoryview(samples), dtype=np.int16))
                wrote_any = True
            if not self._stop_event.is_set():
                stream.stop()
        finally:
            source.close()
            with self._lock:
                self._source = None
            stream.close(ignore_errors=True)
            producer.join(timeout=1.0)

        if failure and not wrote_any:
            # Nada chegou a tocar: o chamador precisa descer a cascata.
            raise failure[0]

    # -- caminho de reserva: MP3 inteiro tocado pelo MCI do Windows -------

    def _play_via_file(self, text: str, voice: str = None, speed: float = 1.0):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        alias = f"zara_tts_{next(self._alias_seq)}"
        try:
            self.synthesize_to_file(text, tmp.name, voice, speed)
            self._mci(f'open "{tmp.name}" type mpegvideo alias {alias}')
            with self._lock:
                self._alias = alias
            try:
                self._mci(f"play {alias} wait")
            finally:
                with self._lock:
                    self._alias = None
                try:
                    self._mci(f"close {alias}")
                except RuntimeError:
                    pass  # stop() ja fechou
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass  # o Windows ainda pode estar segurando o arquivo

    def stop(self):
        """Corta a fala em andamento. Barge-in nao pode depender de sorte."""
        self._stop_event.set()
        with self._lock:
            alias = self._alias
            source = self._source
            self._alias = None
        if source is not None:
            source.close()
        if not alias:
            return
        for command in (f"stop {alias}", f"close {alias}"):
            try:
                self._mci(command)
            except RuntimeError:
                pass

    @classmethod
    def list_voices(cls) -> dict:
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

    Ordem: Edge (gratuita, neural, sem cota) -> Kokoro (local, offline) ->
    Gemini HTTP. A Kore vive um degrau acima, em `gemini_live_voice`, e e
    escolhida antes deste gerenciador ser chamado.
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self.edge: EdgeTTS | None = None
        self.kokoro: KokoroTTS | None = None
        self.gemini: GeminiTTS | None = None
        self._current_playback = None
        self._interrupt_event = threading.Event()

    def initialize(self):
        """Initialize available TTS engines."""
        # Edge: voz neural gratuita, primeira escolha quando a Kore nao fala
        if self.config.prefer_edge:
            try:
                self.edge = EdgeTTS(self.config)
                print(f"[TTS] Edge initialized (gratuita, {self.config.edge_voice})")
            except Exception as e:
                print(f"[TTS] Edge init failed: {e}")
                self.edge = None

        # Kokoro: rede de seguranca offline
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

        if not self.edge and not self.kokoro and not self.gemini:
            raise RuntimeError(
                "No TTS engine available. Install edge-tts or kokoro-onnx, or set Gemini API key."
            )

    def speak(self, text: str, voice: str = None, speed: float = 1.0, blocking: bool = True):
        """Speak text using best available engine."""
        self._interrupt_event.clear()
        engines = ((self.edge, "Edge"), (self.kokoro, "Kokoro"))

        if blocking:
            self._speak_cascade(text, voice, speed, engines, raise_on_exhausted=True)
            return

        # ZARA-TTS-CASCATA-002: a cascata inteira roda dentro da thread, nao so
        # o primeiro engine. Antes, uma falha do Edge depois que a thread ja
        # tinha comecado morria silenciosa ali dentro e nunca chegava ao
        # Kokoro/Gemini — exatamente no modo em que a promessa de "nunca fica
        # muda" mais importa.
        t = threading.Thread(
            target=self._speak_cascade,
            args=(text, voice, speed, engines),
            kwargs={"raise_on_exhausted": False},
            daemon=True,
        )
        t.start()
        self._current_playback = t

    def _speak_cascade(self, text, voice, speed, engines, raise_on_exhausted: bool):
        """Walk Edge -> Kokoro -> Gemini, catching failures at every step."""
        for engine, label in engines:
            if not engine:
                continue
            try:
                engine.play(text, voice, speed, blocking=True)
                return
            except Exception as e:
                print(f"[TTS] {label} failed, trying fallback: {e}")

        if self.gemini:
            if raise_on_exhausted:
                asyncio.run(self._gemini_speak(text, voice))
            else:
                try:
                    asyncio.run(self._gemini_speak(text, voice))
                except Exception as e:
                    print(f"[TTS] Gemini fallback failed: {e}")
            return

        if raise_on_exhausted:
            raise RuntimeError("No TTS engine available")
        print("[TTS] Cascade exhausted (non-blocking) - nenhuma voz falou este texto")

    async def _gemini_speak(self, text: str, voice: str = None):
        """Speak via Gemini (async)."""
        await self.gemini.play(text, voice)

    def interrupt(self):
        """Interrupt current playback."""
        self._interrupt_event.set()
        if self.edge:
            # A Edge toca via MCI, fora do sounddevice: sem isto o barge-in
            # apagaria o Kokoro e deixaria a voz da Edge falando sozinha.
            self.edge.stop()
        if SOUNDDEVICE_AVAILABLE:
            sd.stop()
        if self._current_playback and self._current_playback.is_alive():
            # Thread will check interrupt event
            pass
        print("[TTS] Interrupted")

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        if SOUNDDEVICE_AVAILABLE:
            # sd.get_stream() raises (does not return None) when there is no
            # active stream, which is the common case between utterances.
            try:
                return sd.get_stream().active
            except Exception:
                return False
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
    edge_voice: str = "pt-BR-FranciscaNeural",
) -> TTSManager:
    """Create TTS manager with config."""
    config = TTSConfig(
        prefer_local=prefer_local,
        gemini_api_key=gemini_api_key,
        default_voice=default_voice,
        edge_voice=edge_voice,
    )
    manager = TTSManager(config)
    manager.initialize()
    return manager
