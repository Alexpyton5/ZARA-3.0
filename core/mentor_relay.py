"""ZARA Mentor Relay 001

A truthful, zero-cost bridge contract between the local ZARA LAB and the
external Mentor conversation, carried by an external continuity process.

This module does NOT embed ChatGPT, does NOT use OpenAI API keys, and does NOT
pretend a local model is the Mentor.

Protocol folders:
%LOCALAPPDATA%/ZARA3/data/mentor-relay/
  outbox/   ZARA -> continuity process -> Mentor
  inbox/    continuity process -> ZARA
  archive/  consumed replies / processed outbound messages
  status.json  heartbeat written by the external continuity process

All writes are atomic JSON files. No secrets are required.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class RelayStatus:
    state: str
    detail: str
    online: bool
    updated_at: float | None
    age_seconds: float | None


class MentorRelay:
    HEARTBEAT_TTL_SECONDS = 90

    def __init__(self, root: str | Path | None = None):
        if root is None:
            from core.paths import user_data_dir
            root = user_data_dir() / "data" / "mentor-relay"
        self.root = Path(root)
        self.outbox = self.root / "outbox"
        self.inbox = self.root / "inbox"
        self.archive = self.root / "archive"
        self.status_path = self.root / "status.json"
        for p in (self.outbox, self.inbox, self.archive):
            p.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_json(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def status(self) -> RelayStatus:
        now = time.time()
        if not self.status_path.exists():
            return RelayStatus(
                state="EXTERNAL",
                detail="Relay ainda não publicou heartbeat.",
                online=False,
                updated_at=None,
                age_seconds=None,
            )
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
            updated = float(data.get("updated_at") or 0)
            age = max(0.0, now - updated)
            declared = str(data.get("state") or "OFFLINE").upper()
            online = declared in {"ONLINE", "READY"} and age <= self.HEARTBEAT_TTL_SECONDS
            if online:
                return RelayStatus(
                    state="ONLINE VIA RELAY",
                    detail="Conectado ao Mentor externo pela ponte de continuidade.",
                    online=True,
                    updated_at=updated,
                    age_seconds=age,
                )
            return RelayStatus(
                state="RELAY OFFLINE",
                detail="Mensagens ao Mentor serão preservadas na fila até a ponte voltar.",
                online=False,
                updated_at=updated,
                age_seconds=age,
            )
        except Exception:
            return RelayStatus(
                state="RELAY ERROR",
                detail="Heartbeat do Mentor Relay está inválido.",
                online=False,
                updated_at=None,
                age_seconds=None,
            )

    def enqueue(self, author: str, content: str) -> dict[str, Any]:
        relay_id = f"MR-{int(time.time())}-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "schema": 1,
            "relay_id": relay_id,
            "direction": "ZARA_TO_MENTOR",
            "author": str(author or "alex").lower(),
            "content": str(content or "").strip(),
            "created_at": time.time(),
            "status": "PENDING",
            "conversation_scope": "ZARA3_MAIN_MENTOR",
        }
        if not payload["content"]:
            raise ValueError("Mensagem vazia")
        self._atomic_json(self.outbox / f"{relay_id}.json", payload)
        return payload

    def pending_count(self) -> int:
        return sum(1 for p in self.outbox.glob("MR-*.json") if p.is_file())

    def drain_replies(self, limit: int = 20) -> list[dict[str, Any]]:
        """Consume only well-formed replies written by the external relay."""
        replies: list[dict[str, Any]] = []
        for path in sorted(self.inbox.glob("MR-*.json"), key=lambda p: p.stat().st_mtime)[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                relay_id = str(data.get("relay_id") or "").strip()
                content = str(data.get("content") or "").strip()
                if (
                    not relay_id.startswith("MR-")
                    or data.get("direction") != "MENTOR_TO_ZARA"
                    or not content
                ):
                    raise ValueError("invalid relay reply")
                replies.append({
                    "relay_id": relay_id,
                    "content": content,
                    "created_at": float(data.get("created_at") or time.time()),
                    "source": str(data.get("source") or "mentor_external"),
                    # Preserve the real sender identity so another agent's message
                    # is never rendered as if the Mentor had written it.
                    "agent": str(data.get("agent") or "mentor").strip().lower() or "mentor",
                    "task_id": data.get("task_id"),
                })
                archive_path = self.archive / f"{relay_id}.reply.json"
                if archive_path.exists():
                    # Ja entregue uma vez: duplicata nao pode ser reentregue.
                    replies.pop()
                    dup = self.archive / f"{path.stem}.duplicate-{int(time.time())}.json"
                    os.replace(path, dup)
                    continue
                os.replace(path, archive_path)
            except Exception:
                bad = self.archive / f"{path.stem}.invalid-{int(time.time())}.json"
                try:
                    os.replace(path, bad)
                except Exception:
                    pass
        return replies

    def mark_outbound_processed(self, relay_id: str) -> None:
        src = self.outbox / f"{relay_id}.json"
        if not src.exists():
            return
        dest = self.archive / f"{relay_id}.request.json"
        if dest.exists():
            dest.unlink()
        os.replace(src, dest)

    def _load_outbound(self, relay_id: str) -> tuple[Path, dict[str, Any]] | None:
        src = self.outbox / f"{relay_id}.json"
        if not src.exists():
            return None
        try:
            return src, json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            return src, {}

    def mark_outbound_delivered(self, relay_id: str, detail: str = "") -> bool:
        """Archive an outbound message ONLY when it was really delivered.

        Returns False when the id is unknown, so a caller can never report a
        delivery that did not happen.
        """
        loaded = self._load_outbound(relay_id)
        if loaded is None:
            return False
        src, payload = loaded
        payload["status"] = "DELIVERED"
        payload["delivered_at"] = time.time()
        if detail:
            payload["delivery_detail"] = str(detail)[:200]
        dest = self.archive / f"{relay_id}.request.json"
        self._atomic_json(dest, payload)
        try:
            src.unlink()
        except OSError:
            return False
        return True

    def mark_outbound_failed(self, relay_id: str, reason: str = "") -> bool:
        """Record a real failure and KEEP the message queued for retry.

        A failed send must never look delivered and must never silently vanish.
        """
        loaded = self._load_outbound(relay_id)
        if loaded is None:
            return False
        src, payload = loaded
        payload["status"] = "FAILED"
        payload["attempts"] = int(payload.get("attempts") or 0) + 1
        payload["failed_at"] = time.time()
        # Sanitized: only a short, non-sensitive reason is persisted.
        payload["last_error"] = " ".join(str(reason).split())[:200]
        self._atomic_json(src, payload)
        return True

    def snapshot(self) -> dict[str, Any]:
        s = self.status()
        data = asdict(s)
        data["pending"] = self.pending_count()
        return data
