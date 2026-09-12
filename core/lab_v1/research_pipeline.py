"""Real research pipeline: QUESTION -> real source -> EVIDENCE -> FINDING ->
RELEVANCE -> LIMITATION -> RECOMMENDATION, persisted for reuse.

Mirrors the storage pattern of `feedback_inbox.py`: one small table owned by
this module, opened additively on the shared `LabStore` connection, JSON
document per row, dedup by a content hash so the same question researched
twice does not fork into two disconnected records.

This module persists research; it never performs it. The caller (a human or
an agent with real WebSearch/WebFetch access) gathers each source's fields
for real and hands them to `record_cycle`. Nothing here fabricates a URL, a
finding or an access. `record_cycle` enforces the two invariants the whole
pipeline exists for:

1. at most `MAX_SOURCES_PER_CYCLE` sources per cycle (the owner's per-cycle
   research budget is a hard cap, not a suggestion);
2. duplicating the same question does not create a new cycle — the existing
   one is returned unchanged, so re-running a research task never quietly
   forks the record an owner or another agent will read later.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

MAX_SOURCES_PER_CYCLE = 5
_SOURCE_FIELDS = ("source", "finding", "evidence", "relevance", "limitation")
_RECOMMENDATIONS = {"IMPLEMENTAR", "NAO_IMPLEMENTAR", "PRECISA_MAIS_INVESTIGACAO"}


def _normalize_question(question: str) -> str:
    return " ".join(str(question or "").split()).casefold()


def _question_hash(question: str) -> str:
    return hashlib.sha256(_normalize_question(question).encode("utf-8")).hexdigest()


def _validate_source(source: dict) -> dict:
    if not isinstance(source, dict):
        raise ValueError("SOURCE_MUST_BE_DICT")
    clean: dict[str, str] = {}
    for field in _SOURCE_FIELDS:
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"SOURCE_FIELD_REQUIRED:{field}")
        clean[field] = value.strip()
    if not (clean["source"].startswith("http://") or clean["source"].startswith("https://")):
        raise ValueError("SOURCE_MUST_BE_URL")
    return clean


class ResearchPipeline:
    """Persistent store for real research cycles, sharing the Lab's SQLite DB."""

    def __init__(self, store):
        self.store = store
        with store._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lab_research_cycles(
                    id TEXT PRIMARY KEY,
                    question_sha256 TEXT NOT NULL UNIQUE,
                    question TEXT NOT NULL,
                    document TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )

    def record_cycle(
        self,
        question: str,
        sources: list[dict],
        *,
        recommendation: str,
        implementation_candidate: str | None = None,
    ) -> dict[str, Any]:
        """Persist one research cycle. Returns the stored document.

        If `question` (normalized: collapsed whitespace, case-insensitive)
        was already researched, the existing cycle is returned untouched —
        this is the dedup: no new row, no silent duplicate research.
        """
        clean_question = " ".join(str(question or "").split())
        if not clean_question:
            raise ValueError("QUESTION_REQUIRED")
        if not isinstance(sources, list) or not sources:
            raise ValueError("AT_LEAST_ONE_SOURCE_REQUIRED")
        if len(sources) > MAX_SOURCES_PER_CYCLE:
            raise ValueError(f"SOURCE_BUDGET_EXCEEDED:max={MAX_SOURCES_PER_CYCLE}")
        recommendation = str(recommendation or "").strip().upper()
        if recommendation not in _RECOMMENDATIONS:
            raise ValueError("RECOMMENDATION_INVALID")
        if recommendation == "IMPLEMENTAR" and not (implementation_candidate or "").strip():
            raise ValueError("IMPLEMENTATION_CANDIDATE_REQUIRED")

        clean_sources = [
            {"question": clean_question, **_validate_source(item)} for item in sources
        ]
        digest = _question_hash(clean_question)
        stamp = time.time()
        document = {
            "question": clean_question,
            "sources": clean_sources,
            "recommendation": recommendation,
            "implementation_candidate": (implementation_candidate or "").strip() or None,
            "source_count": len(clean_sources),
            "researched_at": stamp,
        }
        cycle_id = "research:" + digest[:20]
        with self.store._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO lab_research_cycles
                   VALUES(?,?,?,?,?,?,?)""",
                (cycle_id, digest, clean_question,
                 json.dumps(document, ensure_ascii=False), recommendation, stamp, stamp),
            )
            row = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE question_sha256=?", (digest,)
            ).fetchone()
        return self._row_to_dict(row)

    def get_cycle(self, question: str) -> dict[str, Any] | None:
        digest = _question_hash(question)
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE question_sha256=?", (digest,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_by_id(self, cycle_id: str) -> dict[str, Any] | None:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE id=?", (cycle_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_cycles(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lab_research_cycles ORDER BY created_at ASC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        document = json.loads(row["document"])
        document.update(id=row["id"], recommendation=row["recommendation"],
                         created_at=row["created_at"], updated_at=row["updated_at"])
        return document
