"""Durable, provider-independent continuity for Lab agents.

This module stores only caller-supplied operational state: a cursor, a short
summary and bounded JSON data. Explicit private-reasoning fields are rejected;
the caller remains responsible for the meaning of all other fields. The module
never owns the Lab event journal. On resume it selects a bounded set of durable
tasks plus relevant, promoted central lessons with their evidence references.

Recovery uses the same canonical memory services as `LabMemoryAdapter`:
`UserMemoryCore` for verified Lab facts and `LabStore.lab_lessons` for central
marked-verified lessons. Both are returned with source and origin so a new
agent instance knows where a discovery came from.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.lab_v1.domain import LabLesson, Session, SessionState, Task, TaskState
from core.lab_v1.store import LabStore
from memory.user_memory import UserMemoryCore


class StaleCheckpoint(RuntimeError):
    """The caller tried to overwrite a checkpoint revision it did not read."""


@dataclass(frozen=True)
class AgentCheckpoint:
    session_id: str
    agent_id: str
    cursor: str
    summary: str
    state: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    updated_at: float = 0.0


@dataclass(frozen=True)
class MemoryExperience:
    """One recoverable discovery from the shared central memory.

    `source` tells the caller which canonical service produced the item:
    ``lab_lesson`` for central Lab lessons, ``user_memory`` for facts promoted
    into `UserMemoryCore`. `evidence_ref` points back at the durable source
    record so the recovered statement remains auditable.
    """

    statement: str
    source: str
    source_session_id: str | None
    evidence_ref: str
    memory_id: str | None = None


@dataclass(frozen=True)
class ResumeContext:
    session: Session
    agent_id: str
    checkpoint: AgentCheckpoint | None
    open_tasks: list[Task]
    relevant_experiences: list[MemoryExperience]
    handoff: HandoffCheckpoint | None = None
    blocker: str | None = None


@dataclass(frozen=True)
class HandoffCheckpoint:
    """A bounded, durable baton between the four Lab work stages.

    ``rework_from``/``rework_attempt`` are only set on batons created (or
    downstream of batons created) by the explicit rework API. They are
    omitted from the stored state otherwise, so plain batons keep their
    exact historical shape.
    """

    stage: str
    artifact_ref: str
    evidence_refs: tuple[str, ...]
    provenance: dict[str, str]
    rework_from: str | None = None
    rework_attempt: int = 0

    def to_state(self) -> dict[str, Any]:
        handoff: dict[str, Any] = {
            "stage": self.stage,
            "artifact_ref": self.artifact_ref,
            "evidence_refs": list(self.evidence_refs),
            "provenance": dict(self.provenance),
        }
        if self.rework_from is not None:
            handoff["rework_from"] = self.rework_from
        if self.rework_attempt:
            handoff["rework_attempt"] = int(self.rework_attempt)
        return {"handoff": handoff}


_TOKEN = re.compile(r"[a-z0-9\u00c0-\u024f]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "after",
    "agent",
    "antes",
    "com",
    "current",
    "das",
    "depois",
    "dos",
    "for",
    "from",
    "mission",
    "missao",
    "para",
    "that",
    "the",
    "uma",
    "with",
}
_TERMINAL_TASK_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
_MAX_STATE_BYTES = 64 * 1024
_MAX_CURSOR_CHARS = 512
_MAX_SUMMARY_CHARS = 4096
_MAX_OPEN_TASKS = 50
_MAX_TASK_CONTEXT_CHARS = 32 * 1024
_MAX_EXPERIENCE_CHARS = 12 * 1024
_PRIVATE_REASONING_KEYS = {
    "chain_of_thought",
    "internal_reasoning",
    "private_reasoning",
    "reasoning_trace",
}
_HANDOFF_STAGES = ("STRATEGIST", "EXECUTOR", "REVIEWER", "MAESTRO")
# A reviewer rejection may send the baton back one pair (REVIEWER -> EXECUTOR)
# through the explicit rework API, at most this many times per chain.
_MAX_REWORK = 2
# Canonical caller-supplied provenance keys for a handoff backed by a real
# Run. Optional (legacy callers send other keys), but validated when present.
_CANONICAL_PROVENANCE_KEYS = ("run_id", "provider", "model", "model_reported")
_LAST_STAMP = [0.0]


def _next_stamp() -> float:
    """Strictly increasing wall stamp within this process.

    The session-baton scan orders rows by ``updated_at``: two writes landing
    on the same clock tick would make "latest baton" ambiguous. Rows are
    never rewritten retroactively, so instead of a schema change we simply
    refuse to hand out the same stamp twice in this process.
    """
    stamp = time.time()
    if stamp <= _LAST_STAMP[0]:
        stamp = _LAST_STAMP[0] + 1e-6
    _LAST_STAMP[0] = stamp
    return stamp


def _rework_attempt_of(baton: dict[str, Any] | None) -> int:
    """Rework rounds already consumed by the chain that produced ``baton``."""
    if not isinstance(baton, dict):
        return 0
    try:
        return max(0, int(baton.get("rework_attempt") or 0))
    except (TypeError, ValueError):
        return 0


class AgentContinuity:
    """Save and recover one durable checkpoint per mission/agent pair."""

    def __init__(self, store: LabStore, memory: UserMemoryCore | None = None) -> None:
        self.store = store
        self.memory = memory or UserMemoryCore()
        self.store.initialize()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_continuity (
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    agent_id TEXT NOT NULL,
                    cursor TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    revision INTEGER NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(session_id, agent_id)
                )
                """
            )

    @staticmethod
    def _agent_id(value: str) -> str:
        agent_id = str(value or "").strip()
        if not agent_id:
            raise ValueError("Agent id is required")
        return agent_id

    @classmethod
    def _validate_state_value(cls, value: Any) -> None:
        if value is None or isinstance(value, (str, bool, int)):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Checkpoint numbers must be finite")
            return
        if isinstance(value, list):
            for item in value:
                cls._validate_state_value(item)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("Checkpoint state must be JSON-compatible")
                if key.casefold() in _PRIVATE_REASONING_KEYS:
                    raise ValueError("Checkpoint state cannot store private reasoning")
                cls._validate_state_value(item)
            return
        raise ValueError("Checkpoint state must be JSON-compatible")

    def save_checkpoint(
        self,
        session_id: str,
        agent_id: str,
        *,
        cursor: str,
        summary: str,
        state: Mapping[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> AgentCheckpoint:
        """Atomically create or replace a checkpoint.

        ``expected_revision`` is an optimistic lock. It may be omitted only
        for the first write; every replacement must name the revision loaded
        by the worker so stale processes cannot erase newer progress.
        """
        if self.store.get_session(session_id) is None:
            raise ValueError("Unknown session")
        agent_id = self._agent_id(agent_id)
        cursor = " ".join(str(cursor or "").split())
        summary = " ".join(str(summary or "").split())
        if len(cursor) > _MAX_CURSOR_CHARS:
            raise ValueError(f"Cursor exceeds {_MAX_CURSOR_CHARS} characters")
        if len(summary) > _MAX_SUMMARY_CHARS:
            raise ValueError(f"Summary exceeds {_MAX_SUMMARY_CHARS} characters")
        state_document = dict(state or {})
        self._validate_state_value(state_document)
        state_json = json.dumps(
            state_document, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        if len(state_json.encode("utf-8")) > _MAX_STATE_BYTES:
            raise ValueError("Checkpoint state exceeds 64 KiB")

        stamp = _next_stamp()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revision FROM agent_continuity WHERE session_id=? AND agent_id=?",
                (session_id, agent_id),
            ).fetchone()
            current_revision = int(row["revision"]) if row else 0
            if row is not None and expected_revision is None:
                raise StaleCheckpoint(
                    f"Expected revision is required; current is {current_revision}"
                )
            if expected_revision is not None and int(expected_revision) != current_revision:
                raise StaleCheckpoint(
                    f"Expected revision {expected_revision}, found {current_revision}"
                )
            revision = current_revision + 1
            # Delete+insert (not UPSERT) so every write lands on a FRESH
            # rowid: an agent rewriting its own row must move to the end of
            # the insertion order, otherwise the rowid-first session-baton
            # scan would miss it. UPSERT would keep the old rowid and make
            # rowid diverge from logical write order. Same transaction, same
            # stored bytes, same revision semantics.
            conn.execute(
                "DELETE FROM agent_continuity WHERE session_id=? AND agent_id=?",
                (session_id, agent_id),
            )
            conn.execute(
                """
                INSERT INTO agent_continuity(
                    session_id, agent_id, cursor, summary, state_json, revision, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, agent_id, cursor, summary, state_json, revision, stamp),
            )
        return AgentCheckpoint(
            session_id=session_id,
            agent_id=agent_id,
            cursor=cursor,
            summary=summary,
            state=json.loads(state_json),
            revision=revision,
            updated_at=stamp,
        )

    def load_checkpoint(self, session_id: str, agent_id: str) -> AgentCheckpoint | None:
        agent_id = self._agent_id(agent_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_continuity WHERE session_id=? AND agent_id=?",
                (session_id, agent_id),
            ).fetchone()
        if row is None:
            return None
        return AgentCheckpoint(
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            cursor=row["cursor"],
            summary=row["summary"],
            state=json.loads(row["state_json"]),
            revision=int(row["revision"]),
            updated_at=float(row["updated_at"]),
        )

    @staticmethod
    def _validate_provenance(provenance: Mapping[str, str]) -> dict[str, str]:
        """Normalize caller-supplied provenance; never enrich it here.

        Provenance stays exactly what the caller handed in (stripped), so the
        stored dict remains factual data about the Run that produced the
        artifact. Any non-empty string key is accepted for compatibility with
        existing callers; the canonical run keys (``run_id``/``provider``/
        ``model``/``model_reported``) are optional, but when one is present
        it must carry a non-empty string value.
        """
        for key in _CANONICAL_PROVENANCE_KEYS:
            if key in provenance:
                value = provenance[key]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Handoff provenance '{key}' must be a non-empty string when present"
                    )
        provenance_doc = {str(k).strip(): str(v).strip() for k, v in provenance.items()}
        if not provenance_doc or any(not k or not v for k, v in provenance_doc.items()):
            raise ValueError("Handoff provenance is required")
        return provenance_doc

    def _last_session_handoff(self, session_id: str) -> dict[str, Any] | None:
        """Latest handoff baton recorded anywhere in the session.

        The baton belongs to the mission, not to one occupant: roles are
        rebindable, so the +1 stage rule is checked against what the SESSION
        last saw, letting the chain flow STRATEGIST -> EXECUTOR -> REVIEWER
        -> MAESTRO across different agents. Rows are ordered primarily by
        ``rowid`` (globally increasing, immune to wall-clock rollback across
        processes) with ``updated_at`` DESC as the secondary tie-break;
        rows whose state carries no handoff (plain checkpoints) are skipped.
        A caller's own prior row is part of this scan, so the no-baton
        fallback is inherently covered.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT state_json FROM agent_continuity
                WHERE session_id=?
                ORDER BY rowid DESC, updated_at DESC
                """,
                (session_id,),
            ).fetchall()
        for row in rows:
            try:
                state = json.loads(row["state_json"])
            except (TypeError, ValueError):
                continue
            handoff = state.get("handoff") if isinstance(state, dict) else None
            if isinstance(handoff, dict) and "stage" in handoff:
                return handoff
        return None

    def save_handoff_checkpoint(
        self,
        session_id: str,
        agent_id: str,
        *,
        stage: str,
        artifact_ref: str,
        evidence_refs: list[str] | tuple[str, ...],
        provenance: Mapping[str, str],
        cursor: str,
        summary: str,
        expected_revision: int | None = None,
        verify_artifact: bool = False,
    ) -> AgentCheckpoint:
        """Persist one explicit baton with artifact, evidence and provenance.

        This remains a continuity primitive only: it does not dispatch work or
        mutate the mission. Stage order is checked against the latest SESSION
        baton (whoever holds it) so a worker cannot silently skip the reviewer
        or promote an unreviewed artifact. The only legal step backwards is
        the explicit REVIEWER -> EXECUTOR rework, which has its own API
        (`save_rework_checkpoint`) and is never reachable from here.

        ``verify_artifact`` is opt-in: when True, the ``artifact:`` id is
        resolved against the Lab store and an unresolvable reference is
        rejected. Default False keeps the historical contract untouched.
        """
        stage = str(stage or "").strip().upper()
        if stage not in _HANDOFF_STAGES:
            raise ValueError("Unknown handoff stage")
        artifact_ref = str(artifact_ref or "").strip()
        if not artifact_ref:
            raise ValueError("Handoff artifact_ref is required")
        if verify_artifact:
            artifact_id = artifact_ref
            if artifact_id.startswith("artifact:"):
                artifact_id = artifact_id[len("artifact:"):]
            if self.store.get_artifact(artifact_id.strip()) is None:
                raise ValueError("Handoff artifact_ref does not resolve")
        refs = tuple(str(ref or "").strip() for ref in evidence_refs)
        if not refs or any(not ref for ref in refs):
            raise ValueError("Handoff evidence_refs are required")
        provenance_doc = self._validate_provenance(provenance)
        prior = self._last_session_handoff(session_id)
        if prior is not None:
            prior_index = _HANDOFF_STAGES.index(str(prior.get("stage", "")))
            current_index = _HANDOFF_STAGES.index(stage)
            if current_index != prior_index + 1:
                raise ValueError("Handoff stage must advance exactly one step")
        # Carry the rework counter forward (if any) so the rework limit
        # survives the EXECUTOR -> REVIEWER -> ... hops of the repair loop.
        checkpoint = HandoffCheckpoint(
            stage, artifact_ref, refs, provenance_doc,
            rework_attempt=_rework_attempt_of(prior),
        )
        return self.save_checkpoint(
            session_id, agent_id, cursor=cursor, summary=summary,
            state=checkpoint.to_state(),
            expected_revision=expected_revision,
        )

    def save_rework_checkpoint(
        self,
        session_id: str,
        agent_id: str,
        *,
        artifact_ref: str,
        evidence_refs: list[str] | tuple[str, ...],
        provenance: Mapping[str, str],
        cursor: str,
        summary: str,
        expected_revision: int | None = None,
    ) -> AgentCheckpoint:
        """Send the baton back one pair (REVIEWER -> EXECUTOR) after a rejection.

        The reviewer rejected the artifact and the executor re-enters the
        chain with a fresh one. This transition is explicit on purpose: the
        +1 monotony of `save_handoff_checkpoint` stays untouched, so a silent
        backwards write still raises. The attempt counter rides the session
        baton chain and hard-stops at ``_MAX_REWORK``; the caller stays
        responsible for the revision lock of its own row.
        """
        if self.store.get_session(session_id) is None:
            raise ValueError("Unknown session")
        agent_id = self._agent_id(agent_id)
        artifact_ref = str(artifact_ref or "").strip()
        if not artifact_ref:
            raise ValueError("Handoff artifact_ref is required")
        refs = tuple(str(ref or "").strip() for ref in evidence_refs)
        if not refs or any(not ref for ref in refs):
            raise ValueError("Handoff evidence_refs are required")
        provenance_doc = self._validate_provenance(provenance)
        prior = self._last_session_handoff(session_id)
        if prior is None or str(prior.get("stage", "")) != "REVIEWER":
            raise ValueError("Handoff rework requires a prior REVIEWER baton")
        attempt = _rework_attempt_of(prior) + 1
        if attempt > _MAX_REWORK:
            raise ValueError("Handoff rework limit reached")
        checkpoint = HandoffCheckpoint(
            "EXECUTOR", artifact_ref, refs, provenance_doc,
            rework_from="REVIEWER", rework_attempt=attempt,
        )
        return self.save_checkpoint(
            session_id, agent_id, cursor=cursor, summary=summary,
            state=checkpoint.to_state(),
            expected_revision=expected_revision,
        )

    def load_handoff_checkpoint(self, session_id: str, agent_id: str) -> HandoffCheckpoint | None:
        checkpoint = self.load_checkpoint(session_id, agent_id)
        if checkpoint is None:
            return None
        return self._handoff_from_state(checkpoint.state.get("handoff"))

    @staticmethod
    def _handoff_from_state(raw: Mapping[str, Any] | None) -> HandoffCheckpoint | None:
        """Decode a stored baton without assuming the current agent owns it.

        A handoff is a session-level baton, not private progress belonging to
        the agent that wrote the row.  Keeping decoding in one tolerant helper
        lets a replacement AgentInstance recover a valid baton after restart
        while treating malformed legacy state as unavailable rather than
        turning recovery into a crash.
        """
        if not isinstance(raw, dict):
            return None
        try:
            stage = str(raw["stage"])
            artifact_ref = str(raw["artifact_ref"])
            evidence_refs = tuple(str(ref) for ref in raw["evidence_refs"])
            provenance = {str(k): str(v) for k, v in raw["provenance"].items()}
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        rework_from = raw.get("rework_from")
        return HandoffCheckpoint(
            stage=stage,
            artifact_ref=artifact_ref,
            evidence_refs=evidence_refs,
            provenance=provenance,
            rework_from=str(rework_from) if rework_from is not None else None,
            rework_attempt=_rework_attempt_of(raw),
        )

    def resume(
        self,
        session_id: str,
        agent_id: str,
        *,
        memory_limit: int = 5,
        query_text: str | None = None,
    ) -> ResumeContext:
        """Rebuild bounded operational context after a process restart."""
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Unknown session")
        agent_id = self._agent_id(agent_id)
        candidates = [
            task
            for task in self.store.list_tasks(session_id)
            if task.assigned_agent_id == agent_id and task.state not in _TERMINAL_TASK_STATES
        ]
        open_tasks: list[Task] = []
        task_chars = 0
        for task in candidates:
            size = len(f"{task.title} {task.instruction} {task.acceptance}")
            if size > _MAX_TASK_CONTEXT_CHARS - task_chars:
                continue
            open_tasks.append(task)
            task_chars += size
            if len(open_tasks) >= _MAX_OPEN_TASKS:
                break
        default_query = " ".join(
            [session.objective]
            + [f"{task.title} {task.instruction} {task.acceptance}" for task in open_tasks]
        )
        query = query_text.strip() if isinstance(query_text, str) and query_text.strip() else default_query
        memory_limit = max(0, min(int(memory_limit), 20))
        lesson_experiences = self._relevant_lessons(
            query, team_id=session.team_id, limit=memory_limit
        )
        memory_experiences = self._relevant_user_memory(
            query, team_id=session.team_id, limit=memory_limit
        )
        relevant_experiences: list[MemoryExperience] = []
        exp_chars = 0
        for exp in lesson_experiences + memory_experiences:
            if len(relevant_experiences) >= memory_limit:
                break
            if len(exp.statement) > _MAX_EXPERIENCE_CHARS - exp_chars:
                continue
            relevant_experiences.append(exp)
            exp_chars += len(exp.statement)

        checkpoint = self.load_checkpoint(session_id, agent_id)
        # Keep an agent's own checkpoint when it exists (a caller resuming the
        # same role expects the exact baton it persisted). A replacement
        # agent/model normally has no row under its new id, so fall back to
        # the latest session baton for failover.
        handoff = self._handoff_from_state(
            checkpoint.state.get("handoff") if checkpoint is not None else None
        )
        if handoff is None:
            handoff = self._handoff_from_state(self._last_session_handoff(session_id))
        blocker = None
        if session.state in (SessionState.BLOCKED, SessionState.BLOCKED_NEEDS_OWNER):
            blocker = f"Session is {session.state.value}"
        return ResumeContext(
            session=session,
            agent_id=agent_id,
            checkpoint=checkpoint,
            open_tasks=open_tasks,
            relevant_experiences=relevant_experiences,
            handoff=handoff,
            blocker=blocker,
        )

    def _relevant_user_memory(
        self, query: str, *, team_id: str, limit: int
    ) -> list[MemoryExperience]:
        """Recover verified Lab facts promoted into the shared user memory."""
        limit = max(0, min(int(limit), 20))
        if limit == 0 or not query.strip():
            return []
        try:
            facts = self.memory.list()
        except (AttributeError, TypeError):
            return []
        query_tokens = self._tokens(query)
        ranked: list[tuple[float, float, int, dict[str, Any], str]] = []
        for index, fact in enumerate(facts):
            if fact.get("source") != "zara_lab":
                continue
            if fact.get("category", "semantic_fact") != "semantic_fact":
                continue
            if fact.get("status") == "forgotten":
                continue
            ref = fact.get("ref") or ""
            origin = self._origin_from_ref(ref)
            if not self._origin_belongs_to_team(origin, team_id):
                continue
            fact_tokens = self._tokens(fact.get("fact", ""))
            overlap = query_tokens & fact_tokens
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens | fact_tokens))
            ranked.append(
                (score, float(fact.get("updated_at") or 0.0), -index, fact, origin)
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        selected: list[MemoryExperience] = []
        chars = 0
        for _score, _updated_at, _index, fact, origin in ranked:
            statement = fact.get("fact", "")
            if len(statement) > _MAX_EXPERIENCE_CHARS - chars:
                continue
            ref = fact.get("ref") or ""
            selected.append(
                MemoryExperience(
                    statement=statement,
                    source="user_memory",
                    source_session_id=origin,
                    evidence_ref=ref,
                    memory_id=fact.get("id"),
                )
            )
            chars += len(statement)
            if len(selected) >= limit:
                break
        return selected

    def _origin_belongs_to_team(self, origin: str | None, team_id: str) -> bool:
        if not origin:
            return False
        source_session = self.store.get_session(origin)
        return source_session is not None and source_session.team_id == team_id

    @staticmethod
    def _origin_from_ref(ref: str) -> str | None:
        """Parse the Lab session id out of a ``lab:session:event`` memory ref."""
        if ref.startswith("lab:"):
            parts = ref.split(":")
            if len(parts) >= 3:
                return parts[1]
        return None

    def _relevant_lessons(
        self, query: str, *, team_id: str, limit: int
    ) -> list[MemoryExperience]:
        limit = max(0, min(int(limit), 20))
        if limit == 0:
            return []
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []
        ranked: list[tuple[float, float, LabLesson]] = []
        for lesson in self._team_lessons(team_id):
            lesson_tokens = self._tokens(lesson.statement)
            overlap = query_tokens & lesson_tokens
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens | lesson_tokens))
            ranked.append((score, lesson.created_at, lesson))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected: list[MemoryExperience] = []
        chars = 0
        for score, _timestamp, lesson in ranked:
            if len(selected) >= limit:
                break
            if len(lesson.statement) > _MAX_EXPERIENCE_CHARS - chars:
                continue
            selected.append(
                MemoryExperience(
                    statement=lesson.statement,
                    source="lab_lesson",
                    source_session_id=lesson.source_session_id,
                    evidence_ref=lesson.evidence_ref,
                    memory_id=lesson.id,
                )
            )
            chars += len(lesson.statement)
        return selected

    def _team_lessons(self, team_id: str) -> list[LabLesson]:
        """Filter origin in SQL before the bounded candidate limit."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT lessons.*
                FROM lab_lessons AS lessons
                JOIN sessions ON sessions.id = lessons.source_session_id
                WHERE sessions.team_id = ?
                ORDER BY lessons.created_at DESC, lessons.rowid DESC
                LIMIT 500
                """,
                (team_id,),
            ).fetchall()
        return [
            LabLesson(
                id=row["id"],
                source_event_id=row["source_event_id"],
                source_session_id=row["source_session_id"],
                statement=row["statement"],
                evidence_ref=row["evidence_ref"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in _TOKEN.findall(text or "")
            if token.lower() not in _STOPWORDS
        }
