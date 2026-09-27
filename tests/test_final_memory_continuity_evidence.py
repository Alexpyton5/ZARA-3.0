from __future__ import annotations

from pathlib import Path

import pytest

from core.lab_v1.agent_continuity import AgentContinuity
from core.lab_v1.domain import EventType, LabEvent, Session, Team
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.store import LabStore
from memory.second_brain_composition import (
    build_shared_second_brain,
    render_second_brain_context,
)
from memory.user_memory import UserMemoryCore


class _NoProjectMemory:
    def search(self, _query: str, limit: int = 5) -> list[dict]:
        return []


def _durable_fixture(tmp_path: Path) -> tuple[LabStore, UserMemoryCore, Session, Session, str]:
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team(id="team", name="Continuity Team"))
    source = Session(
        id="source-mission",
        team_id="team",
        objective="Validate a durable memory lesson",
    )
    current = Session(
        id="future-mission",
        team_id="team",
        objective="Recover a validated memory lesson after restart",
    )
    store.save_session(source)
    store.save_session(current)

    evidence = store.append_event(
        LabEvent(
            id="evidence:run-042",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id=source.id,
            entity_id="review-task",
            payload={"observed_postcondition": "restart retrieval succeeded"},
        )
    )
    marker = store.append_event(
        LabEvent(
            id="lesson:run-042",
            seq=0,
            type=EventType.LESSON_MARKED_VERIFIED,
            session_id=source.id,
            entity_id=None,
            payload={
                "lesson": (
                    "Persist verified restart continuity so a replacement model can "
                    "recover the lesson with evidence provenance."
                ),
                "evidence_event_id": evidence.id,
            },
        )
    )
    memory = UserMemoryCore(db_path=tmp_path / "user-memory.db")
    return store, memory, source, current, marker.id


def test_final_memory_continuity_rejects_unverified_lesson_and_recovers_by_new_agent(
    tmp_path: Path,
):
    store, memory, source, current, marker_id = _durable_fixture(tmp_path)

    unsupported = store.append_event(
        LabEvent(
            id="ordinary:unverified",
            seq=0,
            type=EventType.TASK_COMPLETED,
            session_id=source.id,
            entity_id=None,
            payload={"lesson": "This claim has no review marker"},
        )
    )
    with pytest.raises(ValueError, match="marked-verified lesson"):
        store.promote_lesson(unsupported.id)

    lesson = store.promote_lesson(marker_id)
    assert lesson is not None
    adapter = LabMemoryAdapter(store, memory)
    marker = next(event for event in store.list_events(source.id, limit=100) if event.id == marker_id)
    memory_id = adapter.promote(
        marker,
        session=source,
        statement=lesson.statement,
        confidence=0.95,
    )
    assert memory_id is not None

    first_agent = AgentContinuity(store, memory)
    first_agent.save_handoff_checkpoint(
        current.id,
        "agent-old-model",
        stage="REVIEWER",
        artifact_ref="artifact:run-042",
        evidence_refs=["event:evidence:run-042", lesson.evidence_ref],
        provenance={
            "run_id": "run-042",
            "provider": "provider-before-restart",
            "model": "model-before-restart",
            "model_reported": "model-before-restart",
        },
        cursor="review-complete",
        summary="Evidence-backed lesson is ready for the next agent.",
    )

    # Reopening both stores simulates a process restart. The replacement has a
    # different identity/model and therefore cannot rely on its own checkpoint.
    reopened_store = LabStore(tmp_path / "lab.db")
    reopened_store.initialize()
    reopened_memory = UserMemoryCore(db_path=tmp_path / "user-memory.db")
    replacement = AgentContinuity(reopened_store, reopened_memory)
    resumed = replacement.resume(
        current.id,
        "agent-new-model",
        memory_limit=5,
        query_text="verified restart continuity evidence provenance",
    )

    assert resumed.checkpoint is None
    assert resumed.handoff is not None
    assert resumed.handoff.stage == "REVIEWER"
    assert resumed.handoff.artifact_ref == "artifact:run-042"
    assert resumed.handoff.evidence_refs == ("event:evidence:run-042", lesson.evidence_ref)
    assert resumed.handoff.provenance == {
        "run_id": "run-042",
        "provider": "provider-before-restart",
        "model": "model-before-restart",
        "model_reported": "model-before-restart",
    }
    recovered = [
        item
        for item in resumed.relevant_experiences
        if item.statement == lesson.statement
    ]
    assert recovered
    assert {item.source for item in recovered} == {"lab_lesson", "user_memory"}
    assert all(item.source_session_id == source.id for item in recovered)
    assert all(item.evidence_ref for item in recovered)


def test_final_memory_continuity_future_retrieval_is_stable_after_restart_with_provenance(
    tmp_path: Path,
):
    store, memory, source, current, marker_id = _durable_fixture(tmp_path)
    lesson = store.promote_lesson(marker_id)
    assert lesson is not None
    adapter = LabMemoryAdapter(store, memory)
    marker = next(event for event in store.list_events(source.id, limit=100) if event.id == marker_id)
    adapter.promote(marker, session=source, statement=lesson.statement, confidence=0.95)

    first = build_shared_second_brain(
        user_memory=memory,
        lab_store=store,
        project_memory=_NoProjectMemory(),
        obsidian_index_db=tmp_path / "shared-brain-index.db",
        sync=False,
    )
    query = "replacement model recover verified restart lesson evidence provenance"
    before = first.query(query, budget_bytes=4096, limit=10)
    assert any(
        item["source"] == "lab_lesson"
        and lesson.evidence_ref in item["provenance"]
        and source.id in item["provenance"]
        for item in before["items"]
    )
    assert any(
        item["source"] == "user_memory"
        and f"lab:{source.id}:{marker_id}" in item["provenance"]
        for item in before["items"]
    )

    restarted_store = LabStore(tmp_path / "lab.db")
    restarted_store.initialize()
    restarted_memory = UserMemoryCore(db_path=tmp_path / "user-memory.db")
    second = build_shared_second_brain(
        user_memory=restarted_memory,
        lab_store=restarted_store,
        project_memory=_NoProjectMemory(),
        obsidian_index_db=tmp_path / "shared-brain-index.db",
        sync=False,
    )
    after = second.query(query, budget_bytes=4096, limit=10)

    assert after["items"] == before["items"]
    rendered = render_second_brain_context(second, query, budget_bytes=4096, limit=10)
    assert lesson.statement in rendered
    # Duplicate statements are rendered once by the canonical facade; the
    # surviving UserMemory row still carries the durable Lab event reference.
    assert "fonte: user_memory" in rendered
    assert f"origem: zara_lab:lab:{source.id}:{marker_id}" in rendered
    assert current.id not in rendered


__all__ = [
    "test_final_memory_continuity_rejects_unverified_lesson_and_recovers_by_new_agent",
    "test_final_memory_continuity_future_retrieval_is_stable_after_restart_with_provenance",
]


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
