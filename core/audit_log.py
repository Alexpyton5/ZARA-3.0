"""ZARA action audit log (ZARA-PC-CONTROL-POLICY-HARDENING-001).

Registra execucoes de acoes MEDIUM/HIGH sem conteudo sensivel:
apenas id da acao, risco, resultado, timestamp. NUNCA parametros crus.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from core.paths import user_data_dir


class AuditLog:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (user_data_dir() / "data" / "audit" / "action_audit.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    action TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def record(self, action: str, risk: str, outcome: str, error: str | None = None) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO audit (ts, action, risk, outcome, error) VALUES (?,?,?,?,?)",
                    (time.time(), action[:64], risk, outcome[:16], (error or "")[:200]),
                )
                conn.commit()
        except Exception:
            pass  # audit never breaks the action path

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


_audit = AuditLog()


def audit_log() -> AuditLog:
    return _audit
