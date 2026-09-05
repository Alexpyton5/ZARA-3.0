from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage
from core.voice_stt import VoiceConfig, VoicePipeline


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
