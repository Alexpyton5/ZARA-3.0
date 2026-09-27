"""Durable operation results mirrored into the Lab event stream without IPC."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from core.lab_v1.operation_ledger import OperationLedger
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


def _service(tmp_path):
    service = LabV1Service()
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    service._store = store
    service._runtime = Mock(store=store)
    service._supervisor = Mock()
    service._supervisor.policy.return_value = {
        "background_enabled": False,
        "cadence_seconds": 3600,
    }
    service._get_runtime = Mock(side_effect=AssertionError("provider forbidden"))
    service.cancel_autopilot = AsyncMock(return_value={"success": True})
    return service, store


def _operation_events(store):
    return [
        event
        for event in store.list_events(limit=500)
        if event.type == "operation.result"
    ]


def test_direct_operation_publishes_one_terminal_lab_event_without_ipc(tmp_path):
    service, store = _service(tmp_path)

    async def exercise():
        await service.start_background()
        admitted = await service.admit_operation(
            "direct", "lab.v1.cancel", {"session_id": "mission-a"}
        )
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        await service.stop_background()
        return admitted

    admitted = asyncio.run(exercise())
    events = _operation_events(store)

    assert len(events) == 1
    assert events[0].id == f"operation-result:{admitted['operation_id']}"
    assert events[0].session_id == "mission-a"
    assert events[0].payload["state"] == "COMPLETED"
    assert events[0].payload["request_id"] == "direct"
    ledger = service._get_operation_ledger()
    assert ledger.event_publication_state(admitted["operation_id"]) == "PUBLISHED"
    assert [item.operation_id for item in ledger.claim_result_publications()] == [
        admitted["operation_id"]
    ]


def test_restart_mirrors_a_terminal_result_left_before_service_boot(tmp_path):
    first, store = _service(tmp_path)
    ledger = first._get_operation_ledger()
    ack = ledger.admit(
        "before-crash", "lab.v1.cancel", {"session_id": "mission-a"}
    )
    assert ledger.claim(ack.operation_id) is not None
    ledger.finish(ack.operation_id, "COMPLETED", {"success": True})
    assert _operation_events(store) == []

    restarted, restarted_store = _service(tmp_path)

    async def boot_twice():
        await restarted.start_background()
        await restarted.stop_background()
        await restarted.start_background()
        await restarted.stop_background()

    asyncio.run(boot_twice())
    events = _operation_events(restarted_store)

    assert len(events) == 1
    assert events[0].id == f"operation-result:{ack.operation_id}"
    assert events[0].payload["result"] == {"success": True}


def test_replayed_admission_keeps_one_operation_and_one_terminal_event(tmp_path):
    service, store = _service(tmp_path)

    async def exercise():
        await service.start_background()
        first = await service.admit_operation(
            "same-request", "lab.v1.cancel", {"session_id": "mission-a"}
        )
        replay = await service.admit_operation(
            "same-request", "lab.v1.cancel", {"session_id": "mission-a"}
        )
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        await service.stop_background()
        return first, replay

    first, replay = asyncio.run(exercise())

    assert first["operation_id"] == replay["operation_id"]
    assert service._get_operation_ledger().count() == 1
    assert len(_operation_events(store)) == 1


def test_restart_publishes_interrupted_unknown_without_redispatch(tmp_path, monkeypatch):
    first, _store = _service(tmp_path)
    ledger = first._get_operation_ledger()
    ack = ledger.admit(
        "claimed-before-crash", "lab.v1.cancel", {"session_id": "mission-a"}
    )
    assert ledger.claim(ack.operation_id) is not None

    monkeypatch.setattr(OperationLedger, "_worker_is_alive", lambda *_args: False)
    restarted, restarted_store = _service(tmp_path)
    restarted.cancel_autopilot = AsyncMock(
        side_effect=AssertionError("an uncertain effect must never be repeated")
    )

    async def boot():
        await restarted.start_background()
        await restarted.stop_background()

    asyncio.run(boot())
    events = _operation_events(restarted_store)

    assert len(events) == 1
    assert events[0].payload["state"] == "INTERRUPTED"
    assert events[0].payload["result"]["code"] == "DISPATCH_OUTCOME_UNKNOWN"
    restarted.cancel_autopilot.assert_not_awaited()


def test_boot_creates_event_store_for_a_ledger_only_terminal_result(tmp_path):
    db_path = tmp_path / "ledger-only.db"
    ledger = OperationLedger(db_path)
    ack = ledger.admit(
        "ledger-only", "lab.v1.cancel", {"session_id": "mission-a"}
    )
    assert ledger.claim(ack.operation_id) is not None
    ledger.finish(ack.operation_id, "COMPLETED", {"success": True})

    service = LabV1Service()
    service._operation_ledger = ledger
    service._supervisor = Mock()
    service._supervisor.policy.return_value = {
        "background_enabled": False,
        "cadence_seconds": 3600,
    }
    service._get_runtime = Mock(side_effect=AssertionError("provider forbidden"))

    async def boot():
        await service.start_background()
        await service.stop_background()

    asyncio.run(boot())
    store = LabStore(db_path)
    store.initialize()

    events = _operation_events(store)
    assert len(events) == 1
    assert events[0].id == f"operation-result:{ack.operation_id}"


def test_finish_rolls_back_if_terminal_event_outbox_cannot_be_created(tmp_path):
    service, _store = _service(tmp_path)
    ledger = service._get_operation_ledger()
    ack = ledger.admit(
        "atomic-finish", "lab.v1.cancel", {"session_id": "mission-a"}
    )
    assert ledger.claim(ack.operation_id) is not None
    with ledger._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_terminal_event_outbox
            BEFORE INSERT ON lab_operation_event_outbox
            BEGIN SELECT RAISE(ABORT, 'forced event outbox failure'); END
            """
        )

    try:
        ledger.finish(ack.operation_id, "COMPLETED", {"success": True})
    except Exception as exc:
        assert "forced event outbox failure" in str(exc)
    else:
        raise AssertionError("finish must not commit without its event outbox")

    assert ledger.operation_status(ack.operation_id).state == "DISPATCHING"
    with ledger._connect() as connection:
        connection.execute("DROP TRIGGER reject_terminal_event_outbox")
    ledger.finish(ack.operation_id, "COMPLETED", {"success": True})
    assert ledger.event_publication_state(ack.operation_id) == "PENDING"
