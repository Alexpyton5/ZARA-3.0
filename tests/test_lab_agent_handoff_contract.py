from __future__ import annotations

import pytest

from core.lab_v1.agent_continuity import AgentContinuity
from core.lab_v1.domain import Session, Team
from core.lab_v1.store import LabStore


def _continuity(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="ZARA Core"))
    store.save_session(Session(id="mission", team_id="team", objective="ship"))
    return AgentContinuity(store)


def _save(c, stage, expected=None):
    return c.save_handoff_checkpoint(
        "mission", "agent", stage=stage, artifact_ref=f"artifact:{stage.lower()}",
        evidence_refs=[f"evidence:{stage.lower()}"],
        provenance={"run_id": f"run:{stage.lower()}", "model": "local-test"},
        cursor=stage.lower(), summary=f"{stage} complete", expected_revision=expected,
    )


def test_handoff_stages_are_durable_and_recoverable(tmp_path):
    c = _continuity(tmp_path)
    first = _save(c, "STRATEGIST")
    second = _save(c, "EXECUTOR", first.revision)
    third = _save(c, "REVIEWER", second.revision)
    final = _save(c, "MAESTRO", third.revision)
    assert final.revision == 4
    assert c.load_handoff_checkpoint("mission", "agent").stage == "MAESTRO"


def test_handoff_requires_artifact_evidence_and_provenance(tmp_path):
    c = _continuity(tmp_path)
    common = dict(session_id="mission", agent_id="agent", stage="STRATEGIST",
                  cursor="x", summary="x")
    with pytest.raises(ValueError, match="artifact_ref"):
        c.save_handoff_checkpoint(**common, artifact_ref="", evidence_refs=["e"], provenance={})
    with pytest.raises(ValueError, match="evidence_refs"):
        c.save_handoff_checkpoint(**common, artifact_ref="a", evidence_refs=[], provenance={"run": "r"})
    with pytest.raises(ValueError, match="provenance"):
        c.save_handoff_checkpoint(**common, artifact_ref="a", evidence_refs=["e"], provenance={})


def test_handoff_cannot_skip_reviewer_or_move_backwards(tmp_path):
    c = _continuity(tmp_path)
    first = _save(c, "STRATEGIST")
    with pytest.raises(ValueError, match="exactly one step"):
        _save(c, "REVIEWER", first.revision)


def test_handoff_uses_optimistic_revision_lock(tmp_path):
    c = _continuity(tmp_path)
    first = _save(c, "STRATEGIST")
    with pytest.raises(Exception):
        _save(c, "EXECUTOR", first.revision - 1)


def test_handoff_rejects_unknown_stage(tmp_path):
    c = _continuity(tmp_path)
    with pytest.raises(ValueError, match="Unknown handoff stage"):
        _save(c, "WORKER")


def test_handoff_provenance_is_factual_caller_supplied_data(tmp_path):
    c = _continuity(tmp_path)
    checkpoint = _save(c, "STRATEGIST")
    assert checkpoint.state["handoff"]["provenance"] == {"model": "local-test", "run_id": "run:strategist"}


def test_non_handoff_checkpoint_remains_compatible(tmp_path):
    c = _continuity(tmp_path)
    saved = c.save_checkpoint("mission", "agent", cursor="plain", summary="plain", state={"ok": True})
    assert c.load_handoff_checkpoint("mission", "agent") is None
    assert saved.state == {"ok": True}


# --------------------------------------------------------------------------
# Phase 1 "Organization" additions (additive; nothing above is weakened).
# --------------------------------------------------------------------------


def test_handoff_baton_belongs_to_the_session_across_agents(tmp_path):
    c = _continuity(tmp_path)
    c.save_handoff_checkpoint(
        "mission", "ceo", stage="STRATEGIST", artifact_ref="artifact:plan",
        evidence_refs=["evidence:plan"],
        provenance={"run_id": "run:plan", "model": "local-test"},
        cursor="plan", summary="plan complete",
    )
    # The builder is a different person with no prior row of its own: the
    # +1 rule is checked against the SESSION baton, not the agent's row.
    built = c.save_handoff_checkpoint(
        "mission", "builder", stage="EXECUTOR", artifact_ref="artifact:build",
        evidence_refs=["evidence:build"],
        provenance={"run_id": "run:build", "model": "local-test"},
        cursor="build", summary="build complete",
    )
    assert built.revision == 1
    with pytest.raises(ValueError, match="exactly one step"):
        c.save_handoff_checkpoint(
            "mission", "builder", stage="MAESTRO", artifact_ref="artifact:final",
            evidence_refs=["evidence:final"],
            provenance={"run_id": "run:final", "model": "local-test"},
            cursor="final", summary="skip the reviewer",
            expected_revision=built.revision,
        )


def test_handoff_provenance_accepts_canonical_run_keys(tmp_path):
    c = _continuity(tmp_path)
    saved = c.save_handoff_checkpoint(
        "mission", "agent", stage="STRATEGIST", artifact_ref="artifact:plan",
        evidence_refs=["evidence:plan"],
        provenance={
            "run_id": "run:1", "provider": "local", "model": "local-test",
            "model_reported": "local-test-2",
        },
        cursor="x", summary="x",
    )
    assert saved.state["handoff"]["provenance"] == {
        "model": "local-test", "model_reported": "local-test-2",
        "provider": "local", "run_id": "run:1",
    }


def test_handoff_provenance_validates_canonical_keys_when_present(tmp_path):
    c = _continuity(tmp_path)
    with pytest.raises(ValueError, match="run_id"):
        c.save_handoff_checkpoint(
            "mission", "agent", stage="STRATEGIST", artifact_ref="a",
            evidence_refs=["e"], provenance={"run_id": None},
            cursor="x", summary="x",
        )
    with pytest.raises(ValueError, match="model_reported"):
        c.save_handoff_checkpoint(
            "mission", "agent", stage="STRATEGIST", artifact_ref="a",
            evidence_refs=["e"], provenance={"model_reported": "  "},
            cursor="x", summary="x",
        )
