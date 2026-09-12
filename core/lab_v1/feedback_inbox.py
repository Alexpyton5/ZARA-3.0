"""Persistent product criticism inbox shared by text, voice and Telegram."""
from __future__ import annotations

import hashlib
import json
import re
import time


_CRITICISM = re.compile(
    r"\b(?:n[aã]o\s+(?:funciona|responde|abre|envia|consegue)|falh(?:a|ou)|erro|bug|"
    r"lent[oa]|demor(?:a|ou)|trav(?:a|ou)|quebr(?:ou|ado)|ruim|mal\s+feit[oa]|"
    r"precisa\s+melhorar|deveria|n[aã]o\s+pode\s+ser|cr[ií]tic[ao])\b",
    re.IGNORECASE,
)


def looks_like_product_criticism(text: str) -> bool:
    clean = " ".join(str(text or "").split())
    return len(clean) >= 8 and bool(_CRITICISM.search(clean))


class FeedbackInbox:
    def __init__(self, store):
        self.store = store
        with store._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS lab_product_feedback(
                id TEXT PRIMARY KEY, evidence_sha256 TEXT NOT NULL UNIQUE,
                document TEXT NOT NULL, status TEXT NOT NULL, mission_id TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL)""")

    def record(self, text: str, *, channel: str = "conversation"):
        clean = " ".join(str(text or "").split())[:4000]
        if not looks_like_product_criticism(clean):
            return None
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        stamp = time.time()
        document = {"text": clean, "channel": str(channel or "conversation")[:80],
                    "evidence_sha256": digest, "observed_at": stamp}
        with self.store._connect() as conn:
            conn.execute("""INSERT OR IGNORE INTO lab_product_feedback
                VALUES(?,?,?,?,?,?,?)""", ("feedback:" + digest[:20], digest,
                json.dumps(document, ensure_ascii=False), "RECEIVED", None, stamp, stamp))
            row = conn.execute("SELECT * FROM lab_product_feedback WHERE evidence_sha256=?",
                               (digest,)).fetchone()
        result = json.loads(row["document"])
        result.update(id=row["id"], status=row["status"], mission_id=row["mission_id"])
        return result

    def next_received(self):
        with self.store._connect() as conn:
            row = conn.execute("""SELECT * FROM lab_product_feedback
                WHERE status='RECEIVED' ORDER BY created_at LIMIT 1""").fetchone()
        if not row:
            return None
        result = json.loads(row["document"])
        result.update(id=row["id"], status=row["status"], mission_id=row["mission_id"])
        return result

    def link(self, feedback_id: str, mission_id: str):
        with self.store._connect() as conn:
            conn.execute("""UPDATE lab_product_feedback SET status='ARCHITECT_REVIEW',
                mission_id=?,updated_at=? WHERE id=? AND status='RECEIVED'""",
                (mission_id, time.time(), feedback_id))

    def finish(self, feedback_id: str, *, completed: bool):
        status = "READY_FOR_OWNER" if completed else "REVIEW_FAILED"
        with self.store._connect() as conn:
            conn.execute("UPDATE lab_product_feedback SET status=?,updated_at=? WHERE id=?",
                         (status, time.time(), feedback_id))

    def counts(self):
        with self.store._connect() as conn:
            return {row["status"]: row["total"] for row in conn.execute(
                "SELECT status,count(*) total FROM lab_product_feedback GROUP BY status")}
