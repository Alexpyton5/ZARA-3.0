"""Focused proofs for the ROOM_WORKER watcher (ZARA-OPENCODE-ROOM-WORKER-001).

The watcher must detect pending tasks, never deliver (exactly-once stays
exclusive to relay.py next), never execute content, stop immediately on
request, and audit append-only without logging task content.
"""

import json
import subprocess
import sys
from pathlib import Path

from tools.room_relay.relay_lib import RelayStore

ROOT = Path(__file__).resolve().parents[1]
WATCH_PY = ROOT / "tools" / "room_relay" / "watch.py"


def _task(message_id="w-1", task_id="T-W", content="read-only watch proof"):
    return {
        "message_id": message_id,
        "sender": "room",
        "recipient": "opencode",
        "task_id": task_id,
        "type": "TASK",
        "content": content,
    }


def _run_watch(store_dir, *extra, timeout=30):
    return subprocess.run(
        [sys.executable, str(WATCH_PY), "--store", str(store_dir), *extra],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_watch_once_detects_pending_without_delivering(tmp_path):
    store = RelayStore(tmp_path / "s")
    store.ingest(_task())
    result = _run_watch(store.dir, "--once")
    assert result.returncode == 0
    assert "NEW_TASK w-1" in result.stdout
    assert store.status()["inbox_pending"] == 1
    assert store.next_message()["message_id"] == "w-1"
    assert store.next_message() is None


def test_watch_audit_is_append_only_and_never_logs_content(tmp_path):
    store = RelayStore(tmp_path / "s")
    store.ingest(_task(content="secret-payload-xyz"))
    result = _run_watch(store.dir, "--once")
    assert result.returncode == 0
    audit_path = store.dir / "audit.jsonl"
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in entries] == ["watcher:start", "watcher:found", "watcher:once_done"]
    assert "w-1" in entries[1]["detail"]
    assert "secret-payload-xyz" not in audit_path.read_text(encoding="utf-8")
    assert "secret-payload-xyz" not in result.stdout


def test_watch_stop_file_stops_immediately(tmp_path):
    store = RelayStore(tmp_path / "s")
    stop_file = tmp_path / "stop.txt"
    stop_file.write_text("", encoding="utf-8")
    result = _run_watch(store.dir, "--stop-file", str(stop_file))
    assert result.returncode == 0
    assert "watcher:stop_file" in result.stdout
    audit = (store.dir / "audit.jsonl").read_text(encoding="utf-8")
    assert "watcher:stop_file" in audit
    assert "watcher:start" in audit


def test_watch_never_executes_or_alters_dangerous_content(tmp_path):
    store = RelayStore(tmp_path / "s")
    payload = "__import__('os').remove('should-not-be-removed')"
    store.ingest(_task(content=payload))
    inbox_before = store.inbox_path.read_text(encoding="utf-8")
    result = _run_watch(store.dir, "--once")
    assert result.returncode == 0
    assert store.inbox_path.read_text(encoding="utf-8") == inbox_before
    assert store.status()["inbox_pending"] == 1
    assert "should-not-be-removed" in store.inbox_path.read_text(encoding="utf-8")
    assert payload not in result.stdout


def test_watch_reports_no_pending_without_errors(tmp_path):
    store = RelayStore(tmp_path / "s")
    result = _run_watch(store.dir, "--once")
    assert result.returncode == 0
    assert "NEW_TASK" not in result.stdout
    assert "watcher:once_done" in result.stdout
