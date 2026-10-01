"""Acceptance gates: offline assets, bounded PCM, worker decode, loop dispatch, stop.

Only fake model output and deterministic generated PCM are used; no mic or app.
Written before the implementation for CODEX-TROPA-DEV-5H-20260930 F1-GARIMPO.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from core.whisper_local import LocalWhisperVoice

RATE = 16_000
FRAME_SAMPLES = 320
SILENCE = bytes(FRAME_SAMPLES * 2)
SPEECH = np.tile(np.array([8192, -8192], dtype="<i2"), FRAME_SAMPLES // 2).tobytes()


@pytest.fixture(autouse=True)
def isolated_test_home(tmp_path, monkeypatch):
    # Self-contained isolation permits ONLY this fake-model file to be run
    # with --noconftest while main owns the shared full-suite lock.
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path / "isolated-home"))


def complete_model(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (path / name).write_bytes(b"fake-local-asset")
    return path


def test_available_small_model_is_preferred_to_base(tmp_path, monkeypatch):
    from core import whisper_local
    home = tmp_path / 'home'
    monkeypatch.setattr(whisper_local, 'user_data_dir', lambda: home)
    complete_model(home / 'models/faster-whisper/base')
    small = complete_model(home / 'models/faster-whisper/small')
    assert whisper_local.resolve_local_whisper_model() == small


@pytest.fixture
def model_factory(monkeypatch):
    models = []

    class FakeModel:
        def __init__(self, path, **kwargs):
            self.path = Path(path)
            self.options = kwargs
            self.calls = []
            self.iteration_threads = []
            self.entered = threading.Event()
            self.release = threading.Event()
            self.release.set()
            self.output = [" synthetic ", " result "]
            self.error = None
            models.append(self)

        def transcribe(self, audio, **kwargs):
            self.calls.append((audio.copy(), kwargs, threading.get_ident()))
            self.entered.set()

            def segments():
                self.iteration_threads.append(threading.get_ident())
                if not self.release.wait(3):
                    raise RuntimeError("Fake worker timed out")
                if self.error:
                    raise self.error
                for value in self.output:
                    yield SimpleNamespace(text=value)

            return segments(), SimpleNamespace(language="pt")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    return models


@pytest.fixture
def voice_factory(tmp_path, model_factory):
    voices = []
    path = complete_model(tmp_path / "explicit-model")

    def create(on_text):
        voice = LocalWhisperVoice(path, on_text)
        voice.initialize()
        voices.append(voice)
        return voice, model_factory[-1]

    yield create
    for voice in voices:
        voice.stop()
    for model in model_factory:
        model.release.set()


async def drain(voice):
    # Join accepted packets, then let their already-posted loop callbacks run.
    await asyncio.wait_for(asyncio.to_thread(voice._queue.join), 3)
    callbacks = tuple(voice._callbacks)
    if callbacks:
        await asyncio.wait_for(
            asyncio.gather(*(asyncio.wrap_future(future) for future in callbacks), return_exceptions=True),
            3,
        )
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def send_frames(voice, count, frame=SPEECH):
    for offset in range(0, count, 32):
        assert voice.feed_pcm(frame * min(32, count - offset))
        await drain(voice)


async def ignore_text(_text):
    pass


def test_explicit_local_model_cpu_int8_and_initialize_idempotent(tmp_path, model_factory):
    path = complete_model(tmp_path / "model")
    voice = LocalWhisperVoice(path, ignore_text)
    voice.initialize()
    voice.initialize()
    assert voice.engine == "offline"
    assert len(model_factory) == 1
    assert model_factory[0].path == path
    assert model_factory[0].options == {
        "device": "cpu", "compute_type": "int8", "local_files_only": True,
    }


@pytest.mark.parametrize("name", ["model.bin", "config.json", "tokenizer.json"])
@pytest.mark.parametrize("defect", ["missing", "empty", "directory"])
def test_partial_explicit_model_fails_before_loading(tmp_path, model_factory, name, defect):
    path = complete_model(tmp_path / "partial")
    (path / name).unlink()
    if defect == "empty":
        (path / name).touch()
    elif defect == "directory":
        (path / name).mkdir()
    voice = LocalWhisperVoice(path, ignore_text)
    with pytest.raises(FileNotFoundError, match="model"):
        voice.initialize()
    assert model_factory == []


def test_model_name_is_not_downloaded_and_does_not_fallback(tmp_path, monkeypatch, model_factory):
    monkeypatch.chdir(tmp_path)
    preferred = complete_model(tmp_path / "home/models/faster-whisper/base")
    monkeypatch.setenv("ZARA3_HOME", str(preferred.parents[2]))
    voice = LocalWhisperVoice("base", ignore_text)
    with pytest.raises(FileNotFoundError):
        voice.initialize()
    assert model_factory == []


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    from core import whisper_local

    home = tmp_path / "user-data"
    cache = tmp_path / "hub"
    monkeypatch.setattr(whisper_local, "user_data_dir", lambda: home)
    monkeypatch.setitem(
        sys.modules, "huggingface_hub.constants", SimpleNamespace(HF_HUB_CACHE=str(cache)),
    )
    return home, cache


def test_auto_prefers_user_model_over_cached_snapshot(isolated_paths, monkeypatch, model_factory):
    home, cache = isolated_paths
    monkeypatch.delenv("ZARA3_HOME", raising=False)
    preferred = complete_model(home / "models/faster-whisper/base")
    complete_model(cache / "models--Systran--faster-whisper-base/snapshots/cached")
    voice = LocalWhisperVoice(None, ignore_text)
    voice.initialize()
    assert model_factory[0].path == preferred


def test_auto_uses_complete_systran_base_snapshot_only(isolated_paths, monkeypatch, model_factory):
    home, cache = isolated_paths
    monkeypatch.delenv("ZARA3_HOME", raising=False)
    (home / "models/faster-whisper/base").mkdir(parents=True)
    snapshots = cache / "models--Systran--faster-whisper-base/snapshots"
    old = complete_model(snapshots / "old")
    newer = complete_model(snapshots / "newer")
    partial = complete_model(snapshots / "partial")
    (partial / "tokenizer.json").unlink()
    os.utime(old, (1, 1))
    os.utime(newer, (2, 2))
    os.utime(partial, (3, 3))
    complete_model(cache / "models--Systran--faster-whisper-base.en/snapshots/wrong")
    voice = LocalWhisperVoice(None, ignore_text)
    voice.initialize()
    assert model_factory[0].path == newer


@pytest.mark.parametrize("override", ["isolated", ""])
def test_isolation_override_never_reads_hf_cache(
    isolated_paths, monkeypatch, model_factory, override,
):
    _home, cache = isolated_paths
    monkeypatch.setenv("ZARA3_HOME", override)
    complete_model(cache / "models--Systran--faster-whisper-base/snapshots/cached")
    voice = LocalWhisperVoice(None, ignore_text)
    with pytest.raises(FileNotFoundError):
        voice.initialize()
    assert model_factory == []


def test_start_requires_initialized_model_and_running_loop(tmp_path, model_factory):
    voice = LocalWhisperVoice(complete_model(tmp_path / "model"), ignore_text)
    assert voice.start() is False
    assert "initialize" in voice.last_error
    voice.stop()  # A failed start is safe to stop.
    voice.initialize()
    voice.stop()  # Staged: initialized but never started.
    assert voice.start() is False
    loop = asyncio.new_event_loop()
    try:
        assert voice.start(loop) is False
    finally:
        loop.close()
    assert voice.start(loop) is False
    voice.stop()
    assert model_factory[0].calls == []


@pytest.mark.asyncio
async def test_worker_decodes_portuguese_normalized_pcm_and_dispatches_on_captured_loop(
    voice_factory, monkeypatch,
):
    delivered = []
    received = asyncio.Event()
    caller_thread = threading.get_ident()
    loop = asyncio.get_running_loop()
    scheduled = []
    original_schedule = asyncio.run_coroutine_threadsafe

    def schedule(coro, target_loop):
        scheduled.append((threading.get_ident(), target_loop))
        return original_schedule(coro, target_loop)

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", schedule)

    async def on_text(text):
        delivered.append((text, threading.get_ident(), asyncio.get_running_loop()))
        received.set()

    voice, model = voice_factory(on_text)
    assert voice.start(loop) is True
    assert voice.start(loop) is True  # Starting twice must not double the worker.
    await send_frames(voice, 8)
    await send_frames(voice, 15, SILENCE)
    assert model.calls == []  # End of speech requires the full 320 ms.
    await send_frames(voice, 1, SILENCE)
    await asyncio.wait_for(received.wait(), 2)
    assert delivered == [("synthetic result", caller_thread, loop)]
    audio, options, worker_thread = model.calls[0]
    assert worker_thread != caller_thread
    assert model.iteration_threads == [worker_thread]
    assert scheduled == [(worker_thread, loop)]
    assert audio.dtype == np.float32
    np.testing.assert_array_equal(audio, np.tile([0.25, -0.25], 8 * FRAME_SAMPLES // 2))
    assert options["language"] == "pt"
    assert options["task"] == "transcribe"
    assert options["vad_filter"] is False
    assert options["condition_on_previous_text"] is False
    assert options["log_progress"] is False


@pytest.mark.asyncio
async def test_empty_silent_near_silent_and_single_click_never_decode(voice_factory):
    voice, model = voice_factory(ignore_text)
    voice.start()
    assert voice.feed_pcm(b"") is False
    await send_frames(voice, 40, SILENCE)
    await send_frames(voice, 40, np.full(FRAME_SAMPLES, 3, dtype="<i2").tobytes())
    await send_frames(voice, 1)
    await send_frames(voice, 16, SILENCE)
    assert model.calls == []


@pytest.mark.asyncio
async def test_pcm_packet_boundaries_do_not_change_audio(voice_factory):
    received = []

    async def on_text(text):
        received.append(text)

    voice, model = voice_factory(on_text)
    voice.start()
    pcm = SPEECH * 5 + SILENCE * 16
    for offset in range(0, len(pcm), 222):
        assert voice.feed_pcm(pcm[offset:offset + 222])
        await drain(voice)
    assert received == ["synthetic result"]
    assert model.calls[0][0].shape == (5 * FRAME_SAMPLES,)


@pytest.mark.asyncio
async def test_continuous_speech_is_split_at_twenty_seconds(voice_factory):
    voice, model = voice_factory(ignore_text)
    voice.start()
    await send_frames(voice, 1_005)
    await send_frames(voice, 16, SILENCE)
    assert [len(call[0]) for call in model.calls] == [20 * RATE, 5 * FRAME_SAMPLES]


@pytest.mark.asyncio
async def test_feed_rejects_bad_pcm_and_oversize_input(voice_factory):
    voice, model = voice_factory(ignore_text)
    assert voice.feed_pcm(SPEECH) is False
    voice.start()
    with pytest.raises(TypeError):
        voice.feed_pcm("pcm")
    with pytest.raises(ValueError):
        voice.feed_pcm(b"\x00")
    with pytest.raises(ValueError):
        voice.feed_pcm(bytes(20 * RATE * 2 + 2))
    assert model.calls == []


@pytest.mark.asyncio
async def test_queue_overflow_drops_backlog_and_resets_partial_utterance(voice_factory):
    voice, model = voice_factory(ignore_text)
    voice.start()
    model.release.clear()
    try:
        assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
        assert await asyncio.to_thread(model.entered.wait, 2)
        capacity = voice._queue.maxsize
        assert 0 < capacity <= 100
        assert voice.feed_pcm(SPEECH * capacity)
        assert voice.feed_pcm(SPEECH) is False
        assert voice._queue.empty()
        assert voice.feed_pcm(SILENCE * 16)
    finally:
        model.release.set()
    await drain(voice)
    assert len(model.calls) == 1  # No artificial splice across dropped speech.


@pytest.mark.asyncio
async def test_stop_discards_inflight_queued_and_partial_audio_and_allows_restart(voice_factory):
    delivered = []

    async def on_text(text):
        delivered.append(text)

    voice, model = voice_factory(on_text)
    voice.start()
    model.release.clear()
    try:
        assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
        assert await asyncio.to_thread(model.entered.wait, 2)
        old_queue = voice._queue
        assert voice.feed_pcm(SPEECH * 5)
        voice.stop()
        voice.stop()
        assert old_queue.empty()
        assert voice.feed_pcm(SPEECH) is False
        voice.start()
        assert voice.feed_pcm(SILENCE * 16)
    finally:
        model.release.set()
    await asyncio.wait_for(asyncio.to_thread(old_queue.join), 3)
    await drain(voice)
    assert delivered == []
    assert len(model.calls) == 1
    await send_frames(voice, 5)
    await send_frames(voice, 16, SILENCE)
    assert delivered == ["synthetic result"]
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_stop_suppresses_callback_already_posted_to_loop(voice_factory):
    delivered = []

    async def on_text(text):
        delivered.append(text)

    voice, _model = voice_factory(on_text)
    voice.start()
    assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
    # Keep the loop occupied until the worker has posted its callback.
    voice._queue.join()
    voice.stop()
    assert voice.start() is True  # The posted callback belongs to an old generation.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert delivered == []
    await send_frames(voice, 5)
    await send_frames(voice, 16, SILENCE)
    assert delivered == ["synthetic result"]


@pytest.mark.asyncio
async def test_stop_cancels_running_async_callback(voice_factory):
    began = asyncio.Event()
    cancelled = asyncio.Event()
    finished = []

    async def on_text(_text):
        began.set()
        try:
            await asyncio.Event().wait()
            finished.append(True)
        finally:
            cancelled.set()

    voice, _model = voice_factory(on_text)
    voice.start()
    assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
    await asyncio.wait_for(began.wait(), 2)
    voice.stop()
    await asyncio.wait_for(cancelled.wait(), 2)
    assert finished == []


@pytest.mark.asyncio
async def test_blank_model_output_is_not_delivered(voice_factory):
    delivered = []

    async def on_text(text):
        delivered.append(text)

    voice, model = voice_factory(on_text)
    model.output = ["", " \n "]
    voice.start()
    assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
    await drain(voice)
    assert delivered == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["decode", "callback"])
async def test_errors_are_reported_without_transcript_logging(voice_factory, caplog, source):
    async def on_text(_text):
        if source == "callback":
            raise RuntimeError("synthetic private content")

    voice, model = voice_factory(on_text)
    if source == "decode":
        model.error = RuntimeError("synthetic private content")
    voice.start()
    assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
    await drain(voice)
    assert voice.last_error and source in voice.last_error
    assert "synthetic private content" not in voice.last_error
    assert caplog.text == ""


def test_public_resolver_returns_complete_path_or_none_without_loading(
    isolated_paths, model_factory,
):
    from core import whisper_local

    home, _cache = isolated_paths
    assert whisper_local.resolve_local_whisper_model() is None
    path = complete_model(home / "models/faster-whisper/base")
    assert whisper_local.resolve_local_whisper_model() == path
    assert whisper_local.resolve_local_whisper_model(path) == path
    (path / "config.json").unlink()
    with pytest.raises(FileNotFoundError):
        whisper_local.resolve_local_whisper_model(path)
    assert whisper_local.resolve_local_whisper_model() is None
    assert model_factory == []


@pytest.mark.asyncio
async def test_stop_joins_idle_worker_but_bounds_wait_for_native_decode(voice_factory):
    voice, model = voice_factory(ignore_text)
    assert voice.start() is True
    idle_worker = voice._thread
    voice.stop()
    assert not idle_worker.is_alive()
    assert voice.start() is True
    model.release.clear()
    try:
        assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
        assert await asyncio.to_thread(model.entered.wait, 2)
        decoding_worker = voice._thread
        started = time.monotonic()
        voice.stop()
        assert time.monotonic() - started < 0.5
        assert decoding_worker.is_alive()  # Native work is allowed to finish privately.
    finally:
        model.release.set()
    await asyncio.to_thread(decoding_worker.join, 2)
    assert not decoding_worker.is_alive()


@pytest.mark.asyncio
async def test_restart_serializes_native_decode_and_only_emits_new_generation(
    voice_factory, monkeypatch,
):
    delivered = []

    async def on_text(text):
        delivered.append(text)

    voice, model = voice_factory(on_text)
    original_decode = voice._decode
    restart_waiting = threading.Event()

    def observe_decode(audio, generation, stream, stopped, loop):
        if restart_waiting_generation == generation:
            restart_waiting.set()
        return original_decode(audio, generation, stream, stopped, loop)

    monkeypatch.setattr(voice, "_decode", observe_decode)
    assert voice.start() is True
    restart_waiting_generation = -1
    model.release.clear()
    try:
        assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
        assert await asyncio.to_thread(model.entered.wait, 2)
        voice.stop()
        assert voice.start() is True
        restart_waiting_generation = voice._generation
        assert voice.feed_pcm(SPEECH * 5 + SILENCE * 16)
        assert await asyncio.to_thread(restart_waiting.wait, 2)
        assert len(model.calls) == 1
    finally:
        model.release.set()
    await drain(voice)
    assert len(model.calls) == 2
    assert delivered == ["synthetic result"]


@pytest.mark.asyncio
async def test_active_tracks_started_state_and_foreign_thread_stop(voice_factory):
    voice, _model = voice_factory(ignore_text)
    assert voice.active is False
    voice.stop()
    assert voice.active is False
    assert voice.start() is True
    assert voice.active is True
    await asyncio.to_thread(voice.stop)
    assert voice.active is False
    assert voice.feed_pcm(SPEECH) is False
