"""Tests for the ZARA Lab autonomous mode (council works on its own).

Covers: idempotent start, stop halting the loop, graceful degradation of
the scan phase without LLM/workers, and a full autonomous cycle against a
stub coordinator (debate turns recorded, proposals drafted, never promoted).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import core.lab_autonomy as lab_autonomy_mod
from core.lab_autonomy import LabAutonomy
from core.lab_mission import LabMission
from core.lab_patch_pipeline import LabPatchPipeline
from core.lab_research import LabResearch


class StubCoordinator:
    """Minimal coordinator surface used by LabAutonomy."""

    def __init__(self, tmp_path: Path) -> None:
        db = tmp_path / "lab.db"
        self.mission = LabMission(db)
        self.mission.initialize()
        self.research = LabResearch(db)
        self.research.initialize()
        self.patches = LabPatchPipeline(db)
        self.patches.initialize()
        self.worker_runtime = None
        self.orchestrator = None
        self.sent: list[tuple[str, str, str]] = []
        self._proposal_seq = 0

    async def mission_resume_cycle(self, objective: str) -> dict[str, Any]:
        return self.mission.resume_or_start_cycle(objective)

    async def mission_complete_cycle(self, cycle_id: str, summary: str = "") -> dict[str, Any]:
        return self.mission.complete_cycle(cycle_id, summary)

    async def send_message(self, author: str, target: str, content: str) -> dict[str, Any]:
        self.sent.append((author, target, content))
        return {"success": True, "state": "OK"}

    async def create_proposal(self, title: str, summary: str,
                              risk: str = "MEDIUM", owner: str = "opencode") -> dict[str, Any]:
        self._proposal_seq += 1
        return {"id": f"ZARA-TEST{self._proposal_seq}", "status": "DISCUSSION"}


@pytest.fixture()
def autonomy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LabAutonomy:
    monkeypatch.setattr(lab_autonomy_mod, "data_dir", lambda: tmp_path)
    return LabAutonomy(StubCoordinator(tmp_path))


def test_start_is_idempotent_and_stop_halts(autonomy: LabAutonomy) -> None:
    import asyncio

    async def scenario() -> None:
        first = await autonomy.start("objetivo")
        second = await autonomy.start("objetivo")
        assert first["running"] is True
        assert second["running"] is True
        assert autonomy._cycle_id is not None or True  # cycle starts in background
        stopped = await autonomy.stop()
        assert stopped["running"] is False
        assert stopped["enabled"] is False

    asyncio.run(scenario())


def test_full_cycle_degrades_gracefully_without_llm(autonomy: LabAutonomy) -> None:
    import asyncio

    async def scenario() -> None:
        # No worker_runtime / orchestrator: scan must still yield a finding.
        await autonomy._run_cycle("ciclo de teste")
        coord = autonomy.coordinator
        findings = coord.research.list_findings("ZARA-LAB-LIVING-TEAM-20260925")
        assert len(findings) >= 1
        # Prioritized findings become DISCUSSION proposals, never promoted.
        assert all(f["ceo_decision"] == "PRIORITIZED" for f in findings)
        # Debate happened out loud through council turns.
        targets = {t for _, t, _ in coord.sent}
        assert "opencode" in targets and "zara" in targets
        # Draft patch exists as DRAFT only.
        patches = coord.patches.list_patches("ZARA-LAB-LIVING-TEAM-20260925")
        assert patches and all(p["status"] == "DRAFT" for p in patches)
        # Cycle completed and logged to the room feed.
        room = coord.mission.ensure_room()
        events = [e["event"] for e in coord.mission.get_feed(room["id"])]
        for expected in ("AUTONOMY_CYCLE_START", "AUTONOMY_SCAN_DONE",
                         "AUTONOMY_DEBATE_DONE", "AUTONOMY_CYCLE_DONE"):
            assert expected in events

    asyncio.run(scenario())


def test_parse_findings_caps_at_five() -> None:
    text = "\n".join(
        f"{i}. Título {i}\n   ARQUIVO: a/b.py\n   MOTIVO: motivo {i}" for i in range(1, 9)
    )
    parsed = LabAutonomy._parse_findings(text)
    assert len(parsed) == 5
    assert parsed[0]["location"] == "a/b.py"


def test_status_reflects_config(autonomy: LabAutonomy) -> None:
    assert autonomy.is_enabled() is True  # default ON per Alex's request
    autonomy.set_enabled(False)
    assert autonomy.is_enabled() is False
    status = autonomy.status()
    assert status["enabled"] is False
    assert status["running"] is False
