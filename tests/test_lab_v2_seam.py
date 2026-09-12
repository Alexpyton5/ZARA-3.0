"""Focused Phase A seam tests. No adapter here touches a real provider."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from core.lab_v1.domain import (
    AgentProfile, Availability, CostBasis, ProviderInfo, ProviderResult,
    RoleBinding, RoleName, Session, Team, TeamMembership, new_id,
)
from core.lab_v1.providers.base import InvocationOptions, ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


class FakeAdapter(ProviderAdapter):
    id = "fake"
    label = "Fake"
    declared_models = (
        ModelDescriptor("fake", "plain", "Plain"),
        ModelDescriptor("fake", "reasoning", "Reasoning", supports_effort=True,
                        effort_levels=("low", "medium", "high")),
    )

    def __init__(self, reply: str = '{"reply_to_alex":"ok"}', wait: threading.Event | None = None):
        self.reply = reply
        self.wait = wait
        self.calls: list[dict] = []
        self.probes = 0
        self.entered = threading.Event()

    def probe(self):
        self.probes += 1
        return ProviderInfo(self.id, self.label, self.id, Availability.AVAILABLE, "fake")

    def complete(self, *, prompt, model, system=None, **kwargs):
        self.calls.append({"prompt": prompt, "model": model, "system": system, "effort": None})
        self.entered.set()
        if self.wait:
            self.wait.wait(5)
        return ProviderResult(True, self.reply, model_reported=model,
                              cost_usd=0, cost_basis=CostBasis.KNOWN)

    def complete_with_options(self, *, prompt, model, system=None, options, **kwargs):
        self.calls.append({"prompt": prompt, "model": model, "system": system,
                           "effort": options.effort})
        return ProviderResult(True, self.reply, model_reported=model,
                              cost_usd=0, cost_basis=CostBasis.KNOWN)


def make_runtime(tmp_path: Path, *, effort: str | None = None, adapter: FakeAdapter | None = None):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    team = Team(new_id("team"), "Team")
    store.save_team(team)
    agent = AgentProfile(new_id("agent"), "Agent", "fake", "reasoning" if effort else "plain",
                         role=RoleName.CEO, instructions="Siga a identidade aprovada.", effort=effort)
    store.save_agent(agent)
    store.save_membership(TeamMembership(new_id("mem"), team.id, agent.id))
    store.save_role_binding(RoleBinding(new_id("bind"), team.id, RoleName.CEO, agent.id))
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(adapter or FakeAdapter())
    return store, team, agent, registry, LabRuntime(store, registry)


def service_for(store, runtime):
    service = LabV1Service()
    service._store = store
    service._runtime = runtime
    return service


def test_snapshot_selection_and_v1_compatibility(tmp_path):
    store, team, _, _, runtime = make_runtime(tmp_path)
    session = Session(new_id("session"), team.id, "one")
    store.save_session(session)
    assert runtime.snapshot(session.id)["session"]["id"] == session.id
    assert runtime.snapshot(team_id=team.id)["session"] is None
    assert runtime.snapshot()["session"] is None


def test_snapshot_rejects_missing_ids_and_team_conflict(tmp_path):
    store, team, _, _, runtime = make_runtime(tmp_path)
    other = Team(new_id("team"), "Other")
    store.save_team(other)
    session = Session(new_id("session"), team.id, "one")
    store.save_session(session)
    for call in (
        lambda: runtime.snapshot("missing"),
        lambda: runtime.snapshot(team_id="missing"),
        lambda: runtime.snapshot(session.id, other.id),
    ):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid room selection was silently accepted")


def test_service_snapshot_and_create_session_contract(tmp_path):
    store, team, _, _, runtime = make_runtime(tmp_path)
    service = service_for(store, runtime)
    created_default = asyncio.run(service.create_session("default"))
    created_selected = asyncio.run(service.create_session("selected", team_id=team.id))
    assert created_default["success"] and created_selected["success"]
    selected_id = created_selected["session"]["id"]
    result = asyncio.run(service.snapshot(selected_id, team.id))
    assert result["success"] and result["session"]["team_id"] == team.id
    assert not asyncio.run(service.snapshot(selected_id, "missing"))["success"]


def test_concurrent_submit_invokes_provider_once(tmp_path):
    release = threading.Event()
    adapter = FakeAdapter(wait=release)
    store, team, _, _, runtime = make_runtime(tmp_path, adapter=adapter)
    session = Session(new_id("session"), team.id, "one")
    store.save_session(session)
    first: list[dict] = []
    thread = threading.Thread(target=lambda: first.append(runtime.submit(session.id, "first")))
    thread.start()
    try:
        assert adapter.entered.wait(3), "First invocation did not start"
        second = runtime.submit(session.id, "second")
    finally:
        release.set()
        thread.join(3)
    assert second["state"] == "BUSY"
    assert len(adapter.calls) == 1


def test_context_instructions_and_session_isolation(tmp_path):
    adapter = FakeAdapter()
    store, team, _, _, runtime = make_runtime(tmp_path, adapter=adapter)
    first = Session(new_id("session"), team.id, "alpha")
    second = Session(new_id("session"), team.id, "beta")
    store.save_session(first)
    store.save_session(second)
    runtime.submit(first.id, "segredo-alpha")
    runtime.submit(second.id, "mensagem-beta")
    latest = adapter.calls[-1]
    assert "Siga a identidade aprovada." in latest["system"]
    assert "mensagem-beta" in latest["prompt"]
    assert "segredo-alpha" not in latest["prompt"]


def test_effort_default_and_supported(tmp_path):
    for effort in (None, "high"):
        adapter = FakeAdapter()
        store, team, _, _, runtime = make_runtime(tmp_path / str(effort), effort=effort, adapter=adapter)
        session = Session(new_id("session"), team.id, "effort")
        store.save_session(session)
        runtime.submit(session.id, "go")
        assert adapter.calls[0]["effort"] == effort


def test_invalid_effort_has_no_call_health_or_failover(tmp_path):
    adapter = FakeAdapter()
    store, team, agent, registry, runtime = make_runtime(tmp_path, effort="ultra", adapter=adapter)
    fallback = AgentProfile(new_id("agent"), "Fallback", "fake", "plain", role=RoleName.MEMBER)
    store.save_agent(fallback)
    store.save_membership(TeamMembership(new_id("mem"), team.id, fallback.id))
    agent.fallback_agent_id = fallback.id
    store.save_agent(agent)
    before = registry.health_snapshot()
    session = Session(new_id("session"), team.id, "effort")
    store.save_session(session)
    runtime.submit(session.id, "go")
    assert adapter.calls == []
    assert registry.health_snapshot() == before
    assert store.active_binding(team.id, RoleName.CEO).agent_id == agent.id
    assert store.list_runs(session.id)[0].error.startswith("INVALID_INVOCATION_OPTIONS:")


def test_catalog_is_local_and_filterable(tmp_path):
    adapter = FakeAdapter()
    registry = ProviderRegistry(tmp_path / "health.json")
    registry.register(adapter)
    models = registry.list_models()
    assert {item["model_id"] for item in models} == {"plain", "reasoning"}
    assert registry.list_models("missing") == []
    assert adapter.probes == 0


def test_adverse_health_survives_probe_and_registry_restart(tmp_path):
    path = tmp_path / "health.json"
    registry = ProviderRegistry(path)
    registry.register(FakeAdapter())
    registry.record_result("fake", "plain", ProviderResult(
        False, availability=Availability.QUOTA_EXHAUSTED,
        error="quota unavailable; token nvapi-abcdefghijklmnopqrstuvwxyz1234567890",
    ))
    reopened = ProviderRegistry(path)
    reopened.register(FakeAdapter())
    info = reopened.list_providers()[0]
    assert info.availability is Availability.QUOTA_EXHAUSTED
    serialized = path.read_text(encoding="utf-8")
    assert "nvapi-" not in serialized and "prompt" not in serialized and "response" not in serialized


def test_reading_absent_health_has_no_write_side_effect(tmp_path):
    path = tmp_path / "missing" / "health.json"
    registry = ProviderRegistry(path)
    assert registry.health_snapshot() == {}
    assert not path.exists()


def test_ipc_handler_forwards_both_room_ids():
    from core.ipc_handlers import IPCHandler, IPCMessage

    captured: dict = {}

    class Service:
        async def snapshot(self, session_id=None, team_id=None):
            captured["args"] = (session_id, team_id)
            return {"success": True, "session": None}

    handler = IPCHandler.__new__(IPCHandler)

    async def ensure(_msg):
        return Service()

    async def respond(request_id, result):
        captured["response"] = (request_id, result)

    handler._ensure_lab_v1 = ensure
    handler.send_response = respond
    handler.send_error = lambda *_args: None
    message = IPCMessage("lab-v1-snapshot", "request-1", {"session_id": "s", "team_id": "t"})
    asyncio.run(handler.handle_lab_v1_snapshot(message))
    assert captured["args"] == ("s", "t")
    assert captured["response"][1]["success"] is True


def test_preload_ipc_and_hook_room_guards_are_present():
    root = Path(__file__).resolve().parents[1]
    preload = (root / "frontend/src/preload.ts").read_text(encoding="utf-8")
    ipc = (root / "core/ipc_handlers.py").read_text(encoding="utf-8")
    hook = (root / "frontend/src/renderer/components/zara-lab-v2/useLabRoom.ts").read_text(encoding="utf-8")
    assert "snapshot: (sessionId?: string, teamId?: string)" in preload
    assert "{ session_id: sessionId, team_id: teamId }" in preload
    assert "svc.snapshot(session_id, team_id)" in ipc
    assert "revision !== generation.current" in hook
    assert "setError(''); setLastSynced(Date.now())" in hook
    assert hook.index("setError(''); setLastSynced(Date.now())") < hook.index("catch (cause)")
