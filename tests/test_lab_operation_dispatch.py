"""Crash-safe command outbox and terminal-result wiring."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage
from core.lab_v1.operation_ledger import OperationLedger
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


def _service(tmp_path):
    service = LabV1Service()
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    service._store = store
    service._runtime = Mock(store=store)
    return service


def test_admission_and_outbox_are_atomic_and_claimed_once(tmp_path):
    ledger = OperationLedger(tmp_path / "lab.db")

    ack = ledger.admit("request-1", "lab.v1.cancel", {"session_id": "s"})
    first = ledger.claim(ack.operation_id)
    second = ledger.claim(ack.operation_id)

    assert first.operation_id == ack.operation_id
    assert first.command == "lab.v1.cancel"
    assert second is None
    assert ledger.operation_status(ack.operation_id).state == "DISPATCHING"


def test_failed_admission_cannot_leave_an_outbox_record(tmp_path, monkeypatch):
    ledger = OperationLedger(tmp_path / "lab.db")

    def fail_before_commit(*_args):
        raise RuntimeError("commit boundary failed")

    monkeypatch.setattr(ledger, "_before_commit", fail_before_commit)
    with pytest.raises(RuntimeError, match="commit boundary failed"):
        ledger.admit("request-1", "lab.v1.submit", {"objective": "A"})

    assert ledger.count() == 0
    assert ledger.pending_count() == 0


def test_terminal_result_survives_restart_and_cannot_be_replaced(tmp_path):
    path = tmp_path / "lab.db"
    ledger = OperationLedger(path)
    ack = ledger.admit("request-1", "lab.v1.cancel", {"session_id": "s"})
    ledger.claim(ack.operation_id)

    saved = ledger.finish(
        ack.operation_id,
        "COMPLETED",
        {"success": True, "mission": {"state": "CANCELLED"}},
    )
    replay = OperationLedger(path).finish(
        ack.operation_id,
        "COMPLETED",
        {"mission": {"state": "CANCELLED"}, "success": True},
    )

    assert replay == saved
    assert OperationLedger(path).operation_status(ack.operation_id) == saved
    with pytest.raises(ValueError, match="already has a different terminal result"):
        OperationLedger(path).finish(
            ack.operation_id, "FAILED", {"success": False, "error": "different"}
        )


def test_second_live_publisher_cannot_claim_the_same_terminal_event(tmp_path):
    path = tmp_path / "lab.db"
    first = OperationLedger(path)
    ack = first.admit("request-1", "lab.v1.cancel", {"session_id": "s"})
    first.claim(ack.operation_id)
    first.finish(ack.operation_id, "COMPLETED", {"success": True})

    assert [item.operation_id for item in first.claim_result_publications()] == [
        ack.operation_id
    ]
    second = OperationLedger(path)
    second.reconcile_interrupted()

    assert second.claim_result_publications() == []


def test_terminal_result_stays_in_publication_outbox_until_acknowledged(tmp_path):
    path = tmp_path / "lab.db"
    ledger = OperationLedger(path)
    ack = ledger.admit("request-1", "lab.v1.cancel", {"session_id": "s"})
    ledger.claim(ack.operation_id)
    ledger.finish(ack.operation_id, "COMPLETED", {"success": True})

    reopened = OperationLedger(path)
    pending = reopened.claim_result_publications()

    assert [item.operation_id for item in pending] == [ack.operation_id]
    reopened.mark_result_published(ack.operation_id)
    assert reopened.claim_result_publications() == []


def test_restart_reconciles_claimed_work_as_interrupted_without_redispatch(
    tmp_path, monkeypatch
):
    path = tmp_path / "lab.db"
    first = OperationLedger(path)
    ack = first.admit("request-1", "lab.v1.message", {"session_id": "s", "content": "go"})
    assert first.claim(ack.operation_id) is not None

    reopened = OperationLedger(path)
    monkeypatch.setattr(reopened, "_worker_is_alive", lambda *_args: False)
    recovered = reopened.reconcile_interrupted()

    assert [item.operation_id for item in recovered] == [ack.operation_id]
    result = reopened.operation_status(ack.operation_id)
    assert result.state == "INTERRUPTED"
    assert result.result["code"] == "DISPATCH_OUTCOME_UNKNOWN"
    assert reopened.claim(ack.operation_id) is None


def test_second_live_ledger_cannot_interrupt_the_active_dispatcher(tmp_path):
    path = tmp_path / "lab.db"
    first = OperationLedger(path)
    ack = first.admit("request-1", "lab.v1.cancel", {"session_id": "s"})
    first.claim(ack.operation_id)

    second = OperationLedger(path)

    assert second.reconcile_interrupted() == []
    assert second.operation_status(ack.operation_id).state == "DISPATCHING"


def test_real_child_process_death_is_reconciled_once_without_redispatch(tmp_path):
    path = tmp_path / "lab.db"
    ledger = OperationLedger(path)
    ack = ledger.admit(
        "request-child-crash",
        "lab.v1.message",
        {"session_id": "s", "content": "go"},
    )
    repository = Path(__file__).resolve().parents[1]
    child = tmp_path / "claim_and_die.py"
    child.write_text(
        "\n".join(
            [
                "import os, sys",
                f"sys.path.insert(0, {str(repository)!r})",
                "from core.lab_v1.operation_ledger import OperationLedger",
                "ledger = OperationLedger(sys.argv[1])",
                "assert ledger.claim(sys.argv[2]) is not None",
                "os._exit(17)",
            ]
        ),
        encoding="utf-8",
    )

    crashed = subprocess.run(
        [sys.executable, str(child), str(path), ack.operation_id],
        check=False,
    )
    assert crashed.returncode == 17

    reopened = OperationLedger(path)
    recovered = reopened.reconcile_interrupted()
    status = reopened.operation_status(ack.operation_id)

    assert [item.operation_id for item in recovered] == [ack.operation_id]
    assert status.state == "INTERRUPTED"
    assert status.result["code"] == "DISPATCH_OUTCOME_UNKNOWN"
    assert reopened.reconcile_interrupted() == []
    assert reopened.claim(ack.operation_id) is None


@pytest.mark.parametrize(
    ("command", "payload", "method", "args", "kwargs"),
    [
        ("lab.v1.submit", {"objective": "Improve", "session_id": "s"}, "start_autopilot", ("Improve",), {"session_id": "s"}),
        ("lab.v1.message", {"session_id": "s", "content": "continue"}, "submit", ("s", "continue"), {}),
        ("lab.v1.cancel", {"session_id": "s"}, "cancel_autopilot", ("s",), {}),
        ("lab.v1.resume", {"session_id": "s"}, "resume_source_autopilot", ("s",), {}),
    ],
)
def test_service_dispatches_each_command_through_its_existing_contract(
    tmp_path, command, payload, method, args, kwargs
):
    service = _service(tmp_path)
    service._get_runtime = Mock(side_effect=AssertionError("provider bootstrap forbidden"))
    target = AsyncMock(return_value={"success": True, "state": "DONE"})
    setattr(service, method, target)
    admitted = asyncio.run(service.admit_operation("request-1", command, payload))

    result = asyncio.run(service.dispatch_operation(admitted["operation_id"]))

    target.assert_awaited_once_with(*args, **kwargs)
    service._get_runtime.assert_not_called()
    assert result["state"] == "COMPLETED"
    assert result["result"]["success"] is True


def test_service_persists_a_terminal_failure_instead_of_retrying(tmp_path):
    service = _service(tmp_path)
    service.cancel_autopilot = AsyncMock(return_value={"success": False, "error": "missing"})
    admitted = asyncio.run(
        service.admit_operation("request-1", "lab.v1.cancel", {"session_id": "s"})
    )

    first = asyncio.run(service.dispatch_operation(admitted["operation_id"]))
    replay = asyncio.run(service.dispatch_operation(admitted["operation_id"]))

    assert first == replay
    assert first["state"] == "FAILED"
    service.cancel_autopilot.assert_awaited_once()


def test_new_service_drains_an_admitted_item_left_before_dispatch(tmp_path):
    first_process = _service(tmp_path)
    admitted = asyncio.run(
        first_process.admit_operation(
            "request-1", "lab.v1.cancel", {"session_id": "s"}
        )
    )

    restarted = _service(tmp_path)
    restarted.cancel_autopilot = AsyncMock(
        return_value={"success": True, "mission": {"state": "CANCELLED"}}
    )
    results = asyncio.run(restarted.dispatch_pending_operations())

    assert [item["operation_id"] for item in results] == [admitted["operation_id"]]
    assert results[0]["state"] == "COMPLETED"
    restarted.cancel_autopilot.assert_awaited_once_with("s")


def test_service_restart_closes_a_crashed_claim_without_repeating_it(
    tmp_path, monkeypatch
):
    first_process = _service(tmp_path)
    admitted = asyncio.run(
        first_process.admit_operation(
            "request-1", "lab.v1.cancel", {"session_id": "s"}
        )
    )
    first_process.cancel_autopilot = AsyncMock(side_effect=SystemExit("crash"))
    with pytest.raises(SystemExit, match="crash"):
        asyncio.run(first_process.dispatch_operation(admitted["operation_id"]))

    restarted = _service(tmp_path)
    monkeypatch.setattr(OperationLedger, "_worker_is_alive", lambda *_args: False)
    restarted.cancel_autopilot = AsyncMock(
        side_effect=AssertionError("uncertain effect must not be repeated")
    )
    results = asyncio.run(restarted.dispatch_pending_operations())
    status = restarted._get_operation_ledger().operation_status(admitted["operation_id"])

    assert results == []
    assert status.state == "INTERRUPTED"
    assert status.result["code"] == "DISPATCH_OUTCOME_UNKNOWN"
    restarted.cancel_autopilot.assert_not_awaited()


def test_ipc_confirmation_releases_durable_work_and_publishes_terminal_event():
    order = []

    async def send(message):
        order.append((message.type, message.response or message.data))

    handler = IPCHandler(send)
    service = Mock()
    service.admit_operation_for_dispatch = AsyncMock(return_value=({
        "success": True,
        "accepted": True,
        "state": "ADMITTED",
        "request_id": "ipc-1",
        "operation_id": "operation:1",
    }, True))
    async def authorize(operation_id):
        order.append(("authorize", operation_id))
        return True

    service.authorize_operation_dispatch = AsyncMock(side_effect=authorize)

    async def dispatch(operation_id):
        order.append(("dispatch", operation_id))
        return {
            "operation_id": operation_id,
            "state": "COMPLETED",
            "result": {"success": True},
        }

    service.dispatch_operation = AsyncMock(side_effect=dispatch)
    service.claim_operation_result_publications = AsyncMock(side_effect=[[
        {
            "operation_id": "operation:1",
            "state": "COMPLETED",
            "result": {"success": True},
        }
    ], []])
    service.mark_operation_result_published = AsyncMock()
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    async def run():
        await handler.handle_lab_v1_admit_operation(
            IPCMessage(
                type="lab-v1-admit-operation",
                request_id="ipc-1",
                payload={"command": "lab.v1.cancel", "payload": {"session_id": "s"}},
            )
        )
        assert order == [("response", {
            "success": True,
            "accepted": True,
            "state": "ADMITTED",
            "request_id": "ipc-1",
            "operation_id": "operation:1",
        })]
        await handler.handle_lab_v1_confirm_operation(IPCMessage(
            type="lab-v1-confirm-operation",
            request_id="confirm-1",
            payload={"operation_id": "operation:1"},
        ))
        await asyncio.gather(*handler._lab_v1_background_tasks)

    asyncio.run(run())

    assert order[0][0] == "response"
    assert order[1] == ("authorize", "operation:1")
    assert order[2][0] == "response"
    assert order[2][1]["state"] == "DISPATCH_AUTHORIZED"
    assert order[3] == ("dispatch", "operation:1")
    assert order[4][0] == "lab-v1-operation-result"
    assert order[4][1]["event_id"] == "operation-result:operation:1"
    service.dispatch_operation.assert_awaited_once_with("operation:1")
    service.mark_operation_result_published.assert_awaited_once_with("operation:1")
    service.authorize_operation_dispatch.assert_awaited_once_with("operation:1")


def test_ipc_replay_waits_for_confirmation_then_schedules_existing_operation():
    handler = IPCHandler(AsyncMock())
    service = Mock()
    service.admit_operation_for_dispatch = AsyncMock(return_value=({
        "success": True,
        "accepted": True,
        "state": "ADMITTED",
        "request_id": "ipc-1",
        "operation_id": "operation:1",
    }, False))
    service.authorize_operation_dispatch = AsyncMock(return_value=True)
    service.dispatch_operation = AsyncMock(return_value={
        "operation_id": "operation:1",
        "state": "ADMITTED",
        "result": None,
    })
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    async def run():
        await handler.handle_lab_v1_admit_operation(IPCMessage(
            type="lab-v1-admit-operation",
            request_id="ipc-1",
            payload={"command": "lab.v1.cancel", "payload": {"session_id": "s"}},
        ))
        service.dispatch_operation.assert_not_awaited()
        await handler.handle_lab_v1_confirm_operation(IPCMessage(
            type="lab-v1-confirm-operation",
            request_id="confirm-1",
            payload={"operation_id": "operation:1"},
        ))
        await asyncio.gather(*handler._lab_v1_background_tasks)

    asyncio.run(run())

    service.dispatch_operation.assert_awaited_once_with("operation:1")


def test_ipc_confirmation_reports_bounded_unknown_outcome_when_authorization_stalls():
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler._LAB_V1_CONFIRM_TIMEOUT_SECONDS = 0.01
    service = Mock()
    async def stall_authorization(_operation_id):
        await asyncio.sleep(1)

    service.authorize_operation_dispatch = AsyncMock(side_effect=stall_authorization)
    service.dispatch_operation = AsyncMock()
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    async def run():
        await asyncio.wait_for(handler.handle_lab_v1_confirm_operation(IPCMessage(
            type="lab-v1-confirm-operation",
            request_id="confirm-1",
            payload={"operation_id": "operation:1"},
        )), timeout=0.2)

    asyncio.run(run())

    response = sent.await_args.args[0]
    assert response.request_id == "confirm-1"
    assert response.response["confirmed"] is False
    assert response.response["code"] == "CONFIRMATION_OUTCOME_UNKNOWN"
    assert response.response["operation_id"] == "operation:1"
    service.dispatch_operation.assert_not_awaited()


def test_delayed_confirmation_keeps_admission_and_eventually_finishes_once(tmp_path):
    service = _service(tmp_path)
    admitted, _ = asyncio.run(service.admit_operation_for_dispatch(
        "request-1", "lab.v1.cancel", {"session_id": "s"}
    ))
    operation_id = admitted["operation_id"]
    real_authorize = service.authorize_operation_dispatch
    release = asyncio.Event()

    async def delayed_authorize(identifier):
        await release.wait()
        return await real_authorize(identifier)

    service.authorize_operation_dispatch = AsyncMock(side_effect=delayed_authorize)
    service.cancel_autopilot = AsyncMock(return_value={"success": True})
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler._LAB_V1_CONFIRM_TIMEOUT_SECONDS = 0.01
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    async def run():
        await handler.handle_lab_v1_confirm_operation(IPCMessage(
            type="lab-v1-confirm-operation",
            request_id="confirm-1",
            payload={"operation_id": operation_id},
        ))
        assert service._get_operation_ledger().operation_status(operation_id).state == "ADMITTED"
        assert sent.await_args_list[0].args[0].response["confirmed"] is False
        release.set()
        await asyncio.gather(*handler._lab_v1_background_tasks)

    asyncio.run(run())

    assert service._get_operation_ledger().operation_status(operation_id).state == "COMPLETED"
    service.cancel_autopilot.assert_awaited_once_with("s")


def test_lab_startup_can_return_while_durable_recovery_is_still_running(tmp_path):
    service = _service(tmp_path)
    service._supervisor = Mock()
    service._supervisor.policy.return_value = {"background_enabled": False}
    admitted = asyncio.run(service.admit_operation_for_dispatch(
        "held-request", "lab.v1.cancel", {"session_id": "s"}
    ))[0]
    asyncio.run(service.authorize_operation_dispatch(admitted["operation_id"]))
    entered = asyncio.Event()
    release = asyncio.Event()
    real_dispatch = service.dispatch_operation
    service.cancel_autopilot = AsyncMock(return_value={"success": True})

    async def slow_dispatch(_operation_id):
        entered.set()
        await release.wait()
        return await real_dispatch(_operation_id)

    service.dispatch_operation = AsyncMock(side_effect=slow_dispatch)

    async def run():
        try:
            started = await asyncio.wait_for(
                service.start_background(wait_for_operation_recovery=False),
                timeout=0.2,
            )
            await asyncio.wait_for(entered.wait(), timeout=0.2)
            assert started["state"] == "PAUSED"
            assert service._get_operation_ledger().operation_status(
                admitted["operation_id"]
            ).state == "ADMITTED"
        finally:
            release.set()
            await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
            await service.stop_background()

    asyncio.run(run())


def test_replayed_terminal_operation_does_not_publish_the_event_twice():
    sent = AsyncMock()
    handler = IPCHandler(sent)
    service = Mock()
    service.dispatch_operation = AsyncMock(return_value={
        "operation_id": "operation:1",
        "state": "COMPLETED",
        "result": {"success": True},
    })
    service.claim_operation_result_publications = AsyncMock(return_value=[])

    asyncio.run(handler._dispatch_lab_v1_operation(service, "operation:1"))

    sent.assert_not_awaited()
    service.claim_operation_result_publications.assert_awaited_once()


def test_background_task_exception_is_observed_and_task_is_drained():
    handler = IPCHandler(AsyncMock())

    async def fail():
        raise RuntimeError("background failed")

    async def run():
        task = handler._schedule_lab_v1_task(fail(), name="failing-operation")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return task

    task = asyncio.run(run())

    assert handler._lab_v1_background_tasks == set()
    assert isinstance(task.exception(), RuntimeError)


def test_ipc_ack_send_failure_keeps_operation_held_for_safe_replay():
    sent = []

    async def send(message):
        sent.append(message.type)
        if message.type == "response":
            raise ConnectionError("renderer disconnected")

    handler = IPCHandler(send)
    service = Mock()
    service.admit_operation_for_dispatch = AsyncMock(return_value=({
        "success": True,
        "accepted": True,
        "state": "ADMITTED",
        "request_id": "ipc-1",
        "operation_id": "operation:1",
    }, True))
    service.authorize_operation_dispatch = AsyncMock(return_value=True)
    service.dispatch_operation = AsyncMock(return_value={
        "operation_id": "operation:1",
        "state": "COMPLETED",
        "result": {"success": True},
    })
    service.claim_operation_result_publications = AsyncMock(side_effect=[[
        {
            "operation_id": "operation:1",
            "state": "COMPLETED",
            "result": {"success": True},
        }
    ], []])
    service.mark_operation_result_published = AsyncMock()
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    async def run():
        with pytest.raises(ConnectionError, match="renderer disconnected"):
            await handler.handle_lab_v1_admit_operation(IPCMessage(
                type="lab-v1-admit-operation",
                request_id="ipc-1",
                payload={"command": "lab.v1.cancel", "payload": {"session_id": "s"}},
            ))
        await asyncio.gather(*handler._lab_v1_background_tasks)

    asyncio.run(run())

    service.authorize_operation_dispatch.assert_not_awaited()
    service.dispatch_operation.assert_not_awaited()


def test_failed_terminal_event_send_releases_its_publication_claim():
    handler = IPCHandler(AsyncMock(side_effect=ConnectionError("renderer offline")))
    service = Mock()
    service.claim_operation_result_publications = AsyncMock(return_value=[{
        "operation_id": "operation:1",
        "state": "COMPLETED",
        "result": {"success": True},
    }])
    service.mark_operation_result_published = AsyncMock()
    service.release_operation_result_publication = AsyncMock()

    asyncio.run(handler._publish_lab_v1_operation_results(service))

    service.mark_operation_result_published.assert_not_awaited()
    service.release_operation_result_publication.assert_awaited_once_with("operation:1")


def test_drain_continues_past_the_first_two_hundred_pending_items(tmp_path):
    service = _service(tmp_path)
    ledger = service._get_operation_ledger()
    for index in range(205):
        ledger.admit(
            f"request-{index}", "lab.v1.cancel", {"session_id": f"s-{index}"}
        )
    service.cancel_autopilot = AsyncMock(return_value={"success": True})

    results = asyncio.run(service.dispatch_pending_operations())

    assert len(results) == 205
    assert ledger.pending_count() == 0
    assert service.cancel_autopilot.await_count == 205
