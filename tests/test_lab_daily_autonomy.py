"""Astra Fase 8: the daily autonomy loop over the EXISTING supervisor path.

Required semantics: dedup, owner priority, backoff, evidence validity and a
persistent budget. No second autonomous engine: everything here rides
AutonomySupervisor and the durable operations rows it persists in the Lab DB.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from core.lab_v1.feedback_inbox import FeedbackInbox
from core.lab_v1.mission_controller import MissionController
from core.lab_v1.research_pipeline import ResearchPipeline
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor
import core.lab_v1.supervisor as supervisor_module


def _store(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    return store


def _supervisor(tmp_path, *, daily_budget=2):
    store = _store(tmp_path)
    MissionController(store)
    calls = []
    autopilot = SimpleNamespace(
        start=lambda objective, **kwargs: calls.append(("start", objective, kwargs)) or {
            "success": True, "state": "QUEUED", "session_id": "research-mission"},
        run=lambda session_id: calls.append(("run", session_id)) or {
            "success": True, "state": "COMPLETED", "session_id": session_id},
    )
    supervisor = AutonomySupervisor(SimpleNamespace(store=store), autopilot=autopilot)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "build_current.py").touch()
    supervisor.configure(enabled=True, workspace=tmp_path)
    supervisor._save(research_daily_budget=daily_budget)
    return supervisor, calls


def _evolution_stub(monkeypatch):
    monkeypatch.setattr(supervisor_module, "EvolutionEngine", lambda *args, **kwargs: SimpleNamespace(
        observe_local=lambda: [], observer_snapshot=lambda: {}, observe_and_plan=lambda **kwargs: {},
    ))


def _scout_stub(monkeypatch):
    monkeypatch.setattr(supervisor_module, "TechnologyScout", lambda store: SimpleNamespace(
        run_due=lambda: None, next_unreviewed=lambda: None))


def _operation_rows(supervisor, evidence_id):
    with supervisor.store._connect() as conn:
        return [json.loads(row["document"]) for row in conn.execute(
            f'SELECT document FROM {supervisor._OPERATIONS_TABLE} WHERE evidence_id=?',
            (evidence_id,))]


def _insert_session(supervisor, session_id):
    with supervisor.store._connect() as conn:
        conn.execute("INSERT INTO sessions(id, team_id, objective, state, created_at, "
                     "updated_at) VALUES(?,?,?,?,1000.0,1000.0)",
                     (session_id, "team", "objetivo", "COMPLETED"))


def _insert_blocked_owner_mission(supervisor, session_id="sess-owner"):
    _insert_session(supervisor, session_id)
    with supervisor.store._connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS mission_autonomy("
                     "session_id TEXT PRIMARY KEY, document TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS autonomy_gaps("
                     "gap_id TEXT PRIMARY KEY, session_id TEXT, stage TEXT, reason TEXT, "
                     "owner_action_required TEXT, candidate_automation TEXT, risk TEXT, "
                     "occurrences INTEGER, created_at REAL)")
        conn.execute("INSERT INTO mission_autonomy VALUES(?,?)",
                     (session_id, json.dumps({"session_id": session_id,
                                              "workflow": supervisor_module.WORKFLOW})))
        conn.execute("INSERT INTO mission_controls(session_id, document, lease_until) "
                     "VALUES(?,?,0)",
                     (session_id, json.dumps({"session_id": session_id,
                                              "state": "BLOCKED_NEEDS_OWNER",
                                              "blocker": "OWNER_DECISION"})))


# Proof 1: a duplicate event generates ONE logical operation.
def test_duplicate_event_generates_one_logical_operation(tmp_path, monkeypatch):
    supervisor, calls = _supervisor(tmp_path)
    monkeypatch.setattr(supervisor, "ensure_team", lambda: None)
    _evolution_stub(monkeypatch)
    _scout_stub(monkeypatch)
    feedback = {"id": "feedback:dedup", "text": "A voz falhou", "channel": "voice",
                "evidence_sha256": "abc", "observed_at": 1}
    inbox = SimpleNamespace(next_received=lambda: feedback, link=lambda *a: None,
                            finish=lambda *a, **k: None)
    monkeypatch.setattr(supervisor_module, "FeedbackInbox", lambda store: inbox)

    first = supervisor.tick()
    assert first["state"] == "COMPLETED", supervisor.policy()["error_detail"]
    supervisor._save(next_evolution_check=0, daily_missions=0, daily_date=None)
    second = supervisor.tick()
    assert second["state"] == "MONITORING"
    assert second["daily_operation_state"] == "DUPLICATE"
    assert calls.count(("run", "research-mission")) == 1

    rows = _operation_rows(supervisor, "feedback:dedup")
    assert len(rows) == 1
    assert rows[0]["budget"]["spent"] == 1
    # One logical operation also means one research intake, not two.
    assert len(ResearchPipeline(supervisor.store).list_intakes()) == 1


# Proof 2: the budget survives a restart because it is persisted with the operation.
def test_budget_survives_restart_persisted_with_the_operation(tmp_path):
    supervisor, _ = _supervisor(tmp_path, daily_budget=2)
    cap = supervisor.policy()["research_daily_budget"]
    admission = supervisor.admit_daily_operation(
        {"id": "ev-budget", "source": "core/lab_v1/service.py"}, now=1000.0)
    assert admission["state"] == "ADMITTED"
    operation_id = admission["operation"]["id"]
    supervisor.link_daily_operation(operation_id, "sess-budget")

    restarted = AutonomySupervisor(SimpleNamespace(store=supervisor.store))
    assert restarted.daily_budget_remaining() == cap - 1
    assert restarted.daily_operation(operation_id)["session_id"] == "sess-budget"
    assert restarted.daily_operation(operation_id)["budget"]["spent"] == 1


# Proof 3: an empty queue spends zero tokens (no model call when nothing is due).
def test_empty_queue_spends_zero_tokens(tmp_path, monkeypatch):
    supervisor, calls = _supervisor(tmp_path)
    spent = []
    monkeypatch.setattr(supervisor, "ensure_team", lambda: spent.append("ensure"))
    _evolution_stub(monkeypatch)
    monkeypatch.setattr(supervisor_module, "FeedbackInbox", lambda store: SimpleNamespace(
        next_received=lambda: None))
    _scout_stub(monkeypatch)

    result = supervisor.tick()
    assert result["state"] == "MONITORING"
    assert result["token_spend"] == 0
    assert calls == []      # no model call: nothing was started or run
    assert spent == []      # not even team provisioning


# Proof 4: pause interrupts new admissions immediately; the already-paused path stays.
def test_pause_blocks_new_admissions_and_keeps_already_paused_path(tmp_path):
    supervisor, calls = _supervisor(tmp_path)
    supervisor.pause_background()
    assert supervisor.admit_daily_operation(
        {"id": "ev-pause", "source": "s"})["state"] == "PAUSED"
    result = supervisor.tick()
    assert result["state"] == "DISABLED"      # already-paused path stays exactly as it was
    assert calls == []
    with supervisor.store._connect() as conn:
        assert conn.execute(
            f'SELECT COUNT(*) FROM {supervisor._OPERATIONS_TABLE}').fetchone()[0] == 0
    supervisor.resume_background()
    assert supervisor.admit_daily_operation(
        {"id": "ev-pause", "source": "s"})["state"] == "ADMITTED"


# Proof 5: owner absence allows finishing safe work and producing a digest with
# only useful items.
def test_owner_absence_finishes_safe_work_and_digest_lists_only_useful(tmp_path, monkeypatch):
    supervisor, calls = _supervisor(tmp_path)
    monkeypatch.setattr(supervisor, "ensure_team", lambda: None)
    _evolution_stub(monkeypatch)
    _scout_stub(monkeypatch)
    finished = []
    feedback = {"id": "feedback:absent", "text": "A voz falhou", "channel": "voice",
                "evidence_sha256": "abd", "observed_at": 1}
    inbox = SimpleNamespace(next_received=lambda: feedback, link=lambda *a: None,
                            finish=lambda *a, **k: finished.append(k))
    monkeypatch.setattr(supervisor_module, "FeedbackInbox", lambda store: inbox)

    # Owner absent: no supported mission is BLOCKED_NEEDS_OWNER, so safe work runs.
    result = supervisor.tick()
    assert result["state"] == "COMPLETED", supervisor.policy()["error_detail"]
    assert finished == [{"completed": True}]

    store = supervisor.store
    _insert_session(supervisor, "sess-int")
    with store._connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS mission_autonomy("
                     "session_id TEXT PRIMARY KEY, document TEXT NOT NULL)")
        conn.execute("INSERT INTO mission_autonomy VALUES(?,?)",
                     ("sess-int", json.dumps({"session_id": "sess-int",
                                              "mission_kind": "DAILY_OPPORTUNITY_REVIEW"})))
        conn.execute("INSERT INTO mission_controls(session_id, document, lease_until) "
                     "VALUES(?,?,0)",
                     ("sess-int", json.dumps({"session_id": "sess-int", "state": "COMPLETED"})))
        stamp = 1000.0
        conn.execute("CREATE TABLE IF NOT EXISTS lab_product_feedback("
                     "id TEXT PRIMARY KEY, evidence_sha256 TEXT NOT NULL UNIQUE, "
                     "document TEXT NOT NULL, status TEXT NOT NULL, mission_id TEXT, "
                     "created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS lab_opportunities("
                     "id TEXT PRIMARY KEY, document TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO lab_product_feedback VALUES(?,?,?,?,?,?,?)",
                     ("fb-ok", "sha-ok", json.dumps({"text": "Pronto para decisao do owner"}),
                      "READY_FOR_OWNER", None, stamp, stamp))
        conn.execute("INSERT INTO lab_product_feedback VALUES(?,?,?,?,?,?,?)",
                     ("fb-bad", "sha-bad", json.dumps({"text": "revisao falhou"}),
                      "REVIEW_FAILED", None, stamp, stamp))
        conn.execute("INSERT INTO lab_opportunities VALUES(?,?,?)",
                     ("op-ok", json.dumps({"state": "READY_FOR_OWNER",
                                           "opportunity": "Sinal"}), stamp))
        conn.execute("INSERT INTO lab_opportunities VALUES(?,?,?)",
                     ("op-rej", json.dumps({"state": "REJECTED_BY_TEAM",
                                            "opportunity": "Rejeitada"}), stamp))

    digest = supervisor.daily_digest()
    assert digest["owner_absent"] is True
    assert digest["useful"] == 3
    assert {item["kind"] for item in digest["items"]} == {
        "INTERNAL_REVIEW", "PRODUCT_FEEDBACK", "DAILY_OPPORTUNITY"}
    assert digest["excluded"] == 2


# Proof 6: evidence validity expiry allows a justified NEW cycle linked to the
# previous one, not blocked by the permanent dedup.
def test_evidence_validity_expiry_allows_justified_linked_cycle(tmp_path):
    supervisor, _ = _supervisor(tmp_path)
    evidence = {"id": "ev-cycle", "source": "https://example.com/release",
                "kind": "DAILY_OPPORTUNITY", "evidence_sha256": "sha", "observed_at": 1}
    first = supervisor.admit_daily_operation(evidence, now=1000.0)
    assert first["state"] == "ADMITTED"
    first_operation = first["operation"]
    valid_for = supervisor.policy()["evidence_validity_seconds"]

    within = supervisor.admit_daily_operation(evidence, now=1000.0 + valid_for - 1)
    assert within["state"] == "DUPLICATE"          # dedup inside the validity window

    cycle = supervisor.admit_daily_operation(evidence, now=1000.0 + valid_for + 1)
    assert cycle["state"] == "RESEARCH_CYCLE"
    assert cycle["operation"]["cycle"] == 2
    assert cycle["operation"]["linked_to"] == first_operation["id"]
    assert cycle["operation"]["justification"] == "EVIDENCE_VALIDITY_EXPIRED"

    # The permanent research dedup does not block the justified cycle: its
    # question forks a NEW intake while the base question stays deduplicated.
    pipeline = ResearchPipeline(supervisor.store)
    base = pipeline.admit_intake("pesquisar base", trigger="EVENT", event_id="b1",
                                 daily_budget=5)
    duplicate = pipeline.admit_intake("pesquisar base", trigger="EVENT", event_id="b2",
                                      daily_budget=5)
    assert base["state"] == "QUEUED"
    assert duplicate["state"] == "DUPLICATE"
    forked = supervisor.research_question_for_cycle("pesquisar base", cycle["operation"])
    assert forked != "pesquisar base"
    assert "EVIDENCE_VALIDITY_EXPIRED" in forked
    assert pipeline.admit_intake(forked, trigger="EVENT", event_id="b3",
                                 daily_budget=5)["state"] == "QUEUED"


# Required semantics: backoff is persisted and read across a restart.
def test_failure_arms_persisted_backoff_across_restart(tmp_path):
    supervisor, _ = _supervisor(tmp_path)
    evidence = {"id": "ev-backoff", "source": "s", "kind": "FEEDBACK", "text": "t",
                "evidence_sha256": "sha"}
    admission = supervisor.admit_daily_operation(evidence, now=1000.0)
    operation_id = admission["operation"]["id"]
    supervisor.record_daily_operation_outcome(operation_id, failure=True, now=1000.0)
    document = supervisor.daily_operation(operation_id)
    assert document["failures"] == 1
    assert document["backoff_until"] == 1000.0 + 900.0      # base backoff, persisted

    restarted = AutonomySupervisor(SimpleNamespace(store=supervisor.store))
    retry = restarted.admit_daily_operation(evidence, now=1500.0)
    assert retry["state"] == "BACKOFF"
    assert retry["retry_at"] == document["backoff_until"]

    # After the backoff passes, the same evidence continues as a linked cycle.
    later = restarted.admit_daily_operation(evidence, now=document["backoff_until"] + 1)
    assert later["state"] == "RESEARCH_CYCLE"
    assert later["operation"]["linked_to"] == operation_id


# Required semantics: owner priority queues nothing ahead of an owner-blocked
# supported mission.
def test_owner_blocked_supported_mission_queues_nothing_ahead_of_owner(tmp_path):
    supervisor, calls = _supervisor(tmp_path)
    _insert_blocked_owner_mission(supervisor)

    result = supervisor.admit_daily_operation({"id": "ev-owner", "source": "s"})
    assert result["state"] == "OWNER_PRIORITY"
    assert result["dispatched"] is False
    assert result["detail"]["blocked_sessions"] == ["sess-owner"]
    assert calls == []
