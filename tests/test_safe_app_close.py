from __future__ import annotations

import ctypes
from unittest.mock import AsyncMock

import pytest

from core.action_registry import ActionResult
from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "app"),
    [
        ("feche a calculadora", "calculator"),
        ("feche o gerenciador de tarefas", "task_manager"),
        ("feche as configurações", "settings"),
        ("feche o spotify", "spotify"),
    ],
)
def test_safe_close_intents_are_local_without_supercerebro(phrase, app):
    result = PcVoiceIntentDetector(pc_control_allowed=False).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_close_safe_app"
    assert result.param == app
    assert result.blocked is False


@pytest.mark.parametrize("app", ["powershell", "regedit", "unknown"])
def test_non_allowlisted_apps_are_never_closed(app, monkeypatch):
    running = AsyncMock()
    monkeypatch.setattr(os_ops, "_running_app_pids", running)

    result = os_ops.os_close_safe_app_action(app)

    assert result.success is False
    assert result.data == {"app": app, "allowlisted": False}
    running.assert_not_called()


def test_safe_close_requires_window_to_disappear(monkeypatch):
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: {123})
    monkeypatch.setattr(os_ops, "_window_for_safe_app", lambda app, pids: 456)
    monkeypatch.setattr(os_ops, "_window_pid", lambda hwnd: 123)
    monkeypatch.setattr(ctypes.windll.user32, "PostMessageW", lambda *args: 1)
    states = iter((1, 0, 0))
    monkeypatch.setattr(ctypes.windll.user32, "IsWindow", lambda hwnd: next(states))
    monkeypatch.setattr(os_ops.time, "sleep", lambda _: None)

    result = os_ops.os_close_safe_app_action("task_manager")

    assert result.success is True
    assert result.data["verified_closed"] is True


@pytest.mark.asyncio
async def test_ipc_routes_explicit_safe_close(monkeypatch):
    execute = AsyncMock(
        return_value=ActionResult(success=True, output="Gerenciador de Tarefas fechado e verificado.")
    )
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_pc_intent("feche o gerenciador de tarefas")

    assert reply == "Gerenciador de Tarefas fechado e verificado."
    execute.assert_awaited_once_with("os_close_safe_app", app="task_manager")
