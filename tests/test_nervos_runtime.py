"""Integration checks for the optional NERVOS backend lifecycle."""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

_pythonpath = os.environ.get("PYTHONPATH")
try:
    import main as backend_entry
finally:
    if _pythonpath is not None:
        os.environ["PYTHONPATH"] = _pythonpath


@pytest.mark.asyncio
async def test_backend_starts_nervos_on_real_inbox_and_stops_after_ipc(monkeypatch, tmp_path, capsys):
    from core import ipc_handlers, paths
    from core import nervos_daemon

    inbox = tmp_path / "ZOE-INBOX"
    inbox.mkdir()
    (inbox / "heartbeat.json").write_text(
        json.dumps({"ts": time.time(), "hora": "test-heartbeat"}), encoding="utf-8"
    )
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    lifecycle = []

    class RecordingRonda(nervos_daemon.NervosRonda):
        def iniciar(self):
            lifecycle.append(("start", self.inbox_dir))
            super().iniciar()

        def parar(self):
            lifecycle.append(("stop", self.inbox_dir))
            super().parar()

    monkeypatch.setattr(nervos_daemon, "NervosRonda", RecordingRonda)

    async def fake_ipc_main():
        assert lifecycle == [("start", str(inbox))]

    monkeypatch.setattr(ipc_handlers, "main", fake_ipc_main)
    await backend_entry.run_ipc_handler()

    assert lifecycle == [("start", str(inbox)), ("stop", str(inbox))]
    output = capsys.readouterr().out
    assert '"zoe_presente": true' in output
    assert "[NERVOS] monitor stopped" in output


@pytest.mark.asyncio
async def test_backend_continues_when_nervos_cannot_start(monkeypatch, tmp_path):
    from core import ipc_handlers, paths
    from core import nervos_daemon

    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    ipc_started = []

    class UnavailableRonda:
        def __init__(self, inbox_dir):
            self.inbox_dir = inbox_dir

        def iniciar(self):
            raise OSError("monitor unavailable")

        def parar(self):
            raise AssertionError("failed monitor is not active")

    async def fake_ipc_main():
        ipc_started.append(True)

    monkeypatch.setattr(nervos_daemon, "NervosRonda", UnavailableRonda)
    monkeypatch.setattr(ipc_handlers, "main", fake_ipc_main)
    await backend_entry.run_ipc_handler()

    assert ipc_started == [True]


@pytest.mark.asyncio
async def test_smoke_backend_does_not_start_monitor_on_live_inbox(monkeypatch):
    from core import ipc_handlers, nervos_daemon

    monkeypatch.setenv("ZARA_SMOKE_TEST", "1")
    ipc_started = []

    class ForbiddenRonda:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("smoke mode must not attach to the live inbox")

    async def fake_ipc_main():
        ipc_started.append(True)

    monkeypatch.setattr(nervos_daemon, "NervosRonda", ForbiddenRonda)
    monkeypatch.setattr(ipc_handlers, "main", fake_ipc_main)

    await backend_entry.run_ipc_handler()

    assert ipc_started == [True]


def test_packaged_backend_resolves_live_workspace_inbox(monkeypatch, tmp_path):
    from core import paths

    package_backend = tmp_path / "installed" / "resources" / "backend"
    workspace_inbox = tmp_path / "Downloads" / "ZARA 3.0 CLEAN 002" / "ZOE-INBOX"
    workspace_inbox.mkdir(parents=True)
    (workspace_inbox / "heartbeat.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "project_root", lambda: package_backend)
    monkeypatch.setattr(backend_entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))

    assert backend_entry._resolve_nervos_inbox_dir(package_backend) == workspace_inbox


@pytest.mark.asyncio
async def test_nervos_status_is_logged_periodically(monkeypatch, capsys):
    statuses = [
        {"zoe_presente": True, "ultimo_sinal": "first", "idade_s": 1.0},
        {"zoe_presente": False, "ultimo_sinal": "second", "idade_s": 601.0},
    ]
    two_statuses_logged = asyncio.Event()

    class ChangingRonda:
        calls = 0

        def get_status(self):
            value = statuses[min(self.calls, len(statuses) - 1)]
            self.calls += 1
            if self.calls >= len(statuses):
                two_statuses_logged.set()
            return value

    task = asyncio.create_task(
        backend_entry._log_nervos_status_periodically(ChangingRonda(), interval_seconds=0.001)
    )
    try:
        await asyncio.wait_for(two_statuses_logged.wait(), timeout=1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    output = capsys.readouterr().out
    assert '"ultimo_sinal": "first"' in output
    assert '"ultimo_sinal": "second"' in output
