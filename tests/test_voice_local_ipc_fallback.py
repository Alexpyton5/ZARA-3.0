"""Focused proof that the no-Gemini voice path reports real readiness."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import core.ipc_handlers as ipc
from core.ipc_handlers import IPCHandler, IPCMessage


class _Pipeline:
    def __init__(self, state: str):
        self.vosk = object()
        self.audio = object()
        self._event_loop = None
        self._state = state

    @property
    def state(self):
        return self._state

    def start(self):
        return None


@pytest.mark.asyncio
async def test_local_voice_does_not_claim_success_when_pipeline_is_in_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ipc, "VOICE_AVAILABLE", True)
    send = AsyncMock()
    handler = IPCHandler(send)
    handler.voice_pipeline = _Pipeline("ERROR")

    await handler.handle_voice_start(IPCMessage(type="voice-start", request_id="r1"))

    assert handler.voice_active is False
    assert handler.voice_mode == "off"
    response = send.await_args.args[0]
    assert response.error and "Local voice unavailable" in response.error


@pytest.mark.asyncio
async def test_local_voice_reports_listening_only_after_pipeline_is_ready(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ipc, "VOICE_AVAILABLE", True)
    send = AsyncMock()
    handler = IPCHandler(send)
    handler.voice_pipeline = _Pipeline("LISTENING")

    await handler.handle_voice_start(IPCMessage(type="voice-start", request_id="r2"))

    assert handler.voice_active is True
    assert handler.voice_mode == "local"
    response = next(
        call.args[0] for call in send.await_args_list
        if call.args and call.args[0].type == "response"
    )
    assert response.response["success"] is True
    assert response.response["mode"] == "local"
