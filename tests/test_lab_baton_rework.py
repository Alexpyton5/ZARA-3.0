"""Rework dimension of the Lab handoff baton (Phase 1 - Organization).

The reviewer can send work back to the executor after a rejection, but only
through the explicit `AgentContinuity.save_rework_checkpoint` API, at most
`_MAX_REWORK` times per chain, and without ever loosening the +1 monotony of
`save_handoff_checkpoint`.
"""
from __future__ import annotations

import pytest

from core.lab_v1.agent_continuity import AgentContinuity, StaleCheckpoint
from core.lab_v1.domain import Session, Team
from core.lab_v1.store import LabStore


def _continuity(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="ZARA Core"))
    store.save_session(Session(id="mission", team_id="team", objective="ship"))
    return AgentContinuity(store)


def _expected(c, session, agent, expected):
    if expected is not None:
        return expected
    current = c.load_checkpoint(session, agent)
    return current.revision if current else None


def _handoff(c, agent, stage, expected=None):
    session = "mission"
    return c.save_handoff_checkpoint(
        session, agent, stage=stage, artifact_ref=f"artifact:{stage.lower()}",
        evidence_refs=[f"evidence:{stage.lower()}"],
        provenance={"run_id": f"run:{stage.lower()}", "model": "local-test"},
        cursor=stage.lower(), summary=f"{stage} complete",
        expected_revision=_expected(c, session, agent, expected),
    )


def _rework(c, agent, expected=None, session="mission"):
    return c.save_rework_checkpoint(
        session, agent, artifact_ref="artifact:rework",
        evidence_refs=["evidence:rework"],
        provenance={"run_id": "run:rework", "model": "local-test"},
        cursor="rework", summary="rework complete",
        expected_revision=_expected(c, session, agent, expected),
    )


def test_rework_sends_the_baton_back_with_an_attempt_dimension(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    _handoff(c, "agent", "REVIEWER")
    reworked = _rework(c, "agent")
    assert reworked.state["handoff"]["stage"] == "EXECUTOR"
    assert reworked.state["handoff"]["rework_from"] == "REVIEWER"
    assert reworked.state["handoff"]["rework_attempt"] == 1
    loaded = c.load_handoff_checkpoint("mission", "agent")
    assert loaded.stage == "EXECUTOR"
    assert loaded.rework_from == "REVIEWER"
    assert loaded.rework_attempt == 1
    # The chain resumes +1 from the reworked EXECUTOR and keeps the counter.
    reviewed = _handoff(c, "agent", "REVIEWER", reworked.revision)
    assert reviewed.state["handoff"]["stage"] == "REVIEWER"
    assert reviewed.state["handoff"]["rework_attempt"] == 1
    assert "rework_from" not in reviewed.state["handoff"]


def test_second_rework_is_allowed_and_the_third_is_blocked(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    _handoff(c, "agent", "REVIEWER")
    first = _rework(c, "agent")
    _handoff(c, "agent", "REVIEWER", first.revision)
    second = _rework(c, "agent")
    assert second.state["handoff"]["rework_attempt"] == 2
    _handoff(c, "agent", "REVIEWER", second.revision)
    with pytest.raises(ValueError, match="rework limit"):
        _rework(c, "agent")


def test_rework_requires_a_prior_reviewer_baton(tmp_path):
    c = _continuity(tmp_path)
    with pytest.raises(ValueError, match="Unknown session"):
        _rework(c, "agent", session="missing")
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    with pytest.raises(ValueError, match="REVIEWER"):
        _rework(c, "agent")


def test_monotony_stays_strict_for_silent_backwards_moves(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    _handoff(c, "agent", "REVIEWER")
    # REVIEWER -> EXECUTOR through the normal API stays illegal: rework is
    # only reachable via the explicit rework API.
    with pytest.raises(ValueError, match="exactly one step"):
        _handoff(c, "agent", "EXECUTOR")


def test_rework_respects_the_optimistic_revision_lock(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    reviewed = _handoff(c, "agent", "REVIEWER")
    with pytest.raises(StaleCheckpoint):
        _rework(c, "agent", reviewed.revision - 1)


def test_rework_crosses_agents_and_the_session_baton_tracks_it(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "ceo", "STRATEGIST")
    built = _handoff(c, "builder", "EXECUTOR")
    reviewed = _handoff(c, "reviewer", "REVIEWER")
    reworked = _rework(c, "builder", built.revision)
    assert reworked.revision == built.revision + 1
    assert reworked.state["handoff"]["rework_attempt"] == 1
    # The reviewer's next baton is a legal +1 from the reworked EXECUTOR and
    # carries the attempt forward for the limit.
    again = _handoff(c, "reviewer", "REVIEWER", reviewed.revision)
    assert again.state["handoff"]["stage"] == "REVIEWER"
    assert again.state["handoff"]["rework_attempt"] == 1


def test_clock_rollback_between_processes_still_picks_the_latest_baton_by_rowid(tmp_path, monkeypatch):
    import time as _time

    import core.lab_v1.agent_continuity as ac

    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    executor_baton = c._last_session_handoff("mission")
    assert executor_baton["stage"] == "EXECUTOR"
    pre_rollback_stamp = _time.time()

    # Simulate a NEW process whose wall clock rolled back: fresh _LAST_STAMP
    # and a time.time() far below the stamps already persisted.
    monkeypatch.setattr(ac, "_LAST_STAMP", [0.0])
    monkeypatch.setattr(ac.time, "time", lambda: 1000.0)

    # The +1 step is still legal against the session baton even though the
    # new row's updated_at is SMALLER than every pre-rollback stamp.
    reviewed = _handoff(c, "agent", "REVIEWER")
    assert reviewed.state["handoff"]["stage"] == "REVIEWER"
    latest = c._last_session_handoff("mission")
    assert latest["stage"] == "REVIEWER"
    assert latest["artifact_ref"] == "artifact:reviewer"
    assert latest is not executor_baton

    # The winning baton carries a rolled-back stamp far below the stamps the
    # table already saw: updated_at ordering alone would be ambiguous, yet
    # the rowid-first scan picks the logically latest baton (REVIEWER).
    import sqlite3 as _sqlite3
    with _sqlite3.connect(str(c.store.db_path)) as conn:
        stamps = [r[0] for r in conn.execute(
            "SELECT updated_at FROM agent_continuity WHERE session_id='mission'"
        )]
    assert stamps and max(stamps) == pytest.approx(1000.0, abs=1.0)
    assert max(stamps) < pre_rollback_stamp
    assert c._last_session_handoff("mission")["stage"] == "REVIEWER"


def test_handoff_contract_is_preserved_under_rowid_first_ordering(tmp_path):
    c = _continuity(tmp_path)
    _handoff(c, "agent", "STRATEGIST")
    _handoff(c, "agent", "EXECUTOR")
    _handoff(c, "agent", "REVIEWER")
    _handoff(c, "agent", "MAESTRO")
    latest = c._last_session_handoff("mission")
    assert latest["stage"] == "MAESTRO"
    # Same steps, same rejections as before the ordering change.
    with pytest.raises(ValueError, match="exactly one step"):
        _handoff(c, "agent", "EXECUTOR")
    with pytest.raises(ValueError, match="Unknown handoff stage"):
        _handoff(c, "agent", "STRATEGIST2")
