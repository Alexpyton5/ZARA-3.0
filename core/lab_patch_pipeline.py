"""ZARA Lab patch pipeline — M060.

A small improvement travels: delimited patch → real verification →
independent review → promotion policy, with visible diff and artifacts.

States: DRAFT → IN_VERIFICATION → IN_REVIEW → PROMOTED | REJECTED.
Transitions are strictly ordered; skipping a gate raises.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

ST_DRAFT = "DRAFT"
ST_VERIFY = "IN_VERIFICATION"
ST_REVIEW = "IN_REVIEW"
ST_PROMOTED = "PROMOTED"
ST_REJECTED = "REJECTED"


class LabPatchPipeline:
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
                CREATE TABLE IF NOT EXISTS mission_patches (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    files_json TEXT NOT NULL DEFAULT '[]',
                    diff TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    verification_json TEXT NOT NULL DEFAULT '{}',
                    review_json TEXT NOT NULL DEFAULT '{}',
                    artifacts_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def create_patch(
        self, mission_id: str, title: str, files: list[str], diff: str = "",
        mission: Any = None,
    ) -> dict[str, Any]:
        """Open a delimited patch: only the listed files may change."""
        title = title.strip()
        files = [str(f).strip() for f in files if str(f).strip()]
        if not title or not files:
            raise ValueError("Título e lista delimitada de arquivos são obrigatórios")
        now = time.time()
        patch_id = f"PATCH-{uuid.uuid4().hex[:6].upper()}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO mission_patches(id, mission_id, title, files_json, diff,"
                " status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (patch_id, mission_id, title, json.dumps(files, ensure_ascii=False),
                 diff, ST_DRAFT, now, now),
            )
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(
                room["id"], "engineer", "PATCH_CREATED",
                f"{patch_id}: {title} — arquivos delimitados: {', '.join(files)}",
            )
        return self.get_patch(patch_id)

    def submit_for_verification(self, patch_id: str) -> dict[str, Any]:
        return self._transition(patch_id, ST_DRAFT, ST_VERIFY, "PATCH_IN_VERIFICATION")

    def record_verification(
        self, patch_id: str, verifier: str, passed: bool, evidence: str,
        mission: Any = None,
    ) -> dict[str, Any]:
        patch = self._require_status(patch_id, ST_VERIFY)
        record = {
            "verifier": verifier.strip(), "passed": bool(passed),
            "evidence": evidence.strip(), "at": time.time(),
        }
        if not record["verifier"] or not record["evidence"]:
            raise ValueError("Verificador e evidência são obrigatórios")
        self._update(patch_id, verification_json=json.dumps(record, ensure_ascii=False))
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(
                room["id"], verifier.strip(), "PATCH_VERIFIED",
                f"{patch_id}: {'PASSOU' if passed else 'FALHOU'} — {evidence.strip()[:200]}",
            )
        patch = self.get_patch(patch_id)
        if not passed:
            return self._transition(patch_id, ST_VERIFY, ST_REJECTED,
                                   "PATCH_REJECTED", mission,
                                   detail="reprovado na verificação")
        return patch

    def submit_for_review(self, patch_id: str, mission: Any = None) -> dict[str, Any]:
        patch = self._require_status(patch_id, ST_VERIFY)
        verification = patch.get("verification") or {}
        if not verification.get("passed"):
            raise ValueError("Revisão exige verificação aprovada")
        return self._transition(patch_id, ST_VERIFY, ST_REVIEW, "PATCH_IN_REVIEW", mission)

    def record_review(
        self, patch_id: str, reviewer: str, approved: bool, notes: str,
        mission: Any = None,
    ) -> dict[str, Any]:
        self._require_status(patch_id, ST_REVIEW)
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("Revisor obrigatório")
        verification = self.get_patch(patch_id).get("verification") or {}
        if reviewer == verification.get("verifier"):
            raise ValueError("Revisão deve ser independente do verificador")
        record = {"reviewer": reviewer, "approved": bool(approved),
                  "notes": notes.strip(), "at": time.time()}
        self._update(patch_id, review_json=json.dumps(record, ensure_ascii=False))
        if mission is not None:
            room = mission.ensure_room()
            mission.log_feed(
                room["id"], reviewer, "PATCH_REVIEWED",
                f"{patch_id}: {'APROVADO' if approved else 'REPROVADO'} — {notes.strip()[:200]}",
            )
        if not approved:
            return self._transition(patch_id, ST_REVIEW, ST_REJECTED,
                                   "PATCH_REJECTED", mission,
                                   detail="reprovado na revisão independente")
        return self.get_patch(patch_id)

    def promote(self, patch_id: str, artifacts: list[str] | None = None,
                mission: Any = None) -> dict[str, Any]:
        """Promotion policy: verified + independently reviewed + artifacts."""
        patch = self._require_status(patch_id, ST_REVIEW)
        verification = patch.get("verification") or {}
        review = patch.get("review") or {}
        if not verification.get("passed"):
            raise ValueError("Promoção exige verificação aprovada")
        if not review.get("approved"):
            raise ValueError("Promoção exige revisão independente aprovada")
        artifacts = [str(a).strip() for a in (artifacts or []) if str(a).strip()]
        self._update(patch_id, artifacts_json=json.dumps(artifacts, ensure_ascii=False))
        return self._transition(patch_id, ST_REVIEW, ST_PROMOTED, "PATCH_PROMOTED",
                               mission,
                               detail=f"artefatos: {', '.join(artifacts) or 'nenhum'}")

    def get_patch(self, patch_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mission_patches WHERE id = ?", (patch_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Patch desconhecido: {patch_id}")
            return self._decode(dict(row))

    def list_patches(self, mission_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mission_patches WHERE mission_id = ? ORDER BY updated_at DESC",
                (mission_id,),
            ).fetchall()
            return [self._decode(dict(r)) for r in rows]

    # -- internals ------------------------------------------------------ #
    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("files_json", "artifacts_json"):
            try:
                row[key.replace("_json", "")] = json.loads(row.pop(key) or "[]")
            except Exception:
                row[key.replace("_json", "")] = []
        for key in ("verification_json", "review_json"):
            try:
                row[key.replace("_json", "")] = json.loads(row.pop(key) or "{}")
            except Exception:
                row[key.replace("_json", "")] = {}
        return row

    def _require_status(self, patch_id: str, status: str) -> dict[str, Any]:
        patch = self.get_patch(patch_id)
        if patch["status"] != status:
            raise ValueError(
                f"{patch_id}: transição inválida (está {patch['status']}, esperado {status})"
            )
        return patch

    def _update(self, patch_id: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE mission_patches SET {assignments} WHERE id = ?",
                (*fields.values(), patch_id),
            )

    def _transition(self, patch_id: str, expected: str, new: str, event: str,
                    mission: Any = None, detail: str = "") -> dict[str, Any]:
        self._require_status(patch_id, expected)
        self._update(patch_id, status=new)
        if mission is not None:
            room = mission.ensure_room()
            text = f"{patch_id} → {new}."
            if detail:
                text += f" {detail}"
            mission.log_feed(room["id"], "system", event, text)
        return self.get_patch(patch_id)
