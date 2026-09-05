"""Bridge between the existing ZARA LAB and the persistent AutonomyEngine.

No worker execution happens here. This layer only:
- migrates already-approved LAB proposals/tasks into the Autonomy database;
- makes new approved proposals create a durable Autonomy task;
- exposes real task state back to the LAB UI;
- keeps preferred owner as metadata, not a hard dependency.

This is important: if OpenCode is unavailable, the task itself must still exist
and later be claimable by another compatible worker.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from core.autonomy_engine import AutonomyEngine, TaskRecord, TaskState

STEP_LABELS = {
    TaskState.WAITING_APPROVAL.value: "Aguardando aprovação de Alex",
    TaskState.QUEUED.value: "Na fila; aguardando worker compatível",
    TaskState.PLANNING.value: "Planejamento em andamento",
    TaskState.RUNNING.value: "Trabalho em andamento",
    TaskState.WAITING.value: "Aguardando nova tentativa/condição",
    TaskState.TESTING.value: "Testes em andamento",
    TaskState.READY_FOR_REVIEW.value: "Pronta para revisão de Alex",
    TaskState.PAUSED.value: "Pausada; precisa de revisão",
    TaskState.FAILED.value: "Falhou",
    TaskState.COMPLETED.value: "Concluída",
    TaskState.CANCELLED.value: "Cancelada",
}


class AutonomyLabBridge:
    def __init__(self, lab_db_path: str | Path, engine: AutonomyEngine | None = None):
        self.lab_db_path = Path(lab_db_path)
        self.engine = engine or AutonomyEngine()

    def _get_existing(self, task_id: str) -> TaskRecord | None:
        try:
            return self.engine.get_task(task_id)
        except KeyError:
            return None

    def ensure_from_proposal(self, proposal_id: str) -> TaskRecord:
        """Create an Autonomy task for an APPROVED LAB proposal, idempotently."""
        if not self.lab_db_path.exists():
            raise RuntimeError("LAB database not found")

        with closing(sqlite3.connect(self.lab_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            proposal = conn.execute(
                "SELECT * FROM proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()
            if not proposal:
                raise ValueError("Proposta não encontrada")
            if str(proposal["status"]).upper() != "APPROVED":
                raise RuntimeError("Somente propostas APPROVED entram no Autonomy Core")

            legacy = conn.execute(
                "SELECT * FROM tasks WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()

        task_id = str(legacy["id"]) if legacy else f"TASK-{proposal_id}"
        existing = self._get_existing(task_id)
        if existing:
            return existing

        preferred_owner = str(proposal["owner"] or "").strip().lower()
        payload = {
            "proposal_id": proposal_id,
            "summary": str(proposal["summary"] or ""),
            "risk": str(proposal["risk"] or "MEDIUM"),
            "preferred_owner": preferred_owner,
            "source": "zara_lab",
        }

        # Capability-based assignment, not worker-name pinning.
        # A future execution layer may let OpenClaw/OpenCode/another worker
        # claim this task if it advertises "development".
        return self.engine.create_task(
            title=str(proposal["title"]),
            kind="development",
            payload=payload,
            required_capabilities=["development"],
            priority=50,
            max_attempts=3,
            requires_approval=True,
            approved=True,  # LAB proposal was already approved by Alex.
            task_id=task_id,
        )

    def migrate_approved_from_lab_db(self) -> dict[str, int]:
        """Idempotently import all already-approved LAB proposals."""
        if not self.lab_db_path.exists():
            return {"approved": 0, "created": 0, "existing": 0}

        with closing(sqlite3.connect(self.lab_db_path)) as conn:
            rows = conn.execute(
                "SELECT id FROM proposals WHERE status='APPROVED' ORDER BY created_at ASC"
            ).fetchall()

        created = 0
        existing = 0
        for row in rows:
            proposal_id = str(row[0])
            legacy_task_id = f"TASK-{proposal_id}"
            # Prefer actual legacy task ID if present.
            with closing(sqlite3.connect(self.lab_db_path)) as conn:
                legacy = conn.execute(
                    "SELECT id FROM tasks WHERE proposal_id=?",
                    (proposal_id,),
                ).fetchone()
            if legacy:
                legacy_task_id = str(legacy[0])

            if self._get_existing(legacy_task_id):
                existing += 1
                continue
            self.ensure_from_proposal(proposal_id)
            created += 1

        return {"approved": len(rows), "created": created, "existing": existing}

    def to_lab_task(self, task: TaskRecord) -> dict[str, Any]:
        payload = task.payload or {}
        state = str(task.state)
        needs_alex = state in {
            TaskState.WAITING_APPROVAL.value,
            TaskState.READY_FOR_REVIEW.value,
            TaskState.PAUSED.value,
        }
        return {
            "id": task.id,
            "proposal_id": payload.get("proposal_id"),
            "title": task.title,
            "owner": str(payload.get("preferred_owner") or "AUTO"),
            "status": state,
            # Do not invent percentages. UI hides the progress bar when null.
            "progress": None,
            "current_step": STEP_LABELS.get(state, state),
            "assigned_worker": task.assigned_worker,
            "attempts": task.attempts,
            "max_attempts": task.max_attempts,
            "checkpoint_saved": bool(task.checkpoint),
            "checkpoint_at": task.checkpoint_at,
            "last_error": task.last_error,
            "needs_alex": needs_alex,
            "updated_at": task.updated_at,
        }

    def lab_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        return [self.to_lab_task(t) for t in self.engine.list_tasks(limit=limit)]

    def summary(self) -> dict[str, Any]:
        tasks = self.engine.list_tasks(limit=500)
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.state] = counts.get(task.state, 0) + 1

        workers = self.engine.worker_status()
        return {
            "status": "ONLINE",
            "persistent": True,
            "execution_enabled": False,
            "total_tasks": len(tasks),
            "counts": counts,
            "online_workers": sum(1 for w in workers if w.get("online")),
            "workers": workers,
        }
