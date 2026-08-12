"""OpenCode <-> ZARA LAB bridge (TASK_ID: ZARA-LAB-OPENCODE-UNIFIED-002).

Routes ZARA LAB messages to OpenCode through the append-only file relay and
imports OpenCode replies back into the LAB chat.

Invariants
----------
* Never executes content: the bridge only moves data between the LAB and the
  relay store.
* EXECUTE gate preserved: authorization is derived from the relay marker in
  the message itself. The literal EXECUTE marker is redacted from any injected
  LAB context so context can never loosen the gate.
* Exactly-once: enqueue deduplicates by task_id; imported replies are tracked
  so a reply never appears twice in the LAB.
* Scope: the bridge only ever writes inside the relay store directory.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from tools.room_relay.relay_lib import EXECUTE_MARKER, RelayStore

DEFAULT_STORE = Path(__file__).resolve().parent / "relay_store"
IMPORTED_FILE = "imported.json"
MENTION_RE = re.compile(r"^@OPENCODE\b", re.IGNORECASE)
_CONTEXT_REDACTED = "[RELAY_CONTEXT_REDACTED]"
_CONTEXT_LIMIT = 6


def resolve_lab_target(target: str, content: str) -> str:
    """Route @OPENCODE mentions to the opencode worker regardless of dropdown.

    Returns the original target when the message is not an OpenCode mention,
    so no other recipient ever has its messages redirected.
    """
    if MENTION_RE.match((content or "").strip()):
        return "opencode"
    return (target or "").strip().lower()


class OpenCodeBridge:
    """LAB <-> OpenCode transport adapter over RelayStore."""

    def __init__(self, store_dir: str | os.PathLike[str] | None = None) -> None:
        self.store = RelayStore(store_dir or DEFAULT_STORE)

    def enqueue(
        self,
        author: str,
        content: str,
        task_id: str | None = None,
        recent: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Queue a LAB message as a relay TASK for OpenCode.

        Returns QUEUED metadata (task_id, message_id, authorization). Raises
        RelayError when the relay store rejects the record.
        """
        content = (content or "").strip()
        task_id = task_id or f"LAB-{uuid.uuid4().hex[:10].upper()}"
        for pending in self.store.pending_records():
            if str(pending.get("task_id")) == task_id:
                return {
                    "success": True,
                    "state": "QUEUED",
                    "duplicate": True,
                    "message_id": str(pending.get("message_id")),
                    "task_id": task_id,
                    "authorization": str(pending.get("authorization") or "READ_ONLY"),
                }
        stored = self.store.ingest(
            {
                "message_id": f"lab-{task_id}",
                "sender": (author or "alex").strip().lower(),
                "recipient": "opencode",
                "task_id": task_id,
                "type": "TASK",
                "content": self._envelope(content, recent),
            }
        )
        return {
            "success": True,
            "state": "QUEUED",
            "message_id": stored["message_id"],
            "task_id": stored["task_id"],
            "authorization": stored["authorization"],
        }

    def _envelope(self, message: str, recent: list[dict[str, Any]] | None) -> str:
        context = [
            {"author": str(item.get("author") or "")[:32], "content": self._redact(str(item.get("content") or ""))}
            for item in (recent or [])
        ][-_CONTEXT_LIMIT:]
        return json.dumps({"message": message, "recent_lab": context}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _redact(content: str) -> str:
        return content.replace(EXECUTE_MARKER, _CONTEXT_REDACTED)

    def drain_replies(self, limit: int = 20) -> list[dict[str, Any]]:
        """Un-imported outbox records (RESULT/BLOCKER/QUESTION/OPINION/PRESENCE_PROOF)."""
        imported = self._imported_ids()
        replies: list[dict[str, Any]] = []
        for record in self.store.outbox_records():
            if str(record.get("message_id")) in imported:
                continue
            replies.append(record)
            if len(replies) >= limit:
                break
        return replies

    def mark_imported(self, message_id: str) -> None:
        """Record an outbox message_id as imported (never re-delivered)."""
        ids = self._imported_ids()
        ids.add(message_id)
        self._save_imported(ids)

    def _imported_ids(self) -> set[str]:
        path = self.store.dir / IMPORTED_FILE
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data.get("imported", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def _save_imported(self, ids: set[str]) -> None:
        path = self.store.dir / IMPORTED_FILE
        self.store.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.store.dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"imported": sorted(ids)}, fh, ensure_ascii=False, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
