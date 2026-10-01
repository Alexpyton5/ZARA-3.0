"""Offline Portuguese STT for renderer AEC: mono 16 kHz, little-endian PCM16.

LocalWhisperVoice(model_path, on_text): use None for automatic local selection.
initialize() synchronously loads CPU/int8 assets or raises; call it off the IPC
loop (e.g. await asyncio.to_thread(voice.initialize)). start(event_loop=None)
returns True on success, False with last_error if unavailable; active is status.
It captures a running asyncio loop. feed_pcm(bytes) is nonblocking and returns
whether the whole packet was accepted. stop() discards pending audio and cancels
callback tasks; an in-flight native decode finishes privately, without delivery.
stop() is safe before start/after failed start and joins for at most 100 ms.
Restart is supported and native decodes remain serialized across restarts.

Energy VAD uses 20 ms frames, 80 ms minimum speech, 320 ms trailing silence and
at most 20 seconds per utterance. This is an integration component, not proof of
physical recognition. No audio capture, Silero, transcript logging or network.
"""
from __future__ import annotations

import asyncio
import os
import queue
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import CancelledError, Future
from pathlib import Path

import numpy as np

from core.paths import user_data_dir

_RATE = 16_000
_FRAME_SAMPLES = 320
_FRAME_BYTES = _FRAME_SAMPLES * 2
_MAX_SAMPLES = 20 * _RATE
_QUEUE_FRAMES = 64
_END_FRAMES = 16
_MIN_SPEECH_FRAMES = 4
_ENERGY_THRESHOLD = 0.01
_ASSETS = ("model.bin", "config.json", "tokenizer.json")


def _complete_model(path: Path) -> bool:
    try:
        return all((path / name).is_file() and (path / name).stat().st_size > 0 for name in _ASSETS)
    except OSError:
        return False


def _resolve_model(explicit: str | os.PathLike[str] | None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if _complete_model(path):
            return path
        raise FileNotFoundError(f"Incomplete local Whisper model: {path}; required: {', '.join(_ASSETS)}")
    model_root = user_data_dir() / "models" / "faster-whisper"
    # The installed small model recognized the Downloads smoke accurately;
    # keep base as the lighter fallback when small is not installed.
    for name in ("small", "base"):
        preferred = model_root / name
        if _complete_model(preferred):
            return preferred
    # Even an empty override means isolation: never escape into the user's cache.
    if "ZARA3_HOME" not in os.environ:
        from huggingface_hub.constants import HF_HUB_CACHE

        snapshots = Path(HF_HUB_CACHE) / "models--Systran--faster-whisper-base" / "snapshots"
        complete = [path for path in snapshots.glob("*") if _complete_model(path)]
        if complete:
            return max(complete, key=lambda path: (path.stat().st_mtime_ns, path.name))
    raise FileNotFoundError(f"No complete local Whisper model; expected: {preferred}; no downloads allowed")


def resolve_local_whisper_model(
    model_path: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Find complete local assets without loading/downloading a model.

    Automatic selection returns None when unavailable. An invalid explicit
    path raises FileNotFoundError instead of silently selecting another model.
    """
    try:
        return _resolve_model(model_path)
    except FileNotFoundError:
        if model_path is not None:
            raise
        return None


class LocalWhisperVoice:
    """A standalone offline worker; last_error contains safe, content-free errors."""

    engine = "offline"

    def __init__(
        self,
        model_path: str | os.PathLike[str] | None,
        on_text: Callable[[str], Awaitable[None]],
    ) -> None:
        self._model_path = model_path
        self._on_text = on_text
        self._model = None
        self._lock = threading.RLock()
        self._decode_lock = threading.Lock()
        self._generation = 0
        self._stream = 0
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: queue.Queue[tuple[int, bytes]] = queue.Queue(_QUEUE_FRAMES)
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._callbacks: set[Future[None]] = set()
        self.last_error: str | None = None

    @property
    def active(self) -> bool:
        """Whether the current session has a live worker and running callback loop."""
        with self._lock:
            return bool(
                self._running and self._thread and self._thread.is_alive()
                and self._loop and self._loop.is_running() and not self._loop.is_closed()
            )

    def initialize(self) -> None:
        """Load only complete local assets. Missing/broken models raise honestly."""
        with self._lock:
            if self._model is not None:
                return
            path = _resolve_model(self._model_path)
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                str(path), device="cpu", compute_type="int8", local_files_only=True,
            )

    def start(self, event_loop: asyncio.AbstractEventLoop | None = None) -> bool:
        """Start once; return False with last_error if model/loop is unavailable."""
        with self._lock:
            if self._model is None:
                self.last_error = "Call initialize() before start()"
                return False
            try:
                loop = event_loop if event_loop is not None else asyncio.get_running_loop()
            except RuntimeError:
                self.last_error = "A running asyncio event loop is required"
                return False
            if loop.is_closed() or not loop.is_running():
                self.last_error = "A running asyncio event loop is required"
                return False
            if self._running:
                if loop is not self._loop:
                    self.last_error = "Stop before changing the callback loop"
                    return False
                return True
            self._generation += 1
            self._stream = 0
            self._loop = loop
            self._queue = queue.Queue(_QUEUE_FRAMES)
            self._stopped = threading.Event()
            self._running = True
            self.last_error = None
            self._thread = threading.Thread(
                target=self._worker,
                args=(self._generation, self._queue, self._stopped, loop),
                name="local-whisper", daemon=True,
            )
            try:
                self._thread.start()
            except RuntimeError as error:
                self._error(self._generation, "start", error)
                self._running = False
                self._thread = None
                return False
            return True

    @staticmethod
    def _drain(packets: queue.Queue) -> None:
        while True:
            try:
                packets.get_nowait()
            except queue.Empty:
                return
            packets.task_done()

    def feed_pcm(self, pcm: bytes) -> bool:
        """Accept a whole PCM16 packet; overload drops backlog and breaks continuity.

        Empty/stopped/overloaded input returns False. Malformed input raises.
        Each call fits the bounded queue (at most 1.28 s when empty); larger
        packets up to 20 s return False. Inputs beyond 20 s raise ValueError.
        """
        if not isinstance(pcm, bytes):
            raise TypeError("PCM must be bytes")
        if len(pcm) % 2:
            raise ValueError("PCM16 requires complete two-byte samples")
        if len(pcm) > _MAX_SAMPLES * 2:
            raise ValueError("PCM packet exceeds 20 seconds")
        if not pcm:
            return False
        with self._lock:
            if not self.active:
                return False
            needed = (len(pcm) + _FRAME_BYTES - 1) // _FRAME_BYTES
            if needed > self._queue.maxsize - self._queue.qsize():
                self._stream += 1
                self._drain(self._queue)
                return False
            for offset in range(0, len(pcm), _FRAME_BYTES):
                self._queue.put_nowait((self._stream, pcm[offset:offset + _FRAME_BYTES]))
            return True

    def stop(self) -> None:
        """Invalidate/cancel even staged sessions; thread join is bounded to 100 ms."""
        with self._lock:
            self._running = False
            self._generation += 1
            self._stopped.set()
            self._drain(self._queue)
            callbacks = tuple(self._callbacks)
            thread, self._thread = self._thread, None
        for future in callbacks:
            future.cancel()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.1)

    def _current(self, generation: int, stream: int) -> bool:
        with self._lock:
            return self._running and generation == self._generation and stream == self._stream

    def _error(self, generation: int, stage: str, error: Exception) -> None:
        with self._lock:
            if self._running and generation == self._generation:
                self.last_error = f"Local Whisper {stage} failed ({type(error).__name__})"

    def _worker(self, generation, packets, stopped, loop) -> None:
        pending = bytearray()
        frames = []
        stream = -1
        speech_frames = silence_frames = last_voice = 0
        while not stopped.is_set():
            try:
                packet_stream, pcm = packets.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                if not self._current(generation, packet_stream):
                    continue
                if stream != packet_stream:
                    pending.clear()
                    frames.clear()
                    speech_frames = silence_frames = last_voice = 0
                    stream = packet_stream
                pending.extend(pcm)
                while len(pending) >= _FRAME_BYTES and self._current(generation, stream):
                    frame = np.frombuffer(bytes(pending[:_FRAME_BYTES]), dtype="<i2").astype(np.float32)
                    del pending[:_FRAME_BYTES]
                    frame /= 32768.0
                    voiced = float(np.sqrt(np.mean(frame * frame))) >= _ENERGY_THRESHOLD
                    if voiced:
                        speech_frames += 1
                        silence_frames = 0
                    elif not frames:
                        continue
                    else:
                        silence_frames += 1
                    frames.append(frame)
                    if voiced:
                        last_voice = len(frames)
                    if silence_frames >= _END_FRAMES or len(frames) * _FRAME_SAMPLES >= _MAX_SAMPLES:
                        audio = np.concatenate(frames[:last_voice]) if speech_frames >= _MIN_SPEECH_FRAMES else None
                        frames.clear()
                        speech_frames = silence_frames = last_voice = 0
                        if audio is not None:
                            self._decode(audio, generation, stream, stopped, loop)
            except Exception as error:
                self._error(generation, "decode", error)
                pending.clear()
                frames.clear()
                speech_frames = silence_frames = last_voice = 0
            finally:
                packets.task_done()

    def _decode(self, audio, generation, stream, stopped, loop) -> None:
        # A stopped native decode cannot be interrupted. A restarted session
        # waits here, away from IPC, and cancelled waiters exit promptly.
        while not stopped.is_set():
            if not self._decode_lock.acquire(timeout=0.05):
                continue
            try:
                if not self._current(generation, stream):
                    return
                segments, _info = self._model.transcribe(
                    audio, language="pt", task="transcribe", beam_size=1, best_of=1,
                    temperature=0.0, condition_on_previous_text=False,
                    vad_filter=False, without_timestamps=True, log_progress=False,
                )
                text = " ".join(part for segment in segments if (part := segment.text.strip()))
            finally:
                self._decode_lock.release()
            if text and self._current(generation, stream):
                self._dispatch(generation, stream, text, loop)
            return

    def _dispatch(self, generation: int, stream: int, text: str, loop) -> None:
        with self._lock:
            if not self._current(generation, stream):
                return
            delivery = self._deliver(generation, stream, text)
            try:
                future = asyncio.run_coroutine_threadsafe(delivery, loop)
            except RuntimeError as error:
                delivery.close()
                self._error(generation, "dispatch", error)
                return
            self._callbacks.add(future)
            future.add_done_callback(lambda done: self._callback_done(generation, done))

    async def _deliver(self, generation: int, stream: int, text: str) -> None:
        if self._current(generation, stream):
            await self._on_text(text)

    def _callback_done(self, generation: int, future: Future[None]) -> None:
        with self._lock:
            self._callbacks.discard(future)
        try:
            future.result()
        except CancelledError:
            pass
        except Exception as error:
            self._error(generation, "callback", error)
