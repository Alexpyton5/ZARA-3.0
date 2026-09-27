import json
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (
    AgentProfile,
    Availability,
    ProviderInfo,
    ProviderResult,
    RoleName,
    Team,
    TeamMembership,
)
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


class ContinuousTextAdapter(ProviderAdapter):
    controlled_text_only = True

    def __init__(self, name):
        self.id = self.label = name
        self.calls = []
        self.invalid = False

    def probe(self):
        return ProviderInfo(self.id, self.label, "test", Availability.AVAILABLE, models=["test"])

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.invalid:
            text = "not a plan"
        else:
            text = json.dumps({
                "mission": "Document",
                "plan_version": 1,
                "tasks": [{
                    "id": "document",
                    "title": "Document",
                    "instruction": "Create the requested short document",
                    "role": "BUILDER",
                    "capability": "artifact.text",
                    "path": "result.md",
                    "risk": "LOW",
                    "repair_budget": 1,
                    "depends_on": [],
                    "acceptance": {
                        "method": "constraints",
                        "min_chars": 10,
                        "max_chars": 100,
                        "required_sections": [],
                    },
                }],
            })
            if "Implement only" in kwargs.get("system", ""):
                text = "CONTINUOUS_OK"
        return ProviderResult(
            True,
            text=text,
            availability=Availability.AVAILABLE,
            model_reported=kwargs["model"],
            input_tokens=1,
            output_tokens=1,
            duration_ms=1,
            provider_session_id="continuous-test",
        )


class ContinuousFiles:
    def __init__(self, sandbox):
        self.sandbox = sandbox

    def execute(self, request, deadline):
        Path(request.path).write_bytes(request.content.encode("utf-8"))
        return {"success": True, "data": {"executor": "test"}}


@pytest.fixture
def engine(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    registry = ProviderRegistry(tmp_path / "health.json")
    primary = ContinuousTextAdapter("primary")
    fallback = ContinuousTextAdapter("fallback")
    for adapter in (primary, fallback):
        registry.register(adapter)
        registry.record_result(adapter.id, "test", ProviderResult(True, availability=Availability.AVAILABLE))
    runtime = LabRuntime(store, registry)
    store.save_team(Team("team", "Continuous autopilot tests"))
    for name, provider, role in (
        ("lead", "primary", RoleName.CEO),
        ("worker", "fallback", RoleName.BUILDER),
        ("spare", "fallback", RoleName.CEO),
    ):
        store.save_agent(AgentProfile(name, name, provider, "test", role=role, capabilities=["model.text"]))
        store.save_membership(TeamMembership("member:" + name, "team", name))
    policy = WorkforcePolicy({
        "mission_entry_enabled": True,
        "background_enabled": True,
        "authorized_providers": ["primary", "fallback"],
        "resource_classes": {
            "primary/*": "OWNER_REPORTED_FREE",
            "fallback/*": "OWNER_REPORTED_FREE",
        },
        "authorized_models": ["primary/*", "fallback/*"],
        "authorized_roles": ["CEO", "BUILDER", "REVIEWER", "RESEARCHER", "MEMBER"],
    })
    return Autopilot(
        runtime,
        root=tmp_path / "missions",
        executor_factory=ContinuousFiles,
        policy=policy,
    )


def _event_types(engine, sid):
    return [event.type for event in engine.store.list_events(sid, limit=500)]


def test_continuous_cycle_closes_and_replays_idempotently(engine):
    sid = engine.start("Create a document")["session_id"]

    first = engine.run_continuous(sid)
    assert first["state"] == "COMPLETED"
    assert set(first["cycle"]) == {"observation", "learning", "next_work"}
    assert first["cycle"]["learning"]["learning"]["outcome"] == "COMPLETED"
    assert first["cycle"]["next_work"]["requires_owner"] is True

    events_before = engine.store.list_events(sid, limit=500)
    runs_before = engine.store.list_runs(sid)
    second = engine.continuous_cycle(sid)

    assert second["state"] == "COMPLETED"
    assert len(engine.store.list_runs(sid)) == len(runs_before) == 2
    assert engine.store.list_events(sid, limit=500) == events_before
    assert second["cycle"]["observation"]["idempotent_replay"] is True
    assert second["cycle"]["learning"]["idempotent_replay"] is True
    assert second["cycle"]["next_work"]["idempotent_replay"] is True
    assert {
        "mission.observed",
        "mission.learning_recorded",
        "mission.next_work_proposed",
    } <= set(_event_types(engine, sid))


def test_pause_is_safe_and_resume_keeps_the_same_mission(engine):
    sid = engine.start("Create a document")["session_id"]
    paused = engine.pause(sid, "owner is reviewing evidence")
    assert paused["success"] is True
    assert engine.pause(sid)["pause_generation"] == paused["pause_generation"]

    stopped = engine.run_continuous(sid)
    assert stopped["state"] == "PAUSED"
    assert stopped["success"] is False
    assert engine.store.list_runs(sid) == []
    assert stopped["cycle"]["next_work"]["requires_owner"] is True
    assert stopped["cycle"]["next_work"]["paused"] is True
    assert "mission.paused" in _event_types(engine, sid)

    resumed = engine.resume(sid)
    assert resumed["success"] is True
    completed = engine.run_continuous(sid)
    assert completed["state"] == "COMPLETED"
    assert len(engine.store.list_runs(sid)) == 2
    assert engine.metrics(sid)["pause_requested"] is False
    assert "mission.resumed" in _event_types(engine, sid)


def test_retry_is_bounded_and_learning_preserves_the_failure(engine):
    engine.runtime.registry.get("primary").invalid = True
    sid = engine.start("Create a document")["session_id"]

    result = engine.run_continuous(sid)
    assert result["state"] == "BLOCKED_NEEDS_OWNER"
    assert result["mission"]["blocker"] == "REPAIR_LIMIT"
    assert result["mission"]["used"]["retries"] == 1
    assert result["cycle"]["learning"]["learning"]["outcome"] == "BLOCKED_NEEDS_OWNER"

    calls_before = len(engine.runtime.registry.get("primary").calls)
    replay = engine.run_continuous(sid)
    assert replay["state"] == "BLOCKED_NEEDS_OWNER"
    assert len(engine.runtime.registry.get("primary").calls) == calls_before
    assert replay["cycle"]["learning"]["idempotent_replay"] is True
    assert replay["cycle"]["next_work"]["idempotent_replay"] is True


def test_explicit_cycle_helpers_are_readable_aliases(engine):
    sid = engine.start("Create a document")["session_id"]
    observed = engine.observe_mission(sid)
    assert observed["state"] == "QUEUED"
    learning = engine.record_learning(sid, observed)
    proposal = engine.next_work(sid, observed)
    assert learning["registered"] is True
    assert proposal["session_id"] == sid
    assert proposal["requires_owner"] is False
    assert _event_types(engine, sid).count("mission.observed") == 1
    assert _event_types(engine, sid).count("mission.learning_recorded") == 1
    assert _event_types(engine, sid).count("mission.next_work_proposed") == 1
