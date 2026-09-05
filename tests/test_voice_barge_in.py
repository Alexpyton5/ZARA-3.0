"""Barge-in: quando Alex fala enquanto a ZARA reproduz audio, a reproducao para imediatamente."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_barge_in_stops_speech_immediately():
    """Quando Alex fala durante a fala da ZARA, o audio para imediatamente."""
    sender = AsyncMock()
    handler = IPCHandler(sender)
    handler._voice_speaking = True

    await handler._on_gemini_live_interrupt()

    assert handler._voice_speaking is False
    assert handler._fala_interrompida is True
    events = [call.args[0] for call in sender.await_args_list]
    assert [(event.type, event.state) for event in events[:1]] == [
        ("state-change", "LISTENING")
    ]
    assert (events[1].type, events[1].level, events[1].tone, events[1].speaking) == (
        "voice-level",
        0.0,
        0.5,
        False,
    )


@pytest.mark.asyncio
async def test_barge_in_resets_turn_state():
    """Barge-in deve resetar o estado do turno para permitir novo processamento."""
    # Arrange
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key="test"))
    voice._utterance_open = True
    voice._turn_route_decided = True
    voice._turn_direct = True
    voice._turn_echo_suspect = True
    voice._turn_echo_references = ("test",)
    voice._turn_rejected_as_echo = True
    voice._routed_turn_task = AsyncMock()

    # Act
    voice._reset_turn_state()

    # Assert
    assert voice._utterance_open is False
    assert voice._turn_route_decided is False
    assert voice._turn_direct is False
    assert voice._turn_echo_suspect is False
    assert voice._turn_echo_references == ()
    assert voice._turn_rejected_as_echo is False
    # _routed_turn_task is not reset by _reset_turn_state; it is managed by _cancel_superseded_routed_turn
    # at the beginning of the next utterance. We do not assert on it here.


@pytest.mark.asyncio
async def test_barge_in_sets_turn_echo_suspect_when_speaking():
    """Quando ZARA está falando e Alex começa a falar, turn_echo_suspect deve ser True."""
    # Arrange
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key="test"))
    voice._assistant_output_active = True  # Simular que ZARA está falando

    # Act
    voice._begin_utterance()  # Alex começa a falar

    # Assert
    assert voice._turn_echo_suspect is True  # Deve ser True pois ZARA estava falando


@pytest.mark.asyncio
async def test_barge_in_clears_audio_queues():
    """Barge-in deve limpar as filas de audio para evitar eco."""
    output_callback = AsyncMock()
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(api_key="test", audio_transport="renderer"),
        on_output_audio=output_callback,
    )
    voice._flush_output = Mock()

    await voice.interrupt_speech()

    voice._flush_output.assert_called_once_with()
    output_callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_barge_in_renderer_emits_stop_command():
    """O renderer deve receber um comando explícito para cortar a Kore."""
    sender = AsyncMock()
    handler = IPCHandler(sender)

    await handler._on_gemini_live_output_audio(b"")

    sender.assert_awaited_once()
    event = sender.await_args.args[0]
    assert (event.type, event.data) == ("voice-output-audio", {"stop": True})
