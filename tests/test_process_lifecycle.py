"""Process ownership, stdin EOF, and fail-closed shutdown contracts."""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
from unittest.mock import AsyncMock

import psutil
import pytest

import core.ipc_handlers as ipc_handlers
import integrations.hermes.ensure_gateway as gateway
from core.action_registry import get_registry
from core.ipc_handlers import IPCHandler
from integrations.hermes.integration import HermesIntegration


@pytest.fixture(autouse=True)
def reset_gateway_ownership():
    gateway.stop_gateway(timeout=0.2)
    yield
    gateway.stop_gateway(timeout=0.2)


def test_preexisting_gateway_is_used_but_never_adopted(monkeypatch):
    monkeypatch.setattr(gateway, "_url_alive", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        gateway.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("must not launch over an existing gateway"),
    )

    assert gateway.start_gateway()
    assert gateway.owned_gateway_pid() is None
    assert gateway.stop_gateway()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree contract")
def test_owned_windows_process_tree_is_terminated_without_name_based_kill(tmp_path):
    child_pid_file = tmp_path / "child.pid"
    child_code = "import time; time.sleep(60)"
    root_code = (
        "import pathlib, subprocess, sys, time; "
        f"p=subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(p.pid)); "
        "time.sleep(60)"
    )
    process = subprocess.Popen([sys.executable, "-c", root_code])
    owned = gateway._OwnedGateway(
        process=process,
        executable=os.path.realpath(sys.executable),
        identity=gateway._identity_for_pid(process.pid),
    )
    try:
        deadline = time.monotonic() + 5
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert child_pid_file.exists()
        child_pid = int(child_pid_file.read_text())

        assert gateway._terminate_exact_process_tree(owned, timeout=2.0)
        process.wait(timeout=3)
        assert not psutil.pid_exists(process.pid)
        assert not psutil.pid_exists(child_pid)
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.asyncio
async def test_failed_hermes_activation_stops_only_owned_gateway(monkeypatch):
    integration = HermesIntegration()
    integration.client = object()  # type: ignore[assignment]
    integration.health_check = AsyncMock(side_effect=[False, False])  # type: ignore[method-assign]
    stopped: list[bool] = []

    monkeypatch.setattr(gateway, "start_gateway", lambda _url: True)
    monkeypatch.setattr(gateway, "stop_gateway", lambda: stopped.append(True) or True)

    assert not await integration.enable_supercerebro()
    assert stopped == [True]
    assert not integration.enabled
    assert not integration.is_connected


@pytest.mark.asyncio
async def test_shutdown_frame_revokes_permission_and_exits_reader():
    sent = []

    async def send(message):
        sent.append(message)

    handler = IPCHandler(send)
    handler._set_supercerebro_state(True)
    reader = asyncio.StreamReader()
    reader.feed_data(
        (json.dumps({"type": "shutdown", "request_id": "shutdown-1", "payload": {}}) + "\n").encode()
    )
    reader.feed_eof()

    await asyncio.wait_for(ipc_handlers._consume_ipc_reader(handler, reader), timeout=1)

    assert handler.shutdown_requested
    assert not handler.supercerebro_active
    assert not get_registry().pc_control_allowed
    assert sent[-1].response == {"success": True, "shutting_down": True}


@pytest.mark.asyncio
async def test_handler_shutdown_is_fail_closed_and_idempotent():
    class FakeOwnedHermes:
        enabled = True
        is_connected = True

        def __init__(self):
            self.shutdown_calls = 0

        async def shutdown(self):
            self.shutdown_calls += 1
            self.enabled = False
            self.is_connected = False

    hermes = FakeOwnedHermes()
    handler = IPCHandler(AsyncMock())
    handler.hermes = hermes  # type: ignore[assignment]
    handler._set_supercerebro_state(True)

    await handler.shutdown()
    await handler.shutdown()

    assert handler.shutdown_requested
    assert handler._shutdown_complete
    assert not handler.supercerebro_active
    assert not get_registry().pc_control_allowed
    assert hermes.shutdown_calls == 1


@pytest.mark.asyncio
async def test_windows_pipe_path_selects_nonblocking_polling(monkeypatch):
    handler = IPCHandler(AsyncMock())
    calls: list[str] = []

    async def pipe_path(_handler):
        calls.append("pipe")

    async def console_path(_handler):
        calls.append("console")

    monkeypatch.setattr(ipc_handlers, "_windows_stdin_is_pipe", lambda: True)
    monkeypatch.setattr(ipc_handlers, "_run_windows_pipe_ipc", pipe_path)
    monkeypatch.setattr(ipc_handlers, "_run_windows_console_ipc", console_path)

    await ipc_handlers._run_windows_ipc(handler)
    assert calls == ["pipe"]


@pytest.mark.skipif(sys.platform != "win32", reason="PeekNamedPipe contract")
@pytest.mark.asyncio
async def test_windows_pipe_polling_consumes_frame_and_observes_broken_pipe(monkeypatch):
    sent = []

    async def send(message):
        sent.append(message)

    handler = IPCHandler(send)
    read_fd, write_fd = os.pipe()
    read_stream = os.fdopen(read_fd, "r", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", read_stream)
    try:
        frame = json.dumps(
            {"type": "shutdown", "request_id": "pipe-shutdown", "payload": {}}
        ).encode() + b"\n"
        os.write(write_fd, frame)
        os.close(write_fd)
        write_fd = -1

        await asyncio.wait_for(ipc_handlers._run_windows_pipe_ipc(handler), timeout=2)

        assert handler.shutdown_requested
        assert sent[-1].response == {"success": True, "shutting_down": True}
    finally:
        read_stream.close()
        if write_fd >= 0:
            os.close(write_fd)


@pytest.mark.asyncio
async def test_windows_console_eof_stops_fallback_loop(monkeypatch):
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    await asyncio.wait_for(ipc_handlers._run_windows_console_ipc(handler), timeout=1)
