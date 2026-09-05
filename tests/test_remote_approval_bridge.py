"""Security contract for the single-use remote approval bridge."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.remote_approval_bridge import RemoteApprovalBridge


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def bridge(clock: FakeClock) -> RemoteApprovalBridge:
    return RemoteApprovalBridge(lambda token: token == "valid", clock=clock)


def test_submit_returns_unique_pending_ids(bridge):
    first = bridge.submit_action("Restart service")
    second = bridge.submit_action("Restart service")
    assert first != second
    assert bridge.get_status(first) == "pending"


@pytest.mark.parametrize("description", ["", "  "])
def test_empty_action_is_rejected(bridge, description):
    with pytest.raises(ValueError):
        bridge.submit_action(description)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(bridge, timeout):
    with pytest.raises(ValueError):
        bridge.submit_action("Action", timeout)


def test_missing_failing_and_wrong_verifiers_fail_closed(clock):
    missing = RemoteApprovalBridge(None, clock=clock)
    missing_id = missing.submit_action("Action")
    assert missing.approve_action(missing_id, "anything") is False
    assert missing.get_status(missing_id) == "pending"

    def raises(_token):
        raise RuntimeError("adapter unavailable")

    failing = RemoteApprovalBridge(raises, clock=clock)
    failing_id = failing.submit_action("Action")
    assert failing.reject_action(failing_id, "anything") is False
    assert failing.get_status(failing_id) == "pending"

    wrong = RemoteApprovalBridge(lambda token: token == "expected", clock=clock)
    wrong_id = wrong.submit_action("Action")
    assert wrong.approve_action(wrong_id, "wrong") is False


def test_approve_then_consume_is_single_use(bridge):
    approval_id = bridge.submit_action("Restart service")
    assert bridge.approve_action(approval_id, "valid") is True
    assert bridge.get_status(approval_id) == "approved"
    assert bridge.consume_approval(approval_id) is True
    assert bridge.get_status(approval_id) == "consumed"
    assert bridge.consume_approval(approval_id) is False
    assert bridge.approve_action(approval_id, "valid") is False
    assert bridge.reject_action(approval_id, "valid") is False


def test_rejection_can_never_be_consumed(bridge):
    approval_id = bridge.submit_action("Delete data")
    assert bridge.reject_action(approval_id, "valid") is True
    assert bridge.get_status(approval_id) == "rejected"
    assert bridge.consume_approval(approval_id) is False


def test_pending_and_approved_requests_expire_without_sleep(bridge, clock):
    pending = bridge.submit_action("Pending", timeout_seconds=5)
    approved = bridge.submit_action("Approved", timeout_seconds=5)
    assert bridge.approve_action(approved, "valid") is True

    clock.advance(5)

    assert bridge.get_status(pending) == "expired"
    assert bridge.get_status(approved) == "expired"
    assert bridge.consume_approval(approved) is False


def test_expiry_during_slow_verification_fails_closed(clock):
    def verifier(_token):
        clock.advance(10)
        return True

    bridge = RemoteApprovalBridge(verifier, clock=clock)
    approval_id = bridge.submit_action("Action", timeout_seconds=5)
    assert bridge.approve_action(approval_id, "token") is False
    assert bridge.get_status(approval_id) == "expired"


def test_only_one_concurrent_remote_decision_wins(bridge):
    approval_id = bridge.submit_action("Action")
    barrier = threading.Barrier(20)

    def decide(index):
        barrier.wait()
        method = bridge.approve_action if index % 2 else bridge.reject_action
        return method(approval_id, "valid")

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(decide, range(20)))

    assert results.count(True) == 1
    assert bridge.get_status(approval_id) in {"approved", "rejected"}


def test_only_one_concurrent_consumer_is_authorized(bridge):
    approval_id = bridge.submit_action("Action")
    assert bridge.approve_action(approval_id, "valid")
    barrier = threading.Barrier(20)

    def consume(_index):
        barrier.wait()
        return bridge.consume_approval(approval_id)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(consume, range(20)))

    assert results.count(True) == 1
    assert bridge.get_status(approval_id) == "consumed"


def test_verifier_is_not_called_for_unknown_or_replayed_ids(clock):
    calls = 0

    def verifier(_token):
        nonlocal calls
        calls += 1
        return True

    bridge = RemoteApprovalBridge(verifier, clock=clock)
    assert bridge.approve_action("unknown", "token") is False
    approval_id = bridge.submit_action("Action")
    assert bridge.approve_action(approval_id, "token") is True
    assert bridge.approve_action(approval_id, "token") is False
    assert calls == 1


def test_adapter_token_is_never_stored(bridge):
    approval_id = bridge.submit_action("Action")
    bridge.approve_action(approval_id, "valid")
    assert "valid" not in repr(bridge._pending)


def test_terminal_history_is_bounded(clock):
    bridge = RemoteApprovalBridge(
        lambda _token: True,
        clock=clock,
        max_terminal_records=3,
    )
    ids = []
    for index in range(8):
        approval_id = bridge.submit_action(f"Action {index}")
        bridge.reject_action(approval_id, "token")
        ids.append(approval_id)
        clock.advance(1)

    # ZARA-TEST-DEBT-001: _pending guarda _ApprovalRecord (dataclass), nao
    # dict -- .status, nao ["status"].
    assert sum(record.status in bridge._TERMINAL for record in bridge._pending.values()) == 3
    assert bridge.get_status(ids[-1]) == "rejected"
    assert bridge.get_status(ids[0]) is None


def test_bridge_has_no_check_then_act_or_execution_api(bridge):
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == {
        "approve_action",
        "consume_approval",
        "get_status",
        "reject_action",
        "submit_action",
    }
