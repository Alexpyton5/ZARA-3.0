from __future__ import annotations

import sqlite3

import pytest

from core.lab_v1.domain import EventType, LabEvent, Session, Team
from core.lab_v1.store import LabStore


def _store_with_session(tmp_path, session_id: str = "session-a") -> LabStore:
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="Mentor"))
    store.save_session(Session(id=session_id, team_id="team", objective="Improve ZARA"))
    return store


def _marked_lesson(store: LabStore, *, event_id: str = "lesson-source", session_id: str = "session-a") -> LabEvent:
    evidence = store.append_event(
        LabEvent(
            id=f"evidence:{event_id}",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id=session_id,
            entity_id="task-1",
            payload={"result": "Observed result"},
        )
    )
    return store.append_event(
        LabEvent(
            id=event_id,
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id=session_id,
            entity_id=None,
            payload={
                "lesson": "Require observed postconditions before reporting an action as complete.",
                "evidence_event_id": evidence.id,
            },
        )
    )


def test_only_a_marked_verified_lesson_event_can_be_promoted(tmp_path):
    store = _store_with_session(tmp_path)
    event = store.append_event(
        LabEvent(
            id="ordinary-result",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id="session-a",
            entity_id=None,
            payload={"lesson": "An unsupported claim", "evidence_ref": "result:1"},
        )
    )

    with pytest.raises(ValueError, match="marked-verified lesson"):
        store.promote_lesson(event.id)

    assert store.list_lessons() == []


def test_promoted_lesson_survives_restart_and_is_visible_across_missions(tmp_path):
    store = _store_with_session(tmp_path)
    event = _marked_lesson(store)

    promoted = store.promote_lesson(event.id)

    reopened = LabStore(tmp_path / "lab.db")
    reopened.initialize()
    reopened.save_session(Session(id="session-b", team_id="team", objective="Another mission"))
    lessons = reopened.list_lessons()
    assert lessons == [promoted]
    assert lessons[0].source_session_id == "session-a"
    assert lessons[0].statement.startswith("Require observed postconditions")
    assert lessons[0].evidence_ref == "event:evidence:lesson-source"
    assert reopened.lesson_context("session-b") == [lessons[0].statement]


def test_replaying_the_same_marked_event_does_not_duplicate_the_lesson(tmp_path):
    store = _store_with_session(tmp_path)
    event = _marked_lesson(store)

    first = store.promote_lesson(event.id)
    second = store.promote_lesson(event.id)

    assert second == first
    assert len(store.list_lessons()) == 1
    promoted_events = [
        item for item in store.list_events("session-a")
        if item.type == EventType.LESSON_PROMOTED
    ]
    assert len(promoted_events) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"evidence_event_id": "evidence:missing-lesson"},
        {"lesson": "Missing evidence"},
        {"lesson": "Unknown evidence", "evidence_event_id": "not-persisted"},
    ],
)
def test_incomplete_or_unresolved_lesson_evidence_is_rejected(tmp_path, payload):
    store = _store_with_session(tmp_path)
    if payload.get("evidence_event_id") == "evidence:missing-lesson":
        store.append_event(LabEvent(
            id="evidence:missing-lesson", seq=0, type=EventType.TASK_COMPLETED,
            session_id="session-a", entity_id="task-1",
        ))
    source = store.append_event(LabEvent(
        id="marked", seq=0, type=EventType.LESSON_MARKED_VERIFIED,
        session_id="session-a", entity_id=None, payload=payload,
    ))

    with pytest.raises(ValueError):
        store.promote_lesson(source.id)

    assert store.list_lessons() == []


def test_promotion_rolls_back_if_its_audit_event_cannot_be_written(tmp_path):
    store = _store_with_session(tmp_path)
    source = _marked_lesson(store)
    store.append_event(LabEvent(
        id=f"lesson-promoted:{source.id}", seq=0, type="collision",
        session_id="session-a", entity_id=None,
    ))

    with pytest.raises(sqlite3.IntegrityError):
        store.promote_lesson(source.id)

    assert store.list_lessons() == []


def test_zero_limit_returns_no_central_lessons(tmp_path):
    store = _store_with_session(tmp_path)
    store.promote_lesson(_marked_lesson(store).id)

    assert store.list_lessons(limit=0) == []
    assert store.lesson_context("session-a", limit=0) == []


def test_lesson_source_must_belong_to_an_existing_session(tmp_path):
    store = _store_with_session(tmp_path)
    store.append_event(LabEvent(
        id="ghost-evidence", seq=0, type=EventType.TASK_COMPLETED,
        session_id="ghost", entity_id="task-ghost",
    ))
    source = store.append_event(LabEvent(
        id="ghost-source", seq=0, type=EventType.LESSON_MARKED_VERIFIED,
        session_id="ghost", entity_id=None,
        payload={"lesson": "Ghost lesson", "evidence_event_id": "ghost-evidence"},
    ))

    with pytest.raises(ValueError, match="existing source session"):
        store.promote_lesson(source.id)


def test_lesson_evidence_must_come_from_the_same_session(tmp_path):
    store = _store_with_session(tmp_path)
    store.save_session(Session(id="session-b", team_id="team", objective="Other"))
    store.append_event(LabEvent(
        id="foreign-evidence", seq=0, type=EventType.TASK_COMPLETED,
        session_id="session-b", entity_id="task-b",
    ))
    source = store.append_event(LabEvent(
        id="cross-source", seq=0, type=EventType.LESSON_MARKED_VERIFIED,
        session_id="session-a", entity_id=None,
        payload={"lesson": "Cross lesson", "evidence_event_id": "foreign-evidence"},
    ))

    with pytest.raises(ValueError, match="earlier event in the same session"):
        store.promote_lesson(source.id)


def test_lesson_evidence_must_precede_its_marker(tmp_path):
    store = _store_with_session(tmp_path)
    source = store.append_event(LabEvent(
        id="early-marker", seq=0, type=EventType.LESSON_MARKED_VERIFIED,
        session_id="session-a", entity_id=None,
        payload={"lesson": "Out-of-order lesson", "evidence_event_id": "late-evidence"},
    ))
    store.append_event(LabEvent(
        id="late-evidence", seq=0, type=EventType.TASK_COMPLETED,
        session_id="session-a", entity_id="task-late",
    ))

    with pytest.raises(ValueError, match="earlier event in the same session"):
        store.promote_lesson(source.id)
