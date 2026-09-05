"""Core of the Room <-> OpenCode file relay (TASK_ID: ZARA-OPENCODE-SAFE-RELAY-002).

Safety invariants
-----------------
* Append-only: ``inbox.jsonl`` and ``outbox.jsonl`` are never rewritten,
  truncated, or edited in place. History is never destroyed.
* Dedupe by ``message_id``: a message_id already present in inbox or outbox is
  rejected.
* Content is never executed: received content is data only. There is no eval,
  exec, subprocess, URL handling, or action dispatch anywhere in this package
  or its CLI.
* Authorization is explicit: inbox TASK records are tagged ``READ_ONLY``
  unless their content contains the literal ``EXECUTE`` marker. Only
  EXECUTE-tagged tasks may later be treated as write tasks, and that decision
  always belongs to the executor, never to the relay.
* Reversible: the only mutable artifact is ``state.json`` (the set of
  delivered message_ids). Deleting or clearing it returns inbox records to
  PENDING without touching any history file.
* No secrets: this relay never reads or writes .env, tokens, cookies,
  passwords, browser profiles, or session stores. No browser automation.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

INBOX_FILE = "inbox.jsonl"
OUTBOX_FILE = "outbox.jsonl"
STATE_FILE = "state.json"
AUDIT_FILE = "audit.jsonl"

REQUIRED_FIELDS = (
    "message_id",
    "timestamp",
    "sender",
    "recipient",
    "task_id",
    "type",
    "content",
    "status",
)
INBOX_TYPES = ("TASK",)
OUTBOX_TYPES = ("RESULT", "BLOCKER", "QUESTION")
EXECUTE_MARKER = "EXECUTE"
AUTH_READ_ONLY = "READ_ONLY"
STATUS_PENDING = "PENDING"
STATUS_SENT = "SENT"


class RelayError(Exception):
    """Raised for validation, duplicate, or consistency failures."""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_common(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise RelayError("Record must be an object")
    for field in ("message_id", "sender", "recipient", "task_id", "content"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RelayError(f"Field {field!r} must be a non-empty string")
    if not isinstance(record["type"], str) or not record["type"].strip():
        raise RelayError("Field 'type' must be a non-empty string")
    timestamp = record.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        raise RelayError("Field 'timestamp' must be an ISO-8601 string when provided")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RelayError(f"{path.name}:{lineno}: invalid JSON line: {exc}") from exc
            if not isinstance(parsed, dict):
                raise RelayError(f"{path.name}:{lineno}: record is not an object")
            records.append(parsed)
    return records


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class RelayStore:
    """Append-only JSONL store with dedupe and explicit authorization."""

    def __init__(self, store_dir: str | os.PathLike[str]) -> None:
        self.dir = Path(store_dir)
        self.inbox_path = self.dir / INBOX_FILE
        self.outbox_path = self.dir / OUTBOX_FILE
        self.state_path = self.dir / STATE_FILE

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for path in (self.inbox_path, self.outbox_path):
            if not path.exists():
                path.touch()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"delivered": []}
        try:
            with self.state_path.open("r", encoding="utf-8") as fh:
                state = json.load(fh)
        except json.JSONDecodeError as exc:
            raise RelayError(
                f"{STATE_FILE} is corrupted; restore or delete it (history files are untouched)"
            ) from exc
        delivered = state.get("delivered")
        if not isinstance(delivered, list):
            raise RelayError(f"{STATE_FILE} has an invalid 'delivered' list")
        return {"delivered": [str(item) for item in delivered]}

    def _save_state(self, state: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=str(self.dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, ensure_ascii=False, sort_keys=True, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _known_ids(self) -> set[str]:
        ids: set[str] = set()
        for path in (self.inbox_path, self.outbox_path):
            for record in _read_jsonl(path):
                if record.get("message_id"):
                    ids.add(str(record["message_id"]))
        return ids

    def inbox_records(self) -> list[dict[str, Any]]:
        self._ensure()
        return _read_jsonl(self.inbox_path)

    def outbox_records(self) -> list[dict[str, Any]]:
        self._ensure()
        return _read_jsonl(self.outbox_path)

    def pending_records(self) -> list[dict[str, Any]]:
        """Undelivered inbox records, in file order. Read-only, never marks."""
        self._ensure()
        delivered = set(self._load_state()["delivered"])
        return [r for r in self.inbox_records() if str(r.get("message_id")) not in delivered]

    def audit(self, event: str, detail: str = "") -> dict[str, Any]:
        """Append one entry to the append-only audit log. Never contains content."""
        self._ensure()
        entry = {"timestamp": _utcnow_iso(), "event": event, "detail": detail}
        _append_jsonl(self.dir / AUDIT_FILE, entry)
        return entry

    def ingest(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append a Room -> OpenCode TASK record to inbox.jsonl.

        Raises RelayError on invalid records or duplicate message_id.
        """
        self._ensure()
        _validate_common(record)
        rtype = record["type"]
        if rtype not in INBOX_TYPES:
            raise RelayError(f"ingest only accepts types {INBOX_TYPES}, got {rtype!r}")
        message_id = record["message_id"]
        if message_id in self._known_ids():
            raise RelayError(f"Duplicate message_id {message_id!r} (already in inbox or outbox)")
        content = record["content"]
        authorization = EXECUTE_MARKER if EXECUTE_MARKER in content else AUTH_READ_ONLY
        stored = {
            "message_id": message_id,
            "timestamp": record.get("timestamp") or _utcnow_iso(),
            "sender": record["sender"],
            "recipient": record["recipient"],
            "task_id": record["task_id"],
            "type": rtype,
            "content": content,
            "status": STATUS_PENDING,
            "authorization": authorization,
        }
        _append_jsonl(self.inbox_path, stored)
        return stored

    def next_message(self, *, deliver: bool = True) -> dict[str, Any] | None:
        """Return the next undelivered inbox record (first in file order).

        With deliver=True (default) the message_id is recorded as delivered in
        state.json, so each message is returned exactly once. The inbox file
        itself is never rewritten.
        """
        self._ensure()
        delivered = set(self._load_state()["delivered"])
        for record in self.inbox_records():
            if record.get("message_id") in delivered:
                continue
            result = dict(record)
            if deliver:
                delivered.add(str(record["message_id"]))
                self._save_state({"delivered": sorted(delivered)})
                result["delivered"] = True
            else:
                result["delivered"] = False
            return result
        return None

    def send(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append an OpenCode -> Room RESULT/BLOCKER/QUESTION record to outbox.jsonl.

        A message_id is generated when not provided. Raises RelayError on
        duplicate message_id or invalid records.
        """
        self._ensure()
        if not isinstance(record, dict):
            raise RelayError("Record must be an object")
        rtype = record.get("type")
        if rtype not in OUTBOX_TYPES:
            raise RelayError(f"send only accepts types {OUTBOX_TYPES}, got {rtype!r}")
        message_id = record.get("message_id") or uuid.uuid4().hex
        record = {**record, "message_id": message_id}
        _validate_common(record)
        if message_id in self._known_ids():
            raise RelayError(f"Duplicate message_id {message_id!r} (already in inbox or outbox)")
        stored = {
            "message_id": message_id,
            "timestamp": record.get("timestamp") or _utcnow_iso(),
            "sender": record["sender"],
            "recipient": record["recipient"],
            "task_id": record["task_id"],
            "type": rtype,
            "content": record["content"],
            "status": STATUS_SENT,
        }
        _append_jsonl(self.outbox_path, stored)
        return stored

    def status(self) -> dict[str, Any]:
        self._ensure()
        inbox = self.inbox_records()
        outbox = self.outbox_records()
        delivered = set(self._load_state()["delivered"])
        pending_ids = [str(r["message_id"]) for r in inbox if str(r["message_id"]) not in delivered]
        delivered_ids = [str(r["message_id"]) for r in inbox if str(r["message_id"]) in delivered]
        return {
            "inbox_total": len(inbox),
            "inbox_pending": len(pending_ids),
            "inbox_delivered": len(delivered_ids),
            "inbox_pending_ids": pending_ids,
            "inbox_delivered_ids": delivered_ids,
            "outbox_total": len(outbox),
            "outbox_ids": [str(r["message_id"]) for r in outbox],
        }
