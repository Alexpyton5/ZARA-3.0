"""The reviewer leg of the V1 pipeline (Phase 1 - Organization).

A real, distinct REVIEWER checks the executor's delivery against the task's
acceptance criteria. Approval follows the normal flow; a rejection returns
the work to the executor with corrections (at most 2 review rounds); a
rejection on the last round ends the loop as typed refusal
REVIEW_LOOP_EXHAUSTED without an extra paid reviewer run. Typed refusals
never cost a Run. All of it happens inside the turn that holds the
claim_v1 token.
"""
from __future__ import annotations

import json

import pytest

from core.lab_v1.domain import (
    Availability,
    CostBasis,
    EventType,
    Lifecycle,
    MessageKind,
    ProviderInfo,
    ProviderResult,
    RoleBinding,
    RoleName,
    Session,
    Team,
    TeamMembership,
    AgentProfile,
    new_id,
)
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore


class _ScriptedAdapter:
    """Routes each call by the agent's model and plays a scripted queue."""

    id = "claude_cli"
    label = "scripted"

    def __init__(self, script: dict[str, list[str]]):
        self.script = {model: list(replies) for model, replies in script.items()}
        self.calls: list[tuple[str, str]] = []

    def probe(self):
        return ProviderInfo(id=self.id, label=self.label, adapter=self.id,
                            availability=Availability.AVAILABLE, detail="scripted")

    def identifies_model(self, requested, reported):
        return reported == f"stub-{requested}"

    def complete(self, *, prompt, model, **kwargs):
        self.calls.append((model, prompt))
        queue = self.script.get(model)
        reply = queue.pop(0) if queue else "sem resposta"
        return ProviderResult(ok=True, text=reply, cost_usd=0.001,
                              cost_basis=CostBasis.KNOWN, model_reported=f"stub-{model}")


class _NullMemory:
    def add(self, fact, **kwargs):
        return {"id": "mem_stub"}


def _plan():
    return json.dumps({
        "reply_to_alex": "vou delegar",
        "delegate": {"to_role": "BUILDER", "title": "tarefa-revisada",
                     "instruction": "instrucao-secreta-de-teste",
                     "acceptance": "criterio-aceite-obrigatorio"},
        "decision": None,
    })


def _consolidation():
    return json.dumps({"reply_to_alex": "pronto, entregue", "delegate": None, "decision": None})


def _verdict(verdict, notes="nota", corrections=None):
    return json.dumps({"verdict": verdict, "notes": notes, "corrections": corrections or []})


def _reviewer_team(store):
    team = Team(id=new_id("team"), name="Trio")
    store.save_team(team)
    ceo = AgentProfile(id=new_id("agent"), name="Artemis", provider_id="claude_cli",
                       model="opus", role=RoleName.CEO)
    builder = AgentProfile(id=new_id("agent"), name="Vulcan", provider_id="claude_cli",
                           model="sonnet", role=RoleName.BUILDER)
    reviewer = AgentProfile(id=new_id("agent"), name="Minerva", provider_id="claude_cli",
                            model="glimmer", role=RoleName.REVIEWER)
    for agent in (ceo, builder, reviewer):
        store.save_agent(agent)
        store.save_membership(TeamMembership(id=new_id("mem"), team_id=team.id, agent_id=agent.id))
    for role, agent in ((RoleName.CEO, ceo), (RoleName.BUILDER, builder),
                        (RoleName.REVIEWER, reviewer)):
        store.save_role_binding(RoleBinding(id=new_id("bind"), team_id=team.id,
                                            role=role, agent_id=agent.id))
    return team, ceo, builder, reviewer


def _runtime(store, adapter):
    registry = ProviderRegistry()
    registry.register(adapter)
    return LabRuntime(store=store, registry=registry,
                      memory_adapter=LabMemoryAdapter(store, _NullMemory()))


def _session(store, team):
    session = Session(id=new_id("sess"), team_id=team.id, objective="obj")
    store.save_session(session)
    return session


def _review_messages(store, session_id):
    return [m for m in store.list_messages(session_id) if m.kind is MessageKind.REVIEW]


@pytest.fixture()
def lab(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    return store


def test_approval_follows_the_normal_flow(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1"],
        "glimmer": [_verdict("APPROVED", "atende")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] is None
    assert result["session_state"] == "COMPLETED"
    task = lab.get_task(result["task_id"])
    assert task is not None and task.state.value == "COMPLETED"
    # Exactly one paid run per stage: plan, build, review, consolidation.
    assert [model for model, _ in adapter.calls] == ["opus", "sonnet", "glimmer", "opus"]
    # The reviewer's verdict is a real REVIEW message with the artifact ref.
    reviews = _review_messages(lab, session.id)
    assert len(reviews) == 1
    payload = json.loads(reviews[0].content)
    assert payload["verdict"] == "APPROVED"
    assert payload["artifact_ref"].startswith("artifact:")
    stored = lab.get_artifact(payload["artifact_ref"][len("artifact:"):])
    assert stored is not None and stored.body == "resultado-v1"
    # Review lifecycle events were emitted.
    types = {e.type for e in lab.list_events(session.id, limit=500)}
    assert EventType.REVIEW_REQUESTED in types and EventType.REVIEW_COMPLETED in types
    assert EventType.REPAIR_STARTED not in types


def test_rejection_returns_to_executor_then_approval(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1", "resultado-v2"],
        "glimmer": [_verdict("CHANGES_REQUESTED", "falta X", ["adicione X"]),
                    _verdict("APPROVED", "agora atende")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] is None
    assert result["session_state"] == "COMPLETED"
    task = lab.get_task(result["task_id"])
    assert task is not None and task.result == "resultado-v2"
    # One repair: builder twice, reviewer twice.
    assert [m for m, _ in adapter.calls if m == "sonnet"] == ["sonnet", "sonnet"]
    assert [m for m, _ in adapter.calls if m == "glimmer"] == ["glimmer", "glimmer"]
    # The corrections reached the executor's repair prompt.
    repair_prompt = adapter.calls[3][1]
    assert "adicione X" in repair_prompt
    assert "REJEITOU" in repair_prompt
    # REPAIRING and VERIFYING were visible session states.
    states = [e.payload.get("state") for e in lab.list_events(session.id, limit=500)
              if e.type == EventType.SESSION_STATUS]
    assert "VERIFYING" in states and "REPAIRING" in states
    assert EventType.REPAIR_STARTED in {e.type for e in lab.list_events(session.id, limit=500)}
    verdicts = [json.loads(m.content)["verdict"] for m in _review_messages(lab, session.id)]
    assert verdicts == ["CHANGES_REQUESTED", "APPROVED"]
    # The full four-stage baton chain was written. The baton row per agent
    # holds its LAST stage (CEO ends at MAESTRO), so the chain is read as:
    # CEO -> MAESTRO, builder -> EXECUTOR reworked from REVIEWER, reviewer
    # -> REVIEWER.
    from core.lab_v1.agent_continuity import AgentContinuity
    continuity = AgentContinuity(lab)
    ceo_handoff = continuity.load_handoff_checkpoint(session.id, ceo.id)
    assert ceo_handoff is not None and ceo_handoff.stage == "MAESTRO"
    reviewer_handoff = continuity.load_handoff_checkpoint(session.id, reviewer.id)
    assert reviewer_handoff is not None and reviewer_handoff.stage == "REVIEWER"
    builder_handoff = continuity.load_handoff_checkpoint(session.id, builder.id)
    assert builder_handoff is not None and builder_handoff.stage == "EXECUTOR"
    assert builder_handoff.rework_from == "REVIEWER" and builder_handoff.rework_attempt == 1


def test_third_rejection_exhausts_the_loop_without_an_extra_reviewer_run(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1", "resultado-v2"],
        "glimmer": [_verdict("CHANGES_REQUESTED", "nao", ["a"]),
                    _verdict("CHANGES_REQUESTED", "ainda nao", ["b"])],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] == "REVIEW_LOOP_EXHAUSTED"
    # Exactly _MAX_REVIEW_ROUNDS paid reviewer runs — never a third.
    assert len([m for m, _ in adapter.calls if m == "glimmer"]) == 2
    assert result["session_state"] == "COMPLETED"
    # The exhausted loop escalates to the OWNER and the human sees a SYSTEM note.
    escalations = [m for m in _review_messages(lab, session.id) if m.to_role == "OWNER"]
    assert len(escalations) == 1
    system_notes = [m for m in lab.list_messages(session.id)
                    if m.kind is MessageKind.SYSTEM and "nao aprovou" in m.content]
    assert len(system_notes) == 1
    # The reviewer's notes reached the CEO consolidation prompt.
    assert "ainda nao" in adapter.calls[-1][1]


def test_no_reviewer_bound_is_typed_and_costs_no_run(lab):
    team = Team(id=new_id("team"), name="Dupla")
    lab.save_team(team)
    ceo = AgentProfile(id=new_id("agent"), name="Artemis", provider_id="claude_cli",
                       model="opus", role=RoleName.CEO)
    builder = AgentProfile(id=new_id("agent"), name="Vulcan", provider_id="claude_cli",
                           model="sonnet", role=RoleName.BUILDER)
    for agent in (ceo, builder):
        lab.save_agent(agent)
        lab.save_membership(TeamMembership(id=new_id("mem"), team_id=team.id, agent_id=agent.id))
    for role, agent in ((RoleName.CEO, ceo), (RoleName.BUILDER, builder)):
        lab.save_role_binding(RoleBinding(id=new_id("bind"), team_id=team.id,
                                          role=role, agent_id=agent.id))
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1"],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] == "NO_REVIEWER_BOUND"
    # Plan + build + consolidation only. The reviewer never ran.
    assert [m for m, _ in adapter.calls] == ["opus", "sonnet", "opus"]
    gaps = [g for g in lab.list_capability_gaps(session.id) if g.required == "REVIEWER"]
    assert gaps, "the missing reviewer must be recorded as a capability gap"


def test_reviewer_self_review_is_typed_and_costs_no_run(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    # The CEO occupies the REVIEWER chair too: any review would be self-review.
    lab.save_role_binding(RoleBinding(id=new_id("bind"), team_id=team.id,
                                      role=RoleName.REVIEWER, agent_id=ceo.id))
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1"],
        "glimmer": [_verdict("APPROVED")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] == "REVIEWER_SELF_REVIEW"
    # The reviewer's model was never paid.
    assert all(m != "glimmer" for m, _ in adapter.calls)
    assert _review_messages(lab, session.id) == []


def test_addressed_messages_share_the_turn_correlation_id(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1"],
        "glimmer": [_verdict("APPROVED")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    messages = lab.list_messages(session.id)
    correlations = {m.correlation_id for m in messages}
    assert len(correlations) == 1
    correlation = correlations.pop()
    assert correlation.startswith("v1turn")
    delegate = next(m for m in messages if m.kind is MessageKind.DELEGATE)
    assert delegate.to_agent_id == builder.id and delegate.to_role == "BUILDER"
    review = _review_messages(lab, session.id)[0]
    assert review.to_agent_id == builder.id and review.to_role == "BUILDER"
    assert review.author_agent_id == reviewer.id
    assert review.reply_to is not None


def test_ceo_context_does_not_swallow_delegate_or_review_traffic(lab):
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1"],
        "glimmer": [_verdict("APPROVED")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)
    runtime.submit(session.id, "faca a coisa")

    everything = lab.list_messages(session.id)
    kinds = {m.kind for m in everything}
    assert MessageKind.DELEGATE in kinds and MessageKind.REVIEW in kinds

    ceo_view = lab.list_messages(session.id, limit=200, for_role="CEO")
    ceo_kinds = {m.kind for m in ceo_view}
    assert MessageKind.DELEGATE not in ceo_kinds
    assert MessageKind.REVIEW not in ceo_kinds
    # Legacy-style (NULL-addressed) messages stay visible to the CEO.
    assert any(m.kind is MessageKind.AGENT and m.author == builder.name for m in ceo_view)
    assert any(m.kind is MessageKind.USER for m in ceo_view)


def test_prose_rejection_is_honored_not_swallowed(lab):
    # A reviewer that answered "CHANGES_REQUESTED: ..." in prose is a
    # legitimate rejection: it must drive a repair round, count against
    # _MAX_REVIEW_ROUNDS, escalate the notes on exhaustion and never seal
    # MAESTRO.
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1", "resultado-v2"],
        "glimmer": ["CHANGES_REQUESTED: falta o criterio X",
                    "CHANGES_REQUESTED: ainda falta o criterio Y"],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] == "REVIEW_LOOP_EXHAUSTED"
    # Both prose verdicts drove repair rounds: builder ran twice.
    assert [m for m, _ in adapter.calls if m == "sonnet"] == ["sonnet", "sonnet"]
    # Notes escalated to the CEO's consolidation prompt; MAESTRO never sealed.
    assert "ainda falta o criterio Y" in adapter.calls[-1][1]
    from core.lab_v1.agent_continuity import AgentContinuity
    continuity = AgentContinuity(lab)
    assert continuity.load_handoff_checkpoint(session.id, ceo.id) is None \
        or continuity.load_handoff_checkpoint(session.id, ceo.id).stage != "MAESTRO"
    # The prose verdict was recorded as a gap, never as approval.
    gaps = [g for g in lab.list_capability_gaps(session.id) if g.required == "REVIEWER"]
    assert any("fail-closed" in g.detail for g in gaps)


def test_unknown_verdict_is_fail_closed_as_changes_requested(lab):
    # "MAYBE" is not a valid verdict: fail-closed as CHANGES_REQUESTED —
    # the repair round runs and MAESTRO is never sealed by an unrecognized
    # review.
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1", "resultado-v2"],
        "glimmer": [_verdict("MAYBE", "talvez sirva"),
                    _verdict("APPROVED", "agora atende")],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] is None
    assert result["session_state"] == "COMPLETED"
    # The unknown verdict still consumed a repair round.
    assert [m for m, _ in adapter.calls if m == "sonnet"] == ["sonnet", "sonnet"]
    verdicts = [json.loads(m.content)["verdict"] for m in _review_messages(lab, session.id)]
    assert verdicts == ["CHANGES_REQUESTED", "APPROVED"]
    assert "talvez sirva" in adapter.calls[3][1]
    gaps = [g for g in lab.list_capability_gaps(session.id) if g.required == "REVIEWER"]
    assert any("fail-closed" in g.detail for g in gaps)


def test_oversized_notes_are_truncated_in_ceo_and_repair_prompts(lab):
    # 200k chars of reviewer notes must arrive bounded (<=2000) both in the
    # executor's repair prompt and in the CEO's consolidation prompt.
    huge = "x" * 200_000
    team, ceo, builder, reviewer = _reviewer_team(lab)
    adapter = _ScriptedAdapter({
        "opus": [_plan(), _consolidation()],
        "sonnet": ["resultado-v1", "resultado-v2"],
        "glimmer": [_verdict("CHANGES_REQUESTED", huge, ["corrigir " + "c" * 200_000]),
                    _verdict("CHANGES_REQUESTED", huge, ["corrigir " + "c" * 200_000])],
    })
    runtime = _runtime(lab, adapter)
    session = _session(lab, team)

    result = runtime.submit(session.id, "faca a coisa")

    assert result["delegation_refusal"] == "REVIEW_LOOP_EXHAUSTED"
    repair_prompt = adapter.calls[3][1]
    assert huge not in repair_prompt
    assert "corrigir " + "c" * 2000 not in repair_prompt
    ceo_prompt = adapter.calls[-1][1]
    assert huge not in ceo_prompt
    # The bounded note reached the CEO prompt and the bounded correction the
    # repair prompt.
    assert "x" * 2000 in ceo_prompt
    assert ("corrigir " + "c" * 1991) in repair_prompt
