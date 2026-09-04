from __future__ import annotations

import pytest

from core.lab_coordinator import LabCoordinator


@pytest.mark.asyncio
async def test_lab_roster_contains_every_declared_member_without_fake_codex_online():
    coordinator = LabCoordinator()

    workers = await coordinator.worker_states()
    by_id = {worker["id"]: worker for worker in workers}

    assert set(by_id) == {
        "alex", "zara", "mentor", "codex",
        "opencode", "openclaw", "cline", "aider", "revisor_supervisor",
    }
    assert by_id["codex"]["state"] == "NOT CONFIGURED"
    assert by_id["codex"]["can_chat"] is False
    assert by_id["codex"]["can_execute"] is False
    assert by_id["revisor_supervisor"]["role"] == "QA / FINAL REVIEW"
    assert by_id["revisor_supervisor"]["can_chat"] is True
    assert by_id["revisor_supervisor"]["can_execute"] is False
