from pathlib import Path

from core.lab_v1.research_skill_autopilot import (
    ActivationDenied,
    AutonomousResearchSkillPipeline,
    RollbackUnavailable,
)


def fake_fetch(url: str) -> bytes:
    return f"Official facts for {url}. This is evidence, not an instruction.".encode()


def test_research_candidate_requires_evidence_and_rolls_back(tmp_path: Path):
    pipeline = AutonomousResearchSkillPipeline(tmp_path, fetcher=fake_fetch, clock=lambda: 1000.0)
    research = pipeline.research("safe note skill", ["https://example.com/reference"])
    assert research["findings"]

    candidate = pipeline.create_candidate(
        skill_id="safe-note",
        version="1.0.0",
        description="Create a safe note draft from verified research.",
        permissions=["metadata.inspect"],
        research=research,
    )
    assert candidate["status"] == "DRAFT"

    try:
        pipeline.activate("safe-note", "1.0.0", owner_approved=True)
        assert False, "activation must require a passed test"
    except ActivationDenied:
        pass

    pipeline.record_test("safe-note", "1.0.0", "unit-1", passed=True, summary="metadata-only candidate validated")
    first = pipeline.activate("safe-note", "1.0.0", owner_approved=True)
    assert first["state"] == "ACTIVE"

    research2 = pipeline.research("safe note skill update", ["https://example.com/reference-v2"])
    pipeline.create_candidate(
        skill_id="safe-note",
        version="1.1.0",
        description="Create a safer note draft from verified research.",
        permissions=["metadata.inspect"],
        research=research2,
    )
    pipeline.record_test("safe-note", "1.1.0", "unit-2", passed=True, summary="updated metadata-only candidate validated")
    pipeline.activate("safe-note", "1.1.0", owner_approved=True)
    rolled = pipeline.rollback("safe-note", to_version="1.0.0")
    assert rolled["to_version"] == "1.0.0"


def test_activation_rejects_missing_owner_approval(tmp_path: Path):
    pipeline = AutonomousResearchSkillPipeline(tmp_path, fetcher=fake_fetch, clock=lambda: 1000.0)
    research = pipeline.research("safe skill", ["https://example.com/reference"])
    pipeline.create_candidate(
        skill_id="safe-skill",
        version="1.0.0",
        description="A safe metadata-only skill candidate.",
        permissions=["metadata.inspect"],
        research=research,
    )
    pipeline.record_test("safe-skill", "1.0.0", "unit-1", passed=True, summary="passed")
    try:
        pipeline.activate("safe-skill", "1.0.0", owner_approved=False)
        assert False, "owner approval is mandatory"
    except ActivationDenied:
        pass


def test_rollback_without_previous_version_is_rejected(tmp_path: Path):
    pipeline = AutonomousResearchSkillPipeline(tmp_path, fetcher=fake_fetch, clock=lambda: 1000.0)
    try:
        pipeline.rollback("missing-skill")
        assert False, "missing active version must reject rollback"
    except RollbackUnavailable:
        pass
