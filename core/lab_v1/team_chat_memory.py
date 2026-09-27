"""Append-only, secret-free team-chat journal for the real Obsidian vault."""
from __future__ import annotations

import json
import hashlib
import re
from threading import RLock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.obsidian_memory import ObsidianMemoryManager

_ROLES = {"RESEARCHER", "ARCHITECT", "ENGINEER", "CODER", "TESTER", "REVIEWER", "CEO", "ZARA"}
_STATES = {"OBSERVED", "ANALYZING", "PLANNED", "IMPLEMENTING", "TESTING", "REVIEWING", "WAITING_CEO", "APPROVED", "REJECTED", "ROLLED_BACK"}
_SENSITIVE = re.compile(r"(?:api[_-]?key|password|passwd|secret|token|bearer)\s*[:=]", re.I)


class TeamChatMemory:
    """Obsidian is the shared journal; SQLite remains the live chat index."""

    def __init__(self, manager: ObsidianMemoryManager | None = None):
        self.manager = manager or ObsidianMemoryManager()
        self._write_lock = RLock()

    def append(self, *, mission_id: str, role: str, state: str, summary: str,
               evidence_refs: list[str] | None = None, next_action: str = "") -> dict[str, Any]:
        return self.append_once(
            mission_id=mission_id, role=role, state=state, summary=summary,
            evidence_refs=evidence_refs, next_action=next_action,
        )

    def append_once(self, *, mission_id: str, role: str, state: str, summary: str,
                    evidence_refs: list[str] | None = None, next_action: str = "",
                    record_id: str | None = None) -> dict[str, Any]:
        mission_id = str(mission_id or "").strip()
        role = str(role or "").strip().upper()
        state = str(state or "").strip().upper()
        summary = str(summary or "").strip()
        next_action = str(next_action or "").strip()
        if not mission_id or role not in _ROLES or state not in _STATES or not summary:
            raise ValueError("mensagem de equipe inválida")
        if _SENSITIVE.search(summary) or _SENSITIVE.search(next_action):
            raise ValueError("mensagem potencialmente sensível rejeitada")
        refs = [str(item).strip() for item in (evidence_refs or []) if str(item).strip()][:20]
        if any(len(ref) > 200 or _SENSITIVE.search(ref) for ref in refs):
            raise ValueError("referência de evidência inválida ou sensível")
        record = {
            "mission_id": mission_id[:160], "role": role, "state": state,
            "summary": summary[:4000], "evidence_refs": refs,
            "next_action": next_action[:1000],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if record_id:
            record["record_id"] = str(record_id)[:200]
        if not self.manager.available:
            return {"success": False, "state": "MEMORY_UNAVAILABLE", "record": record}
        folder = self.manager.vault_path / "Zara-Memoria" / "Chat-Lab"
        folder.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", mission_id)[:100]
        suffix = hashlib.sha256(mission_id.encode("utf-8")).hexdigest()[:12]
        path = folder / f"{safe_id}-{suffix}.md"
        line = "\n" + json.dumps(record, ensure_ascii=False) + "\n"
        with self._write_lock:
            if path.exists():
                if record_id:
                    marker = '"record_id": ' + json.dumps(record["record_id"], ensure_ascii=False)
                    # This vault file is bounded by the mission's own compact
                    # journal entries.  A direct marker search makes a replay
                    # of one canonical Lab message a no-op after restart.
                    if marker in path.read_text(encoding="utf-8"):
                        return {"success": True, "state": "ALREADY_SAVED", "path": str(path), "record": record}
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            else:
                path.write_text("---\ntitle: ZARA Lab — Chat " + safe_id + "\ncategory: team-chat\n---\n" + line, encoding="utf-8")
        return {"success": True, "state": "SAVED", "path": str(path), "record": record}


__all__ = ["TeamChatMemory"]
