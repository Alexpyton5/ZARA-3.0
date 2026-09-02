"""Persistent conversation memory backed by SQLite and FTS5."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ConversationMemory:
    """Small thread-safe store with a normal table plus an FTS5 index."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            from core.paths import user_data_dir

            db_path = user_data_dir() / "data" / "memory" / "conversation_memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'user',
                    user_text TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT 'null',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
                    user_text, action, result
                );
                CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                    INSERT INTO conversations_fts(rowid,user_text,action,result)
                    VALUES(new.id,new.user_text,new.action,new.result_json);
                END;
                CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                    INSERT INTO conversations_fts(conversations_fts,rowid,user_text,action,result)
                    VALUES('delete',old.id,old.user_text,old.action,old.result_json);
                END;
                CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                    INSERT INTO conversations_fts(conversations_fts,rowid,user_text,action,result)
                    VALUES('delete',old.id,old.user_text,old.action,old.result_json);
                    INSERT INTO conversations_fts(rowid,user_text,action,result)
                    VALUES(new.id,new.user_text,new.action,new.result_json);
                END;
                """
            )

    @staticmethod
    def _decode(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _row(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "session_id": row["session_id"],
            "role": row["role"],
            "user_text": row["user_text"],
            "action": row["action"],
            "result": cls._decode(row["result_json"], row["result_json"]),
            "metadata": cls._decode(row["metadata_json"], {}),
            "created_at": float(row["created_at"]),
        }

    def add(
        self,
        user_text: str,
        action: str = "",
        result: Any = None,
        *,
        session_id: str = "",
        role: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO conversations(
                    session_id,role,user_text,action,result_json,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    str(session_id), str(role), str(user_text), str(action),
                    json.dumps(result, ensure_ascii=False, default=str),
                    json.dumps(metadata or {}, ensure_ascii=False, default=str), time.time(),
                ),
            )
            return int(cursor.lastrowid)

    def search(self, query: str, limit: int = 10, session_id: str | None = None) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 100))
        sql = (
            "SELECT c.* FROM conversations_fts f JOIN conversations c ON c.id=f.rowid "
            "WHERE conversations_fts MATCH ?"
        )
        params: list[Any] = [query]
        if session_id is not None:
            sql += " AND c.session_id=?"
            params.append(str(session_id))
        sql += " ORDER BY bm25(conversations_fts), c.created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                escaped = '"' + query.replace('"', '""') + '"'
                params[0] = escaped
                rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def recent(self, limit: int = 20, session_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM conversations"
        params: list[Any] = []
        if session_id is not None:
            sql += " WHERE session_id=?"
            params.append(str(session_id))
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._lock, self._connect() as conn:
            return [self._row(row) for row in conn.execute(sql, params).fetchall()]

    def delete(self, entry_id: int) -> bool:
        with self._lock, self._connect() as conn:
            return conn.execute("DELETE FROM conversations WHERE id=?", (int(entry_id),)).rowcount == 1


_default: ConversationMemory | None = None
_default_lock = threading.Lock()


def get_memory() -> ConversationMemory:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = ConversationMemory()
    return _default


def add_entry(user_text: str, action: str, result: Any) -> int:
    return get_memory().add(user_text, action, result)


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    return get_memory().search(query, limit)
