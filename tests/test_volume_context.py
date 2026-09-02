from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "context", "expected_param"),
    [
        ("volume em 30%", None, "30"),
        # ZARA-INTENSIDADE-VOLUME-001: "um pouco" explícito agora vira um
        # passo menor de verdade (5, não os 10 padrão) em vez de ser ignorado.
        ("deixa um pouco mais alto", 30, "up_pouco"),
        ("deixa um pouco mais baixo", 30, "down_pouco"),
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


# ZARA-INTENSIDADE-VOLUME-001 (Alex, 2026-08-28): "põe o som lá em baixo"
# virava -10% fixo, igual a "diminua um pouco" -- nenhuma diferença de
# magnitude. Agora frase com intensidade explícita ou idiomática usa um
# passo maior (30) na mesma hora, sem chamada de rede nova.
@pytest.mark.parametrize(
    ("phrase", "expected_param"),
    [
        ("diminua muito o volume", "down_muito"),
        ("abaixa bastante o volume", "down_muito"),
        ("aumenta muito o volume", "up_muito"),
        ("põe o som lá em baixo", "down_muito"),
        ("poe o volume la embaixo", "down_muito"),
        ("diminua o volume", "down"),
    ],
)
def test_volume_intensity_recognition(phrase, expected_param):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_volume"
    assert result.param == expected_param


@pytest.mark.asyncio
async def test_volume_muito_applies_larger_step_immediately(monkeypatch):
    observed_levels = []
    # Primeira leitura = nível ANTES do ajuste (usado pra calcular o alvo);
    # segunda leitura = verificação PÓS-ação, que num sistema real já reflete
    # a mudança. Um mock estático não simula o Windows mudando de estado.
    read_calls = {"n": 0}

    async def fake_execute_action(action, **params):
        observed_levels.append((action, params["level"]))
        return type("Result", (), {"success": True, "error": ""})()

    def fake_read_volume():
        read_calls["n"] += 1
        return 50 if read_calls["n"] == 1 else 20

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)
    monkeypatch.setattr("core.ipc_handlers._read_windows_volume", fake_read_volume)

    reply = await handler._try_pc_intent("diminua muito o volume")

    assert observed_levels == [("os_volume", 20)]
    assert reply == "Volume definido para 20%."


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
        (30, "deixa um pouco mais alto", 35),
        (30, "deixa um pouco mais baixo", 25),
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
