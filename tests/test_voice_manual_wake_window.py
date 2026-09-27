from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

import core.ipc_handlers as ipc
from core.ipc_handlers import IPCHandler, IPCMessage


class _LiveVoice:
    def __init__(self, *, active: bool = False, error: Exception | None = None):
        self.active = active
        self.error = error

    async def start(self, timeout: float = 20.0):
        if self.error is not None:
            raise self.error
        self.active = True
        return self.status()

    def status(self):
        return {
            "active": self.active,
            "mode": "gemini_live",
            "session_state": "LISTENING",
            "audio_transport": "renderer",
        }


def _handler(live: _LiveVoice) -> IPCHandler:
    handler = IPCHandler(AsyncMock())
    handler.gemini_live_voice = live
    handler._ligar_vigia_das_respostas = AsyncMock()
    return handler


@pytest.mark.asyncio
async def test_manual_mic_arms_first_turn_after_live_start(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured-for-test")
    handler = _handler(_LiveVoice())

    before = time.monotonic()
    await handler.handle_voice_start(IPCMessage(type="voice-start", request_id="manual-1"))

    assert handler.voice_active is True
    assert handler._manual_voice_session is True
    assert handler._gemini_wake_armed_until >= before + handler._JANELA_DE_CONVERSA


@pytest.mark.asyncio
async def test_manual_mic_rearms_first_turn_when_live_is_already_running():
    handler = _handler(_LiveVoice(active=True))
    handler.voice_active = True

    before = time.monotonic()
    await handler.handle_voice_start(IPCMessage(type="voice-start", request_id="manual-2"))

    assert handler._gemini_wake_armed_until >= before + handler._JANELA_DE_CONVERSA
    assert handler._manual_voice_session is True


@pytest.mark.asyncio
async def test_failed_manual_mic_start_does_not_arm_window(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured-for-test")
    monkeypatch.setattr(ipc, "VOICE_AVAILABLE", False)
    handler = _handler(_LiveVoice(error=RuntimeError("live unavailable")))

    await handler.handle_voice_start(IPCMessage(type="voice-start", request_id="manual-3"))

    assert handler.voice_active is False
    assert handler._manual_voice_session is False
    assert handler._gemini_wake_armed_until == 0.0


@pytest.mark.asyncio
async def test_manual_mic_keeps_accepting_turns_after_wake_timer_expires():
    handler = IPCHandler(AsyncMock())
    handler._manual_voice_session = True
    handler._gemini_wake_armed_until = 0.0
    handler._append_conversation_message = AsyncMock(return_value={})
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await handler._on_gemini_live_turn("continue nossa conversa", "draft")

    handler._process_voice_message.assert_awaited_once_with("continue nossa conversa")


@pytest.mark.asyncio
@pytest.mark.parametrize("spoken", ["Lázara, que horas são?", "o Lazara, que horas são?"])
async def test_observed_wake_transcriptions_route_without_opening_always_on_gate(spoken):
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock(return_value={})
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await handler._on_gemini_live_turn(spoken, "draft")

    handler._process_voice_message.assert_awaited_once_with("que horas são?")
