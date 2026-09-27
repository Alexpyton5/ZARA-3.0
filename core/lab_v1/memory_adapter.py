"""ZARA LAB REAL V1 — bridge from Lab events to ZARA's existing memory.

Why this does not own a database
---------------------------------
The Lab already has its own record of everything that happened (`LabStore`,
`lab/zara_lab_v1.db`). This module does not duplicate that. It selectively
promotes a small number of Lab outcomes into `UserMemoryCore`
(`memory/user_memory.py`), the SAME semantic-fact store ZARA already uses
for everything else it knows about Alex. A promoted fact looks, to the rest
of ZARA, exactly like any other fact she learned — the only difference is
its `ref`, which points back at the exact Lab event that produced it.

Why idempotency matters here specifically
------------------------------------------
`submit()` in `runtime.py` can be interrupted between "wrote the memory" and
"recorded that we wrote it" — a crash, a restart, a retried step. Without a
guard, replaying that event would write the same fact twice into Alex's
permanent memory. `store.memory_outbox_seen()` / `memory_outbox_record()`
are the guard: check before writing, record only after the write succeeds.
"""
from __future__ import annotations

import re
from typing import Any

from core.lab_v1.agent_continuity import AgentContinuity
from core.lab_v1.domain import EventType, LabEvent, Session, new_id, now
from core.lab_v1.store import LabStore
from memory.second_brain_composition import is_safe_text, same_fact_text
from memory.user_memory import UserMemoryCore


def is_safe_recovery_text(value: str) -> bool:
    """Whether text is safe to inject as model-visible recovered context."""
    return is_safe_text(value)

_CURRENT_MESSAGE_MARKER = re.compile(r"(?im)^\s*mensagem\s+atual\s+de\s+alex\s*:\s*$")


def is_current_message_echo(value: str, current_text: str) -> bool:
    """Reject only a structured echo, never a partial overlap with a lesson.

    Recovered context is an appendix.  It must not carry its own current-user
    section, and a standalone recovered block cannot be a second copy of the
    current turn.  Comparing normalized blocks instead of substrings preserves
    legitimate lessons that merely share a few words with Alex's request.
    """
    if not isinstance(value, str) or not isinstance(current_text, str):
        return False
    if _CURRENT_MESSAGE_MARKER.search(value):
        return True
    current = " ".join(current_text.split()).casefold()
    if not current:
        return False
    blocks = re.split(r"\n\s*\n", value.strip())
    return any(" ".join(block.split()).casefold() == current for block in blocks)


class LabMemoryAdapter:
    """Promotes verified Lab outcomes into ZARA's permanent user memory."""

    def __init__(self, store: LabStore, memory: UserMemoryCore | None = None, obsidian=None,
                 second_brain=None) -> None:
        self.store = store
        self.memory = memory or UserMemoryCore()
        self.obsidian = obsidian
        self.second_brain = second_brain

    def sync_to_obsidian(self, session_id: str, *, limit: int = 20) -> int:
        """Mirror promoted Lab facts into the shared Obsidian vault.

        The marker is the durable Lab reference, so retries reconcile an
        interrupted write by inspecting the vault before appending anything.
        """
        if self.obsidian is None:
            return 0
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError('Unknown session')
        facts = [f for f in self.memory.list() if f.get('source') == 'zara_lab'
                 and (f.get('ref') or '').startswith(f'lab:{session_id}:')]
        synced = 0
        for fact in facts[:max(0, int(limit))]:
            try:
                result = self.obsidian.sync_memory(
                    fact['ref'],
                    f"Lab {session_id}",
                    fact['fact'],
                    category='Lab',
                )
                if result.status == 'written':
                    synced += 1
                # 'unchanged' retries are idempotent no-ops; 'conflict'
                # preserves the human edit and leaves a conflict artifact for
                # review; 'unavailable' keeps the durable Lab/UserMemory
                # result and retries on the next sync.
            except OSError:
                # Obsidian is an optional, reconnectable projection. Keep
                # the durable Lab/UserMemory result and retry on next sync.
                continue
        return synced

    def layers(self, session_id: str) -> dict:
        """Logical views over the existing Lab journal and UserMemoryCore."""
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError('Unknown session')
        events = self.store.list_events(session_id, limit=100)
        return {
            'working': {'objective': session.objective, 'state': session.state.value,
                'tasks': [{'id': t.id, 'title': t.title, 'state': t.state.value} for t in self.store.list_tasks(session_id)],
                'decisions': [d.statement for d in self.store.list_decisions(session_id)]},
            'episodic': [{'event_id': e.id, 'type': e.type, 'occurred_at': e.occurred_at}
                for e in events if e.type in ('mission.verified', 'mission.blocked', 'run.failed', 'handoff.completed')],
            'semantic': self.memory.search(session.objective, category='semantic_fact', limit=4),
            'procedural': [a.to_dict() for a in self.store.list_artifacts(session_id) if a.kind == 'VERIFIED_PROCEDURE'],
            'long_term_store': 'UserMemoryCore', 'chat_promoted': False,
        }

    def promote_verified_mission(self, session_id: str, statement: str) -> str | None:
        """Only a completed governed mission can promote its short verified outcome."""
        mission = self.store.mission_snapshot(session_id)
        if (not mission or mission['state'] != 'COMPLETED' or not mission.get('steps')
                or any(s.get('verification', {}).get('verdict') != 'PASS' for s in mission['steps'])):
            raise ValueError('Mission has no complete verification chain')
        event_id = 'verified-memory:' + session_id
        if self.store.memory_outbox_seen(event_id): return None
        session = self.store.get_session(session_id)
        event = LabEvent(event_id, 0, 'mission.verified_outcome', session_id, session_id,
            {'verification_refs': [s['verification']['evidence_ref'] for s in mission['steps']]}, now())
        if not any(e.id == event_id for e in self.store.list_events(session_id, limit=500)):
            self.store.append_event(event)
        return self.promote(event, session=session, statement=statement, confidence=.9)

    def recover_discoveries(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return Lab-promoted facts from the shared user memory with provenance.

        This is the read side of ``promote``: a new mission instance can recover
        a verified discovery from Mission A without Alex repeating it.
        """
        limit = max(1, min(int(limit), 20))
        facts = self.memory.search(query, category="semantic_fact", limit=limit)
        results: list[dict[str, Any]] = []
        for fact in facts:
            if fact.get("source") != "zara_lab":
                continue
            ref = fact.get("ref") or ""
            origin = None
            if ref.startswith("lab:"):
                parts = ref.split(":")
                if len(parts) >= 3:
                    origin = parts[1]
            results.append(
                {
                    "statement": fact["fact"],
                    "source": fact.get("source"),
                    "ref": ref,
                    "origin_session_id": origin,
                    "memory_id": fact.get("id"),
                    "confidence": fact.get("confidence"),
                }
            )
            if len(results) >= limit:
                break
        return results

    def recover_session_context(
        self,
        session: Session,
        text: str,
        *,
        limit: int = 5,
    ) -> str:
        """Append bounded, marked-verified Lab lessons with provenance."""
        limit = max(0, min(int(limit), 5))
        if limit == 0:
            return ""
        recovered = AgentContinuity(self.store, self.memory).resume(
            session.id,
            "ceo",
            memory_limit=limit,
            query_text=f"{session.objective} {text}",
        )
        experiences = []
        seen: set[tuple[str, str]] = set()
        for item in recovered.relevant_experiences:
            if item.source == "user_memory" and not self._has_verified_source(item):
                continue
            if not is_safe_recovery_text(item.statement):
                continue
            if is_current_message_echo(item.statement, text):
                continue
            identity = (item.statement, item.evidence_ref)
            if identity in seen:
                continue
            # A verified outcome can be promoted into BOTH canonical stores
            # (user memory and the central lesson) with different evidence
            # refs; it is still one fact and must render once.
            if any(same_fact_text(item.statement, kept.statement) for kept in experiences):
                continue
            seen.add(identity)
            experiences.append(item)
            if len(experiences) >= limit:
                break
        lines = []
        chars = 0
        covered: list[str] = []
        for experience in experiences:
            origin = experience.source_session_id or "desconhecida"
            line = (
                f"- {experience.statement} "
                f"[origem: sessao {origin}; evidencia: {experience.evidence_ref}; "
                f"fonte: {experience.source}]"
            )
            if len(line) > 6000 - chars:
                continue
            lines.append(line)
            chars += len(line)
            covered.append(experience.statement)
        for item in self._shared_brain_items(f"{session.objective} {text}", text):
            statement = item["text"]
            if any(same_fact_text(statement, seen) for seen in covered):
                continue
            line = f"- {statement} [fonte: {item['source']}; origem: {item['provenance']}]"
            if len(line) > 6000 - chars:
                continue
            lines.append(line)
            chars += len(line)
            covered.append(statement)
        if not lines:
            return ""
        return (
            "Contexto compartilhado relevante (dados com proveniencia):\n"
            + "\n".join(lines)
        )

    def _shared_brain_items(self, query: str, current_text: str) -> list[dict[str, Any]]:
        """Extra shared-context items (project events, Obsidian notes).

        The facade is the same one ZARA consults; user-memory and lesson rows
        already recovered above are deduplicated by statement. Items that
        would replay the current turn are dropped here so the runtime echo
        guards never have to discard the whole appendix. Failure degrades to
        the adapter's own recovery and never breaks the turn.
        """
        if self.second_brain is None or not query.strip():
            return []
        try:
            from memory.second_brain_composition import (
                dedup_items_by_text,
                repeats_current_message,
            )

            result = self.second_brain.query(query, budget_bytes=2048, limit=6)
        except Exception:
            return []
        items: list[dict[str, Any]] = []
        for raw in (result or {}).get("items") or []:
            text = str((raw or {}).get("text") or "").strip()
            if not text or not is_safe_recovery_text(text):
                continue
            if repeats_current_message(text, current_text or ""):
                continue
            items.append(
                {
                    "text": text,
                    "source": str((raw or {}).get("source") or "unknown"),
                    "provenance": str((raw or {}).get("provenance") or "unknown"),
                }
            )
        return dedup_items_by_text(items)

    def _has_verified_source(self, experience) -> bool:
        """Accept shared facts only when their originating event is auditable."""
        ref = experience.evidence_ref or ""
        prefix = f"lab:{experience.source_session_id}:"
        if not experience.source_session_id or not ref.startswith(prefix):
            return False
        event_id = ref[len(prefix):]
        allowed = {EventType.LESSON_MARKED_VERIFIED, "mission.verified_outcome"}
        return any(
            event.id == event_id and event.type in allowed
            for event in self.store.list_events(
                experience.source_session_id, limit=10000
            )
        )

    def promote(
        self,
        event: LabEvent,
        *,
        session: Session,
        statement: str,
        category: str = "semantic_fact",
        confidence: float = 0.8,
    ) -> str | None:
        """Write `statement` to ZARA's memory once per `event.id`, at most.

        Returns the new memory id, or None if this event was already
        promoted (idempotent replay) or if the fact is empty. Secret-looking
        content is rejected by `UserMemoryCore.add()` itself (it raises) —
        that raise is left to propagate so a skipped promotion is visible as
        a failure, never silently swallowed into a fake success.
        """
        # Idempotency guard: a crash/replay between "wrote to memory" and
        # "recorded that we did" must never double-write the same fact.
        if self.store.memory_outbox_seen(event.id):
            return None

        statement = " ".join((statement or "").split())
        if not statement:
            return None

        memory_ref = f"lab:{session.id}:{event.id}"
        record = self.memory.add(
            statement,
            category=category,
            confidence=confidence,
            source="zara_lab",
            ref=memory_ref,
        )
        memory_id = record["id"]

        self.store.memory_outbox_record(event.id, memory_ref)
        self.store.append_event(
            LabEvent(
                id=new_id("evt"),
                seq=0,
                type=EventType.MEMORY_LINKED,
                session_id=session.id,
                entity_id=memory_id,
                payload={"source_event_id": event.id, "memory_ref": memory_ref},
                occurred_at=now(),
            )
        )
        return memory_id
