"""Event-driven consumption of durable Lab operations without provider calls."""

from __future__ import annotations

import asyncio
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


def _multiprocess_operation_consumer(db_path, operation_id, commands, observations):
    """Boot a genuinely separate service process against the shared ledger."""
    async def run():
        service = LabV1Service()
        store = LabStore(Path(db_path))
        store.initialize()
        service._store = store
        service._runtime = SimpleNamespace(store=store)
        service._supervisor = SimpleNamespace(
            policy=lambda: {"background_enabled": False, "cadence_seconds": 3600}
        )
        calls = []

        async def cancel(session_id):
            calls.append(session_id)
            return {"success": True}

        service.cancel_autopilot = cancel
        await service.start_background()
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=3)
        status = service._get_operation_ledger().operation_status(operation_id)
        observations.put(("boot", list(calls), status.state))
        command = await asyncio.to_thread(commands.get, True, 5)
        if command == "wake":
            # Duplicate notifications must still produce one external effect.
            service.wake_operation_consumer(operation_id)
            service.wake_operation_consumer(operation_id)
            await asyncio.wait_for(service.wait_for_operation_idle(), timeout=3)
        status = service._get_operation_ledger().operation_status(operation_id)
        observations.put(("after", list(calls), status.state))
        await service.stop_background()

    try:
        asyncio.run(run())
    except BaseException as exc:
        observations.put(("error", type(exc).__name__, str(exc)))


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
    service._get_runtime = Mock(side_effect=AssertionError("provider bootstrap forbidden"))
    return service


def test_paused_autonomy_still_drains_operation_left_before_boot(tmp_path):
    service = _service(tmp_path)
    admitted = asyncio.run(
        service.admit_operation(
            "request-before-boot", "lab.v1.cancel", {"session_id": "s"}
        )
    )
    service.cancel_autopilot = AsyncMock(return_value={"success": True})

    async def exercise():
        started = await service.start_background()
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        stopped = await service.stop_background()
        return started, stopped

    started, stopped = asyncio.run(exercise())

    assert started["state"] == "PAUSED"
    assert stopped["state"] == "PAUSED"
    assert service._get_operation_ledger().operation_status(
        admitted["operation_id"]
    ).state == "COMPLETED"
    service.cancel_autopilot.assert_awaited_once_with("s")
    service._get_runtime.assert_not_called()


def test_later_durable_admission_wakes_same_consumer_without_polling(tmp_path):
    service = _service(tmp_path)
    service.cancel_autopilot = AsyncMock(return_value={"success": True})

    async def exercise():
        await service.start_background()
        first_task = service._operation_consumer_task
        admitted = await service.admit_operation(
            "request-after-boot", "lab.v1.cancel", {"session_id": "s"}
        )
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        await service.start_background()
        same_task = service._operation_consumer_task
        await service.stop_background()
        return admitted, first_task, same_task

    admitted, first_task, same_task = asyncio.run(exercise())

    assert first_task is same_task
    assert service._get_operation_ledger().operation_status(
        admitted["operation_id"]
    ).state == "COMPLETED"
    service.cancel_autopilot.assert_awaited_once_with("s")
    service._get_runtime.assert_not_called()


def test_ipc_style_admission_cannot_dispatch_before_explicit_post_ack_call(tmp_path):
    service = _service(tmp_path)
    service._background_interval = 0.01
    service.cancel_autopilot = AsyncMock(return_value={"success": True})

    async def exercise():
        await service.start_background()
        admitted, _new = await service.admit_operation_for_dispatch(
            "ipc-request", "lab.v1.cancel", {"session_id": "s"}
        )
        await asyncio.sleep(0.05)
        calls_before_ack = service.cancel_autopilot.await_count
        await service.authorize_operation_dispatch(admitted["operation_id"])
        terminal = await service.dispatch_operation(admitted["operation_id"])
        await service.stop_background()
        return calls_before_ack, terminal

    calls_before_ack, terminal = asyncio.run(exercise())

    assert calls_before_ack == 0
    assert terminal["state"] == "COMPLETED"
    service.cancel_autopilot.assert_awaited_once_with("s")


def test_direct_wakeup_cannot_sweep_a_concurrent_ipc_admission_before_ack(tmp_path):
    service = _service(tmp_path)
    dispatched = []

    async def cancel(session_id):
        dispatched.append(session_id)
        return {"success": True}

    service.cancel_autopilot = AsyncMock(side_effect=cancel)

    async def exercise():
        await service.start_background()
        ipc, _new = await service.admit_operation_for_dispatch(
            "ipc-request", "lab.v1.cancel", {"session_id": "ipc"}
        )
        direct = await service.admit_operation(
            "direct-request", "lab.v1.cancel", {"session_id": "direct"}
        )
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        before_ack = list(dispatched)
        await service.authorize_operation_dispatch(ipc["operation_id"])
        await service.dispatch_operation(ipc["operation_id"])
        await service.stop_background()
        return direct, before_ack

    direct, before_ack = asyncio.run(exercise())

    assert before_ack == ["direct"]
    assert service._get_operation_ledger().operation_status(
        direct["operation_id"]
    ).state == "COMPLETED"
    assert dispatched == ["direct", "ipc"]


def test_other_process_boot_and_wake_cannot_dispatch_ipc_before_durable_post_ack_release(tmp_path):
    path = tmp_path / "lab.db"
    admitting = _service(tmp_path)
    admitted, created = asyncio.run(admitting.admit_operation_for_dispatch(
        "ipc-multiprocess", "lab.v1.cancel", {"session_id": "mission"}
    ))
    assert created is True

    context = multiprocessing.get_context("spawn")
    commands = context.Queue()
    observations = context.Queue()
    process = context.Process(
        target=_multiprocess_operation_consumer,
        args=(str(path), admitted["operation_id"], commands, observations),
    )
    process.start()
    try:
        boot = observations.get(timeout=10)
        assert boot == ("boot", [], "ADMITTED")
        assert admitting._get_operation_ledger().pending_operation_ids() == []

        # This is the durable transition performed only after send_response
        # has completed in IPCHandler.
        assert asyncio.run(admitting.authorize_operation_dispatch(
            admitted["operation_id"]
        )) is True
        commands.put("wake")
        after = observations.get(timeout=10)
        assert after == ("after", ["mission"], "COMPLETED")
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


def test_consumer_exposes_a_durable_failed_result(tmp_path):
    service = _service(tmp_path)
    service.cancel_autopilot = AsyncMock(
        return_value={"success": False, "error": "mission missing"}
    )

    async def exercise():
        await service.start_background()
        admitted = await service.admit_operation(
            "failed-request", "lab.v1.cancel", {"session_id": "missing"}
        )
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=1)
        status = service.operation_consumer_status()
        await service.stop_background()
        return admitted, status

    admitted, status = asyncio.run(exercise())

    assert status["state"] == "FAILED"
    assert status["error"] == "OPERATION_FAILED"
    assert status["results"][0]["operation_id"] == admitted["operation_id"]


def test_consumer_exposes_nonterminal_dispatch_failure(tmp_path):
    service = _service(tmp_path)
    service.dispatch_pending_operations = AsyncMock(return_value=[{
        "success": False,
        "operation_id": "operation:stuck",
        "state": "DISPATCHING",
        "result": {"code": "OPERATION_CONSUMER_FAILED"},
    }])

    async def exercise():
        await service.start_background()
        status = service.operation_consumer_status()
        await service.stop_background()
        return status

    status = asyncio.run(exercise())

    assert status["state"] == "FAILED"
    assert status["error"] == "OPERATION_FAILED"
    assert status["results"][0]["state"] == "DISPATCHING"


def test_shutdown_marks_an_in_flight_claim_interrupted(tmp_path):
    service = _service(tmp_path)
    entered = asyncio.Event()

    async def block(_session_id):
        entered.set()
        await asyncio.Event().wait()

    service.cancel_autopilot = AsyncMock(side_effect=block)

    async def exercise():
        await service.start_background()
        admitted = await service.admit_operation(
            "in-flight", "lab.v1.cancel", {"session_id": "s"}
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        await service.stop_background()
        return admitted

    admitted = asyncio.run(exercise())
    terminal = service._get_operation_ledger().operation_status(
        admitted["operation_id"]
    )

    assert terminal.state == "INTERRUPTED"
    assert terminal.result["code"] == "CONSUMER_SHUTDOWN_OUTCOME_UNKNOWN"


def test_stop_background_cancels_operation_consumer(tmp_path):
    service = _service(tmp_path)

    async def exercise():
        await service.start_background()
        task = service._operation_consumer_task
        await service.stop_background()
        return task

    task = asyncio.run(exercise())

    assert task.done()
    assert task.cancelled()
    assert service._operation_consumer_task is None
