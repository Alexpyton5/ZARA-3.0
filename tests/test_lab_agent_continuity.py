from __future__ import annotations

import pytest

from core.lab_v1.agent_continuity import AgentContinuity, StaleCheckpoint
from core.lab_v1.domain import (
    EventType,
    LabEvent,
    Session,
    SessionState,
    Task,
    TaskState,
    Team,
)
from core.lab_v1.store import LabStore
from core.lab_v1.memory_adapter import LabMemoryAdapter
from memory.user_memory import UserMemoryCore


class _EmptyMemory:
    def search(self, *_args, **_kwargs):
        return []


def _store(tmp_path) -> LabStore:
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="Mentor"))
    store.save_session(
        Session(
            id="mission-current",
            team_id="team",
            objective="Recover an agent checkpoint after restart",
        )
    )
    return store


def _promote_lesson(
    store: LabStore, *, session_id: str, event_id: str, statement: str
) -> None:
    if store.get_session(session_id) is None:
        store.save_session(Session(id=session_id, team_id="team", objective="Previous mission"))
    evidence = store.append_event(
        LabEvent(
            id=f"evidence:{event_id}",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id=session_id,
            entity_id="task-old",
            payload={"result": "observed"},
        )
    )
    marker = store.append_event(
        LabEvent(
            id=event_id,
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id=session_id,
            entity_id=None,
            payload={"lesson": statement, "evidence_event_id": evidence.id},
        )
    )
    store.promote_lesson(marker.id)


def test_checkpoint_survives_process_restart_and_restores_only_open_agent_work(tmp_path):
    store = _store(tmp_path)
    store.save_task(
        Task(
            id="open",
            session_id="mission-current",
            title="Persist checkpoint",
            instruction="Save the current cursor",
            created_by_agent_id="mentor",
            assigned_agent_id="worker",
            state=TaskState.RUNNING,
        )
    )
    store.save_task(
        Task(
            id="done",
            session_id="mission-current",
            title="Finished work",
            instruction="Do not replay this",
            created_by_agent_id="mentor",
            assigned_agent_id="worker",
            state=TaskState.COMPLETED,
        )
    )

    first_process = AgentContinuity(store)
    saved = first_process.save_checkpoint(
        "mission-current",
        "worker",
        cursor="open",
        summary="Database opened; migration still pending.",
        state={"attempt": 2, "files": ["core/lab_v1/agent_continuity.py"]},
    )

    reopened_store = LabStore(tmp_path / "lab.db")
    reopened_store.initialize()
    resumed = AgentContinuity(reopened_store).resume("mission-current", "worker")

    assert resumed.checkpoint == saved
    assert resumed.checkpoint.revision == 1
    assert resumed.checkpoint.state["attempt"] == 2
    assert [task.id for task in resumed.open_tasks] == ["open"]


def test_resume_recovers_only_experiences_relevant_to_the_current_mission(tmp_path):
    store = _store(tmp_path)
    _promote_lesson(
        store,
        session_id="mission-memory",
        event_id="lesson-memory",
        statement="Persist checkpoint state before restart so an agent can recover the mission.",
    )
    _promote_lesson(
        store,
        session_id="mission-ui",
        event_id="lesson-ui",
        statement="Use balanced colors and spacing in the dashboard header.",
    )

    resumed = AgentContinuity(store).resume("mission-current", "worker", memory_limit=3)

    assert [lesson.statement for lesson in resumed.relevant_experiences] == [
        "Persist checkpoint state before restart so an agent can recover the mission."
    ]
    assert resumed.relevant_experiences[0].evidence_ref == "event:evidence:lesson-memory"
    assert resumed.relevant_experiences[0].source_session_id == "mission-memory"


def test_resume_filters_foreign_team_before_ranking_and_limit(tmp_path):
    store = _store(tmp_path)
    store.save_team(Team(id="foreign-team", name="Foreign"))
    store.save_session(
        Session(id="foreign", team_id="foreign-team", objective="Foreign mission")
    )
    _promote_lesson(
        store,
        session_id="foreign",
        event_id="foreign-best-match",
        statement="Recover agent checkpoint after restart",
    )
    _promote_lesson(
        store,
        session_id="same-team",
        event_id="same-team-match",
        statement="Recover checkpoint safely after restart",
    )

    resumed = AgentContinuity(store).resume(
        "mission-current", "worker", memory_limit=1, query_text="checkpoint restart"
    )

    assert [item.source_session_id for item in resumed.relevant_experiences] == [
        "same-team"
    ]


def test_recovery_filters_bearer_and_private_reasoning_before_context_limit(tmp_path):
    store = _store(tmp_path)
    _promote_lesson(
        store,
        session_id="unsafe-memory",
        event_id="unsafe-bearer",
        statement="Bearer eyJhbGciOiJIUzI1NiJ9 hidden credential",
    )
    _promote_lesson(
        store,
        session_id="unsafe-memory",
        event_id="unsafe-reasoning",
        statement="Raciocinio privado: hidden internal steps",
    )
    _promote_lesson(
        store,
        session_id="safe-memory",
        event_id="safe-recovery",
        statement="Recover a checkpoint only after confirming its evidence.",
    )

    context = LabMemoryAdapter(store, _EmptyMemory()).recover_session_context(
        store.get_session("mission-current"), "checkpoint recovery", limit=1
    )

    assert "Bearer" not in context
    assert "Raciocinio privado" not in context
    assert "Recover a checkpoint" in context


def test_resume_filters_team_before_the_500_lesson_candidate_bound(tmp_path):
    store = _store(tmp_path)
    store.save_team(Team(id="foreign-team", name="Foreign"))
    store.save_session(
        Session(id="foreign", team_id="foreign-team", objective="Foreign mission")
    )
    store.save_session(
        Session(id="same-team", team_id="team", objective="Same team mission")
    )
    continuity = AgentContinuity(store)
    with continuity._connect() as conn:
        conn.executemany(
            """
            INSERT INTO lab_lessons(
                id, source_event_id, source_session_id, statement, evidence_ref, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"foreign-{number}",
                    f"foreign-event-{number}",
                    "foreign",
                    f"checkpoint restart foreign {number}",
                    f"event:foreign-{number}",
                    float(number + 10),
                )
                for number in range(501)
            ]
            + [
                (
                    "same-team-local",
                    "same-team-event",
                    "same-team",
                    "checkpoint restart same team",
                    "event:same-team",
                    1.0,
                )
            ],
        )

    resumed = continuity.resume(
        "mission-current", "worker", memory_limit=1, query_text="checkpoint restart"
    )

    assert [item.source_session_id for item in resumed.relevant_experiences] == [
        "same-team"
    ]


def test_checkpoint_update_is_revisioned_and_rejects_a_stale_writer(tmp_path):
    continuity = AgentContinuity(_store(tmp_path))
    first = continuity.save_checkpoint(
        "mission-current", "worker", cursor="one", summary="first"
    )
    second = continuity.save_checkpoint(
        "mission-current",
        "worker",
        cursor="two",
        summary="second",
        expected_revision=first.revision,
    )

    assert second.revision == 2
    with pytest.raises(StaleCheckpoint):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="blind", summary="revision omitted"
        )
    with pytest.raises(StaleCheckpoint):
        continuity.save_checkpoint(
            "mission-current",
            "worker",
            cursor="stale",
            summary="must not overwrite",
            expected_revision=first.revision,
        )
    assert continuity.load_checkpoint("mission-current", "worker") == second


def test_unknown_mission_cannot_create_or_resume_continuity_state(tmp_path):
    continuity = AgentContinuity(_store(tmp_path))

    with pytest.raises(ValueError, match="Unknown session"):
        continuity.save_checkpoint("missing", "worker", cursor="x", summary="x")
    with pytest.raises(ValueError, match="Unknown session"):
        continuity.resume("missing", "worker")


def test_resume_normalizes_agent_identity_like_checkpoint_writes(tmp_path):
    continuity = AgentContinuity(_store(tmp_path))
    saved = continuity.save_checkpoint(
        "mission-current", " worker ", cursor="open", summary="ready"
    )

    resumed = continuity.resume("mission-current", " worker ")

    assert saved.agent_id == "worker"
    assert resumed.agent_id == "worker"
    assert resumed.checkpoint == saved


def test_blank_agent_identity_cannot_be_loaded_or_resumed(tmp_path):
    continuity = AgentContinuity(_store(tmp_path))

    with pytest.raises(ValueError, match="Agent id is required"):
        continuity.load_checkpoint("mission-current", "  ")
    with pytest.raises(ValueError, match="Agent id is required"):
        continuity.resume("mission-current", "  ")


def test_resume_excludes_foreign_failed_and_cancelled_work(tmp_path):
    store = _store(tmp_path)
    for task_id, assigned, state in (
        ("mine", "worker", TaskState.RUNNING),
        ("foreign", "other", TaskState.RUNNING),
        ("failed", "worker", TaskState.FAILED),
        ("cancelled", "worker", TaskState.CANCELLED),
    ):
        store.save_task(
            Task(
                id=task_id,
                session_id="mission-current",
                title=task_id,
                instruction="continue",
                created_by_agent_id="mentor",
                assigned_agent_id=assigned,
                state=state,
            )
        )

    resumed = AgentContinuity(store).resume("mission-current", "worker")

    assert [task.id for task in resumed.open_tasks] == ["mine"]


def test_resume_enforces_requested_and_hard_experience_limits(tmp_path):
    store = _store(tmp_path)
    for number in range(25):
        _promote_lesson(
            store,
            session_id=f"memory-{number}",
            event_id=f"lesson-{number}",
            statement=f"Checkpoint restart recovery pattern {number}",
        )
    continuity = AgentContinuity(store)

    assert continuity.resume("mission-current", "worker", memory_limit=0).relevant_experiences == []
    assert len(continuity.resume("mission-current", "worker", memory_limit=3).relevant_experiences) == 3
    assert len(continuity.resume("mission-current", "worker", memory_limit=999).relevant_experiences) == 20


def test_checkpoint_rejects_non_standard_or_oversized_operational_state(tmp_path):
    continuity = AgentContinuity(_store(tmp_path))

    with pytest.raises(ValueError, match="JSON-compatible"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="x", summary="x", state={"bad": object()}
        )
    with pytest.raises(ValueError, match="finite"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="x", summary="x", state={"score": float("nan")}
        )
    with pytest.raises(ValueError, match="private reasoning"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="x", summary="x", state={"chain_of_thought": "hidden"}
        )
    with pytest.raises(ValueError, match="64 KiB"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="x", summary="x", state={"payload": "x" * (65 * 1024)}
        )


def test_checkpoint_and_resume_context_are_size_bounded(tmp_path):
    store = _store(tmp_path)
    continuity = AgentContinuity(store)

    with pytest.raises(ValueError, match="Cursor exceeds"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="x" * 513, summary="ok"
        )
    with pytest.raises(ValueError, match="Summary exceeds"):
        continuity.save_checkpoint(
            "mission-current", "worker", cursor="ok", summary="x" * 4097
        )

    for number in range(60):
        store.save_task(
            Task(
                id=f"task-{number:02d}",
                session_id="mission-current",
                title="checkpoint restart recovery",
                instruction="continue",
                created_by_agent_id="mentor",
                assigned_agent_id="worker",
                state=TaskState.RUNNING,
            )
        )
    resumed = continuity.resume("mission-current", "worker")
    assert len(resumed.open_tasks) == 50


def test_resume_skips_work_and_lessons_that_exceed_context_budgets(tmp_path):
    store = _store(tmp_path)
    store.save_task(
        Task(
            id="oversized",
            session_id="mission-current",
            title="checkpoint restart recovery",
            instruction="x" * (33 * 1024),
            created_by_agent_id="mentor",
            assigned_agent_id="worker",
            state=TaskState.RUNNING,
        )
    )
    _promote_lesson(
        store,
        session_id="large-memory",
        event_id="large-lesson",
        statement="checkpoint restart recovery " + "x" * (13 * 1024),
    )

    resumed = AgentContinuity(store).resume("mission-current", "worker")

    assert resumed.open_tasks == []
    assert resumed.relevant_experiences == []


class _Memory:
    def __init__(self): self.rows = []
    def add(self, fact, **kwargs):
        row = {'id': str(len(self.rows)), 'fact': fact, **kwargs}
        self.rows.append(row); return row
    def list(self): return list(self.rows)


def test_resume_filters_foreign_user_memory_before_ranking_and_limit(tmp_path):
    store = _store(tmp_path)
    store.save_team(Team(id="foreign-team", name="Foreign"))
    store.save_session(
        Session(id="foreign", team_id="foreign-team", objective="Foreign mission")
    )
    store.save_session(
        Session(id="same-team", team_id="team", objective="Same team mission")
    )
    memory = _Memory()
    for number in range(25):
        memory.add(
            f"checkpoint restart exact foreign match {number}",
            category="semantic_fact",
            source="zara_lab",
            ref=f"lab:foreign:event-{number}",
        )
    memory.add(
        "checkpoint restart same team match",
        category="semantic_fact",
        source="zara_lab",
        ref="lab:same-team:event-local",
    )

    resumed = AgentContinuity(store, memory).resume(
        "mission-current", "worker", memory_limit=1, query_text="checkpoint restart"
    )

    assert [item.source_session_id for item in resumed.relevant_experiences] == [
        "same-team"
    ]


class _Vault:
    """Fake of `ObsidianMemoryManager.sync_memory` semantics (reconciliable)."""

    def __init__(self):
        self.notes = {}
        self.conflicts = []

    def sync_memory(self, identity, topic, content, *, category='Lab'):
        from core.obsidian_memory import SyncResult
        if identity in self.notes:
            if self.notes[identity] == content:
                return SyncResult('unchanged', identity=identity)
            self.conflicts.append({'identity': identity, 'pending': content})
            return SyncResult('conflict', identity=identity)
        self.notes[identity] = content
        return SyncResult('written', f'vault/{identity}.md', identity)


class _UnavailableVault:
    def sync_memory(self, identity, topic, content, *, category='Lab'):
        raise OSError('vault disconnected')


def test_lab_facts_sync_to_shared_obsidian_idempotently(tmp_path):
    store = _store(tmp_path)
    memory, vault = _Memory(), _Vault()
    adapter = LabMemoryAdapter(store, memory, vault)
    event = LabEvent('event-1', 0, EventType.TASK_COMPLETED, 'mission-current', 'x', {})
    adapter.promote(event, session=store.get_session('mission-current'), statement='Use checkpoint recovery')
    assert adapter.sync_to_obsidian('mission-current') == 1
    assert adapter.sync_to_obsidian('mission-current') == 0
    assert len(vault.notes) == 1
    assert len(vault.conflicts) == 0


def test_resume_recovers_user_memory_discovery_from_another_mission(tmp_path):
    store = _store(tmp_path)
    memory = UserMemoryCore(db_path=tmp_path / "user_memory.db")
    adapter = LabMemoryAdapter(store, memory)
    event = LabEvent(
        id="discovery-event",
        seq=0,
        type=EventType.TASK_COMPLETED,
        session_id="mission-current",
        entity_id="task-discovery",
        payload={},
    )
    adapter.promote(
        event,
        session=store.get_session("mission-current"),
        statement="Persist checkpoint state before restart so an agent can recover the mission.",
        confidence=0.9,
    )

    store.save_session(
        Session(
            id="mission-b",
            team_id="team",
            objective="Recover an agent checkpoint after restart",
        )
    )
    resumed = AgentContinuity(store, memory).resume("mission-b", "worker", memory_limit=3)

    memory_items = [exp for exp in resumed.relevant_experiences if exp.source == "user_memory"]
    assert len(memory_items) == 1
    assert memory_items[0].statement == (
        "Persist checkpoint state before restart so an agent can recover the mission."
    )
    assert memory_items[0].source_session_id == "mission-current"
    assert memory_items[0].evidence_ref == "lab:mission-current:discovery-event"
    assert memory_items[0].memory_id is not None


def test_checkpoint_recovery_restores_tasks_review_state_and_blocker(tmp_path):
    store = _store(tmp_path)
    store.save_task(
        Task(
            id="review-task",
            session_id="mission-current",
            title="Review artifact",
            instruction="Check the handoff artifact",
            created_by_agent_id="mentor",
            assigned_agent_id="worker",
            state=TaskState.RUNNING,
        )
    )
    continuity = AgentContinuity(store)
    continuity.save_handoff_checkpoint(
        "mission-current",
        "worker",
        stage="REVIEWER",
        artifact_ref="artifact://review-1",
        evidence_refs=["evidence-1"],
        provenance={"source_session": "mission-current", "reviewer": "worker"},
        cursor="review",
        summary="Ready for review",
    )
    store.save_session(
        Session(
            id="mission-current",
            team_id="team",
            objective="Recover an agent checkpoint after restart",
            state=SessionState.BLOCKED_NEEDS_OWNER,
        )
    )

    resumed = continuity.resume("mission-current", "worker")

    assert [task.id for task in resumed.open_tasks] == ["review-task"]
    assert resumed.handoff is not None
    assert resumed.handoff.stage == "REVIEWER"
    assert resumed.handoff.artifact_ref == "artifact://review-1"
    assert resumed.blocker is not None
    assert "BLOCKED_NEEDS_OWNER" in resumed.blocker


def test_lab_facts_sync_survives_temporary_obsidian_disconnect(tmp_path):
    store = _store(tmp_path)
    memory = _Memory()
    adapter = LabMemoryAdapter(store, memory, _UnavailableVault())
    event = LabEvent('event-disconnected', 0, EventType.TASK_COMPLETED,
                     'mission-current', 'x', {})
    adapter.promote(event, session=store.get_session('mission-current'),
                    statement='Keep durable recovery state')

    assert adapter.sync_to_obsidian('mission-current') == 0


def test_lab_sync_preserves_human_edit_to_existing_obsidian_note(tmp_path):
    store = _store(tmp_path)
    memory, vault = _Memory(), _Vault()
    adapter = LabMemoryAdapter(store, memory, vault)
    event = LabEvent('event-human-edit', 0, EventType.TASK_COMPLETED,
                     'mission-current', 'x', {})
    adapter.promote(event, session=store.get_session('mission-current'),
                    statement='Original durable recovery state')
    assert adapter.sync_to_obsidian('mission-current') == 1
    # A human edit makes the managed note diverge: the retry must neither
    # count it as synced nor overwrite the human's words.
    key = next(iter(vault.notes))
    vault.notes[key] += '\n\nHuman correction: use the approved recovery path.'

    assert adapter.sync_to_obsidian('mission-current') == 0
    assert 'Human correction' in vault.notes[key]
    assert len(vault.conflicts) == 1
    assert vault.conflicts[0]['pending'] == 'Original durable recovery state'
