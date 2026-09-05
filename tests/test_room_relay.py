"""Focused proofs for the Room <-> OpenCode file relay (ZARA-OPENCODE-SAFE-RELAY-002).

Each test uses an isolated temporary store; nothing touches the repository or
any ZARA module. All assertions are read-only against the relay store.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.room_relay.relay_lib import EXECUTE_MARKER, RelayError, RelayStore

ROOT = Path(__file__).resolve().parents[1]
RELAY_PY = ROOT / "tools" / "room_relay" / "relay.py"


@pytest.fixture
def store(tmp_path):
    return RelayStore(tmp_path / "relay_store")


def _task(message_id="m-1", task_id="T-1", content="Inspect core/zara_orchestrator.py read-only."):
    return {
        "message_id": message_id,
        "sender": "room",
        "recipient": "opencode",
        "task_id": task_id,
        "type": "TASK",
        "content": content,
    }


def _result(task_id="T-1", content="inspection done", message_id=None):
    record = {
        "sender": "opencode",
        "recipient": "room",
        "task_id": task_id,
        "type": "RESULT",
        "content": content,
    }
    if message_id is not None:
        record["message_id"] = message_id
    return record


def test_read_only_task_delivered_exactly_once(store):
    stored = store.ingest(_task())
    assert stored["status"] == "PENDING"
    assert stored["authorization"] == "READ_ONLY"

    first = store.next_message()
    assert first["message_id"] == "m-1"
    assert first["delivered"] is True

    assert store.next_message() is None
    assert store.next_message() is None
    assert len(store.inbox_records()) == 1


def test_second_read_does_not_duplicate(store):
    store.ingest(_task())
    first = store.next_message()
    second = store.next_message()
    assert first is not None
    assert second is None
    status = store.status()
    assert status["inbox_pending"] == 0
    assert status["inbox_delivered"] == 1
    assert status["inbox_pending_ids"] == []
    assert status["inbox_delivered_ids"] == ["m-1"]


def test_peek_does_not_consume_delivery(store):
    store.ingest(_task())
    peeked = store.next_message(deliver=False)
    peeked_again = store.next_message(deliver=False)
    assert peeked["message_id"] == peeked_again["message_id"] == "m-1"
    assert peeked["delivered"] is False
    assert store.status()["inbox_pending"] == 1
    delivered = store.next_message()
    assert delivered["message_id"] == "m-1"
    assert store.next_message() is None


def test_result_appears_once_in_outbox(store):
    store.ingest(_task())
    store.next_message()
    sent = store.send(_result(message_id="out-1"))
    assert sent["status"] == "SENT"
    assert [r["message_id"] for r in store.outbox_records()] == ["out-1"]

    outbox_before = store.outbox_path.read_text(encoding="utf-8")
    with pytest.raises(RelayError, match="Duplicate message_id"):
        store.send(_result(message_id="out-1"))
    assert len(store.outbox_records()) == 1
    assert store.outbox_path.read_text(encoding="utf-8") == outbox_before


def test_content_without_execute_never_becomes_write_task(store):
    fake_command = "delete-everything --force /tmp/x"
    stored = store.ingest(_task(message_id="m-noexec", content=fake_command))
    assert stored["authorization"] == "READ_ONLY"

    delivered = store.next_message()
    assert delivered["authorization"] == "READ_ONLY"
    assert EXECUTE_MARKER not in delivered["content"]
    assert delivered["content"] == fake_command

    store.ingest(
        _task(
            message_id="m-exec",
            task_id="T-2",
            content=f"{EXECUTE_MARKER} implement tooling under tools/room_relay/",
        )
    )
    assert store.next_message()["authorization"] == "EXECUTE"
    assert store.next_message() is None


def test_duplicate_ingest_rejected(store):
    store.ingest(_task())
    with pytest.raises(RelayError, match="Duplicate message_id"):
        store.ingest(_task())
    assert len(store.inbox_records()) == 1
    assert store.inbox_path.read_text(encoding="utf-8").count("m-1") == 1


def test_append_only_history_preserved(store):
    store.ingest(_task("m-1"))
    store.ingest(_task("m-2", task_id="T-2"))
    inbox_before = store.inbox_path.read_text(encoding="utf-8")

    store.next_message()
    store.next_message()
    store.send(_result(task_id="T-1", content="done m-1"))
    outbox_after_first_send = store.outbox_path.read_text(encoding="utf-8")
    store.send(_result(task_id="T-2", content="done m-2"))

    assert store.inbox_path.read_text(encoding="utf-8") == inbox_before
    outbox = store.outbox_path.read_text(encoding="utf-8")
    assert outbox.startswith(outbox_after_first_send)
    assert outbox.count("\n") == 2


def test_ingest_validation_and_exit_codes(tmp_path):
    store_dir = tmp_path / "store"
    result = subprocess.run(
        [sys.executable, str(RELAY_PY), "ingest", "--store", str(store_dir), "--json", "not-json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "relay error" in result.stderr


def test_cli_round_trip_ingest_next_send_status(tmp_path):
    store_dir = tmp_path / "store"
    task = _task("cli-1", task_id="T-CLI", content="read-only relay smoke test")

    def run(*args):
        return subprocess.run(
            [sys.executable, str(RELAY_PY), *args, "--store", str(store_dir)],
            capture_output=True,
            text=True,
        )

    ingested = run("ingest", "--json", json.dumps(task))
    assert ingested.returncode == 0
    assert json.loads(ingested.stdout)["authorization"] == "READ_ONLY"

    nxt = run("next")
    assert nxt.returncode == 0
    assert json.loads(nxt.stdout)["message_id"] == "cli-1"

    again = run("next")
    assert again.returncode == 0
    assert "NO_PENDING_TASK" in again.stdout

    sent = run(
        "send",
        "--type",
        "RESULT",
        "--task-id",
        "T-CLI",
        "--sender",
        "opencode",
        "--recipient",
        "room",
        "--content",
        "done",
    )
    assert sent.returncode == 0
    assert json.loads(sent.stdout)["status"] == "SENT"

    status = run("status", "--json")
    data = json.loads(status.stdout)
    assert data["inbox_total"] == 1
    assert data["inbox_delivered"] == 1
    assert data["outbox_total"] == 1

    duplicate = run("ingest", "--json", json.dumps(task))
    assert duplicate.returncode == 1
    assert "Duplicate message_id" in duplicate.stderr


def test_cli_has_no_execute_or_run_subcommand(tmp_path):
    help_text = subprocess.run(
        [sys.executable, str(RELAY_PY), "--help"], capture_output=True, text=True
    ).stdout
    assert "{ingest,next,send,status}" in help_text
