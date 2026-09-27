"""Tests for the ZARA Lab Living Team mission engine (M000–M080).

Covers: milestone seeding and guarded transitions, idempotent room/cycle
handling (M010/M020), research prioritization (M040), patch pipeline gates
(M060) and per-bot config limits with 429 logging (M070).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.lab_bot_config import MAX_FALLBACKS, LabBotConfig
from core.lab_mission import (
    MISSION_ID,
    STATE_DONE,
    STATE_PARTIAL,
    LabMission,
)
from core.lab_patch_pipeline import LabPatchPipeline
from core.lab_research import LabResearch
from core.lab_roles import list_roles, recruit_specialists


@pytest.fixture()
def mission(tmp_path: Path) -> LabMission:
    m = LabMission(tmp_path / "lab.db")
    m.initialize()
    return m


def test_seed_creates_nine_milestones_with_expected_initial_states(mission: LabMission) -> None:
    milestones = mission.list_milestones()
    assert len(milestones) == 9
    by_code = {m["code"]: m for m in milestones}
    assert by_code["M000"]["state"] == STATE_DONE
    assert by_code["M010"]["state"] == STATE_PARTIAL
    assert by_code["M080"]["state"] == "pending"
    # Seeding is idempotent: re-initializing keeps states and evidence.
    mission.initialize()
    assert len(mission.list_milestones()) == 9
    assert mission.list_milestones()[0]["evidence"]


def test_done_requires_evidence_and_alex_confirmation(mission: LabMission) -> None:
    with pytest.raises(ValueError, match="evidência"):
        mission.set_milestone_state("M040", STATE_DONE, evidence=[])
    with pytest.raises(ValueError, match="Alex"):
        mission.set_milestone_state(
            "M040", STATE_DONE, evidence=["some/GATES.md"], confirmed_by="zara"
        )
    result = mission.set_milestone_state(
        "M040", STATE_DONE, evidence=["some/GATES.md"], confirmed_by="Alex",
        note="conferido no pacote",
    )
    assert result["state"] == STATE_DONE
    assert result["evidence"] == ["some/GATES.md"]


def test_partial_needs_no_evidence(mission: LabMission) -> None:
    result = mission.set_milestone_state("M050", STATE_PARTIAL)
    assert result["state"] == STATE_PARTIAL


def test_room_is_single_and_persistent(mission: LabMission) -> None:
    first = mission.ensure_room()
    second = mission.ensure_room()
    assert first["id"] == second["id"]
    assert first["name"] == "ZARA Core"
    state = mission.get_state()
    assert state["mission_id"] == MISSION_ID
    assert state["room"]["id"] == first["id"]


def test_cycle_resume_never_duplicates(mission: LabMission) -> None:
    first = mission.resume_or_start_cycle("Preparar sala do conselho")
    second = mission.resume_or_start_cycle("Preparar sala do conselho")
    assert first["id"] == second["id"]
    assert second["resumed"] is True

    # A different objective while one cycle is open resumes the open cycle.
    third = mission.resume_or_start_cycle("Outro objetivo qualquer")
    assert third["id"] == first["id"]
    assert third["resumed"] is True

    mission.complete_cycle(first["id"], "sala pronta")
    fourth = mission.resume_or_start_cycle("Novo objetivo após conclusão")
    assert fourth["id"] != first["id"]
    assert fourth["resumed"] is False


def test_feed_is_chronological(mission: LabMission) -> None:
    room = mission.ensure_room()
    mission.log_feed(room["id"], "ceo", "E1", "primeiro")
    mission.log_feed(room["id"], "reader", "E2", "segundo")
    feed = mission.get_feed(room["id"])
    events = [e["event"] for e in feed]
    assert events.index("E1") < events.index("E2")
    assert "ROOM_CREATED" in events


def test_research_requires_url_and_ceo_justification(mission: LabMission) -> None:
    research = LabResearch(mission.db_path)
    research.initialize()
    with pytest.raises(ValueError, match="URL"):
        research.submit_finding(MISSION_ID, "reader", "Blog", "nota-sem-url", "resumo")
    finding = research.submit_finding(
        MISSION_ID, "reader", "Blog", "https://exemplo.com/post", "achado relevante"
    )
    assert finding["ceo_decision"] == "PENDING"
    with pytest.raises(ValueError, match="Justificativa"):
        research.ceo_prioritize(finding["id"], "NO_CHANGE", note="")
    done = research.ceo_prioritize(
        finding["id"], "NO_CHANGE", note="fora do escopo da missão"
    )
    assert done["ceo_decision"] == "NO_CHANGE"


def test_patch_pipeline_enforces_gate_order(mission: LabMission) -> None:
    pipeline = LabPatchPipeline(mission.db_path)
    pipeline.initialize()
    patch = pipeline.create_patch(
        MISSION_ID, "Ajuste pequeno", ["core/lab_mission.py"], "diff..."
    )
    patch_id = patch["id"]
    # Cannot skip straight to review.
    with pytest.raises(ValueError, match="transição inválida"):
        pipeline.submit_for_review(patch_id)
    pipeline.submit_for_verification(patch_id)
    with pytest.raises(ValueError, match="verificação aprovada"):
        pipeline.submit_for_review(patch_id)
    pipeline.record_verification(patch_id, "zara", True, "pytest 12 passed", mission)
    pipeline.submit_for_review(patch_id, mission)
    # Review must be independent from the verifier.
    with pytest.raises(ValueError, match="independente"):
        pipeline.record_review(patch_id, "zara", True, "ok", mission)
    pipeline.record_review(patch_id, "mentor", True, "revisão independente ok", mission)
    promoted = pipeline.promote(patch_id, artifacts=["build.log"], mission=mission)
    assert promoted["status"] == "PROMOTED"
    assert promoted["artifacts"] == ["build.log"]


def test_failed_verification_rejects_patch(mission: LabMission) -> None:
    pipeline = LabPatchPipeline(mission.db_path)
    pipeline.initialize()
    patch = pipeline.create_patch(MISSION_ID, "Outro ajuste", ["a.py"])
    pipeline.submit_for_verification(patch["id"])
    rejected = pipeline.record_verification(
        patch["id"], "zara", False, "teste quebrou", mission
    )
    assert rejected["status"] == "REJECTED"


def test_bot_config_limits_fallbacks_and_logs_429(mission: LabMission) -> None:
    config = LabBotConfig(mission.db_path)
    config.initialize()
    with pytest.raises(ValueError, match="Máximo de"):
        config.set_config("zara", fallbacks=[f"model-{i}" for i in range(MAX_FALLBACKS + 1)])
    updated = config.set_config(
        "zara", soul="Nova SOUL de teste", fallbacks=["m1", "m2", "m1"]
    )
    assert updated["fallbacks"] == ["m1", "m2"]  # de-duplicated, order kept
    assert updated["is_default"] is False
    restored = config.restore_default("zara", mission)
    assert restored["is_default"] is True
    swap = config.record_429_swap("zara", "m1", "m2", "rate limit", mission)
    assert swap["from_model"] == "m1"
    assert swap["to_model"] == "m2"
    room = mission.ensure_room()
    events = [e["event"] for e in mission.get_feed(room["id"])]
    assert "MODEL_429_SWAP" in events


def test_recruit_uses_builtin_catalog_without_roster() -> None:
    result = recruit_specialists("pesquisar fontes", ["pesquisa"])
    names = [s["name"] for s in result["recruited"]]
    assert "Pesquisador" in names
    assert result["pool_source"] == "builtin"
    assert len(list_roles()) == 4


def test_recruit_uses_agency_roster_when_provided() -> None:
    roster = [
        {"id": "a1", "name": "Agente Relâmpago", "capabilities": ["pesquisa"],
         "description": "", "source": "agency"},
        {"id": "a2", "name": "Agente Trovão", "capabilities": ["código"],
         "description": "", "source": "agency"},
    ]
    result = recruit_specialists("pesquisar fontes", ["pesquisa"], roster=roster)
    names = [s["name"] for s in result["recruited"]]
    assert names == ["Agente Relâmpago"]
    assert result["pool_size"] == 2
    assert result["pool_source"] == "agency"


def test_load_agency_roster_reads_json_and_ignores_invalid(tmp_path: Path) -> None:
    from core.lab_roles import load_agency_roster
    assert load_agency_roster(tmp_path) == []
    (tmp_path / "agency-agents.json").write_text(
        '[{"name": "Agente Um", "capabilities": ["x"]}, "invalido", {"sem_nome": 1}]',
        encoding="utf-8",
    )
    roster = load_agency_roster(tmp_path)
    assert [r["name"] for r in roster] == ["Agente Um"]
    assert roster[0]["source"] == "agency"
    (tmp_path / "agency-agents.json").write_text("não é json", encoding="utf-8")
    assert load_agency_roster(tmp_path) == []
