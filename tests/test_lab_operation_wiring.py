"""Public operation admission wiring without execution or provider calls."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from core.ipc_handlers import IPCHandler, IPCMessage
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


def _service(tmp_path):
    service = LabV1Service()
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    service._store = store
    service._runtime = Mock(store=store)
    return service


def test_service_admission_is_durable_json_and_replay_is_stable(tmp_path):
    service = _service(tmp_path)

    first = asyncio.run(
        service.admit_operation(
            "request-1", "lab.v1.message", {"session_id": "s", "content": "continue"}
        )
    )
    reopened = _service(tmp_path)
    replay = asyncio.run(
        reopened.admit_operation(
            "request-1", "lab.v1.message", {"content": "continue", "session_id": "s"}
        )
    )

    assert first == replay
    assert first["accepted"] is True
    assert first["state"] == "ADMITTED"
    assert first["request_id"] == "request-1"
    assert first["operation_id"].startswith("operation:")
    assert set(first) == {
        "success", "accepted", "state", "request_id", "operation_id",
        "command", "payload_sha256", "accepted_at",
    }


def test_clean_service_admission_does_not_initialize_runtime_or_providers(
    tmp_path, monkeypatch
):
    service = LabV1Service()
    store = LabStore(tmp_path / "lab.db")
    monkeypatch.setattr("core.lab_v1.service.LabStore", lambda: store)
    service._get_runtime = Mock(side_effect=AssertionError("runtime bootstrap forbidden"))

    result = asyncio.run(
        service.admit_operation("request-1", "lab.v1.submit", {"objective": "A"})
    )

    assert result["success"] is True
    assert result["state"] == "ADMITTED"
    service._get_runtime.assert_not_called()


def test_service_returns_structured_conflict_without_dispatch(tmp_path):
    service = _service(tmp_path)
    service._get_autopilot = Mock(side_effect=AssertionError("dispatch forbidden"))
    asyncio.run(service.admit_operation("request-1", "lab.v1.submit", {"objective": "A"}))

    conflict = asyncio.run(
        service.admit_operation("request-1", "lab.v1.submit", {"objective": "B"})
    )

    assert conflict == {
        "success": False,
        "accepted": False,
        "state": "REJECTED",
        "code": "IDEMPOTENCY_CONFLICT",
        "request_id": "request-1",
        "error": "O request_id já foi usado com outro comando ou conteúdo.",
    }
    service._get_autopilot.assert_not_called()


def test_ipc_admission_requires_explicit_renderer_confirmation_before_dispatch():
    handler = IPCHandler(AsyncMock())
    service = Mock()
    service.admit_operation_for_dispatch = AsyncMock(return_value=({
        "success": True, "accepted": True, "state": "ADMITTED",
        "request_id": "ipc-1", "operation_id": "operation:1",
    }, True))
    service.authorize_operation_dispatch = AsyncMock(return_value=True)
    service.dispatch_operation = AsyncMock(return_value={
        "operation_id": "operation:1", "state": "COMPLETED",
        "result": {"success": True},
    })
    service.claim_operation_result_publications = AsyncMock(side_effect=[[
        {"operation_id": "operation:1", "state": "COMPLETED",
         "result": {"success": True}}
    ], []])
    service.mark_operation_result_published = AsyncMock()
    handler.lab_v1 = service
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

    service.admit_operation_for_dispatch.assert_awaited_once_with(
        "ipc-1", "lab.v1.cancel", {"session_id": "s"}
    )
    service.authorize_operation_dispatch.assert_awaited_once_with("operation:1")
    response = handler.send.await_args_list[0].args[0]
    assert response.request_id == "ipc-1"
    assert response.response["state"] == "ADMITTED"


def test_ipc_confirmation_requires_an_operation_id():
    handler = IPCHandler(AsyncMock())
    service = Mock()
    service.authorize_operation_dispatch = AsyncMock()
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    asyncio.run(handler.handle_lab_v1_confirm_operation(IPCMessage(
        type="lab-v1-confirm-operation",
        request_id="confirm-1",
        payload={},
    )))

    service.authorize_operation_dispatch.assert_not_awaited()
    assert handler.send.call_args.args[0].error == "operation_id ausente"


def test_electron_lab_mutations_use_the_durable_admit_then_confirm_protocol():
    """The real renderer bridge must not bypass the durable two-phase gate."""
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1]
    main = (root / "frontend/src/main.ts").read_text(encoding="utf-8")
    preload = (root / "frontend/src/preload.ts").read_text(encoding="utf-8")

    assert "async function sendDurableLabOperation" in main
    helper = main[main.index("async function sendDurableLabOperation"):]
    admit = helper.index("'lab-v1-admit-operation'")
    confirm = helper.index("'lab-v1-confirm-operation'")
    assert admit < confirm
    for command in ("submit", "message", "cancel"):
        assert re.search(
            rf"sendDurableLabOperation\(\s*'lab\.v1\.{command}'", main
        )
    assert "requestId?: string" in preload


def test_ipc_admission_rejects_unknown_command_before_service_call():
    handler = IPCHandler(AsyncMock())
    service = Mock(admit_operation=AsyncMock())
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    asyncio.run(handler.handle_lab_v1_admit_operation(IPCMessage(
        type="lab-v1-admit-operation",
        request_id="ipc-1",
        payload={"command": "provider.call", "payload": {}},
    )))

    service.admit_operation.assert_not_awaited()
    response = handler.send.call_args.args[0]
    assert response.request_id == "ipc-1"
    assert response.error == "Comando do Lab inválido"


def test_ipc_admission_requires_object_payload_before_service_call():
    handler = IPCHandler(AsyncMock())
    service = Mock(admit_operation=AsyncMock())
    handler._ensure_lab_v1 = AsyncMock(return_value=service)

    asyncio.run(handler.handle_lab_v1_admit_operation(IPCMessage(
        type="lab-v1-admit-operation",
        request_id="ipc-1",
        payload={"command": "lab.v1.submit", "payload": "not-an-object"},
    )))

    service.admit_operation.assert_not_awaited()
    assert handler.send.call_args.args[0].error == "Payload do comando inválido"


def test_public_ipc_router_preserves_replay_and_surfaces_conflict(tmp_path):
    handler = IPCHandler(AsyncMock())
    handler.lab_v1 = _service(tmp_path)

    async def route(content):
        await handler.handle_message(IPCMessage(
            type="lab-v1-admit-operation",
            request_id="ipc-1",
            payload={
                "command": "lab.v1.message",
                "payload": {"session_id": "s", "content": content},
            },
        ))

    asyncio.run(route("continue"))
    first = handler.send.call_args.args[0].response
    asyncio.run(route("continue"))
    replay = handler.send.call_args.args[0].response
    asyncio.run(route("different"))
    conflict = handler.send.call_args.args[0].response

    assert replay == first
    assert first["state"] == "ADMITTED"
    assert conflict["success"] is False
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
