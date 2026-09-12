"""Phase C multi-agent contract tests; adapters are deterministic and offline."""
from __future__ import annotations

import json

from core.lab_v1.domain import (
    AgentProfile, Availability, CostBasis, EventType, ProviderInfo, ProviderResult,
    RoleBinding, RoleName, Session, TaskState, Team, TeamMembership, new_id,
)
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore


class TwoAgentNvidiaFake:
    id = "nvidia"
    label = "NVIDIA fake"

    def __init__(self):
        self.calls = []

    def probe(self):
        return ProviderInfo(self.id, self.label, "fake", Availability.AVAILABLE, "isolated fake")

    def complete(self, *, prompt, model, system=None, **_kwargs):
        self.calls.append({"prompt": prompt, "model": model, "system": system})
        number = len(self.calls)
        if number == 1:
            text = json.dumps({
                "reply_to_alex": "Vou delegar a elaboração.",
                "delegate": {
                    "to_role": "BUILDER", "title": "Validar JSON em três passos",
                    "instruction": "Entregue exatamente três passos curtos para validar um arquivo JSON.",
                    "acceptance": "Três passos objetivos e tecnicamente corretos.",
                },
                "decision": None,
            })
        elif number == 2:
            text = "1. Leia o arquivo. 2. Faça o parse JSON. 3. Valide o schema esperado."
        else:
            text = json.dumps({"reply_to_alex": "Os três passos foram entregues.", "delegate": None, "decision": None})
        return ProviderResult(
            True, text=text, model_reported=model, provider_session_id=f"request-{number}",
            input_tokens=10, output_tokens=8, duration_ms=5,
            cost_usd=None, cost_basis=CostBasis.UNKNOWN,
        )


def isolated_world(tmp_path):
    store = LabStore(tmp_path / "phase-c.db")
    store.initialize()
    team = Team(new_id("team"), "NVIDIA Phase C")
    lead = AgentProfile(new_id("agent"), "Aegis", "nvidia", "mistralai/mistral-nemotron",
                        role=RoleName.CEO)
    worker = AgentProfile(new_id("agent"), "Forge", "nvidia", "mistralai/mistral-nemotron",
                          role=RoleName.BUILDER)
    store.save_team(team)
    for agent in (lead, worker):
        store.save_agent(agent)
        store.save_membership(TeamMembership(new_id("mem"), team.id, agent.id))
    store.save_role_binding(RoleBinding(new_id("bind"), team.id, RoleName.CEO, lead.id))
    store.save_role_binding(RoleBinding(new_id("bind"), team.id, RoleName.BUILDER, worker.id))
    adapter = TwoAgentNvidiaFake()
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(adapter)
    runtime = LabRuntime(store, registry, memory_adapter=None)
    return store, team, lead, worker, adapter, runtime


def test_two_distinct_agents_and_role_bindings(tmp_path):
    store, team, lead, worker, _, _ = isolated_world(tmp_path)
    assert lead.id != worker.id
    assert store.active_binding(team.id, RoleName.CEO).agent_id == lead.id
    assert store.active_binding(team.id, RoleName.BUILDER).agent_id == worker.id


def test_real_delegation_contract_stays_in_one_session(tmp_path):
    store, team, lead, worker, adapter, runtime = isolated_world(tmp_path)
    session = Session(new_id("session"), team.id, "Delegue três passos para validar JSON.")
    store.save_session(session)
    result = runtime.submit(session.id, "Delegue ao Worker e consolide o resultado.")

    tasks = store.list_tasks(session.id)
    runs = store.list_runs(session.id)
    assert result["task_id"] == tasks[0].id
    assert len(tasks) == 1 and tasks[0].state is TaskState.COMPLETED
    assert tasks[0].created_by_agent_id == lead.id
    assert tasks[0].assigned_agent_id == worker.id
    assert tasks[0].result
    assert len(adapter.calls) == len(runs) == 3
    assert {run.session_id for run in runs} == {session.id}
    assert [run.agent_id for run in runs] == [lead.id, worker.id, lead.id]


def test_run_provenance_and_zara_observation_are_persisted(tmp_path):
    store, team, _, _, _, runtime = isolated_world(tmp_path)
    session = Session(new_id("session"), team.id, "Delegue três passos para validar JSON.")
    store.save_session(session)
    runtime.submit(session.id, "Execute a delegação.")
    runs = store.list_runs(session.id)
    assert all(run.provider_id == "nvidia" for run in runs)
    assert all(run.model_reported == run.model for run in runs)
    assert all(run.provider_session_id and run.input_tokens == 10 and run.output_tokens == 8 for run in runs)
    events = store.list_events(session.id, limit=500)
    assert sum(event.type == EventType.DELEGATION_CREATED for event in events) == 1
    assert sum(event.type == EventType.TASK_COMPLETED for event in events) == 1
    zara = [message for message in store.list_messages(session.id) if message.author == "ZARA"]
    assert len(zara) == 1 and "concluido" in zara[0].content.lower()


def test_storage_and_memory_are_isolated(tmp_path):
    store, team, _, _, _, runtime = isolated_world(tmp_path)
    session = Session(new_id("session"), team.id, "Teste técnico isolado.")
    store.save_session(session)
    runtime.submit(session.id, "Execute a delegação.")
    assert store.db_path.is_relative_to(tmp_path)
    assert not any(path.name != "phase-c.db" and "memory" in path.name for path in tmp_path.rglob("*"))
