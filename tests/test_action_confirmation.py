"""One-shot HIGH-risk confirmation contract tests with in-memory fakes only."""

from concurrent.futures import ThreadPoolExecutor

from core.action_confirmation import ConfirmationBroker
from core.action_registry import ActionRegistry


def _isolated_registry() -> ActionRegistry:
    registry = object.__new__(ActionRegistry)
    registry._initialized = False
    ActionRegistry.__init__(registry)
    registry._audit_action = lambda _name, _spec, _result: None
    return registry


def _grant_ok(monkeypatch, tmp_path):
    """Portão do PC exige grant WhatsApp válido (ordem do Alex, 02/10/2026)."""
    from core import supercerebro_grant as sg
    p = tmp_path / "whatsapp_grant.json"
    sg.write_grant(minutes=30, path=p)
    monkeypatch.setenv("ZARA_WHATSAPP_GRANT_PATH", str(p))


def _proof(result):
    return result.data["confirmation"]


def test_challenge_has_fixed_shape_and_allowlisted_summary():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "terminal",
        lambda command: calls.append(command) or "done",
        risk="HIGH",
    )

    result = registry.execute("terminal", command="echo exact-target")

    assert not result.success
    assert result.error == "CONFIRMATION_REQUIRED"
    assert result.data["status"] == "CONFIRMATION_REQUIRED"
    confirmation = result.data["confirmation"]
    assert set(confirmation) == {
        "confirmation_id",
        "action_fingerprint",
        "expires_at",
        "action",
        "summary",
    }
    assert confirmation["action"] == "terminal"
    assert "echo exact-target" in confirmation["summary"]
    assert calls == []


def test_exact_proof_executes_once_and_replay_is_blocked():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "files_delete",
        lambda path: calls.append(path) or "deleted",
        risk="HIGH",
    )
    challenge = registry.execute("files_delete", path="C:/fake/target.txt")
    proof = _proof(challenge)

    first = registry.execute_confirmed(
        "files_delete",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        path="C:/fake/target.txt",
    )
    replay = registry.execute_confirmed(
        "files_delete",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        path="C:/fake/target.txt",
    )

    assert first.success
    assert not replay.success
    assert replay.error == "CONFIRMATION_INVALID"
    assert calls == ["C:/fake/target.txt"]


def test_parameter_mismatch_consumes_proof_without_execution():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "files_delete",
        lambda path: calls.append(path) or "deleted",
        risk="HIGH",
    )
    challenge = registry.execute("files_delete", path="C:/fake/a.txt")
    proof = _proof(challenge)

    mismatch = registry.execute_confirmed(
        "files_delete",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        path="C:/fake/b.txt",
    )
    retry = registry.execute_confirmed(
        "files_delete",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        path="C:/fake/a.txt",
    )

    assert mismatch.error == "CONFIRMATION_MISMATCH"
    assert retry.error == "CONFIRMATION_INVALID"
    assert calls == []


def test_expired_proof_is_rejected_without_sleeping():
    now = [100.0]
    registry = _isolated_registry()
    registry._confirmation_broker = ConfirmationBroker(
        ttl_seconds=30,
        clock=lambda: now[0],
        wall_clock=lambda: 1_700_000_000,
    )
    calls: list[str] = []
    registry.register(
        "system_kill",
        lambda pid: calls.append(pid) or "killed",
        risk="HIGH",
    )
    challenge = registry.execute("system_kill", pid=123)
    proof = _proof(challenge)
    now[0] = 131.0

    result = registry.execute_confirmed(
        "system_kill",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        pid=123,
    )

    assert result.error == "CONFIRMATION_EXPIRED"
    assert calls == []


def test_retired_capability_gate_does_not_revoke_valid_high_risk_proof(monkeypatch, tmp_path):
    _grant_ok(monkeypatch, tmp_path)
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "terminal",
        lambda command: calls.append(command) or "done",
        risk="HIGH",
        capability="PC_CONTROL",
    )

    challenge = registry.execute("terminal", command="echo safe")
    proof = _proof(challenge)
    registry.pc_control_allowed = False
    executed = registry.execute_confirmed(
        "terminal",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        command="echo safe",
    )
    retry = registry.execute_confirmed(
        "terminal",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        command="echo safe",
    )

    assert executed.success
    assert retry.error == "CONFIRMATION_INVALID"
    assert calls == ["echo safe"]


def test_policy_metadata_change_invalidates_proof():
    registry = _isolated_registry()
    registry.register("os_power", lambda action_type: "done", risk="HIGH")
    challenge = registry.execute("os_power", action_type="shutdown")
    proof = _proof(challenge)
    registry.get_spec("os_power").category = "changed-after-challenge"

    result = registry.execute_confirmed(
        "os_power",
        proof["confirmation_id"],
        proof["action_fingerprint"],
        action_type="shutdown",
    )

    assert result.error == "CONFIRMATION_MISMATCH"


def test_unmapped_high_action_fails_closed_without_challenge():
    registry = _isolated_registry()
    registry.register("unknown_high", lambda target: "done", risk="HIGH")

    result = registry.execute("unknown_high", target="anything")

    assert result.error == "CONFIRMATION_POLICY_MISSING"
    assert result.data == {"status": "CONFIRMATION_POLICY_MISSING"}


def test_concurrent_redemption_executes_at_most_once():
    registry = _isolated_registry()
    calls: list[int] = []
    registry.register(
        "system_kill",
        lambda pid: calls.append(pid) or "done",
        risk="HIGH",
    )
    challenge = registry.execute("system_kill", pid=321)
    proof = _proof(challenge)

    def redeem():
        return registry.execute_confirmed(
            "system_kill",
            proof["confirmation_id"],
            proof["action_fingerprint"],
            pid=321,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: redeem(), range(2)))

    assert sum(result.success for result in results) == 1
    assert calls == [321]


def test_raw_params_are_not_logged_or_stored(capsys):
    registry = _isolated_registry()
    registry.register("files_delete", lambda path: "done", risk="HIGH")
    secret_path = "C:/fake/private-do-not-log.txt"

    result = registry.execute("files_delete", path=secret_path)

    assert result.error == "CONFIRMATION_REQUIRED"
    assert secret_path not in capsys.readouterr().out
    assert secret_path not in repr(registry._confirmation_broker._pending)
