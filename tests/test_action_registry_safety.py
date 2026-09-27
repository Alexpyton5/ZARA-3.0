"""Regression tests for the action risk and capability gates.

All registered actions in this module are in-memory fakes. No real action,
database, filesystem mutation, or PC-control primitive is invoked.
"""

import asyncio

import pytest

from core.action_registry import ActionRegistry


def _isolated_registry() -> ActionRegistry:
    registry = object.__new__(ActionRegistry)
    registry._initialized = False
    ActionRegistry.__init__(registry)
    # Executing fake MEDIUM/HIGH actions must not initialize the real audit DB.
    registry._audit_action = lambda _name, _spec, _result: None
    return registry


@pytest.mark.parametrize(
    "untrusted_confirmation",
    [None, False, 0, 1, "true", "false", {}, []],
)
def test_high_risk_legacy_confirmation_only_returns_challenge(untrusted_confirmation):
    registry = _isolated_registry()
    calls: list[str] = []

    def fake_destructive_action(command: str) -> str:
        calls.append("ran")
        return "done"

    registry.register(
        "terminal",
        fake_destructive_action,
        risk="HIGH",
        requires_confirmation=True,
    )

    result = registry.execute(
        "terminal",
        command="echo safe",
        confirm=untrusted_confirmation,
    )

    assert not result.success
    assert result.error == "CONFIRMATION_REQUIRED"
    assert calls == []


def test_high_risk_does_not_accept_explicit_boolean_true():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "terminal",
        lambda command: calls.append(command) or "done",
        risk="HIGH",
        requires_confirmation=True,
    )

    result = registry.execute("terminal", command="echo safe", confirm=True)

    assert not result.success
    assert result.error == "CONFIRMATION_REQUIRED"
    assert calls == []


def test_medium_risk_stays_closed_until_separately_authorized():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register("fake_medium", lambda: calls.append("ran") or "done", risk="MEDIUM")

    blocked = registry.execute("fake_medium")
    string_blocked = registry.execute("fake_medium", confirm="true")
    confirmed = registry.execute("fake_medium", confirm=True)

    registry.medium_risk_open = True
    policy_authorized = registry.execute("fake_medium")

    assert not blocked.success
    assert not string_blocked.success
    assert confirmed.success
    assert policy_authorized.success
    assert calls == ["ran", "ran"]


def test_supercerebro_off_blocks_non_read_only_even_with_confirmation():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "fake_pc_control",
        lambda: calls.append("ran") or "done",
        risk="LOW",
        capability="PC_CONTROL",
    )

    result = registry.execute("fake_pc_control", confirm=True)

    assert not result.success
    assert "Superc" in result.error
    assert calls == []


def test_supercerebro_off_keeps_sanitized_read_only_available():
    registry = _isolated_registry()
    registry.register("fake_read", lambda: "safe", capability="READ_ONLY")

    result = registry.execute("fake_read")

    assert result.success
    assert result.output == "safe"


def test_registration_normalizes_known_policy_values():
    registry = _isolated_registry()
    registry.register("normalized", lambda: "done", risk="high", capability="pc_control")

    spec = registry.get_spec("normalized")

    assert spec.risk == "HIGH"
    assert spec.capability == "PC_CONTROL"


def test_legacy_local_pc_control_uses_existing_gate():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "legacy_pc_control",
        lambda: calls.append("ran") or "done",
        capability="LOCAL_PC_CONTROL",
    )

    assert registry.get_spec("legacy_pc_control").capability == "PC_CONTROL"
    blocked = registry.execute("legacy_pc_control", confirm=True)
    assert not blocked.success
    assert calls == []


@pytest.mark.parametrize(
    ("metadata", "value"),
    [("risk", "CRITICAL"), ("capability", "UNRESTRICTED")],
)
def test_registration_rejects_unknown_policy_values_without_orphan_action(metadata, value):
    registry = _isolated_registry()
    kwargs = {metadata: value}

    with pytest.raises(ValueError):
        registry.register("invalid_policy", lambda: "must not run", **kwargs)

    assert registry.get("invalid_policy") is None
    assert registry.get_spec("invalid_policy") is None


def test_async_gate_matches_sync_gate():
    registry = _isolated_registry()
    calls: list[str] = []

    async def fake_destructive_action(script: str) -> str:
        calls.append("ran")
        return "done"

    registry.register("browser_eval", fake_destructive_action, risk="HIGH")

    challenge = asyncio.run(
        registry.execute_async("browser_eval", script="return 1", confirm=True)
    )
    proof = challenge.data["confirmation"]
    confirmed = asyncio.run(
        registry.execute_confirmed_async(
            "browser_eval",
            proof["confirmation_id"],
            proof["action_fingerprint"],
            script="return 1",
        )
    )

    assert not challenge.success
    assert confirmed.success
    assert calls == ["ran"]
