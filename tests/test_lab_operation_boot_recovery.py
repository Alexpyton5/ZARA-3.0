"""Sidecar readiness must not wait for a recovered Lab provider operation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core import ipc_handlers
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


@pytest.mark.asyncio
async def test_ipc_boot_returns_while_recovered_operation_is_still_running(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    service = LabV1Service()
    service._store = store
    service._runtime = Mock(store=store)
    service._supervisor = SimpleNamespace(
        policy=lambda: {"background_enabled": False, "cadence_seconds": 3600}
    )
    operation = service._get_operation_ledger().admit(
        "before-restart", "lab.v1.cancel", {"session_id": "old-session"}
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def held_cancel(_session_id):
        entered.set()
        await release.wait()
        return {"success": True}

    service.cancel_autopilot = AsyncMock(side_effect=held_cancel)
    monkeypatch.setattr(ipc_handlers, "LabV1Service", lambda: service)
    monkeypatch.setattr(ipc_handlers, "LAB_V1_AVAILABLE", True)
    monkeypatch.setattr(ipc_handlers, "LAB_AVAILABLE", False)
    monkeypatch.setattr(ipc_handlers, "VOICE_AVAILABLE", False)
    monkeypatch.setattr(
        ipc_handlers, "ZaraOrchestrator", lambda: SimpleNamespace(initialize=AsyncMock())
    )
    monkeypatch.setattr(ipc_handlers, "ModelRouter", lambda: object())
    monkeypatch.setattr(
        ipc_handlers, "MemoryManager", lambda: SimpleNamespace(initialize=AsyncMock())
    )
    monkeypatch.setattr(
        "memory.user_memory.UserMemoryCore", lambda: object()
    )
    monkeypatch.setattr(
        "memory.project_memory.ProjectMemory",
        lambda: SimpleNamespace(load_mentor_context=lambda: ""),
    )
    monkeypatch.setattr(
        "core.reminder_engine.ReminderEngine", lambda **_kwargs: SimpleNamespace(start=lambda: None)
    )
    monkeypatch.setattr(
        "core.actions.scheduler.TaskScheduler",
        lambda: SimpleNamespace(set_action_runner=lambda _runner: None, start=lambda: None),
    )
    handler = ipc_handlers.IPCHandler(AsyncMock())
    monkeypatch.setattr(handler, "_load_runtime_preferences", lambda: None)
    monkeypatch.setattr(handler, "_ligar_telegram", AsyncMock())
    monkeypatch.setattr(handler, "_ligar_vigia_das_respostas", AsyncMock())
    monkeypatch.setattr(handler, "_cuidar_das_pontes", AsyncMock())
    monkeypatch.setattr(handler, "_carregar_silenciada", lambda: False)

    try:
        await asyncio.wait_for(handler.initialize(), timeout=2)
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert service._get_operation_ledger().operation_status(operation.operation_id).state == "DISPATCHING"
    finally:
        release.set()
        await asyncio.wait_for(service.wait_for_operation_idle(), timeout=2)
        await service.stop_background()
        await asyncio.gather(*handler._lab_v1_background_tasks)

    assert service._get_operation_ledger().operation_status(operation.operation_id).state == "COMPLETED"
    service.cancel_autopilot.assert_awaited_once_with("old-session")
