"""ZARA action audit log (ZARA-PC-CONTROL-POLICY-HARDENING-001).

Registra execucoes de acoes MEDIUM/HIGH sem conteudo sensivel:
apenas id da acao, risco, resultado, timestamp. NUNCA parametros crus.

FRENTE B3 (GIGANTE 3): + colunas autonomous (0/1) e why (motivo curto).
Migracao automatica: ALTER TABLE ADD COLUMN se a coluna nao existir.
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
            # FRENTE B3: migracao idempotente para autonomous/why.
            for col, ddl in (
                ("autonomous", "ALTER TABLE audit ADD COLUMN autonomous INTEGER NOT NULL DEFAULT 0"),
                ("why", "ALTER TABLE audit ADD COLUMN why TEXT NOT NULL DEFAULT ''"),
            ):
                try:
                    cols = [r[1] for r in conn.execute("PRAGMA table_info(audit)").fetchall()]
                    if col not in cols:
                        conn.execute(ddl)
                except Exception:
                    pass
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def record(
        self,
        action: str,
        risk: str,
        outcome: str,
        error: str | None = None,
        autonomous: bool = False,
        why: str = "",
    ) -> None:
        """Registra uma execucao/bloqueio. NUNCA recebe parametros crus.

        autonomous=True + why="autonomia:acao-direta" para acoes diretas
        no modo autonomo (FRENTE B3). Bloqueios usam outcome="blocked".
        """
        try:
            with self._lock, self._connect() as conn:
                try:
                    conn.execute(
                        "INSERT INTO audit (ts, action, risk, outcome, error, autonomous, why)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (
                            time.time(),
                            action[:64],
                            risk,
                            outcome[:16],
                            (error or "")[:200],
                            1 if autonomous else 0,
                            str(why or "")[:140],
                        ),
                    )
                except Exception:
                    # Tabela antiga sem as colunas (migracao nao aplicada):
                    # cai para o schema legado sem quebrar o caminho da acao.
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
        result = []
        for r in rows:
            d = dict(r)
            # Normaliza para o schema B3 mesmo em DBs legados.
            d.setdefault("autonomous", 0)
            d.setdefault("why", "")
            result.append(d)
        return result


_audit = AuditLog()


def audit_log() -> AuditLog:
    return _audit
