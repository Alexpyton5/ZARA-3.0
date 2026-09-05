"""Persistent operational context: last window, folder and volume."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ContextualMemory:
    VALID_KEYS = frozenset({"last_window", "last_folder", "last_volume"})

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            from core.paths import user_data_dir

            db_path = user_data_dir() / "data" / "memory" / "contextual_memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS context(key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at REAL NOT NULL)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def set(self, key: str, value: Any) -> None:
        if key not in self.VALID_KEYS:
            raise ValueError(f"Chave contextual invalida: {key}")
        if key == "last_volume":
            value = int(value)
            if not 0 <= value <= 100:
                raise ValueError("Volume deve estar entre 0 e 100")
        if key == "last_folder":
            value = str(Path(value).expanduser().resolve())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO context(key,value_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False, default=str), time.time()),
            )

    def get(self, key: str, default: Any = None, max_age_seconds: float | None = None) -> Any:
        if key not in self.VALID_KEYS:
            raise ValueError(f"Chave contextual invalida: {key}")
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value_json,updated_at FROM context WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        if max_age_seconds is not None and time.time() - float(row["updated_at"]) > float(max_age_seconds):
            return default
        try:
            return json.loads(row["value_json"])
        except (TypeError, ValueError):
            return default

    def snapshot(self, max_age_seconds: float | None = None) -> dict[str, Any]:
        return {key: self.get(key, max_age_seconds=max_age_seconds) for key in sorted(self.VALID_KEYS)}

    def set_last_window(self, value: Any) -> None:
        self.set("last_window", value)

    def set_last_folder(self, value: str | Path) -> None:
        self.set("last_folder", value)

    def set_last_volume(self, value: int) -> None:
        self.set("last_volume", value)

    def get_last_window(self, default: Any = None) -> Any:
        return self.get("last_window", default)

    def get_last_folder(self, default: Any = None) -> Any:
        return self.get("last_folder", default)

    def get_last_volume(self, default: Any = None) -> Any:
        return self.get("last_volume", default)
