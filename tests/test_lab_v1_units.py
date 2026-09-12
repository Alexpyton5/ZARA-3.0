"""Unit tests for the ZARA Lab V1 foundation: domain, store and providers.

These cover the invariants that a future change is most likely to break by
accident. The end-to-end multi-agent proof lives in
`tools/lab_v1_acceptance.py`, which spends real money; nothing here calls a
model or touches the network.
"""
from __future__ import annotations

import shutil

import pytest

from core.lab_v1.domain import (
    AgentProfile,
    Availability,
    CostBasis,
    Decision,
    LabEvent,
    Lifecycle,
    Message,
    MessageKind,
    RoleBinding,
    RoleName,
    Run,
    RunState,
    Session,
    Task,
    TaskState,
    Team,
    TeamMembership,
    new_id,
)
from core.lab_v1.providers.registry import default_registry
from core.lab_v1.store import LabStore


@pytest.fixture()
def store(tmp_path):
    s = LabStore(tmp_path / "lab_v1.db")
    s.initialize()
    return s


@pytest.fixture()
def team_with_two_agents(store):
    team = Team(id=new_id("team"), name="ZARA Core")
    store.save_team(team)
    ceo = AgentProfile(id=new_id("agent"), name="Artemis", provider_id="claude_cli",
                       model="opus", role=RoleName.CEO, lifecycle=Lifecycle.PERMANENT)
    builder = AgentProfile(id=new_id("agent"), name="Vulcan", provider_id="claude_cli",
                           model="sonnet", role=RoleName.BUILDER)
    ceo.fallback_agent_id = builder.id
    store.save_agent(ceo)
    store.save_agent(builder)
    for agent in (ceo, builder):
        store.save_membership(TeamMembership(id=new_id("mem"), team_id=team.id, agent_id=agent.id))
    return team, ceo, builder


# --------------------------------------------------------------------------
# The invariant the whole feature exists for
# --------------------------------------------------------------------------

def test_role_survives_changing_its_occupant(store, team_with_two_agents):
    """Rebinding CEO must not disturb the team, the session or the history.

    This is the product promise: when Astra runs out of quota the mission does
    not restart, it changes hands.
    """
    team, ceo, builder = team_with_two_agents
    session = Session(id=new_id("sess"), team_id=team.id, objective="entregar o Lab")
    store.save_session(session)
    store.add_message(Message(id=new_id("msg"), session_id=session.id,
                              kind=MessageKind.USER, author="Alex", content="comece"))

    first = RoleBinding(id=new_id("bind"), team_id=team.id, role=RoleName.CEO,
                        agent_id=ceo.id, designation="ACTING")
    store.save_role_binding(first)

    store.close_role_binding(first.id, unbound_at=1.0)
    second = RoleBinding(id=new_id("bind"), team_id=team.id, role=RoleName.CEO,
                         agent_id=builder.id, designation="ACTING",
                         reason="CEO indisponivel")
    store.save_role_binding(second)

    active = store.active_binding(team.id, RoleName.CEO)
    assert active is not None and active.agent_id == builder.id

    # Nothing about the mission moved.
    assert store.get_team(team.id) is not None
    assert store.get_session(session.id) is not None
    assert len(store.list_messages(session.id)) == 1
    # And the history of who held the post is still answerable.
    ceo_bindings = [b for b in store.list_bindings(team.id) if b.role is RoleName.CEO]
    assert len(ceo_bindings) == 2
    assert sum(1 for b in ceo_bindings if b.active) == 1


def test_only_one_binding_per_role_is_active(store, team_with_two_agents):
    team, ceo, builder = team_with_two_agents
    a = RoleBinding(id=new_id("bind"), team_id=team.id, role=RoleName.CEO, agent_id=ceo.id)
    store.save_role_binding(a)
    store.close_role_binding(a.id, unbound_at=1.0)
    assert store.active_binding(team.id, RoleName.CEO) is None


# --------------------------------------------------------------------------
# Persistence: the mission must survive the process dying
# --------------------------------------------------------------------------

def test_mission_survives_a_new_store_instance(tmp_path, store, team_with_two_agents):
    team, ceo, builder = team_with_two_agents
    session = Session(id=new_id("sess"), team_id=team.id, objective="sobreviver")
    store.save_session(session)
    task = Task(id=new_id("task"), session_id=session.id, title="justificar",
                instruction="explique", created_by_agent_id=ceo.id,
                assigned_agent_id=builder.id, state=TaskState.COMPLETED, result="pronto")
    store.save_task(task)
    store.save_run(Run(id=new_id("run"), session_id=session.id, agent_id=ceo.id,
                       provider_id="claude_cli", model="opus", state=RunState.COMPLETED,
                       cost_usd=0.02, cost_basis=CostBasis.KNOWN))

    reopened = LabStore(store.db_path)
    reopened.initialize()

    recovered = reopened.get_task(task.id)
    assert recovered is not None
    assert recovered.state is TaskState.COMPLETED
    assert recovered.result == "pronto"
    assert recovered.assigned_agent_id != recovered.created_by_agent_id
    assert reopened.total_cost(session.id) == pytest.approx(0.02)


def test_message_order_is_insertion_order_within_one_tick(store, team_with_two_agents):
    """Two messages saved in the same clock tick must not swap places.

    The old Lab coordinator hit exactly this and fixed it the same way; a
    regression here reorders a conversation in front of Alex.
    """
    team, _, _ = team_with_two_agents
    session = Session(id=new_id("sess"), team_id=team.id, objective="ordem")
    store.save_session(session)
    stamp = 1700000000.0
    for i in range(5):
        store.add_message(Message(id=new_id("msg"), session_id=session.id,
                                  kind=MessageKind.AGENT, author="Vulcan",
                                  content=str(i), created_at=stamp))
    assert [m.content for m in store.list_messages(session.id)] == ["0", "1", "2", "3", "4"]


def test_enums_and_lists_rehydrate_as_real_types(store, team_with_two_agents):
    team, ceo, _ = team_with_two_agents
    session = Session(id=new_id("sess"), team_id=team.id, objective="tipos",
                      acceptance_criteria=["a", "b"])
    store.save_session(session)
    got = store.get_session(session.id)
    assert isinstance(got.state, __import__("core.lab_v1.domain", fromlist=["SessionState"]).SessionState)
    assert got.acceptance_criteria == ["a", "b"]
    agent = store.get_agent(ceo.id)
    assert isinstance(agent.role, RoleName)
    assert isinstance(agent.lifecycle, Lifecycle)


def test_events_get_monotonic_sequence_and_filter(store, team_with_two_agents):
    team, _, _ = team_with_two_agents
    session = Session(id=new_id("sess"), team_id=team.id, objective="eventos")
    store.save_session(session)
    seqs = [
        store.append_event(LabEvent(id=new_id("ev"), seq=0, type=f"t.{i}",
                                    session_id=session.id, entity_id=None)).seq
        for i in range(4)
    ]
    assert seqs == sorted(seqs) and len(set(seqs)) == 4
    later = store.list_events(session_id=session.id, after_seq=seqs[1])
    assert all(e.seq > seqs[1] for e in later)


# --------------------------------------------------------------------------
# Memory promotion must not double-write
# --------------------------------------------------------------------------

def test_memory_outbox_blocks_a_replay(store):
    assert store.memory_outbox_seen("ev_1") is False
    store.memory_outbox_record("ev_1", "mem_abc")
    assert store.memory_outbox_seen("ev_1") is True


# --------------------------------------------------------------------------
# Honesty of the provider matrix
# --------------------------------------------------------------------------

def test_providers_report_a_real_availability_never_a_guess(tmp_path, monkeypatch):
    """Every registered provider must answer with a real state, and a provider
    that is merely registered must never come back AVAILABLE."""
    from core.lab_v1.providers import codex_app_server, registry
    monkeypatch.setattr(codex_app_server, 'data_dir', lambda: tmp_path)
    monkeypatch.setattr(registry.AnthropicApiAdapter, '_has_configured_key', lambda self: False)
    monkeypatch.setattr(registry, 'data_dir', lambda: tmp_path)
    infos = {p.id: p for p in default_registry().list_providers()}
    assert {"claude_cli", "codex_cli", "anthropic_api"} <= set(infos)
    for info in infos.values():
        assert isinstance(info.availability, Availability)
        assert info.detail, f"{info.id} reported no explanation for its state"

    # Empty isolated account cache cannot establish Codex authentication.
    assert not infos["codex_cli"].availability.can_work
    assert infos["anthropic_api"].availability is Availability.DISABLED_BY_OWNER_POLICY
    # claude_cli was re-authorized by Alex on 2026-09-10, so it is no longer
    # DISABLED_BY_OWNER_POLICY. It must still answer from a real local fact:
    # AVAILABLE only where the `claude` binary actually exists, OFFLINE where it
    # does not. Never a guess, and never AVAILABLE just because it is registered.
    claude = infos["claude_cli"]
    assert claude.availability is not Availability.DISABLED_BY_OWNER_POLICY
    assert claude.availability is (
        Availability.AVAILABLE if shutil.which("claude") else Availability.OFFLINE
    )
    assert claude.installed is bool(shutil.which("claude"))


def test_unknown_is_not_treated_as_usable():
    assert not Availability.UNKNOWN.can_work
    assert not Availability.QUOTA_EXHAUSTED.can_work
    assert Availability.AVAILABLE.can_work
    # A transient outage is worth retrying; an auth problem is not.
    assert Availability.RATE_LIMITED.is_transient
    assert not Availability.AUTH_REQUIRED.is_transient


def test_cost_of_unknown_origin_is_never_reported_as_free():
    run = Run(id=new_id("run"), session_id="s", agent_id="a",
              provider_id="claude_cli", model="opus")
    assert run.cost_usd is None
    assert run.cost_basis is CostBasis.UNKNOWN


# --------------------------------------------------------------------------
# Nothing stored may carry private reasoning
# --------------------------------------------------------------------------

def test_no_persisted_shape_has_a_chain_of_thought_field():
    banned = {"chain_of_thought", "thinking", "reasoning_trace", "scratchpad", "internal_reasoning"}
    samples = [
        Message(id="m", session_id="s", kind=MessageKind.AGENT, author="x", content="y"),
        Run(id="r", session_id="s", agent_id="a", provider_id="p", model="m"),
        Decision(id="d", session_id="s", author_agent_id="a", statement="x"),
        Task(id="t", session_id="s", title="t", instruction="i", created_by_agent_id="a"),
    ]
    for sample in samples:
        assert not (set(sample.to_dict()) & banned), f"{type(sample).__name__} would persist reasoning"


# --------------------------------------------------------------------------
# Self-delegation must be refused, not billed twice
# --------------------------------------------------------------------------

class _StubAdapter:
    """Counts real calls so a test can prove none were wasted."""

    id = "claude_cli"
    label = "stub"

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[str] = []

    def probe(self):
        from core.lab_v1.domain import ProviderInfo
        return ProviderInfo(id=self.id, label=self.label, adapter=self.id,
                            availability=Availability.AVAILABLE, detail="stub")

    def complete(self, *, prompt, model, **kwargs):
        from core.lab_v1.domain import CostBasis, ProviderResult
        self.calls.append(model)
        return ProviderResult(ok=True, text=self.reply, cost_usd=0.001,
                              cost_basis=CostBasis.KNOWN, model_reported=f"stub-{model}")


def _runtime_with(store, adapter):
    from core.lab_v1.memory_adapter import LabMemoryAdapter
    from core.lab_v1.providers.registry import ProviderRegistry
    from core.lab_v1.runtime import LabRuntime
    reg = ProviderRegistry()
    reg.register(adapter)
    return LabRuntime(store=store, registry=reg, memory_adapter=LabMemoryAdapter(store, _NullMemory()))


class _NullMemory:
    """Keeps promotion out of any real memory file during unit tests."""

    def add(self, fact, **kwargs):
        return {"id": "mem_stub"}


def test_self_delegation_is_refused_and_not_billed_twice(store):
    """One agent holding two roles is legitimate; delegating to itself is not.

    A second paid call would still produce a second Run with a real cost and a
    real model id — the exact shape the multi-agent gates look for. So it must
    be refused, in a typed way, without spending anything.
    """
    import json as _json

    from core.lab_v1.domain import RoleBinding
    from core.lab_v1.domain import Session as _S
    team = Team(id=new_id("team"), name="Solo")
    store.save_team(team)
    solo = AgentProfile(id=new_id("agent"), name="Solo", provider_id="claude_cli",
                        model="opus", role=RoleName.CEO)
    store.save_agent(solo)
    store.save_membership(TeamMembership(id=new_id("mem"), team_id=team.id, agent_id=solo.id))
    # The same agent holds BOTH chairs.
    for role in (RoleName.CEO, RoleName.BUILDER):
        store.save_role_binding(RoleBinding(id=new_id("bind"), team_id=team.id,
                                            role=role, agent_id=solo.id))

    adapter = _StubAdapter(_json.dumps({
        "reply_to_alex": "vou delegar",
        "delegate": {"to_role": "BUILDER", "title": "t", "instruction": "i", "acceptance": "a"},
        "decision": None,
    }))
    runtime = _runtime_with(store, adapter)
    session = _S(id=new_id("sess"), team_id=team.id, objective="obj")
    store.save_session(session)

    result = runtime.submit(session.id, "faca algo")

    assert result["delegation_refusal"] == "SELF_DELEGATION"
    assert result["task_id"] is None, "a refused delegation must not create a task"
    assert store.list_tasks(session.id) == [], "no task may be persisted"
    # One CEO turn only. A second call would have been the fake "delegation".
    assert len(adapter.calls) == 1, f"expected 1 paid call, got {adapter.calls}"


def test_self_delegation_offers_another_agent_when_one_exists(store):
    import json as _json

    from core.lab_v1.domain import RoleBinding
    from core.lab_v1.domain import Session as _S
    team = Team(id=new_id("team"), name="Duo")
    store.save_team(team)
    solo = AgentProfile(id=new_id("agent"), name="Solo", provider_id="claude_cli",
                        model="opus", role=RoleName.CEO)
    spare = AgentProfile(id=new_id("agent"), name="Spare", provider_id="claude_cli",
                         model="sonnet", role=RoleName.RESEARCHER)
    for a in (solo, spare):
        store.save_agent(a)
        store.save_membership(TeamMembership(id=new_id("mem"), team_id=team.id, agent_id=a.id))
    for role in (RoleName.CEO, RoleName.BUILDER):
        store.save_role_binding(RoleBinding(id=new_id("bind"), team_id=team.id,
                                            role=role, agent_id=solo.id))

    adapter = _StubAdapter(_json.dumps({
        "reply_to_alex": "delegando",
        "delegate": {"to_role": "BUILDER", "title": "t", "instruction": "i", "acceptance": ""},
        "decision": None,
    }))
    runtime = _runtime_with(store, adapter)
    session = _S(id=new_id("sess"), team_id=team.id, objective="obj")
    store.save_session(session)

    result = runtime.submit(session.id, "faca algo")
    assert result["delegation_refusal"] == "SELF_DELEGATION"
    # The caller must be able to route around it rather than just be told no.
    assert spare.id in result["delegation_candidate_agent_ids"]
