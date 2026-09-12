import asyncio
from types import SimpleNamespace

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_actual_executor_failure_is_forwarded_without_blocking(monkeypatch):
    captured = []

    async def capture(action_id, **evidence):
        captured.append((action_id, evidence))
        return {"success": True}

    def executor():
        pass

    executor.__module__ = "core.actions.browser"
    registry = SimpleNamespace(_actions={"browser_open_url": executor})
    monkeypatch.setattr("core.action_registry.get_registry", lambda: registry)
    handler = IPCHandler.__new__(IPCHandler)
    handler.lab_v1 = SimpleNamespace(capture_runtime_failure=capture)
    handler._lab_v1_background_tasks = set()
    handler._active_voice_turn_id = 17

    handler._remember_action_failure("browser_open_url", "executor", "window did not open")
    assert captured == []
    await asyncio.sleep(0)

    action_id, evidence = captured[0]
    assert action_id == "browser_open_url"
    assert evidence["source_path"] == "core/actions/browser.py"
    assert evidence["status"] == "EXECUTOR_FAILED"
    assert evidence["channel"] == "voice" and evidence["run_id"] == "voice:17"


@pytest.mark.asyncio
async def test_policy_refusal_is_not_recorded_as_runtime_defect():
    captured = []

    async def capture(*args, **kwargs):
        captured.append((args, kwargs))

    handler = IPCHandler.__new__(IPCHandler)
    handler.lab_v1 = SimpleNamespace(capture_runtime_failure=capture)
    handler._lab_v1_background_tasks = set()
    handler._active_voice_turn_id = None
    handler._remember_action_failure("os_power", "capability_gate", "confirmation required")
    await asyncio.sleep(0)
    assert captured == []
