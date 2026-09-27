"""ZARA Lab proactive research — M040.

Readers deliver source findings to the CEO; public research always carries a
visible URL and retrieval date; the CEO either turns a finding into a proposal
or logs a justification for not changing anything.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any


class LabResearch:
    def __init__(self, db_path: Any) -> None:
        self.db_path = str(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mission_research (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    reader TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    retrieved_at REAL NOT NULL,
                    summary TEXT NOT NULL,
                    ceo_decision TEXT NOT NULL DEFAULT 'PENDING',
                    ceo_note TEXT NOT NULL DEFAULT '',
                    proposal_id TEXT,
                    created_at REAL NOT NULL
                );
                """
            )

    def submit_finding(
        self,
        mission_id: str,
        reader: str,
        source_name: str,
        url: str,
        summary: str,
        mission: Any = None,
    ) -> dict[str, Any]:
        """A reader delivers a finding to the CEO (M040). URL + date required."""
        source_name, url, summary = source_name.strip(), url.strip(), summary.strip()
        if not source_name or not url or not summary:
            raise ValueError("Fonte, URL e resumo são obrigatórios")
        if not (url.startswith("http://") or url.startswith("https://")
                or url.startswith("file://")):
            raise ValueError("URL pública inválida")
        now = time.time()
        finding_id = f"FIND-{uuid.uuid4().hex[:6].upper()}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO mission_research(id, mission_id, reader, source_name, url,"
                " retrieved_at, summary, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (finding_id, mission_id, reader.strip() or "reader",
                 source_name, url, now, summary, now),
            )
            row = conn.execute(
                "SELECT * FROM mission_research WHERE id = ?", (finding_id,)
            ).fetchone()
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(
                room["id"], reader.strip() or "reader", "RESEARCH_FINDING",
                f"{finding_id}: {source_name} — {url} (lido em "
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}). {summary[:160]}",
            )
        return dict(row)

    def ceo_prioritize(
        self,
        finding_id: str,
        decision: str,
        note: str = "",
        proposal_id: str | None = None,
        mission: Any = None,
    ) -> dict[str, Any]:
        """CEO prioritizes a finding into a proposal or justifies no change."""
        decision = decision.strip().upper()
        if decision not in {"PRIORITIZED", "NO_CHANGE"}:
            raise ValueError("Decisão inválida: use PRIORITIZED ou NO_CHANGE")
        note = note.strip()
        if decision == "NO_CHANGE" and not note:
            raise ValueError("Justificativa obrigatória quando nada muda")
        if decision == "PRIORITIZED" and not (proposal_id or "").strip():
            raise ValueError("proposal_id obrigatório ao priorizar")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_research WHERE id = ?", (finding_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Achado desconhecido: {finding_id}")
            conn.execute(
                "UPDATE mission_research SET ceo_decision = ?, ceo_note = ?, proposal_id = ?"
                " WHERE id = ?",
                (decision, note, (proposal_id or "").strip() or None, finding_id),
            )
            updated = dict(conn.execute(
                "SELECT * FROM mission_research WHERE id = ?", (finding_id,)
            ).fetchone())
        if mission is not None:
            room = mission.ensure_room()
            detail = f"{finding_id} → {decision}."
            if note:
                detail += f" {note}"
            if proposal_id:
                detail += f" Proposta: {proposal_id}."
            mission.log_feed(room["id"], "ceo", "RESEARCH_PRIORITIZED", detail)
        return updated

    def list_findings(self, mission_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_research WHERE mission_id = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (mission_id, max(1, min(limit, 200))),
            ).fetchall()
            return [dict(r) for r in rows]
