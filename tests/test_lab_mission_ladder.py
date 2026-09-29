"""Integracao FRENTE 1 + FRENTE 2 (FASE 2, 28/09/2026): o turno de missao
percorre a escada do assento em vez de falhar no primeiro provedor.

Quando a cota morre, o app desce um degrau e continua: o motor do agente
primeiro, depois os modelos gratis (NVIDIA NIM), Luna via Codex so em
ultimo caso. Numa escada esgotada, o resultado final e o do PRIMEIRO
degrau, para o failover de papel continuar decidindo sobre o motor do
agente.
"""
from __future__ import annotations

import pytest

from core.lab_v1.domain import (
    AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, RunState,
    Session, Team,
)
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore

# Degraus gratis da escada do CEO (seat_engines.default_ladder_for).
FREE_RUNG = "nvidia/nemotron-3-ultra-550b-a55b"
CHEAP_RUNG = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"


class LadderFixture(ProviderAdapter):
    label = "Ladder fixture"

    def __init__(self, provider_id: str, models: tuple[str, ...], *, succeed: bool = True):
        self.id = provider_id
        self.declared_models = tuple(ModelDescriptor(provider_id, m, m) for m in models)
        self.succeed = succeed
        self.calls: list[str] = []

    def probe(self):
        return ProviderInfo(self.id, self.label, self.id, Availability.AVAILABLE)

    def complete(self, *, prompt, model, **kwargs):
        self.calls.append(model)
        if not self.succeed:
            return ProviderResult(False, availability=Availability.ERROR, error="fixture failure")
        return ProviderResult(True, text="OK", availability=Availability.AVAILABLE,
                              model_reported=model)


def setup_runtime(tmp_path, agent: AgentProfile, adapters: list[LadderFixture]):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    team = Team("team", "Ladder")
    store.save_team(team)
    session = Session("session", team.id, "Ladder")
    store.save_session(session)
    store.save_agent(agent)
    registry = ProviderRegistry(tmp_path / "health.json")
    for adapter in adapters:
        registry.register(adapter)
    return LabRuntime(store, registry), session


def test_ladder_kicks_in_when_agent_provider_fails(tmp_path):
    broken = LadderFixture("broken", ("broken/m1",), succeed=False)
    nvidia = LadderFixture("nvidia", (FREE_RUNG, CHEAP_RUNG), succeed=True)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken, nvidia])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    assert result.ok and result.text == "OK"
    assert run.state is RunState.COMPLETED
    assert run.provider_id == "nvidia" and run.model == FREE_RUNG
    assert broken.calls == ["broken/m1"]
    assert nvidia.calls == [FREE_RUNG]


def test_exhausted_ladder_returns_first_rung_failure(tmp_path):
    broken = LadderFixture("broken", ("broken/m1",), succeed=False)
    agent = AgentProfile("agent", "Worker", "broken", "broken/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [broken])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    assert not result.ok and run.state is RunState.FAILED
    # O erro final e o do motor do agente (primeiro degrau), nao um
    # generico da escada: o failover de papel decide sobre ele.
    assert result.error == "fixture failure"
    assert run.provider_id == "broken" and run.model == "broken/m1"
    assert broken.calls == ["broken/m1"]


def test_unregistered_agent_provider_still_walks_ladder(tmp_path):
    nvidia = LadderFixture("nvidia", (FREE_RUNG, CHEAP_RUNG), succeed=True)
    agent = AgentProfile("agent", "Worker", "ghost", "ghost/m1", role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [nvidia])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    assert result.ok and run.state is RunState.COMPLETED
    assert run.provider_id == "nvidia" and run.model == FREE_RUNG
    assert nvidia.calls == [FREE_RUNG]


def test_archived_agent_never_calls(tmp_path):
    nvidia = LadderFixture("nvidia", (FREE_RUNG, CHEAP_RUNG), succeed=True)
    agent = AgentProfile("agent", "Worker", "nvidia", FREE_RUNG,
                         role=RoleName.CEO, archived=True)
    runtime, session = setup_runtime(tmp_path, agent, [nvidia])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    assert not result.ok and run.state is RunState.FAILED
    assert result.error == "Agente arquivado."
    assert nvidia.calls == []


def test_model_mismatch_is_hard_stop_not_ladder_walk(tmp_path):
    class LyingFixture(LadderFixture):
        def complete(self, *, prompt, model, **kwargs):
            self.calls.append(model)
            return ProviderResult(True, text="OK", availability=Availability.AVAILABLE,
                                  model_reported="nvidia/outro-modelo")

    lying = LyingFixture("nvidia", (FREE_RUNG, CHEAP_RUNG))
    agent = AgentProfile("agent", "Worker", "nvidia", FREE_RUNG, role=RoleName.CEO)
    runtime, session = setup_runtime(tmp_path, agent, [lying])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    # Mismatch nao desce a escada: o turno falha e o failover de papel decide.
    assert not result.ok and result.error == "CODEX_MODEL_MISMATCH"
    assert run.state is RunState.FAILED
    assert lying.calls == [FREE_RUNG]
