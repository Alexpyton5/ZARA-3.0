"""First-use evidence boundary for exact discovered hosted models."""
from __future__ import annotations

import pytest

from core.lab_v1.domain import (
    AgentProfile, Availability, ProviderInfo, ProviderResult, RunState,
    Session, Team,
)
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore


class UnknownUntilCalled(ProviderAdapter):
    label = "First-use fixture"

    def __init__(self, provider_id: str, models: tuple[str, str], *,
                 initial: Availability = Availability.UNKNOWN, succeed: bool = True,
                 reported_model: str | None = None):
        self.id = provider_id
        self.declared_models = tuple(ModelDescriptor(provider_id, model, model) for model in models)
        self.initial = initial
        self.succeed = succeed
        self.reported_model = reported_model
        self.verified = False
        self.calls: list[str] = []

    def probe(self):
        status = Availability.AVAILABLE if self.verified else self.initial
        return ProviderInfo(self.id, self.label, self.id, status)

    def complete(self, *, prompt, model, **kwargs):
        self.calls.append(model)
        if not self.succeed:
            return ProviderResult(False, availability=Availability.ERROR, error="fixture failure")
        self.verified = True
        return ProviderResult(True, text="OK", availability=Availability.AVAILABLE,
                              model_reported=self.reported_model or model)


def setup_runtime(tmp_path, adapter: UnknownUntilCalled, model: str):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    team = Team("team", "First use")
    store.save_team(team)
    session = Session("session", team.id, "First use")
    store.save_session(session)
    agent = AgentProfile("agent", "Worker", adapter.id, model, capabilities=["model.text"])
    store.save_agent(agent)
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(adapter)
    return LabRuntime(store, registry), session, agent


@pytest.mark.parametrize("provider,models", [
    ("opencode", ("opencode/a-free", "opencode/b-free")),
    ("nvidia", ("nvidia/nemotron-a", "nvidia/nemotron-b")),
])
def test_exact_unknown_first_call_proves_only_invoked_model(tmp_path, provider, models):
    adapter = UnknownUntilCalled(provider, models)
    runtime, session, agent = setup_runtime(tmp_path, adapter, models[0])
    assert runtime.registry.model_status(provider, models[0])["availability"] == "UNKNOWN"

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture", timeout_s=3)

    assert result.ok and result.text == "OK"
    assert adapter.calls == [models[0]]
    assert run.state is RunState.COMPLETED and run.model_reported == models[0]
    receipt = runtime.registry.health_snapshot()[f"model:{provider}:{models[0]}"]
    assert receipt["source"] == "provider_result" and receipt["availability"] == "AVAILABLE"
    assert runtime.registry.model_status(provider, models[0])["availability"] == "AVAILABLE"
    assert runtime.registry.model_status(provider, models[1])["availability"] == "DISCOVERED_UNPROVEN"


@pytest.mark.parametrize("provider,models", [
    ("opencode", ("opencode/a-free", "opencode/b-free")),
    ("nvidia", ("nvidia/nemotron-a", "nvidia/nemotron-b")),
])
def test_failed_first_call_does_not_promote_provider_or_model(tmp_path, provider, models):
    adapter = UnknownUntilCalled(provider, models, succeed=False)
    runtime, session, agent = setup_runtime(tmp_path, adapter, models[0])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture")

    assert adapter.calls == [models[0]]
    assert not result.ok and run.state is RunState.FAILED
    assert adapter.probe().availability is Availability.UNKNOWN
    assert runtime.registry.model_status(provider, models[0])["availability"] != "AVAILABLE"
    assert runtime.registry.model_status(provider, models[1])["availability"] != "AVAILABLE"


@pytest.mark.parametrize("provider,models", [
    ("opencode", ("opencode/a-free", "opencode/b-free")),
    ("nvidia", ("nvidia/nemotron-a", "nvidia/nemotron-b")),
])
def test_auth_denial_and_undeclared_id_never_invoke(tmp_path, provider, models):
    auth = UnknownUntilCalled(provider, models, initial=Availability.AUTH_REQUIRED)
    runtime, session, agent = setup_runtime(tmp_path / "auth", auth, models[0])
    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture")
    assert not result.ok and run.state is RunState.FAILED and auth.calls == []
    assert runtime.registry.model_status(provider, models[0])["availability"] != "AVAILABLE"

    unknown = UnknownUntilCalled(provider, models)
    runtime, session, agent = setup_runtime(tmp_path / "unknown", unknown, f"{provider}/not-listed")
    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture")
    assert not result.ok and run.state is RunState.FAILED and unknown.calls == []
    assert runtime.registry.model_status(provider, agent.model)["availability"] != "AVAILABLE"


def test_successful_transport_with_different_model_is_failed_without_promotion(tmp_path):
    models = ("nvidia/nemotron-a", "nvidia/nemotron-b")
    adapter = UnknownUntilCalled("nvidia", models, reported_model=models[1])
    runtime, session, agent = setup_runtime(tmp_path, adapter, models[0])

    run, result = runtime._run_agent(session, agent, "Reply exactly OK", "fixture")

    assert adapter.calls == [models[0]]
    assert not result.ok and result.error == "CODEX_MODEL_MISMATCH"
    assert run.state is RunState.FAILED and run.model_reported == models[1]
    assert runtime.registry.model_status("nvidia", models[0])["availability"] != "AVAILABLE"
