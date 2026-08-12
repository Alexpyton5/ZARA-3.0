"""Low-latency Gemini Live native-audio voice session for ZARA.

The API key stays in the Python sidecar. The Electron renderer only receives
state, levels and transcripts through the existing local IPC bridge.

Wake-gate behavior (ZARA-VOICE-WAKE-GATE-001):
- IDLE: mic audio is NOT streamed to Gemini. A local Vosk detector (grammar
  reduced to the wake word) listens for "zara"/"sara" only.
- WAKE -> LISTENING: after the wake word, mic audio streams to Gemini.
- SPEAKING: Gemini Live keeps receiving microphone audio so server-side VAD can
  interrupt Kore. Only local fallback TTS suppresses recognition.
- turn complete -> short cooldown -> IDLE again.
- If Vosk is unavailable the gate degrades to the previous always-streaming
  behavior (no regression on machines without the model).
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

AsyncCallback = Callable[..., Awaitable[None] | None]


@dataclass(slots=True)
class GeminiLiveVoiceConfig:
    api_key: str
    model: str = "gemini-3.1-flash-live-preview"
    voice_name: str = "Kore"
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000
    block_ms: int = 40
    input_device: int | None = None
    output_device: int | None = None
    wake_word_enabled: bool = True
    wake_words: tuple[str, ...] = ("zara", "sara")
    wake_cooldown_seconds: float = 1.5
    system_instruction: str = (
        "Você é ZARA, a assistente pessoal de Alex. RESPONDA EM PORTUGUÊS DO BRASIL quando "
        "Alex falar em português. Fale naturalmente, com respostas úteis, objetivas e humanas. "
        "Você deve responder inequivocamente em português do Brasil. Não diga que executou "
        "ações no computador quando nenhuma ferramenta confirmou a execução. "
        "Quando receber texto iniciado por FALE_EXATAMENTE:, pronuncie somente o texto "
        "depois dos dois-pontos, sem acrescentar nenhuma palavra."
    )


class GeminiLiveVoice:
    """Persistent microphone -> Gemini Live -> speaker audio bridge."""

    def __init__(
        self,
        config: GeminiLiveVoiceConfig,
        *,
        on_state: AsyncCallback | None = None,
        on_level: AsyncCallback | None = None,
        on_turn: AsyncCallback | None = None,
        on_interrupt: AsyncCallback | None = None,
        on_error: AsyncCallback | None = None,
    ) -> None:
        self.config = config
        self.on_state = on_state
        self.on_level = on_level
        self.on_turn = on_turn
        self.on_interrupt = on_interrupt
        self.on_error = on_error

        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_queue: asyncio.Queue[bytes] | None = None
        self._speech_queue: asyncio.Queue[str] | None = None
        self._speech_done: asyncio.Event | None = None
        self._play_generated_audio = False
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error: Exception | None = None
        self._input_stream: Any = None
        self._output_stream: Any = None
        self._session_handle: str | None = None
        self._input_text = ""
        self._output_text = ""
        self._connected = False
        self._last_state = "STANDBY"
        self._stream_generation = 0
        self._audio_frames_received = 0
        # --- Wake-gate state (ZARA-VOICE-WAKE-GATE-001) ---
        self._gate_open = False          # True only while LISTENING (mic -> Gemini)
        self._wake_detector: Any | None = None  # lazy Vosk grammar detector
        self._wake_grammar_json: str | None = None
        self._gate_until_idle = False    # suppress wake while ZARA is speaking
        self._last_wake_at = 0.0
        self._wake_rolling = b""         # rolling buffer for wake detection

    def _ensure_wake_detector(self) -> None:
        """Lazily build a Vosk recognizer with a grammar reduced to the wake word.

        Keeps memory footprint small and startup fast: the full Portuguese model
        is only loaded once the voice session actually starts. If Vosk or the
        model is missing, the gate degrades to always-streaming (old behavior).
        """
        if not self.config.wake_word_enabled:
            return
        if self._wake_detector is not None:
            return
        try:
            import vosk  # type: ignore

            from core.paths import user_data_dir

            model_dir = user_data_dir() / "models" / "vosk"
            pt = model_dir / "vosk-model-small-pt-0.3"
            en = model_dir / "vosk-model-small-en-us-0.15"
            model_path = pt if pt.exists() else (en if en.exists() else None)
            if model_path is None:
                print("[WakeGate] Vosk model not found; gate OFF (always stream)")
                return
            model = vosk.Model(str(model_path))
            rec = vosk.KaldiRecognizer(model, self.config.input_sample_rate)
            words = list(self.config.wake_words)
            self._wake_grammar_json = json.dumps(words)
            rec.SetGrammar(self._wake_grammar_json)
            self._wake_detector = rec
            print(f"[WakeGate] Vosk wake detector ready (words={words})")
        except Exception as exc:  # pragma: no cover - env dependent
            print(f"[WakeGate] detector init failed, gate OFF: {exc}")
            self._wake_detector = None

    def _check_wake_word(self, raw: bytes) -> bool:
        """Feed one mic chunk to the local wake detector.

        Returns True when the wake word appears in the streaming result.
        Uses a rolling partial buffer so short words are not lost.
        """
        rec = self._wake_detector
        if rec is None:
            return False
        try:
            # Accumulate into a small rolling buffer so "zara" is not split
            # across chunk boundaries, then test the partial result.
            self._wake_rolling += raw
            if len(self._wake_rolling) > self.config.input_sample_rate * 1.2:
                self._wake_rolling = self._wake_rolling[-self.config.input_sample_rate:]
            rec.AcceptWaveform(self._wake_rolling)
            partial = json.loads(rec.PartialResult()).get("partial", "").strip().lower()
            if not partial:
                return False
            for ww in self.config.wake_words:
                if ww.lower() in partial:
                    self._wake_rolling = b""
                    return True
            # reset the recognizer periodically so it does not accumulate
            if len(partial) > 24:
                rec.Reset()
                self._wake_rolling = b""
            return False
        except Exception:
            return False

    @property
    def gate_open(self) -> bool:
        """True when mic audio is being streamed to Gemini (LISTENING)."""
        return self._gate_open

    async def open_gate(self) -> None:
        """Open the mic gate (wake word detected) -> LISTENING."""
        if self._gate_open:
            return
        self._gate_open = True
        self._last_wake_at = time.time()
        await self._emit_state("LISTENING")

    async def close_gate(self) -> None:
        """Close the mic gate -> IDLE (waiting for wake word)."""
        if not self._gate_open:
            return
        self._gate_open = False
        await self._emit_state("IDLE")

    def pause_input(self) -> None:
        """Drop microphone frames while ZARA speaks through local TTS."""
        self._gate_until_idle = True
        queue = self._audio_queue
        if queue is not None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    def resume_input(self) -> None:
        self._gate_until_idle = False

    async def speak(self, text: str, timeout: float = 25.0) -> bool:
        """Speak verified ZARA text with the configured Gemini Live voice."""
        value = str(text or "").strip()
        if not value or not self.active or self._speech_queue is None or self._speech_done is None:
            return False
        self._speech_done.clear()
        await self._speech_queue.put(value)
        try:
            await asyncio.wait_for(self._speech_done.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
        finally:
            self._play_generated_audio = False

    async def interrupt_speech(self) -> None:
        """Stop only the current generated reply and keep the live session usable."""
        self._play_generated_audio = False
        await asyncio.to_thread(self._flush_output)
        if self._speech_done is not None:
            self._speech_done.set()
        await self._emit_level(0.0, False)
        await self._emit_state("LISTENING")

    @property
    def active(self) -> bool:
        return bool(self._task and not self._task.done())

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.active:
            return self.status()
        if not self.config.api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self._loop = asyncio.get_running_loop()
        self._audio_queue = asyncio.Queue(maxsize=64)
        self._speech_queue = asyncio.Queue(maxsize=8)
        self._speech_done = asyncio.Event()
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error = None
        self._stream_generation += 1
        generation = self._stream_generation
        self._audio_frames_received = 0
        self._task = asyncio.create_task(self._run(generation), name="zara-gemini-live")

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError as exc:
            self._stream_generation += 1
            self._stop.set()
            task = self._task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._task = None
            self._connected = False
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=TIMEOUT", flush=True)
            raise RuntimeError("VOICE_START_TIMEOUT") from exc
        if self._ready_error:
            await self.stop()
            raise RuntimeError(str(self._ready_error)) from self._ready_error
        return self.status()

    async def stop(self) -> None:
        self._stop.set()
        self._stream_generation += 1
        await asyncio.to_thread(self._close_input_stream)
        task = self._task
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=2.5)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._connected = False
        await asyncio.to_thread(self._close_output_stream)
        self._gate_open = False
        self._gate_until_idle = False
        self._wake_rolling = b""
        await self._emit_state("STANDBY")
        await self._emit_level(0.0, False)

    def status(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "connected": self._connected,
            "mode": "gemini_live",
            "model": self.config.model,
            "voice": self.config.voice_name,
            "input_sample_rate": self.config.input_sample_rate,
            "output_sample_rate": self.config.output_sample_rate,
            "block_ms": self.config.block_ms,
            "wake_word_enabled": self.config.wake_word_enabled,
            "gate_open": self._gate_open,
            "wake_detector_ready": self._wake_detector is not None,
            "session_state": self._last_state,
        }

    async def _run(self, generation: int) -> None:
        try:
            try:
                import sounddevice as sd
                from google import genai
                from google.genai import types
            except Exception as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "Gemini Live requer google-genai e sounddevice instalados"
                ) from exc

            print("[VOICE_TRACE] stage=MIC_DEVICE_ENUMERATION result=START", flush=True)
            opened = await asyncio.to_thread(self._open_streams, sd, generation)
            if not opened:
                return
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=PASS", flush=True)
            if self.config.wake_word_enabled:
                print("[VOICE_TRACE] stage=WAKE_ENGINE_LOAD result=START", flush=True)
                self._ensure_wake_detector()
            client = genai.Client(api_key=self.config.api_key)
            first_connection = True
            if self.config.wake_word_enabled and self._wake_detector is not None:
                await self._emit_state("IDLE")

            while not self._stop.is_set():
                try:
                    live_config = types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=self.config.voice_name
                                )
                            )
                        ),
                        input_audio_transcription=types.AudioTranscriptionConfig(),
                        output_audio_transcription=types.AudioTranscriptionConfig(),
                        context_window_compression=types.ContextWindowCompressionConfig(
                            sliding_window=types.SlidingWindow()
                        ),
                        session_resumption=types.SessionResumptionConfig(
                            handle=self._session_handle
                        ),
                        system_instruction=types.Content(
                            parts=[types.Part(text=self.config.system_instruction)]
                        ),
                    )

                    async with client.aio.live.connect(
                        model=self.config.model,
                        config=live_config,
                    ) as session:
                        self._connected = True
                        if first_connection:
                            self._ready.set()
                            first_connection = False
                        await self._emit_state("LISTENING")

                        send_task = asyncio.create_task(
                            self._send_audio_loop(session, types),
                            name="zara-gemini-live-send",
                        )
                        receive_task = asyncio.create_task(
                            self._receive_loop(session, sd),
                            name="zara-gemini-live-receive",
                        )
                        speech_task = asyncio.create_task(
                            self._send_speech_loop(session, types),
                            name="zara-gemini-live-speech",
                        )
                        stop_task = asyncio.create_task(
                            self._stop.wait(),
                            name="zara-gemini-live-stop-wait",
                        )
                        done, pending = await asyncio.wait(
                            {send_task, receive_task, speech_task, stop_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for pending_task in pending:
                            pending_task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        for finished in done:
                            if finished is stop_task:
                                continue
                            exc = finished.exception()
                            if exc:
                                raise exc

                    self._connected = False
                    if not self._stop.is_set():
                        await asyncio.sleep(0.35)

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._connected = False
                    if first_connection:
                        self._ready_error = exc
                        self._ready.set()
                        return
                    await self._emit_error(exc)
                    await self._emit_state("PROCESSING")
                    if not self._stop.is_set():
                        await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self._ready.is_set():
                self._ready_error = exc
                self._ready.set()
            await self._emit_error(exc)
        finally:
            self._connected = False
            await asyncio.to_thread(self._close_input_stream)
            await asyncio.to_thread(self._close_output_stream)
            await self._emit_state("STANDBY")
            await self._emit_level(0.0, False)

    def _open_streams(self, sd: Any, generation: int) -> bool:
        if self._loop is None or self._audio_queue is None:
            raise RuntimeError("Voice loop não inicializado")

        blocksize = max(
            160,
            int(self.config.input_sample_rate * (self.config.block_ms / 1000.0)),
        )

        def mic_callback(indata: Any, _frames: int, _time: Any, status: Any) -> None:
            if status:
                # PortAudio status is informational unless the callback fails.
                pass
            raw = bytes(indata)
            self._audio_frames_received += 1
            if self._audio_frames_received == 1:
                print("[VOICE_TRACE] stage=AUDIO_FRAMES_RECEIVED result=PASS", flush=True)
            level = self._pcm_level(raw)
            loop = self._loop
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(self._queue_audio, raw, level)

        devices = sd.query_devices()
        default_devices = getattr(getattr(sd, "default", None), "device", (None, None))
        print(
            "[VOICE_TRACE] stage=SELECTED_INPUT_DEVICE "
            f"configured={self.config.input_device is not None} "
            f"default_index={default_devices[0] if default_devices else None} "
            f"device_count={len(devices)}",
            flush=True,
        )
        input_stream = None
        output_stream = None
        try:
            input_stream = sd.RawInputStream(
                samplerate=self.config.input_sample_rate,
                blocksize=blocksize,
                channels=1,
                dtype="int16",
                device=self.config.input_device,
                callback=mic_callback,
            )
            input_stream.start()
            if generation != self._stream_generation or self._stop.is_set():
                self._close_stream_pair(input_stream, output_stream)
                return False
            self._input_stream = input_stream
            self._output_stream = output_stream
            return True
        except Exception:
            self._close_stream_pair(input_stream, output_stream)
            raise

    @staticmethod
    def _close_stream_pair(input_stream: Any, output_stream: Any) -> None:
        for stream in (input_stream, output_stream):
            if stream is None:
                continue
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def _queue_audio(self, raw: bytes, level: float) -> None:
        queue = self._audio_queue
        if queue is None or self._stop.is_set():
            return

        if self._gate_until_idle:
            asyncio.create_task(self._emit_level(0.0, False))
            return

        # --- Wake-gate (ZARA-VOICE-WAKE-GATE-001) ---
        if self.config.wake_word_enabled and self._wake_detector is not None:
            if not self._gate_open:
                # IDLE: only run the local wake detector; nothing reaches Gemini.
                woke = self._check_wake_word(raw)
                if woke:
                    asyncio.create_task(self._open_gate_task())
                # Keep level animation responsive in IDLE too.
                asyncio.create_task(self._emit_level(level, False))
                return
        # LISTENING (or gate disabled -> legacy always-stream): enqueue for Gemini.
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(raw)
        except asyncio.QueueFull:
            pass
        asyncio.create_task(self._emit_level(level, False))

    async def _open_gate_task(self) -> None:
        """Wake word fired: open the gate so the next speech streams to Gemini."""
        await self.open_gate()

    async def _send_audio_loop(self, session: Any, types: Any) -> None:
        if self._audio_queue is None:
            return
        while not self._stop.is_set():
            chunk = await self._audio_queue.get()
            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type=f"audio/pcm;rate={self.config.input_sample_rate}",
                )
            )

    async def _send_speech_loop(self, session: Any, types: Any) -> None:
        if self._speech_queue is None:
            return
        while not self._stop.is_set():
            text = await self._speech_queue.get()
            self._play_generated_audio = True
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=f"FALE_EXATAMENTE: {text}")],
                ),
                turn_complete=True,
            )

    async def _receive_loop(self, session: Any, sd: Any) -> None:
        while not self._stop.is_set():
            async for response in session.receive():
                if self._stop.is_set():
                    return

                update = getattr(response, "session_resumption_update", None)
                if update and getattr(update, "resumable", False):
                    new_handle = getattr(update, "new_handle", None)
                    if new_handle:
                        self._session_handle = str(new_handle)

                if getattr(response, "go_away", None) is not None:
                    return

                content = getattr(response, "server_content", None)
                if not content:
                    continue

                if getattr(content, "interrupted", False):
                    self._flush_output()
                    self._play_generated_audio = False
                    if self._speech_done is not None:
                        self._speech_done.set()
                    self._gate_until_idle = False
                    if self.config.wake_word_enabled and self._wake_detector is not None:
                        self._gate_open = False
                        await self._emit_state("IDLE")
                    else:
                        await self._emit_state("LISTENING")
                    await self._emit_level(0.0, False)
                    await self._call(self.on_interrupt)

                input_tx = getattr(content, "input_transcription", None)
                if input_tx and getattr(input_tx, "text", None):
                    self._input_text = self._merge_fragment(
                        self._input_text, str(input_tx.text)
                    )

                output_tx = getattr(content, "output_transcription", None)
                if output_tx and getattr(output_tx, "text", None):
                    self._output_text = self._merge_fragment(
                        self._output_text, str(output_tx.text)
                    )

                model_turn = getattr(content, "model_turn", None)
                if model_turn:
                    # Gemini Live is used as the low-latency transcription
                    # transport. Its generated audio is intentionally muted;
                    # the recognized text is routed through ZARA's local
                    # intent/action/postcondition pipeline and spoken once.
                    for part in getattr(model_turn, "parts", []) or []:
                        inline = getattr(part, "inline_data", None)
                        audio_data = getattr(inline, "data", None) if inline else None
                        if audio_data and self._play_generated_audio:
                            if self._output_stream is None:
                                await asyncio.to_thread(self._ensure_output_stream, sd)
                            audio_bytes = bytes(audio_data)
                            await self._emit_state("SPEAKING")
                            await self._emit_level(self._pcm_level(audio_bytes), True)
                            await asyncio.to_thread(self._output_stream.write, audio_bytes)

                if getattr(content, "turn_complete", False):
                    await self._finish_turn()
                    if self._play_generated_audio and self._speech_done is not None:
                        self._speech_done.set()
                    # Return to wake mode after a short cooldown so Alex can
                    # say "Zara" again without the previous turn bleeding in.
                    self._gate_open = False
                    await asyncio.sleep(self.config.wake_cooldown_seconds)
                    if not self._stop.is_set():
                        await self._emit_state("IDLE")

    async def _finish_turn(self) -> None:
        user_text = self._input_text.strip()
        model_text = self._output_text.strip()
        self._input_text = ""
        self._output_text = ""
        if user_text or model_text:
            # Do not block the receive loop: deterministic action routing may
            # ask this same Live session to speak the verified result.
            asyncio.create_task(
                self._call(self.on_turn, user_text, model_text),
                name="zara-gemini-live-routed-turn",
            )
        await self._emit_level(0.0, False)
        # With the wake gate the turn completes back into IDLE (cooldown is
        # applied by the caller); legacy mode keeps LISTENING.
        if self.config.wake_word_enabled and self._wake_detector is not None:
            await self._emit_state("IDLE")
        else:
            await self._emit_state("LISTENING")

    def _ensure_output_stream(self, sd: Any) -> None:
        if self._output_stream is not None:
            return
        stream = sd.RawOutputStream(
            samplerate=self.config.output_sample_rate,
            channels=1,
            dtype="int16",
            device=self.config.output_device,
        )
        stream.start()
        self._output_stream = stream

    def _flush_output(self) -> None:
        stream = self._output_stream
        if stream is None:
            return
        try:
            stream.abort()
            stream.start()
        except Exception:
            pass

    def _close_input_stream(self) -> None:
        stream, self._input_stream = self._input_stream, None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    def _close_output_stream(self) -> None:
        stream, self._output_stream = self._output_stream, None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    @staticmethod
    def _merge_fragment(current: str, fragment: str) -> str:
        fragment = fragment or ""
        if not fragment:
            return current
        if not current:
            return fragment
        if fragment.startswith(current):
            return fragment
        if current.endswith(fragment):
            return current
        separator = "" if current.endswith((" ", "\n")) or fragment.startswith((" ", "\n", ".", ",", "!", "?", ":", ";")) else " "
        return current + separator + fragment

    @staticmethod
    def _pcm_level(raw: bytes) -> float:
        if len(raw) < 2:
            return 0.0
        try:
            import numpy as np
            values = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            if values.size == 0:
                return 0.0
            rms = float(np.sqrt(np.mean(values * values)))
        except Exception:
            # Small pure-Python fallback for environments where numpy import is delayed.
            count = len(raw) // 2
            if count <= 0:
                return 0.0
            total = 0.0
            for i in range(0, count * 2, 2):
                sample = int.from_bytes(raw[i:i + 2], "little", signed=True)
                total += float(sample * sample)
            rms = math.sqrt(total / count)
        # Around 6k RMS is already a strong close-mic signal. Soft knee keeps
        # the particle animation expressive without clipping constantly.
        return max(0.0, min(1.0, rms / 6000.0))

    async def _emit_state(self, state: str) -> None:
        if state == self._last_state:
            return
        self._last_state = state
        await self._call(self.on_state, state)

    async def _emit_level(self, level: float, speaking: bool) -> None:
        await self._call(self.on_level, max(0.0, min(1.0, float(level))), speaking)

    async def _emit_error(self, exc: Exception) -> None:
        await self._call(self.on_error, str(exc))

    @staticmethod
    async def _call(callback: AsyncCallback | None, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result
