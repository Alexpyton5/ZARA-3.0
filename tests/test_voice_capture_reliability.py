from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", ["zara", "lázara", "o lazara"])
async def test_local_wake_opens_gate_and_next_audio_reaches_live_session(partial):
    states = AsyncMock()
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(
            api_key="test",
            audio_transport="renderer",
            wake_word_enabled=True,
        ),
        on_state=states,
    )
    voice._loop = asyncio.get_running_loop()
    voice._audio_queue = asyncio.Queue()
    voice._wake_detector = Mock()
    voice._wake_detector.PartialResult.return_value = f'{{"partial": "{partial}"}}'

    voice._queue_audio(b"\x00\x00" * 160, level=0.2)
    await asyncio.sleep(0)

    assert voice.gate_open is True
    assert voice._audio_queue.empty()
    states.assert_awaited_once_with("LISTENING")

    command_audio = b"\x01\x00" * 160
    voice._queue_audio(command_audio, level=0.2)

    assert voice._audio_queue.get_nowait() == command_audio


class _TranscriptSession:
    def __init__(self, transcript: str, stop_event: asyncio.Event):
        self.transcript = transcript
        self.stop_event = stop_event

    async def receive(self):
        yield SimpleNamespace(
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text=self.transcript),
            )
        )
        yield SimpleNamespace(
            server_content=SimpleNamespace(model_turn=SimpleNamespace(parts=[]))
        )
        yield SimpleNamespace(server_content=SimpleNamespace(turn_complete=True))
        self.stop_event.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transcript",
    [
        "Zara, que horas são?",
        "Lázara, que horas são?",
        "o Lazara, que horas são?",
    ],
)
async def test_live_transcription_is_delivered_once_to_backend(transcript):
    on_turn = AsyncMock()
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(api_key="test", audio_transport="renderer"),
        on_turn=on_turn,
        can_answer_directly=lambda _text: False,
    )

    await voice._receive_loop(_TranscriptSession(transcript, voice._stop), sd=None)
    await asyncio.sleep(0)

    on_turn.assert_awaited_once_with(transcript, "", False)
