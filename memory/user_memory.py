"""
ZARA User Memory Core (ZARA-USER-MEMORY-DESIGN-001).

Nucleo separado da Project Memory. Guarda fatos SEMANTICOS estruturados
sobre o usuario (Alex) com:

  - timestamp (created_at / updated_at / last_used)
  - source / conversation ref
  - confidence (0..1)
  - status: active | confirmed | corrected | forgotten
  - confirm / correct / forget
  - busca por intervalo temporal + busca lexica/semantica simples

Categorias:
  - episodic_ref   : o que aconteceu / quando (aponta para episodios)
  - semantic_fact  : fatos estaveis aprendidos
  - preference     : gostos / preferencias
  - relationship   : estilo de interacao / relacao

NUNCA armazena secrets / API keys (rejeitado na escrita).
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from core.paths import user_data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_facts (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    fact TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.6,
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL DEFAULT 'manual',
    ref TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_used REAL
);
CREATE INDEX IF NOT EXISTS idx_user_facts_cat ON user_facts(category);
CREATE INDEX IF NOT EXISTS idx_user_facts_status ON user_facts(status);
CREATE INDEX IF NOT EXISTS idx_user_facts_created ON user_facts(created_at);
"""

_SENSITIVE = re.compile(
    r"(api[_-]?key|secret|password|token|senha|credential|authorization|bearer\s+[a-z0-9]|"
    r"sk-[a-z0-9]{8}|nvapi-[a-z0-9]{8}|gsk_[a-z0-9]{8}|AIza[a-z0-9]{8}|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----)",
    re.IGNORECASE,
)

VALID_CATEGORIES = {"episodic_ref", "semantic_fact", "preference", "relationship"}


class UserMemoryCore:
    """Fatos semanticos persistentes sobre o usuario."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (user_data_dir() / "data" / "user_memory" / "user_facts.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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

    # ---- CRUD ----

    def add(self, fact: str, *, category: str = "semantic_fact",
            confidence: float = 0.6, source: str = "manual", ref: str | None = None) -> dict:
        """Add a semantic fact about the user. Rejects secrets."""
        fact = " ".join((fact or "").split())
        if not fact:
            raise ValueError("fato vazio")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"categoria invalida: {category}")
        if _SENSITIVE.search(fact):
            raise ValueError("conteudo sensivel rejeitado (nunca armazenamos secrets)")
        confidence = max(0.0, min(1.0, float(confidence)))
        now = time.time()
        rid = uuid.uuid4().hex[:16]
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO user_facts (id, category, fact, confidence, status, source, ref, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (rid, category, fact, confidence, "active", source[:48], ref, now, now),
                )
                conn.commit()
        return self.get(rid)

    def get(self, rid: str) -> dict | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM user_facts WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None

    def list(self, category: str | None = None, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM user_facts WHERE 1=1"
        args: list = []
        if category:
            sql += " AND category=?"
            args.append(category)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY updated_at DESC"
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, *, category: str | None = None,
               since: float | None = None, until: float | None = None,
               limit: int = 5) -> list[dict]:
        """Busca por intervalo temporal + correspondencia lexica simples."""
        q = (query or "").strip().lower()
        tokens = set(re.findall(r"[a-z0-9à-ú]{3,}", q))
        with self._lock:
            with self._connect() as conn:
                sql = "SELECT * FROM user_facts WHERE status != 'forgotten'"
                args: list = []
                if category:
                    sql += " AND category=?"
                    args.append(category)
                if since is not None:
                    sql += " AND created_at >= ?"
                    args.append(since)
                if until is not None:
                    sql += " AND created_at <= ?"
                    args.append(until)
                sql += " ORDER BY updated_at DESC"
                rows = conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            fact_lower = (r["fact"] or "").lower()
            if tokens:
                fact_tokens = set(re.findall(r"[a-z0-9à-ú]{3,}", fact_lower))
                score = len(tokens.intersection(fact_tokens)) / max(1, len(tokens))
                if score <= 0.0:
                    continue
            else:
                score = 1.0
            d = dict(r)
            d["_score"] = round(score, 3)
            out.append(d)
        out.sort(key=lambda x: (x["_score"], x["updated_at"]), reverse=True)
        return out[:max(1, min(limit, 20))]

    def confirm(self, rid: str) -> dict | None:
        """Marcar fato como confirmado (confidence -> 1.0)."""
        return self._update_status(rid, "confirmed", confidence=1.0)

    def correct(self, rid: str, new_fact: str, confidence: float = 0.9) -> dict | None:
        """Corrigir o conteudo do fato (mantem historico de status)."""
        new_fact = " ".join((new_fact or "").split())
        if not new_fact:
            return None
        if _SENSITIVE.search(new_fact):
            raise ValueError("conteudo sensivel rejeitado")
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE user_facts SET fact=?, confidence=?, status='confirmed', "
                    "updated_at=? WHERE id=? AND status != 'forgotten'",
                    (new_fact, max(0.0, min(1.0, confidence)), now, rid),
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None
        return self.get(rid)

    def forget(self, rid: str) -> bool:
        """Esquecer fato (soft delete, mantem historico auditavel)."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE user_facts SET status='forgotten', updated_at=? WHERE id=?",
                    (time.time(), rid),
                )
                conn.commit()
                return cur.rowcount > 0

    def mark_used(self, rid: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE user_facts SET last_used=? WHERE id=?",
                    (time.time(), rid),
                )
                conn.commit()

    def _update_status(self, rid: str, status: str, confidence: float | None = None) -> dict | None:
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                if confidence is not None:
                    cur = conn.execute(
                        "UPDATE user_facts SET status=?, confidence=?, updated_at=? "
                        "WHERE id=? AND status != 'forgotten'",
                        (status, confidence, now, rid),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE user_facts SET status=?, updated_at=? WHERE id=? AND status != 'forgotten'",
                        (status, now, rid),
                    )
                conn.commit()
                if cur.rowcount == 0:
                    return None
        return self.get(rid)

    def context(self, query: str, limit: int = 4, max_chars: int = 800) -> str:
        """Trecho pronto para prompt do modelo."""
        matches = self.search(query, limit=limit)
        if not matches:
            return ""
        lines = ["[MEMÓRIAS DO USUÁRIO — use apenas se relevantes e verdadeiras]"]
        for m in matches:
            date = time.strftime("%Y-%m-%d", time.localtime(m["created_at"]))
            conf = "confirmado" if m["confidence"] >= 0.9 else "hipótese"
            lines.append(f"- [{m['category']}|{date}|{conf}] {m['fact']}")
        return "\n".join(lines)[:max_chars]


def create_user_memory(db_path: Path | None = None) -> UserMemoryCore:
    return UserMemoryCore(db_path=db_path)
