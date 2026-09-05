"""207/208 — destructive OS power confirmation gate.

Never invokes a real Windows power command: the gate must deny before any
subprocess call, and the authorized path is exercised only against a mock.
"""
from __future__ import annotations

import pytest

from core.action_registry import ActionRegistry
from core.actions import os_ops

DESTRUCTIVE = ["shutdown", "poweroff", "restart", "reboot", "sleep", "suspend", "hibernate", "logoff"]


@pytest.fixture(autouse=True)
def _no_real_power(monkeypatch):
    """Hard guard: any subprocess.run inside os_ops during these tests fails."""
    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError(f"REAL POWER COMMAND ATTEMPTED: {a!r}")
    monkeypatch.setattr(os_ops.subprocess, "run", _boom)
    monkeypatch.delenv("ZARA_ALLOW_OS_POWER", raising=False)


@pytest.mark.parametrize("action_type", DESTRUCTIVE)
def test_destructive_power_denied_by_default(action_type):
    res = os_ops.os_power_action(action_type)
    assert res.success is False
    assert res.error == "POWER_ACTION_DENIED"
    assert res.data["status"] == "DENIED"


def test_unknown_power_action_is_error_not_success(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    res = os_ops.os_power_action("__nope__")
    assert res.success is False
    assert "Unknown power action" in (res.error or "")


def test_empty_action_type_does_not_crash():
    res = os_ops.os_power_action("")
    assert res.success is False


def test_gate_holds_even_with_valid_high_risk_confirmation(monkeypatch):
    """A correct one-shot proof still cannot trigger a real power command."""
    registry = ActionRegistry()
    registry.register("os_power", os_ops.os_power_action, risk="HIGH", capability="SYSTEM_POWER")

    challenge = registry.execute("os_power", action_type="shutdown")
    assert challenge.success is False
    assert challenge.data["status"] == "CONFIRMATION_REQUIRED"
    conf = challenge.data["confirmation"]

    res = registry.execute_confirmed(
        "os_power",
        conf["confirmation_id"],
        conf["action_fingerprint"],
        action_type="shutdown",
    )
    assert res.success is False
    assert res.error == "POWER_ACTION_DENIED"


def test_missing_confirmation_is_denied():
    registry = ActionRegistry()
    registry.register("os_power", os_ops.os_power_action, risk="HIGH", capability="SYSTEM_POWER")
    res = registry.execute("os_power", action_type="restart")
    assert res.success is False
    assert res.data["status"] == "CONFIRMATION_REQUIRED"


def test_wrong_expired_and_reused_confirmation_are_denied():
    registry = ActionRegistry()
    registry.register("os_power", os_ops.os_power_action, risk="HIGH", capability="SYSTEM_POWER")

    challenge = registry.execute("os_power", action_type="restart")
    conf = challenge.data["confirmation"]

    # wrong fingerprint
    bad = registry.execute_confirmed("os_power", conf["confirmation_id"], "hmac-sha256:deadbeef", action_type="restart")
    assert bad.success is False
    assert bad.error in {"CONFIRMATION_MISMATCH", "CONFIRMATION_INVALID"}

    # reuse of the (now consumed) id
    again = registry.execute_confirmed("os_power", conf["confirmation_id"], conf["action_fingerprint"], action_type="restart")
    assert again.success is False
    assert again.error in {"CONFIRMATION_INVALID", "CONFIRMATION_EXPIRED"}


def test_authorized_path_calls_only_mock_handler(monkeypatch):
    """With the opt-in set, the handler runs — but against a mock, never Windows."""
    calls = []
    monkeypatch.setenv("ZARA_ALLOW_OS_POWER", "1")
    monkeypatch.setattr(os_ops.subprocess, "run", lambda *a, **k: calls.append(a) or None)
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")

    res = os_ops.os_power_action("sleep")
    assert res.success is True
    assert len(calls) == 1
    assert "rundll32.exe" in calls[0][0][0]
