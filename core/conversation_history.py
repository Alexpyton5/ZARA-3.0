"""Bounded, local-only persistence for the Home conversation log.

This store is intentionally separate from semantic and episodic memory.  It is
the renderer's durable transcript, not knowledge that should be injected into
future model prompts.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Any

from core.paths import data_dir

ALLOWED_ROLES = frozenset({"user", "assistant", "system"})
MAX_MESSAGES = 500
MAX_CONTENT_CHARS = 12_000
MAX_ENGINE_CHARS = 64
RETENTION_DAYS = 180
DEFAULT_LIST_LIMIT = 200


class ConversationHistory:
    """Keep a small private transcript in the user's local ZARA data folder."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_messages: int = MAX_MESSAGES,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self.path = Path(path) if path is not None else data_dir() / "conversation_history.sqlite3"
        self.max_messages = max(1, int(max_messages))
        self.retention_days = max(1, int(retention_days))
        self._lock = Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                engine TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_created_at "
            "ON conversation_messages(created_at DESC, sequence DESC)"
        )
        return connection

    @staticmethod
    def _clean_content(content: str) -> str:
        value = str(content or "").replace("\x00", "").strip()
        if not value:
            raise ValueError("conversation content cannot be empty")
        return value[:MAX_CONTENT_CHARS]

    @staticmethod
    def _clean_role(role: str) -> str:
        value = str(role or "").strip().lower()
        if value not in ALLOWED_ROLES:
            raise ValueError("invalid conversation role")
        return value

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "role": str(row["role"]),
            "content": str(row["content"]),
            "engine": str(row["engine"]),
            "timestamp": int(row["created_at"]),
        }

    def _prune(self, connection: sqlite3.Connection, now_ms: int) -> None:
        cutoff_ms = now_ms - (self.retention_days * 24 * 60 * 60 * 1000)
        connection.execute(
            "DELETE FROM conversation_messages WHERE created_at < ?",
            (cutoff_ms,),
        )
        connection.execute(
            """
            DELETE FROM conversation_messages
            WHERE sequence NOT IN (
                SELECT sequence FROM conversation_messages
                ORDER BY created_at DESC, sequence DESC
                LIMIT ?
            )
            """,
            (self.max_messages,),
        )

    def append(
        self,
        role: str,
        content: str,
        *,
        engine: str = "",
        timestamp: int | None = None,
    ) -> dict[str, Any]:
        """Persist one normalized message and return its public representation."""
        safe_role = self._clean_role(role)
        safe_content = self._clean_content(content)
        safe_engine = str(engine or "").replace("\x00", "").strip()[:MAX_ENGINE_CHARS]
        now_ms = max(0, int(timestamp if timestamp is not None else time.time() * 1000))
        message_id = uuid.uuid4().hex

        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO conversation_messages(id, role, content, engine, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, safe_role, safe_content, safe_engine, now_ms),
            )
            self._prune(connection, now_ms)
            connection.commit()

        return {
            "id": message_id,
            "role": safe_role,
            "content": safe_content,
            "engine": safe_engine,
            "timestamp": now_ms,
        }

    def list_recent(self, limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
        """Return recent messages in display order (oldest first)."""
        safe_limit = max(1, min(int(limit), self.max_messages))
        now_ms = int(time.time() * 1000)
        with self._lock, closing(self._connect()) as connection:
            self._prune(connection, now_ms)
            rows = connection.execute(
                """
                SELECT id, role, content, engine, created_at
                FROM conversation_messages
                ORDER BY created_at DESC, sequence DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            connection.commit()
        return [self._row_to_message(row) for row in reversed(rows)]

    def clear(self) -> int:
        """Delete the complete transcript, including SQLite journal files."""
        with self._lock:
            count = 0
            if self.path.exists():
                with closing(self._connect()) as connection:
                    count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM conversation_messages"
                        ).fetchone()[0]
                    )

            # Every operation uses a short-lived connection, so no handle is
            # open here. Removing the database and WAL/SHM files makes CLEAR a
            # physical reset instead of merely hiding rows from the interface.
            for candidate in (
                self.path,
                Path(f"{self.path}-wal"),
                Path(f"{self.path}-shm"),
            ):
                candidate.unlink(missing_ok=True)
            return count
