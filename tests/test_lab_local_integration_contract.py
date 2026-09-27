"""Local integration checks for the Lab contract.

These tests intentionally use only temporary SQLite/workspace state.  They
never invoke a provider, build a package, or write to the production tree.
"""

import json

from core.lab_v1.domain import LabEvent
from core.lab_v1.source_scope import select_source_scope
from core.lab_v1.store import LabStore


def test_events_are_ordered_and_recoverable_after_store_restart(tmp_path):
    db = tmp_path / "lab.db"
    first = LabStore(db)
    first.initialize()
    first.append_event(LabEvent("evt-a", 999, "session.created", "s1", "s1", {"state": "queued"}, "2026-01-01T00:00:00Z"))
    first.append_event(LabEvent("evt-b", 1, "session.status_changed", "s1", "s1", {"state": "running"}, "2026-01-01T00:00:01Z"))

    restarted = LabStore(db)
    restarted.initialize()
    events = restarted.list_events("s1")

    assert [(event.id, event.seq) for event in events] == [("evt-a", 1), ("evt-b", 2)]
    assert restarted.list_events("s1", after_seq=1)[0].id == "evt-b"
    assert restarted.list_events("s1", limit=1)[0].payload == {"state": "queued"}


def test_source_scope_indexes_real_local_modules_and_excludes_lab_engine(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "memory").mkdir()
    (tmp_path / "core" / "voice_pipeline.py").write_text("def transcribe_microphone_audio():\n    return 'voice'\n", encoding="utf-8")
    (tmp_path / "core" / "lab_v1").mkdir()
    (tmp_path / "core" / "lab_v1" / "runtime.py").write_text("def transcribe_microphone_audio(): pass\n", encoding="utf-8")
    (tmp_path / "memory" / "facts.py").write_text("def save_fact(value): return value\n", encoding="utf-8")

    selected = select_source_scope(tmp_path, "microphone audio transcription fails")

    assert selected
    assert selected[0] == "core/voice_pipeline.py"
    assert all("lab_v1" not in path for path in selected)


def test_autonomy_snapshot_is_durable_json_across_restart(tmp_path):
    db = tmp_path / "lab.db"
    store = LabStore(db)
    store.initialize()
    with store._connect() as conn:
        conn.execute(
            "CREATE TABLE mission_autonomy (session_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE autonomy_gaps (session_id TEXT, stage TEXT, reason TEXT, "
            "owner_action_required INTEGER, risk TEXT, occurrences INTEGER)"
        )
        conn.execute(
            "INSERT INTO mission_autonomy(session_id, document) VALUES (?, ?)",
            ("session-1", json.dumps({"owner_touches": 1, "automatic": True})),
        )

    restarted = LabStore(db)
    restarted.initialize()

    assert restarted.autonomy_snapshot("session-1") == {
        "owner_touches": 1,
        "automatic": True,
        "gaps": [],
    }
