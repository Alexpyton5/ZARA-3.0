"""
ZARA Project Memory (ZARA-PROJECT-MEMORY-001).

Memoria DO PROJETO (separada da User Memory): historia da ZARA que nao
depende da conversa do ChatGPT. Persiste Mentor Charter, Architecture,
Decisions, Current State, Roadmap.

Layout (spec do Mentor):
  %LOCALAPPDATA%\\ZARA3\\data\\project-memory\\
      project_memory.db
      mentor_context_latest.md
      vault\\          (arquivos markdown do projeto)
"""
from __future__ import annotations

import sqlite3
import json
import threading
import time
from pathlib import Path

from core.paths import user_data_dir


def _detect_real_obsidian_vault() -> Path | None:
    """Locate the most recently used real Obsidian vault, if available."""
    config_path = Path.home() / "AppData" / "Roaming" / "obsidian" / "obsidian.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        vaults = data.get("vaults", {})
        if not vaults:
            return None
        most_recent = max(vaults.values(), key=lambda value: value.get("ts", 0))
        vault_path = Path(most_recent["path"])
        return vault_path if vault_path.is_dir() else None
    except Exception:
        return None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_docs (
    key TEXT PRIMARY KEY,          -- charter | architecture | decisions | state | roadmap
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mentor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT
);
"""


class ProjectMemory:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (user_data_dir() / "data" / "project-memory")
        self.db_path = self.base_dir / "project_memory.db"
        self.vault_dir = self.base_dir / "vault"
        self.context_file = self.base_dir / "mentor_context_latest.md"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # ---- documentos do projeto ----

    def save_doc(self, key: str, title: str, content: str) -> None:
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO project_docs (key, title, content, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET title=excluded.title, "
                    "content=excluded.content, updated_at=excluded.updated_at",
                    (key, title, content, now),
                )
                conn.commit()
        # espelha no vault (markdown legivel)
        safe = key.replace(" ", "_")
        (self.vault_dir / f"{safe}.md").write_text(content, encoding="utf-8")

    def get_doc(self, key: str) -> dict | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM project_docs WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def list_docs(self) -> list[str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT key FROM project_docs").fetchall()
        return [r["key"] for r in rows]

    # ---- contexto do mentor ----

    def save_mentor_context(self, content: str) -> None:
        """Escreve mentor_context_latest.md (fonte da verdade para o proximo turno)."""
        self.context_file.write_text(content, encoding="utf-8")

    def load_mentor_context(self) -> str:
        if self.context_file.exists():
            return self.context_file.read_text(encoding="utf-8")
        return ""

    # ---- eventos do mentor ----

    def record_mentor_event(self, task_id: str, status: str, summary: str = "") -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO mentor_events (ts, task_id, status, summary) VALUES (?,?,?,?)",
                    (time.time(), task_id[:64], status[:16], summary[:500]),
                )
                conn.commit()

    def recent_events(self, limit: int = 20) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM mentor_events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]


def create_project_memory(base_dir: Path | None = None) -> ProjectMemory:
    return ProjectMemory(base_dir=base_dir)
