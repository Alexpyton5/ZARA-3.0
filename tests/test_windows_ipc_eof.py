"""Regression tests for Windows stdin EOF handling."""

import asyncio
import io
import json
import sys

import pytest

from core import ipc_handlers
from core.ipc_handlers import (
    IPCHandler,
    IPCMessage,
    _run_ipc_with_parent_watchdog,
    _run_windows_ipc,
)


@pytest.mark.asyncio
async def test_windows_ipc_processes_frame_and_exits_after_eof(monkeypatch):
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    frame = json.dumps({"type": "action-list", "request_id": "one"})
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{frame}\n"))

    await asyncio.wait_for(_run_windows_ipc(IPCHandler(send)), timeout=1.0)

    assert [message.request_id for message in sent] == ["one"]
    assert sent[0].type == "response"


@pytest.mark.asyncio
async def test_windows_ipc_drains_all_queued_frames_before_eof(monkeypatch):
    handled: list[str | None] = []

    class RecordingHandler:
        async def handle_message(self, message: IPCMessage) -> None:
            handled.append(message.request_id)

    frames = [
        json.dumps({"type": "probe", "request_id": request_id})
        for request_id in ("first", "second", "third")
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(frames) + "\n"))

    await asyncio.wait_for(_run_windows_ipc(RecordingHandler()), timeout=1.0)

    assert handled == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_voice_start_cannot_starve_typed_message_ipc(monkeypatch):
    voice_started = asyncio.Event()
    release_voice = asyncio.Event()
    handled: list[str] = []

    class BlockingVoiceHandler:
        async def handle_message(self, message: IPCMessage) -> None:
            if message.type == "voice-start":
                voice_started.set()
                await release_voice.wait()
                handled.append("voice-finished")
                return
            await asyncio.wait_for(voice_started.wait(), timeout=0.5)
            handled.append(str(message.request_id))
            release_voice.set()

    frames = [
        json.dumps({"type": "voice-start", "request_id": "mic"}),
        json.dumps({"type": "send-message", "request_id": "typed"}),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(frames) + "\n"))

    await asyncio.wait_for(_run_windows_ipc(BlockingVoiceHandler()), timeout=1.0)

    assert "typed" in handled


@pytest.mark.asyncio
async def test_parent_watchdog_cancels_sidecar_ipc_when_electron_exits(monkeypatch):
    ipc_cancelled = asyncio.Event()

    async def blocked_ipc(_handler):
        try:
            await asyncio.Event().wait()
        finally:
            ipc_cancelled.set()

    async def parent_already_exited(_parent_pid):
        await asyncio.sleep(0)

    monkeypatch.setenv("ZARA_PARENT_PID", "4242")
    monkeypatch.setattr(ipc_handlers, "_run_windows_ipc", blocked_ipc)
    monkeypatch.setattr(ipc_handlers, "_wait_for_windows_parent_exit", parent_already_exited)

    await asyncio.wait_for(_run_ipc_with_parent_watchdog(object()), timeout=1.0)

    assert ipc_cancelled.is_set()
