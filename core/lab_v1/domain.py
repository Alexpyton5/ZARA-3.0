"""ZARA LAB REAL V1 — domain contract.

Why this module is separate from `core/lab_coordinator.py`
----------------------------------------------------------
The existing coordinator (LAB-AUTONOMY-001) is a council room: messages,
proposals and legacy tasks in `lab/zara_lab.db`. It works and Alex uses it.
It is NOT a multi-agent runtime: worker roles are fixed strings, and there is
no concept of a role that survives its occupant.

This module adds the missing layer without touching that one. The old DB is
never opened here; V1 owns `lab/zara_lab_v1.db`.

The single invariant that shapes every dataclass below
-------------------------------------------------------
Alex's problem is that today the mission dies with the model. He opens Astra,
Astra runs out of quota, and the whole context has to be carried by hand into
Claude. So:

    PROVIDER  is who serves the tokens          (Anthropic)
    MODEL     is what answers                   (claude-opus-5)
    AGENT     is a named participant            ("Artemis")
    ROLE      is a job inside a team            (CEO)
    TEAM      is who is working together        (ZARA Core)
    SESSION   is the mission                    ("ship the Lab")

A handoff rebinds ROLE -> different AGENT. It does not recreate TEAM or
SESSION, and it does not touch a single Message, Task or Decision. If a future
change makes a role unable to outlive its occupant, that change is wrong.

What is deliberately NOT modelled
----------------------------------
Chain-of-thought. Nothing here has a field for a model's private reasoning.
`Decision.rationale` is a short delivered summary, written for Alex, and it is
the only place close to it. Storing hidden reasoning would be both a product
lie (it is not ours to keep) and a privacy problem.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def new_id(prefix: str) -> str:
    """Short, sortable-enough, human-greppable id. Not a security token."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> float:
    return time.time()


# --------------------------------------------------------------------------
# Availability — normalized by the adapter, never invented by the UI
# --------------------------------------------------------------------------

class Availability(str, Enum):
    """What we actually observed about a provider/agent, and when.

    `UNKNOWN` is a real and frequent answer. It is not a synonym for OFFLINE
    and must never render as "working". A provider we have not probed yet is
    UNKNOWN, not AVAILABLE.
    """

    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DISABLED_BY_OWNER_POLICY = "DISABLED_BY_OWNER_POLICY"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

    @property
    def can_work(self) -> bool:
        return self is Availability.AVAILABLE

    @property
    def is_transient(self) -> bool:
        """Worth retrying later; a failover may be reversed once it clears."""
        return self in (
            Availability.BUSY, Availability.RATE_LIMITED,
            Availability.PROVIDER_ERROR, Availability.ERROR,
        )


class ParticipationState(str, Enum):
    """What an agent is doing *in this session*.

    Kept separate from Availability on purpose: a provider can be AVAILABLE
    while the agent is IDLE. Only an event moves this. There is no timer that
    promotes IDLE to WORKING to make the screen look busy.
    """

    IDLE = "IDLE"
    THINKING = "THINKING"
    WORKING = "WORKING"
    WAITING = "WAITING"
    REVIEWING = "REVIEWING"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    OFFLINE = "OFFLINE"


class Lifecycle(str, Enum):
    PERMANENT = "PERMANENT"
    TEMPORARY = "TEMPORARY"


class RoleName(str, Enum):
    """Roles are a closed set in V1 on purpose.

    An open string here would let the UI invent a "CTO" with no fallback
    policy and no meaning to the runtime. Widen this enum deliberately.
    """

    CEO = "CEO"
    BUILDER = "BUILDER"
    REVIEWER = "REVIEWER"
    RESEARCHER = "RESEARCHER"
    MEMBER = "MEMBER"


class SessionState(str, Enum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WORKING = "WORKING"
    WAITING_USER = "WAITING_USER"
    REPAIRING = "REPAIRING"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    BLOCKED_NEEDS_OWNER = "BLOCKED_NEEDS_OWNER"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class TaskState(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MessageKind(str, Enum):
    USER = "USER"            # Alex typed it
    AGENT = "AGENT"          # a real model produced it in a real run
    ZARA = "ZARA"            # ZARA speaking as the regent
    SYSTEM = "SYSTEM"        # operational note, compact in the UI


class RunState(str, Enum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CostBasis(str, Enum):
    """Never let an unknown cost render as free."""

    KNOWN = "KNOWN"          # provider reported it for this exact call
    ESTIMATED = "ESTIMATED"  # derived from a rate card
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------
# Provider / model / agent
# --------------------------------------------------------------------------

@dataclass
class ProviderInfo:
    """A place tokens can come from, and whether it is usable *right now*.

    `detail` is written for Alex, not for a log. "Falta a chave da Anthropic"
    beats "AUTH_REQUIRED".
    """

    id: str
    label: str
    adapter: str
    availability: Availability = Availability.UNKNOWN
    detail: str = ""
    observed_at: float = field(default_factory=now)
    models: list[str] = field(default_factory=list)
    supports_effort: bool = False
    supports_resume: bool = False
    installed: bool | None = None
    authenticated: bool | None = None
    quota_available: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "adapter": self.adapter,
            "availability": self.availability.value,
            "detail": self.detail,
            "observed_at": self.observed_at,
            "models": list(self.models),
            "supports_effort": self.supports_effort,
            "supports_resume": self.supports_resume,
            "installed": self.installed,
            "authenticated": self.authenticated,
            "quota_available": self.quota_available,
        }


@dataclass
class AgentProfile:
    """A named participant Alex can create, keep, and reuse across sessions.

    `fallback_agent_id` is what makes failover possible without asking a human
    at 3am. It points at another AgentProfile, never at a model name: the
    fallback must itself be a full participant with its own provider and auth.
    """

    id: str
    name: str
    provider_id: str
    model: str
    role: RoleName = RoleName.MEMBER
    instructions: str = ""
    capabilities: list[str] = field(default_factory=list)
    lifecycle: Lifecycle = Lifecycle.PERMANENT
    reports_to: str | None = None
    fallback_agent_id: str | None = None
    effort: str | None = None
    max_turns: int = 1
    archived: bool = False
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider_id": self.provider_id,
            "model": self.model,
            "role": self.role.value,
            "instructions": self.instructions,
            "capabilities": list(self.capabilities),
            "lifecycle": self.lifecycle.value,
            "reports_to": self.reports_to,
            "fallback_agent_id": self.fallback_agent_id,
            "effort": self.effort,
            "max_turns": self.max_turns,
            "archived": self.archived,
            "created_at": self.created_at,
        }


@dataclass
class Team:
    id: str
    name: str
    objective: str = ""
    created_at: float = field(default_factory=now)
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "objective": self.objective,
            "created_at": self.created_at, "archived": self.archived,
        }


@dataclass
class RoleBinding:
    """THE pivot of this whole design: which agent currently holds which role.

    `designation` carries "ACTING" while a stand-in holds the post. Opus is
    Acting CEO today because Astra is out of quota; when Astra returns this
    row changes and nothing else does.

    History is kept by never deleting: a binding is closed with `unbound_at`
    and a new row opens. That is what lets the Lab answer "who was CEO when
    this decision was taken?" after three handoffs.
    """

    id: str
    team_id: str
    role: RoleName
    agent_id: str
    designation: str = "PERMANENT"   # PERMANENT | ACTING
    bound_at: float = field(default_factory=now)
    unbound_at: float | None = None
    reason: str = ""

    @property
    def active(self) -> bool:
        return self.unbound_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "team_id": self.team_id, "role": self.role.value,
            "agent_id": self.agent_id, "designation": self.designation,
            "bound_at": self.bound_at, "unbound_at": self.unbound_at,
            "reason": self.reason, "active": self.active,
        }


@dataclass
class TeamMembership:
    id: str
    team_id: str
    agent_id: str
    joined_at: float = field(default_factory=now)
    left_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "team_id": self.team_id, "agent_id": self.agent_id,
            "joined_at": self.joined_at, "left_at": self.left_at,
        }


# --------------------------------------------------------------------------
# Mission: session, thread, message
# --------------------------------------------------------------------------

@dataclass
class Session:
    """One mission. Survives restarts, model swaps and CEO handoffs."""

    id: str
    team_id: str
    objective: str
    state: SessionState = SessionState.QUEUED
    acceptance_criteria: list[str] = field(default_factory=list)
    max_delegations: int = 4
    max_cost_usd: float | None = None
    revision: int = 0
    created_at: float = field(default_factory=now)
    updated_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "team_id": self.team_id, "objective": self.objective,
            "state": self.state.value, "acceptance_criteria": list(self.acceptance_criteria),
            "max_delegations": self.max_delegations, "max_cost_usd": self.max_cost_usd,
            "revision": self.revision, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Message:
    """A delivered message. Never a draft, never a thought.

    `author_agent_id` is filled by the backend from the run that produced it.
    The renderer's opinion about who wrote something is not trusted.
    """

    id: str
    session_id: str
    kind: MessageKind
    author: str                     # display name: "Alex", "ZARA", agent name
    content: str
    author_agent_id: str | None = None
    run_id: str | None = None
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "kind": self.kind.value,
            "author": self.author, "content": self.content,
            "author_agent_id": self.author_agent_id, "run_id": self.run_id,
            "created_at": self.created_at,
        }


@dataclass
class Run:
    """One real invocation of one real model. The unit of truth for cost.

    If there is no Run row, no model was called. This is what stops the UI
    from ever showing "working..." over nothing: `ParticipationState.WORKING`
    is only legal while a Run is STARTED.
    """

    id: str
    session_id: str
    agent_id: str
    provider_id: str
    model: str
    model_reported: str | None = None   # provider's own canonical id; proof this run was real
    state: RunState = RunState.STARTED
    task_id: str | None = None
    provider_session_id: str | None = None   # lets the adapter resume its own thread
    cost_usd: float | None = None
    cost_basis: CostBasis = CostBasis.UNKNOWN
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    started_at: float = field(default_factory=now)
    ended_at: float | None = None
    effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "agent_id": self.agent_id,
            "provider_id": self.provider_id, "model": self.model,
            "model_reported": self.model_reported, "state": self.state.value,
            "task_id": self.task_id, "provider_session_id": self.provider_session_id,
            "cost_usd": self.cost_usd, "cost_basis": self.cost_basis.value,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms, "error": self.error,
            "started_at": self.started_at, "ended_at": self.ended_at, "effort": self.effort,
        }


# --------------------------------------------------------------------------
# Delegation
# --------------------------------------------------------------------------

@dataclass
class Task:
    """Work the CEO handed to somebody else. Bounded on purpose.

    `max_turns` and `budget_usd` exist so two agents cannot talk to each other
    forever burning Alex's quota while he sleeps. Hitting a limit is a real
    outcome (FAILED with a reason), never a silent stop.
    """

    id: str
    session_id: str
    title: str
    instruction: str
    created_by_agent_id: str
    assigned_agent_id: str | None = None
    state: TaskState = TaskState.CREATED
    acceptance: str = ""
    result: str | None = None
    max_turns: int = 1
    budget_usd: float | None = None
    created_at: float = field(default_factory=now)
    updated_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "title": self.title,
            "instruction": self.instruction, "created_by_agent_id": self.created_by_agent_id,
            "assigned_agent_id": self.assigned_agent_id, "state": self.state.value,
            "acceptance": self.acceptance, "result": self.result,
            "max_turns": self.max_turns, "budget_usd": self.budget_usd,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class ContextPacket:
    """What a worker is told. Deliberately small.

    Handing a worker the whole memory would be expensive, slow, and a privacy
    leak. It gets the objective, its own task, the constraints, and only the
    decisions that already bind it.
    """

    objective: str
    task_title: str
    task_instruction: str
    acceptance: str = ""
    constraints: list[str] = field(default_factory=list)
    relevant_decisions: list[str] = field(default_factory=list)
    relevant_memory: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [
            f"Objetivo da missao: {self.objective}",
            "",
            f"Sua tarefa: {self.task_title}",
            self.task_instruction,
        ]
        if self.acceptance:
            parts += ["", f"Criterio de aceite: {self.acceptance}"]
        if self.constraints:
            parts += ["", "Restricoes:"] + [f"- {c}" for c in self.constraints]
        if self.relevant_decisions:
            parts += ["", "Decisoes ja tomadas:"] + [f"- {d}" for d in self.relevant_decisions]
        if self.relevant_memory:
            parts += ["", "Contexto da memoria da ZARA:"] + [f"- {m}" for m in self.relevant_memory]
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective, "task_title": self.task_title,
            "task_instruction": self.task_instruction, "acceptance": self.acceptance,
            "constraints": list(self.constraints),
            "relevant_decisions": list(self.relevant_decisions),
            "relevant_memory": list(self.relevant_memory),
        }


@dataclass
class Handoff:
    """Proof that a role changed hands without the mission restarting.

    Written for both failover (CEO went down) and promotion (Astra came back).
    Same row shape either way, because to the mission they are the same event.
    """

    id: str
    session_id: str
    team_id: str
    role: RoleName
    from_agent_id: str | None
    to_agent_id: str
    reason: str
    context_summary: str = ""
    unfinished_task_ids: list[str] = field(default_factory=list)
    outcome: str = "COMPLETED"
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "team_id": self.team_id,
            "role": self.role.value, "from_agent_id": self.from_agent_id,
            "to_agent_id": self.to_agent_id, "reason": self.reason,
            "context_summary": self.context_summary,
            "unfinished_task_ids": list(self.unfinished_task_ids),
            "outcome": self.outcome, "created_at": self.created_at,
        }


# --------------------------------------------------------------------------
# Outcomes ZARA cares about
# --------------------------------------------------------------------------

@dataclass
class Decision:
    """A conclusion worth keeping. `rationale` is a delivered summary only."""

    id: str
    session_id: str
    author_agent_id: str | None
    statement: str
    rationale: str = ""
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id,
            "author_agent_id": self.author_agent_id, "statement": self.statement,
            "rationale": self.rationale, "created_at": self.created_at,
        }


@dataclass
class Artifact:
    id: str
    session_id: str
    task_id: str | None
    kind: str
    title: str
    body: str = ""
    path: str | None = None
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "task_id": self.task_id,
            "kind": self.kind, "title": self.title, "body": self.body,
            "path": self.path, "created_at": self.created_at,
        }


@dataclass
class CapabilityGap:
    """The mission needs something ZARA does not have.

    V1 only records it. Deliberately no autonomous reaction: a system that
    notices a gap and starts fixing it unattended is a much bigger decision
    than this phase is allowed to make.
    """

    id: str
    session_id: str | None
    required: str
    available: bool = False
    detail: str = ""
    created_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "session_id": self.session_id, "required": self.required,
            "available": self.available, "detail": self.detail,
            "created_at": self.created_at,
        }


@dataclass
class LabEvent:
    """Ordered operational envelope. `seq` is assigned by the store.

    This is what lets the UI rebuild itself after a restart without asking
    every table what happened, and what ZARA observes to decide what deserves
    to become memory.
    """

    id: str
    seq: int
    type: str
    session_id: str | None
    entity_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "seq": self.seq, "type": self.type,
            "session_id": self.session_id, "entity_id": self.entity_id,
            "payload": dict(self.payload), "occurred_at": self.occurred_at,
        }


class EventType:
    """String constants, not an enum: the store must accept an event type
    added by a later phase without a migration."""

    TEAM_CREATED = "team.created"
    AGENT_CREATED = "agent.created"
    AGENT_ARCHIVED = "agent.archived"
    ROLE_BOUND = "role.bound"
    SESSION_STARTED = "session.started"
    SESSION_STATUS = "session.status_changed"
    SESSION_RESUMED = "session.resumed"
    MESSAGE_CREATED = "message.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    DELEGATION_CREATED = "delegation.created"
    AGENT_STATUS = "agent.status_changed"
    HANDOFF_STARTED = "handoff.started"
    HANDOFF_COMPLETED = "handoff.completed"
    DECISION_RECORDED = "decision.recorded"
    ARTIFACT_CREATED = "artifact.created"
    CAPABILITY_GAP = "capability_gap.detected"
    MEMORY_LINKED = "memory.linked"


# --------------------------------------------------------------------------
# Adapter result — the only thing a provider is allowed to return
# --------------------------------------------------------------------------

@dataclass
class ProviderResult:
    """Normalized outcome of one real model call.

    `availability` is how the adapter classified whatever went wrong. The
    runtime reads only this field to decide failover; it never parses a
    provider's raw error text, because that string changes without notice.
    """

    ok: bool
    text: str = ""
    availability: Availability = Availability.AVAILABLE
    error: str | None = None
    provider_session_id: str | None = None
    cost_usd: float | None = None
    cost_basis: CostBasis = CostBasis.UNKNOWN
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    model_reported: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "text": self.text, "availability": self.availability.value,
            "error": self.error, "provider_session_id": self.provider_session_id,
            "cost_usd": self.cost_usd, "cost_basis": self.cost_basis.value,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms, "model_reported": self.model_reported,
        }
