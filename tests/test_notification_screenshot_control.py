from __future__ import annotations

import builtins

import pytest

from core.action_registry import get_registry
from core.actions import os_ops
import core.actions  # noqa: F401 -- garante que as actions estao registradas
from core.action_registry import get_registry


def load_capability(name):
    return get_registry().get_spec(name) is not None
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "action", "param"),
    [
        ("tire uma captura de tela", "vision_screenshot", "full"),
        ("capture screenshot", "vision_screenshot", "full"),
        ("mostre uma notificação dizendo teste concluído", "os_notify", "teste concluído"),
    ],
)
def test_visual_commands_are_local_voice_intents(phrase, action, param):
    result = PcVoiceIntentDetector(pc_control_allowed=False).detect(phrase)

    assert result.action == action
    assert result.param == param
    assert result.blocked is False


def test_notification_fallback_never_interpolates_message_into_script(monkeypatch):
    original_import = builtins.__import__
    calls = []

    def controlled_import(name, *args, **kwargs):
        if name == "win10toast":
            raise ImportError
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", controlled_import)
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    malicious = 'fim"; Stop-Process -Name explorer; #'
    result = os_ops.os_notify_action("ZARA", malicious, timeout=2)

    assert result.success is True
    command = calls[0][0][0]
    assert malicious not in command[-1]
    assert calls[0][1]["env"]["ZARA_NOTIFY_MESSAGE"] == malicious
    assert result.data["visual_verified"] is False


def test_notification_metadata_is_low_risk_local_control():
    assert load_capability("os_notify") is True
    spec = get_registry().get_spec("os_notify")

    assert spec.risk == "LOW"
    assert spec.capability == "LOCAL_PC_CONTROL"
