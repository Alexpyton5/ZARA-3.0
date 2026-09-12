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

from core.lab_v1.domain import EventType, LabEvent, Session, new_id, now
from core.lab_v1.store import LabStore
from memory.user_memory import UserMemoryCore


class LabMemoryAdapter:
    """Promotes verified Lab outcomes into ZARA's permanent user memory."""

    def __init__(self, store: LabStore, memory: UserMemoryCore | None = None) -> None:
        self.store = store
        self.memory = memory or UserMemoryCore()

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
