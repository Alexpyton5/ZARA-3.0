from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core import voice_stt
from core.ipc_handlers import IPCHandler, IPCMessage
from core.voice_stt import AudioInput, VoiceConfig, VoiceNotConfiguredError, VoicePipeline


class _FakeAudio:
    def start(self):
        return None

    def stop(self):
        return None

    def read(self, timeout=0.1):
        return None


class _FakeVosk:
    def reset(self):
        return None


class _PortAudioFailure(Exception):
    pass


class _SynchronousInputStream:
    def __init__(self, callback, *, frame: bytes = b"", failure: Exception | None = None):
        self.callback = callback
        self.frame = frame
        self.failure = failure
        self.closed = False

    def start(self):
        if self.frame:
            self.callback(self.frame, len(self.frame) // 2, None, None)
        if self.failure is not None:
            raise self.failure

    def stop(self):
        return None

    def close(self):
        self.closed = True


class _RetryAudio(_FakeAudio):
    def __init__(self):
        self.attempts = 0

    def start(self):
        self.attempts += 1
        if self.attempts == 1:
            raise VoiceNotConfiguredError("AUDIO_INPUT_FAILED: device busy")


def _pipeline(*, wake_word: bool) -> VoicePipeline:
    pipeline = VoicePipeline(VoiceConfig(), Mock(), Mock())
    pipeline.vosk = _FakeVosk()
    pipeline.audio = _FakeAudio()
    pipeline.porcupine = Mock() if wake_word else None
    return pipeline


def test_local_pipeline_starts_behind_wake_gate_when_available():
    pipeline = _pipeline(wake_word=True)
    pipeline.start()
    try:
        assert pipeline.state == "SLEEPING"
    finally:
        pipeline.stop()


def test_pause_discards_capture_and_resume_returns_to_wake_gate():
    pipeline = _pipeline(wake_word=True)
    pipeline._running = True
    pipeline._speech_buffer = [b"zara speaking"]

    pipeline.pause_listening()
    assert pipeline.state == "PAUSED"
    assert pipeline._speech_buffer == []

    pipeline.resume_listening(require_wake_word=True)
    assert pipeline.state == "SLEEPING"


def test_audio_input_keeps_frame_emitted_synchronously_during_start(monkeypatch):
    frame = b"\x01\x00" * 32
    stream_holder = {}

    def open_stream(**kwargs):
        stream = _SynchronousInputStream(kwargs["callback"], frame=frame)
        stream_holder["stream"] = stream
        return stream

    monkeypatch.setattr(voice_stt, "SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr(
        voice_stt,
        "sd",
        SimpleNamespace(RawInputStream=open_stream, PortAudioError=_PortAudioFailure),
    )

    audio = AudioInput(VoiceConfig())
    audio.start()
    try:
        assert audio.read(timeout=0.01) == frame
    finally:
        audio.stop()

    assert stream_holder["stream"].closed is True


def test_audio_input_failure_resets_live_state_and_closes_partial_stream(monkeypatch):
    stream_holder = {}

    def open_stream(**kwargs):
        stream = _SynchronousInputStream(
            kwargs["callback"],
            failure=_PortAudioFailure("device busy"),
        )
        stream_holder["stream"] = stream
        return stream

    monkeypatch.setattr(voice_stt, "SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr(
        voice_stt,
        "sd",
        SimpleNamespace(RawInputStream=open_stream, PortAudioError=_PortAudioFailure),
    )

    audio = AudioInput(VoiceConfig())
    with pytest.raises(VoiceNotConfiguredError, match="AUDIO_INPUT_FAILED"):
        audio.start()

    assert audio._running is False
    assert audio.stream is None
    assert stream_holder["stream"].closed is True


def test_local_pipeline_can_retry_after_microphone_open_failure():
    pipeline = VoicePipeline(VoiceConfig(), Mock(), Mock())
    pipeline.vosk = _FakeVosk()
    pipeline.audio = _RetryAudio()

    pipeline.start()
    assert pipeline.state == "ERROR"
    assert pipeline._running is False

    pipeline.start()
    try:
        assert pipeline.audio.attempts == 2
        assert pipeline.state == "LISTENING"
        assert pipeline._running is True
    finally:
        pipeline.stop()


@pytest.mark.asyncio
async def test_interrupt_stops_tts_and_voice_capture():
    handler = IPCHandler(AsyncMock())
    handler.tts_manager = Mock()
    handler.voice_pipeline = Mock()
    handler.send_response = AsyncMock()
    handler.send_event = AsyncMock()

    await handler.handle_interrupt(IPCMessage(type="interrupt", request_id="r1"))

    handler.tts_manager.interrupt.assert_called_once_with()
    handler.voice_pipeline.interrupt.assert_called_once_with()


@pytest.mark.asyncio
async def test_muted_response_keeps_microphone_listening():
    handler = IPCHandler(AsyncMock())
    handler._silenciada = True
    handler.voice_active = True
    handler.voice_pipeline = Mock()
    handler.tts_manager = Mock()
    handler.send_event = AsyncMock()

    await handler._speak_response("resposta silenciada")

    handler.voice_pipeline.pause_listening.assert_not_called()
    handler.tts_manager.initialize.assert_not_called()
    assert handler._voice_speaking is False
    handler.send_event.assert_awaited_once_with("state-change", "LISTENING")


@pytest.mark.asyncio
async def test_failed_kore_speech_is_not_retried_for_another_full_timeout():
    handler = IPCHandler(AsyncMock())
    handler.voice_active = False
    handler.voice_pipeline = None
    handler.tts_manager = None
    handler.gemini_live_voice = Mock(active=True, speak=AsyncMock(return_value=False))
    handler.send_event = AsyncMock()

    await handler._speak_response("oi")

    handler.gemini_live_voice.speak.assert_awaited_once_with("oi", timeout=6.0)
    assert handler._voice_speaking is False


@pytest.mark.asyncio
async def test_failed_kore_initializes_fallback_once_and_plays_edge(capsys):
    handler = IPCHandler(AsyncMock())
    handler.gemini_live_voice = Mock(
        active=True,
        speak=AsyncMock(return_value=False),
        ultimo_audio_entregue=Mock(return_value=None),
    )
    handler.send_event = AsyncMock()
    edge = SimpleNamespace(voice_name="pt-BR-FranciscaNeural", play=Mock())
    manager = SimpleNamespace(edge=None, kokoro=None, gemini=None)

    def initialize():
        manager.edge = edge

    manager.initialize = Mock(side_effect=initialize)
    handler.tts_manager = manager

    await handler._speak_response("primeira resposta")
    await handler._speak_response("segunda resposta")

    manager.initialize.assert_called_once_with()
    assert handler._tts_initialized is True
    edge.play.assert_any_call("primeira resposta", blocking=True)
    edge.play.assert_any_call("segunda resposta", blocking=True)
    assert edge.play.call_count == 2
    assert "engine=edge/pt-BR-FranciscaNeural" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_partial_kore_audio_does_not_restart_phrase_in_fallback(capsys):
    handler = IPCHandler(AsyncMock())
    handler.gemini_live_voice = Mock(
        active=True,
        speak=AsyncMock(return_value=False),
        ultimo_audio_entregue=Mock(return_value=123.4),
    )
    handler.send_event = AsyncMock()
    edge = SimpleNamespace(voice_name="pt-BR-FranciscaNeural", play=Mock())
    manager = SimpleNamespace(
        edge=edge, kokoro=None, gemini=None, initialize=Mock(),
    )
    handler.tts_manager = manager

    await handler._speak_response("frase parcialmente falada")

    manager.initialize.assert_not_called()
    edge.play.assert_not_called()
    assert "SUPPRESSED_AFTER_LIVE_AUDIO" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_fallback_init_does_not_speak_after_voice_turn_is_invalidated():
    handler = IPCHandler(AsyncMock())
    handler.gemini_live_voice = Mock(
        active=True,
        speak=AsyncMock(return_value=False),
        ultimo_audio_entregue=Mock(return_value=None),
    )
    handler.send_event = AsyncMock()
    turn_id = handler._begin_voice_turn()
    edge = SimpleNamespace(voice_name="pt-BR-FranciscaNeural", play=Mock())
    manager = SimpleNamespace(edge=None, kokoro=None, gemini=None)

    def initialize():
        manager.edge = edge
        handler._invalidate_voice_turn()

    manager.initialize = Mock(side_effect=initialize)
    handler.tts_manager = manager

    await handler._speak_response("não falar", voice_turn_id=turn_id)

    manager.initialize.assert_called_once_with()
    edge.play.assert_not_called()


@pytest.mark.asyncio
async def test_voice_processing_returns_behind_wake_gate():
    handler = IPCHandler(AsyncMock())
    handler.voice_active = True
    handler.voice_pipeline = Mock()
    handler._try_jarvis_multi_action = AsyncMock(return_value="Pronto.")
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._speak_response = AsyncMock()

    await handler._process_voice_message("Zara, faça isso")

    handler.voice_pipeline.resume_listening.assert_called_with(require_wake_word=True)


@pytest.mark.asyncio
async def test_voice_answer_persistence_does_not_hold_speech_and_traces_completion(capsys):
    handler = IPCHandler(AsyncMock())
    handler.gemini_live_voice = None
    handler.voice_pipeline = None
    handler.voice_active = False
    handler.memory = None
    handler.lab_v1 = None
    handler.conversation_history = None
    handler.send_event = AsyncMock()
    handler._speak_response = AsyncMock()
    handler._front_conversation_reply = AsyncMock(return_value={
        "success": True, "response": "resposta privada", "engine": "test",
    })
    for name in (
        "_try_jarvis_multi_action", "_try_reminder_intent",
        "_try_operational_memory_intent", "_try_self_knowledge",
        "_try_file_intent", "_try_compound_pc_intent", "_try_pc_intent",
        "_try_lab_intent",
    ):
        setattr(handler, name, AsyncMock(return_value=None))

    entered = asyncio.Event()
    release = asyncio.Event()

    async def held_history(*_args, **_kwargs):
        entered.set()
        await release.wait()
        return None

    handler._append_conversation_message = held_history
    try:
        await asyncio.wait_for(handler._process_voice_message("converse comigo"), timeout=1)
        await asyncio.wait_for(entered.wait(), timeout=1)
        handler._speak_response.assert_awaited_once()
        assert len(handler._voice_persistence_tasks) == 1
        assert not next(iter(handler._voice_persistence_tasks)).done()
        assert "stage=VOICE_PERSIST" not in capsys.readouterr().out
    finally:
        release.set()
        await asyncio.gather(*tuple(handler._voice_persistence_tasks))
        await asyncio.sleep(0)  # Let the completion callback emit its trace.

    lines = [
        line for line in capsys.readouterr().out.splitlines()
        if "stage=VOICE_PERSIST" in line
    ]
    assert len(lines) == 1
    assert "result=FINISHED" in lines[0]
    assert float(lines[0].split("duration_ms=", 1)[1]) >= 0
    assert "resposta privada" not in lines[0]
