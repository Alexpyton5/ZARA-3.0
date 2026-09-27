from __future__ import annotations

from types import SimpleNamespace

from core.lab_v1.research_pipeline import ResearchPipeline
from core.lab_v1.mission_controller import MissionController
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor
import core.lab_v1.supervisor as supervisor_module


def _store(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    return store


def _supervisor(tmp_path):
    store = _store(tmp_path)
    MissionController(store)
    calls = []
    autopilot = SimpleNamespace(
        start=lambda objective, **kwargs: calls.append(("start", objective, kwargs)) or {
            "success": True, "state": "QUEUED", "session_id": "research-mission"
        },
        run=lambda session_id: calls.append(("run", session_id)) or {
            "success": True, "state": "COMPLETED", "session_id": session_id
        },
    )
    supervisor = AutonomySupervisor(SimpleNamespace(store=store), autopilot=autopilot)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "build_current.py").touch()
    supervisor.configure(enabled=True, workspace=tmp_path)
    supervisor._save(research_daily_budget=2)
    return supervisor, calls


def test_research_intake_is_persistent_deduplicated_and_budgeted(tmp_path):
    store = _store(tmp_path)
    pipeline = ResearchPipeline(store)
    first = pipeline.admit_intake(
        "Pesquisar interrupção de voz", trigger="EVENT", event_id="voice-failed",
        daily_budget=1, observed_at=1_700_000_000,
    )
    duplicate = pipeline.admit_intake(
        "  pesquisar INTERRUPÇÃO de voz ", trigger="EVENT", event_id="voice-failed-again",
        daily_budget=1, observed_at=1_700_000_001,
    )
    exhausted = pipeline.admit_intake(
        "Pesquisar latência de voz", trigger="DAILY", daily_budget=1,
        observed_at=1_700_000_002,
    )

    assert first["state"] == "QUEUED"
    assert duplicate == {**first, "state": "DUPLICATE"}
    assert exhausted["state"] == "DAILY_BUDGET_EXHAUSTED"
    reopened = ResearchPipeline(store)
    assert reopened.get_intake(first["id"])["event_id"] == "voice-failed"
    assert len(reopened.list_intakes()) == 1


def test_event_intake_uses_the_existing_supervisor_without_provider_calls(tmp_path):
    supervisor, calls = _supervisor(tmp_path)
    first = supervisor.queue_research_event("Pesquisar falha de wake word", event_id="evt-1")
    duplicate = supervisor.queue_research_event("pesquisar FALHA de wake word", event_id="evt-2")

    assert first["state"] == "QUEUED"
    assert duplicate["state"] == "DUPLICATE"
    assert calls == []


def test_feedback_tick_links_event_research_to_existing_autonomy_mission(tmp_path, monkeypatch):
    supervisor, calls = _supervisor(tmp_path)
    monkeypatch.setattr(supervisor, "ensure_team", lambda: None)
    monkeypatch.setattr(supervisor_module, "EvolutionEngine", lambda *args, **kwargs: SimpleNamespace(
        observe_local=lambda: [], observer_snapshot=lambda: {}, observe_and_plan=lambda **kwargs: {},
    ))
    inbox = SimpleNamespace(
        next_received=lambda: {"id": "feedback:1", "text": "A voz falhou", "channel": "voice",
                               "evidence_sha256": "abc", "observed_at": 1},
        link=lambda *args: None, finish=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(supervisor_module, "FeedbackInbox", lambda store: inbox)

    result = supervisor.tick()
    assert result["state"] == "COMPLETED", supervisor.policy()["error_detail"]
    started = next(item for item in calls if item[0] == "start")
    intake = ResearchPipeline(supervisor.store).get_intake(started[2]["evidence"]["research_intake_id"])
    assert intake["trigger"] == "EVENT"
    assert calls.count(("run", "research-mission")) == 1


def test_daily_scout_links_daily_research_to_existing_autonomy_mission(tmp_path, monkeypatch):
    supervisor, calls = _supervisor(tmp_path)
    monkeypatch.setattr(supervisor, "ensure_team", lambda: None)
    monkeypatch.setattr(supervisor_module, "EvolutionEngine", lambda *args, **kwargs: SimpleNamespace(
        observe_local=lambda: [], observer_snapshot=lambda: {}, observe_and_plan=lambda **kwargs: {},
    ))
    monkeypatch.setattr(supervisor_module, "FeedbackInbox", lambda store: SimpleNamespace(next_received=lambda: None))
    scout = SimpleNamespace(
        run_due=lambda: None,
        next_unreviewed=lambda: {"id": "opportunity:1", "opportunity": "Novo release", "source": "https://example.com/release",
                                  "evidence_sha256": "def", "evidence_excerpt": "mudança", "observed_at": 1},
        link_review=lambda *args: None, verify_review=lambda *args: {"passed": True}, finish_review=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(supervisor_module, "TechnologyScout", lambda store: scout)

    result = supervisor.tick()
    assert result["state"] == "COMPLETED", supervisor.policy()["error_detail"]
    started = next(item for item in calls if item[0] == "start")
    intake = ResearchPipeline(supervisor.store).get_intake(started[2]["evidence"]["research_intake_id"])
    assert intake["trigger"] == "DAILY"
