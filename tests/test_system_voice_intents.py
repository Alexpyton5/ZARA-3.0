from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.action_registry import ActionResult
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "action"),
    [
        ("como está o computador", "system_metrics"),
        ("status do pc", "system_metrics"),
        ("mostre as informações do sistema", "system_info"),
        ("liste os processos", "system_processes"),
        ("que horas são?", "system_time"),
    ],
)
def test_read_only_system_commands_are_local(phrase, action):
    result = PcVoiceIntentDetector().detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == action
    assert result.blocked is False


@pytest.mark.asyncio
async def test_ipc_returns_real_system_action_output(monkeypatch):
    execute = AsyncMock(return_value=ActionResult(success=True, output="CPU: 12% | RAM: 34%"))
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_pc_intent("como está o computador")

    assert reply == "CPU: 12% | RAM: 34%"
    execute.assert_awaited_once_with("system_metrics")


@pytest.mark.asyncio
async def test_process_list_is_bounded(monkeypatch):
    execute = AsyncMock(return_value=ActionResult(success=True, output="[]"))
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    handler = IPCHandler(AsyncMock())

    await handler._try_pc_intent("liste os processos")

    execute.assert_awaited_once_with("system_processes", limit=10)


@pytest.mark.parametrize(
    ("phrase", "action"),
    [
        ("ativar modo noturno", "os_night_light_on"),
        ("ative a luz noturna", "os_night_light_on"),
        ("desativar modo noturno", "os_night_light_off"),
    ],
)
def test_night_light_natural_variants_are_deterministic(phrase, action):
    result = PcVoiceIntentDetector().detect(phrase)
    assert result.is_pc_intent is True
    assert result.action == action
    assert result.blocked is False
