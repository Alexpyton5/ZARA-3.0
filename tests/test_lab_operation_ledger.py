from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from core.lab_v1.operation_ledger import IdempotencyConflict, OperationLedger


def test_first_admission_returns_a_durable_ack_and_replay_returns_the_same_ack(tmp_path):
    ledger = OperationLedger(tmp_path / "lab.db")

    first = ledger.admit("request-1", "lab.v1.submit", {"objective": "Improve ZARA"})
    replay = ledger.admit("request-1", "lab.v1.submit", {"objective": "Improve ZARA"})

    assert first.accepted is True
    assert first.request_id == "request-1"
    assert first.operation_id.startswith("operation:")
    assert replay == first
    operation = ledger.get_operation(first.operation_id)
    assert operation.state == "ADMITTED"
    assert operation.command == "lab.v1.submit"


def test_replay_survives_restart_and_canonicalizes_mapping_order(tmp_path):
    path = tmp_path / "lab.db"
    first = OperationLedger(path).admit(
        "request-1",
        "lab.v1.message",
        {"session_id": "session", "content": "continue"},
    )

    replay = OperationLedger(path).admit(
        "request-1",
        "lab.v1.message",
        {"content": "continue", "session_id": "session"},
    )

    assert replay == first
    operation = OperationLedger(path).get_operation(first.operation_id)
    assert operation.request_id == replay.request_id
    assert operation.command == replay.command
    assert operation.payload_sha256 == replay.payload_sha256
    assert operation.admitted_at == replay.accepted_at


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("lab.v1.cancel", {"objective": "Improve ZARA"}),
        ("lab.v1.submit", {"objective": "Replace ZARA"}),
    ],
)
def test_reusing_request_id_for_different_intent_is_rejected(tmp_path, command, payload):
    ledger = OperationLedger(tmp_path / "lab.db")
    original = ledger.admit("request-1", "lab.v1.submit", {"objective": "Improve ZARA"})

    with pytest.raises(IdempotencyConflict, match="request-1"):
        ledger.admit("request-1", command, payload)

    assert ledger.get("request-1") == original


@pytest.mark.parametrize(
    ("request_id", "command", "payload", "message"),
    [
        ("", "lab.v1.submit", {}, "Request id"),
        ("request-1", "", {}, "Command"),
        ("request-1", "lab.v1.submit", {"score": float("nan")}, "finite"),
        ("request-1", "lab.v1.submit", {"bad": object()}, "JSON-compatible"),
    ],
)
def test_invalid_admission_rolls_back_without_reserving_request_id(
    tmp_path, request_id, command, payload, message
):
    ledger = OperationLedger(tmp_path / "lab.db")

    with pytest.raises(ValueError, match=message):
        ledger.admit(request_id, command, payload)

    if request_id:
        assert ledger.get(request_id) is None


def test_concurrent_duplicate_admission_creates_one_operation(tmp_path):
    path = tmp_path / "lab.db"

    def admit_once(_):
        return OperationLedger(path).admit(
            "request-1", "lab.v1.submit", {"objective": "Improve ZARA"}
        )

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(admit_once, range(16)))

    assert len({item.operation_id for item in results}) == 1
    assert OperationLedger(path).count() == 1


def test_failed_operation_insert_cannot_reserve_an_ack(tmp_path, monkeypatch):
    ledger = OperationLedger(tmp_path / "lab.db")

    def fail_operation(*_args):
        raise RuntimeError("operation insert failed")

    monkeypatch.setattr(ledger, "_insert_operation", fail_operation)
    with pytest.raises(RuntimeError, match="operation insert failed"):
        ledger.admit("request-1", "lab.v1.submit", {"objective": "Improve ZARA"})

    assert ledger.get("request-1") is None
    assert ledger.count() == 0


def test_operation_and_ack_roll_back_when_commit_boundary_fails(tmp_path, monkeypatch):
    ledger = OperationLedger(tmp_path / "lab.db")

    def fail_before_commit(*_args):
        raise RuntimeError("commit boundary failed")

    monkeypatch.setattr(ledger, "_before_commit", fail_before_commit)
    with pytest.raises(RuntimeError, match="commit boundary failed"):
        ledger.admit("request-1", "lab.v1.submit", {"objective": "Improve ZARA"})

    assert ledger.get("request-1") is None
    assert ledger.count() == 0


def test_concurrent_conflicting_payloads_have_one_winner_and_one_persisted_operation(tmp_path):
    path = tmp_path / "lab.db"
    OperationLedger(path)

    def admit(objective):
        try:
            return OperationLedger(path).admit(
                "request-1", "lab.v1.submit", {"objective": objective}
            )
        except IdempotencyConflict:
            return "CONFLICT"

    objectives = ["Improve ZARA", "Replace ZARA"] * 8
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(admit, objectives))

    acknowledgements = [item for item in results if item != "CONFLICT"]
    assert acknowledgements
    assert len({item.operation_id for item in acknowledgements}) == 1
    assert "CONFLICT" in results
    assert OperationLedger(path).count() == 1
