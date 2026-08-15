from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "context", "expected_param"),
    [
        ("volume em 30%", None, "30"),
        ("deixa um pouco mais alto", 30, "up"),
        ("deixa um pouco mais baixo", 30, "down"),
    ],
)
def test_volume_intent_recognition(phrase, context, expected_param):
    result = PcVoiceIntentDetector(
        pc_control_allowed=True,
        volume_context_level=context,
    ).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_volume"
    assert result.param == expected_param


def test_contextual_volume_without_volume_context_is_blocked_clearly():
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(
        "deixa um pouco mais alto"
    )

    assert result.is_pc_intent is True
    assert result.blocked is True
    assert "volume verificado" in result.reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starting_level", "phrase", "expected_target"),
    [
        (30, "deixa um pouco mais alto", 40),
        (30, "deixa um pouco mais baixo", 20),
        (95, "deixa um pouco mais alto", 100),
        (5, "deixa um pouco mais baixo", 0),
    ],
)
async def test_contextual_volume_uses_verified_context_and_limits(
    monkeypatch, starting_level, phrase, expected_target
):
    observed_levels = []

    async def fake_execute_action(action, **params):
        observed_levels.append((action, params["level"]))
        return type("Result", (), {"success": True, "error": ""})()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    handler._last_volume_level = starting_level
    handler._touch_operational_context()
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)
    monkeypatch.setattr("core.ipc_handlers._read_windows_volume", lambda: expected_target)

    reply = await handler._try_pc_intent(phrase)

    assert observed_levels == [("os_volume", expected_target)]
    assert handler._last_volume_level == expected_target
    assert reply == f"Volume definido para {expected_target}%."


@pytest.mark.asyncio
async def test_volume_success_without_post_action_read_does_not_claim_level(monkeypatch):
    async def fake_execute_action(action, **params):
        return type("Result", (), {"success": True, "error": ""})()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)
    monkeypatch.setattr("core.ipc_handlers._read_windows_volume", lambda: None)

    reply = await handler._try_pc_intent("coloque o volume em 30%")

    assert reply == "Ajustei, mas não consegui confirmar o nível."
    assert handler._last_volume_level is None
