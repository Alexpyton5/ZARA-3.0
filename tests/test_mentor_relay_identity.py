"""Mentor/agent relay proofs (ZARA-NIGHT-SHIFT 039-044).

Covers the previously untested core/mentor_relay.py contract and the identity
propagation added to LabCoordinator._sync_mentor_replies, so a Hermes message can
never be rendered as if the Mentor had written it.

All tests are isolated: each one gets its own relay root under tmp_path.
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from core.mentor_relay import MentorRelay


@pytest.fixture
def relay(tmp_path):
    return MentorRelay(root=tmp_path / "mentor-relay")


def _write_inbox(relay: MentorRelay, relay_id: str, **overrides):
    payload = {
        "schema": 1,
        "relay_id": relay_id,
        "direction": "MENTOR_TO_ZARA",
        "content": "resposta real do mentor",
        "created_at": time.time(),
        "source": "mentor_external",
    }
    payload.update(overrides)
    (relay.inbox / f"{relay_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


# ---------- outbound ----------
def test_enqueue_writes_pending_outbound_message(relay):
    payload = relay.enqueue("alex", "mensagem para o mentor")
    assert payload["direction"] == "ZARA_TO_MENTOR"
    assert payload["status"] == "PENDING"
    assert payload["relay_id"].startswith("MR-")
    assert relay.pending_count() == 1
    stored = json.loads((relay.outbox / f"{payload['relay_id']}.json").read_text(encoding="utf-8"))
    assert stored["content"] == "mensagem para o mentor"


def test_enqueue_rejects_empty_content(relay):
    with pytest.raises(ValueError):
        relay.enqueue("alex", "   ")


def test_mark_outbound_processed_archives_request(relay):
    payload = relay.enqueue("alex", "arquivar isto")
    relay.mark_outbound_processed(payload["relay_id"])
    assert relay.pending_count() == 0
    assert (relay.archive / f"{payload['relay_id']}.request.json").exists()


# ---------- inbound ----------
def test_drain_replies_imports_valid_reply_once(relay):
    _write_inbox(relay, "MR-1-AAAA")
    first = relay.drain_replies()
    assert len(first) == 1
    assert first[0]["content"] == "resposta real do mentor"
    assert relay.drain_replies() == []  # arquivada, nao reprocessa


def test_drain_replies_quarantines_invalid_payload(relay):
    (relay.inbox / "MR-1-BAD.json").write_text(
        json.dumps({"relay_id": "MR-1-BAD", "direction": "ZARA_TO_MENTOR", "content": "x"}),
        encoding="utf-8",
    )
    assert relay.drain_replies() == []
    assert list(relay.inbox.glob("*.json")) == []
    assert list(relay.archive.glob("*invalid*.json"))


def test_drain_replies_defaults_agent_to_mentor(relay):
    _write_inbox(relay, "MR-1-CCCC")
    reply = relay.drain_replies()[0]
    assert reply["agent"] == "mentor"


def test_drain_replies_preserves_hermes_identity(relay):
    _write_inbox(relay, "MR-1-DDDD", agent="hermes", source="hermes", task_id="H-7")
    reply = relay.drain_replies()[0]
    assert reply["agent"] == "hermes"
    assert reply["source"] == "hermes"
    assert reply["task_id"] == "H-7"


# ---------- status / heartbeat ----------
def test_status_is_offline_without_heartbeat(relay):
    status = relay.status()
    assert status.online is False
    assert status.state == "EXTERNAL"


def test_status_is_offline_when_heartbeat_is_stale(relay):
    relay.status_path.write_text(
        json.dumps({"state": "ONLINE", "updated_at": time.time() - 10_000}), encoding="utf-8"
    )
    status = relay.status()
    assert status.online is False
    assert status.state == "RELAY OFFLINE"


def test_status_is_online_with_fresh_heartbeat(relay):
    relay.status_path.write_text(
        json.dumps({"state": "ONLINE", "updated_at": time.time()}), encoding="utf-8"
    )
    status = relay.status()
    assert status.online is True
    assert status.state == "ONLINE VIA RELAY"


def test_snapshot_reports_pending_count(relay):
    relay.enqueue("alex", "um")
    relay.enqueue("alex", "dois")
    snap = relay.snapshot()
    assert snap["pending"] == 2
    assert "online" in snap


# ---------- identidade persistida no LAB ----------
def _lab_db(tmp_path):
    db = tmp_path / "lab.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE messages(id TEXT PRIMARY KEY, author TEXT, target TEXT, "
        "content TEXT, kind TEXT, created_at REAL)"
    )
    conn.commit()
    conn.close()
    return db


def test_lab_insert_uses_real_agent_identity(tmp_path):
    """_insert_mentor_reply_sync must store the sender, not a hardcoded 'mentor'."""
    from core.lab_coordinator import LabCoordinator

    db = _lab_db(tmp_path)
    coord = LabCoordinator.__new__(LabCoordinator)
    coord.db_path = db
    coord._connect = lambda: sqlite3.connect(db)  # type: ignore[method-assign]

    now = time.time()
    assert coord._insert_mentor_reply_sync("m-1", "MR-1", "oi", now, "hermes") is True
    assert coord._insert_mentor_reply_sync("m-2", "MR-2", "oi", now, "mentor") is True
    # idempotencia por id
    assert coord._insert_mentor_reply_sync("m-1", "MR-1", "oi de novo", now, "hermes") is False

    conn = sqlite3.connect(db)
    rows = dict(conn.execute("SELECT id, author FROM messages").fetchall())
    conn.close()
    assert rows == {"m-1": "hermes", "m-2": "mentor"}


def test_lab_insert_defaults_to_mentor(tmp_path):
    from core.lab_coordinator import LabCoordinator

    db = _lab_db(tmp_path)
    coord = LabCoordinator.__new__(LabCoordinator)
    coord.db_path = db
    coord._connect = lambda: sqlite3.connect(db)  # type: ignore[method-assign]

    coord._insert_mentor_reply_sync("m-9", "MR-9", "sem agente", time.time())
    conn = sqlite3.connect(db)
    author = conn.execute("SELECT author FROM messages WHERE id='m-9'").fetchone()[0]
    conn.close()
    assert author == "mentor"
