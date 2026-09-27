"""The durable Core reviewer is a configured worker, never availability proof."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (
    AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName,
    Session, Task, TeamMembership,
)
from core.lab_v1.execution_scope import ExecutionScope
from core.lab_v1.mission_controller import MissionStep
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.source_mission import SourceMission
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


class CodexCatalog(ProviderAdapter):
    id = "codex_cli"
    label = "Isolated Codex fixture"
    controlled_text_only = True
    declared_models = tuple(ModelDescriptor("codex_cli", model, model) for model in (
        "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra",
    ))

    def probe(self):
        return ProviderInfo(self.id, self.label, "fixture", Availability.AVAILABLE)

    def complete(self, **kwargs):
        raise AssertionError("Roster and plan expansion must not invoke a model")


def _runtime(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(CodexCatalog())
    return LabRuntime(store, registry)


def _roster(runtime, team):
    return runtime.store.list_agents(team_id=team.id)


def _simulate_older_roster(runtime, team):
    """Remove only fixture-created Kairos rows from this isolated test DB."""
    reviewer_id = f"core-reviewer:{team.id}"
    with runtime.store._connect() as conn:
        conn.execute("DELETE FROM role_bindings WHERE id=?", (f"core-reviewer-binding:{team.id}",))
        conn.execute("DELETE FROM team_memberships WHERE id=?", (f"core-reviewer-member:{team.id}",))
        conn.execute("DELETE FROM agents WHERE id=?", (reviewer_id,))


def test_reviewer_migration_is_distinct_durable_and_preserves_owner_members(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()
    reviewer = next(a for a in _roster(runtime, team) if a.role is RoleName.REVIEWER)
    _simulate_older_roster(runtime, team)
    custom = AgentProfile("owner-member", "Owner choice", "codex_cli", "gpt-5.6-sol",
                          role=RoleName.MEMBER, capabilities=[])
    runtime.store.save_agent(custom)
    runtime.store.save_membership(TeamMembership("owner-member-link", team.id, custom.id))

    restarted = _runtime(tmp_path)
    restarted.ensure_core_team()
    restarted.ensure_core_team()
    roster = _roster(restarted, team)
    reviewers = [a for a in roster if a.role is RoleName.REVIEWER]
    assert len(reviewers) == 1
    assert reviewers[0].id == reviewer.id
    assert reviewers[0].name == "Kairos"
    assert (reviewers[0].provider_id, reviewers[0].model) == ("codex_cli", "gpt-5.6-terra")
    assert all((reviewers[0].provider_id, reviewers[0].model) != (a.provider_id, a.model)
               for a in roster if a.role in (RoleName.CEO, RoleName.BUILDER))
    assert restarted.store.active_binding(team.id, RoleName.REVIEWER).agent_id == reviewer.id
    assert restarted.store.get_agent(custom.id).capabilities == []
    assert restarted.registry.model_status("codex_cli", "gpt-5.6-terra")["availability"] != "AVAILABLE"


def test_existing_owner_reviewer_is_not_replaced(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()
    _simulate_older_roster(runtime, team)
    owner_reviewer = AgentProfile("owner-reviewer", "Owner reviewer", "codex_cli",
                                  "gpt-5.6-terra", role=RoleName.REVIEWER,
                                  capabilities=["model.text"])
    runtime.store.save_agent(owner_reviewer)
    runtime.store.save_membership(TeamMembership("owner-reviewer-link", team.id,
                                                 owner_reviewer.id))

    runtime.ensure_core_team()
    assert [a.id for a in _roster(runtime, team) if a.role is RoleName.REVIEWER] == [owner_reviewer.id]
    assert runtime.store.active_binding(team.id, RoleName.REVIEWER).agent_id == owner_reviewer.id
    assert runtime.store.get_agent(f"core-reviewer:{team.id}") is None


def _source_plan():
    tasks = []
    for key, role, method in (("patch", "BUILDER", "source_changed"),
                              ("tests", "BUILDER", "pytest"),
                              ("review", "REVIEWER", "independent_review")):
        tasks.append({"id": key, "title": key, "instruction": "Repair and verify one reported bug.",
                      "role": role, "capability": "source." + key, "path": key + ".json",
                      "risk": "LOW", "repair_budget": 1,
                      "depends_on": [] if not tasks else [tasks[-1]["id"]],
                      "acceptance": {"method": method}})
    return {"mission": "Repair one bug", "plan_version": 1, "tasks": tasks}


def test_verified_reviewer_allows_persisted_source_apply_step(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()
    agents = {agent.role: agent for agent in _roster(runtime, team)
              if agent.role in (RoleName.CEO, RoleName.BUILDER, RoleName.REVIEWER)
              and agent.provider_id == "codex_cli"}
    policy = WorkforcePolicy({})
    engine = Autopilot(runtime, root=tmp_path / "missions", policy=policy)
    # A discovered model is not selectable until a real provider result exists.
    assert engine.candidates(team.id, RoleName.REVIEWER) == []
    assert engine._decision(agents[RoleName.REVIEWER], team_id=team.id).code == "RESOURCE_UNAVAILABLE"
    for agent in agents.values():
        runtime.registry.record_result(agent.provider_id, agent.model,
                                       ProviderResult(True, availability=Availability.AVAILABLE))
    assert [a.id for a in engine.candidates(team.id, RoleName.REVIEWER)] == [agents[RoleName.REVIEWER].id]

    sid = "source-reviewer-roster"
    runtime.store.save_session(Session(sid, team.id, "Repair one bug"))
    runtime.store.save_task(Task(sid + ":plan", sid, "Plan", "Write a bounded plan",
                                 agents[RoleName.CEO].id,
                                 assigned_agent_id=agents[RoleName.CEO].id,
                                 acceptance="Three verified tasks",
                                 result=json.dumps(_source_plan())))
    sandbox = tmp_path / "candidate"
    sandbox.mkdir()
    resources = (str(sandbox), *(f"provider:{a.provider_id}/{a.model}" for a in agents.values()))
    engine.controller.plan(
        sid, [MissionStep("plan", sid + ":plan", "INVOKE", capability="model.text",
                          resources=(f"provider:{agents[RoleName.CEO].provider_id}/{agents[RoleName.CEO].model}",))],
        scope=ExecutionScope(resources, ("model.text", "source.apply", "source.tests", "source.build"),
                             authorization_state="POLICY_AUTHORIZED", authorization_ref="autopilot:test"),
        dynamic=True,
    )
    with runtime.store._connect() as conn:
        row = conn.execute("SELECT document FROM mission_controls WHERE session_id=?", (sid,)).fetchone()
        document = json.loads(row[0])
        document["steps"][0]["status"] = "DONE"  # verified planner is this test's precondition
        conn.execute("UPDATE mission_controls SET document=? WHERE session_id=?",
                     (json.dumps(document), sid))
        conn.execute("INSERT INTO mission_autonomy VALUES(?,?)", (sid, json.dumps({
            "planner_id": agents[RoleName.CEO].id,
            "source_work": {"sandbox": str(sandbox)},
        })))
    mission = object.__new__(SourceMission)
    mission.engine, mission.store, mission.sid = engine, runtime.store, sid
    mission.metrics = engine.metrics(sid)
    mission.meta = mission.metrics["source_work"]
    mission.expand()

    persisted = engine.controller.snapshot(sid)
    assert persisted["awaiting_expansion"] is False
    assert any(step["capability"] == "source.apply" for step in persisted["steps"])
    review = next(step for step in persisted["steps"] if step["id"] == "review")
    assert runtime.store.get_task(review["task_id"]).assigned_agent_id == agents[RoleName.REVIEWER].id


def test_interactive_service_bootstraps_reviewer_before_autopilot_start(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()
    _simulate_older_roster(runtime, team)
    observed = []

    def start(*args, **kwargs):
        observed.append(runtime.store.active_binding(team.id, RoleName.REVIEWER).agent_id)
        return {"success": False, "state": "WAITING_RESOURCE",
                "code": "RESOURCE_UNAVAILABLE"}

    service = LabV1Service()
    service._runtime, service._store = runtime, runtime.store
    service._autopilot = SimpleNamespace(runtime=runtime, start=start)
    service._supervisor = SimpleNamespace(policy=WorkforcePolicy.default_document)
    service._promotion_block = lambda: None
    result = asyncio.run(service.start_autopilot("Corrija um problema na ZARA"))
    assert observed == [f"core-reviewer:{team.id}"]
    assert result["code"] == "RESOURCE_UNAVAILABLE"
