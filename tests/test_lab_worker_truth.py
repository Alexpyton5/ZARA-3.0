from __future__ import annotations

import pytest

from core.lab_coordinator import LabCoordinator


@pytest.mark.asyncio
async def test_lab_roster_matches_integrations_wired_in_the_current_build():
    coordinator = LabCoordinator()

    workers = await coordinator.worker_states()
    by_id = {worker["id"]: worker for worker in workers}

    assert set(by_id) == {
        "alex", "zara", "mentor", "hermes",
        "opencode", "openclaw", "cline", "aider",
    }
    assert by_id["hermes"]["state"] == "OFFLINE"
    assert by_id["hermes"]["can_chat"] is False
    assert by_id["hermes"]["can_execute"] is False
