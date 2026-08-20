"""ZARA Autonomy Core 001

Persistent, crash-safe task state machine for ZARA.

This module deliberately does NOT execute workers or write to production code.
It provides the durable "memory of work":
- persistent queue
- approval gate
- worker heartbeats
- task leases
- checkpoints
- retry/backoff
- stale-task recovery after restart
- append-only event history

SQLite is stored under:
%LOCALAPPDATA%/ZARA3/data/autonomy/zara_autonomy.db
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class TaskState(StrEnum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    TESTING = "TESTING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {
    TaskState.FAILED,
    TaskState.COMPLETED,
    TaskState.CANCELLED,
}


ACTIVE_LEASE_STATES = {
    TaskState.PLANNING,
    TaskState.RUNNING,
    TaskState.TESTING,
}


@dataclass
class TaskRecord:
    id: str
    title: str
    kind: str
    state: str
    priority: int
    payload: dict[str, Any]
    required_capabilities: list[str]
    requires_approval: bool
    approved: bool
    attempts: int
    max_attempts: int
    assigned_worker: str | None
    lease_expires_at: float | None
    available_at: float
    created_at: float
    updated_at: float
    last_error: str | None
    checkpoint: dict[str, Any] | None
    checkpoint_at: float | None


class AutonomyEngine:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path | None = None, worker_ttl_seconds: int = 90):
        self.worker_ttl_seconds = max(10, int(worker_ttl_seconds))
        self.db_path = Path(db_path) if db_path else self._default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.recover_stale_leases()

    @staticmethod
    def _default_db_path() -> Path:
        from core.paths import user_data_dir
        return user_data_dir() / "data" / "autonomy" / "zara_autonomy.db"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        # WAL leaves -wal/-shm files that Windows keeps locked briefly after
        # close, which breaks tempdir cleanup in the verification harness.
        # Test databases use the plain journal so cleanup is reliable.
        if "zara-autonomy-test-" in str(self.db_path):
            conn.execute("PRAGMA journal_mode=DELETE")
        else:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    requires_approval INTEGER NOT NULL DEFAULT 1,
                    approved INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    assigned_worker TEXT,
                    lease_expires_at REAL,
                    available_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_error TEXT,
                    checkpoint_json TEXT,
                    checkpoint_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_queue
                ON tasks(state, approved, available_at, priority, created_at);

                CREATE TABLE IF NOT EXISTS task_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT,
                    worker_id TEXT,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );

                CREATE INDEX IF NOT EXISTS idx_task_events_task
                ON task_events(task_id, seq);

                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    last_heartbeat REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _loads(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback

    def _event(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_type: str,
        state: str | None = None,
        worker_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO task_events(task_id, event_type, state, worker_id, detail_json, created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (task_id, event_type, state, worker_id, self._json(detail or {}), time.time()),
        )

    def create_task(
        self,
        title: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        required_capabilities: Iterable[str] = (),
        priority: int = 50,
        max_attempts: int = 3,
        requires_approval: bool = True,
        approved: bool = False,
        task_id: str | None = None,
    ) -> TaskRecord:
        now = time.time()
        task_id = task_id or f"TASK-{uuid.uuid4().hex[:10].upper()}"
        approved = bool(approved) or not requires_approval
        state = TaskState.QUEUED if approved else TaskState.WAITING_APPROVAL
        caps = sorted({str(x).strip() for x in required_capabilities if str(x).strip()})
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO tasks(
                    id,title,kind,state,priority,payload_json,capabilities_json,
                    requires_approval,approved,attempts,max_attempts,assigned_worker,
                    lease_expires_at,available_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id, title.strip(), kind.strip(), state.value, int(priority),
                    self._json(payload or {}), self._json(caps),
                    int(bool(requires_approval)), int(approved), 0, max(1, int(max_attempts)),
                    None, None, now, now, now,
                ),
            )
            self._event(conn, task_id, "CREATED", state.value, detail={"approved": approved})
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def approve_task(self, task_id: str, approver: str = "alex") -> TaskRecord:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                raise KeyError(task_id)
            if row["state"] in {s.value for s in TERMINAL_STATES}:
                conn.execute("ROLLBACK")
                raise RuntimeError("Tarefa terminal não pode ser aprovada")
            conn.execute(
                """
                UPDATE tasks
                SET approved=1,
                    state=CASE WHEN state=? THEN ? ELSE state END,
                    available_at=?, updated_at=?
                WHERE id=?
                """,
                (TaskState.WAITING_APPROVAL.value, TaskState.QUEUED.value, now, now, task_id),
            )
            state = conn.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()["state"]
            self._event(conn, task_id, "APPROVED", state, approver)
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def cancel_task(self, task_id: str, actor: str = "alex") -> TaskRecord:
        return self._set_terminal(task_id, TaskState.CANCELLED, actor, None)

    def heartbeat_worker(
        self,
        worker_id: str,
        state: str = "ONLINE",
        capabilities: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        caps = sorted({str(x).strip() for x in capabilities if str(x).strip()})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workers(worker_id,state,capabilities_json,metadata_json,last_heartbeat,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    state=excluded.state,
                    capabilities_json=excluded.capabilities_json,
                    metadata_json=excluded.metadata_json,
                    last_heartbeat=excluded.last_heartbeat,
                    updated_at=excluded.updated_at
                """,
                (worker_id, state, self._json(caps), self._json(metadata or {}), now, now),
            )
        return {
            "worker_id": worker_id,
            "state": state,
            "capabilities": caps,
            "last_heartbeat": now,
            "online": state.upper() == "ONLINE",
        }

    def worker_status(self) -> list[dict[str, Any]]:
        cutoff = time.time() - self.worker_ttl_seconds
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM workers ORDER BY worker_id").fetchall()
        out = []
        for row in rows:
            state = str(row["state"])
            online = state.upper() == "ONLINE" and float(row["last_heartbeat"]) >= cutoff
            out.append({
                "worker_id": row["worker_id"],
                "state": state if online else ("STALE" if state.upper() == "ONLINE" else state),
                "online": online,
                "capabilities": self._loads(row["capabilities_json"], []),
                "metadata": self._loads(row["metadata_json"], {}),
                "last_heartbeat": row["last_heartbeat"],
            })
        return out

    def claim_next(
        self,
        worker_id: str,
        capabilities: Iterable[str],
        lease_seconds: int = 120,
        allowed_kinds: Iterable[str] | None = None,
    ) -> TaskRecord | None:
        now = time.time()
        worker_caps = {str(x).strip() for x in capabilities if str(x).strip()}
        kinds = {str(x).strip() for x in allowed_kinds or [] if str(x).strip()}
        self.recover_stale_leases(now=now)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE state=? AND approved=1 AND available_at<=?
                ORDER BY priority DESC, created_at ASC
                """,
                (TaskState.QUEUED.value, now),
            ).fetchall()

            selected = None
            for row in rows:
                req = set(self._loads(row["capabilities_json"], []))
                if not req.issubset(worker_caps):
                    continue
                if kinds and row["kind"] not in kinds:
                    continue
                selected = row
                break

            if not selected:
                conn.execute("COMMIT")
                return None

            attempts = int(selected["attempts"]) + 1
            if attempts > int(selected["max_attempts"]):
                conn.execute(
                    "UPDATE tasks SET state=?, updated_at=? WHERE id=?",
                    (TaskState.PAUSED.value, now, selected["id"]),
                )
                self._event(
                    conn, selected["id"], "MAX_ATTEMPTS_REACHED", TaskState.PAUSED.value,
                    worker_id, {"attempts": attempts - 1},
                )
                conn.execute("COMMIT")
                return None

            lease_expires = now + max(15, int(lease_seconds))
            conn.execute(
                """
                UPDATE tasks
                SET state=?, assigned_worker=?, lease_expires_at=?, attempts=?, updated_at=?, last_error=NULL
                WHERE id=?
                """,
                (
                    TaskState.PLANNING.value, worker_id, lease_expires, attempts, now,
                    selected["id"],
                ),
            )
            self._event(
                conn, selected["id"], "CLAIMED", TaskState.PLANNING.value, worker_id,
                {"lease_expires_at": lease_expires, "attempt": attempts},
            )
            conn.execute("COMMIT")
            return self.get_task(selected["id"])

    def set_stage(self, task_id: str, worker_id: str, state: TaskState) -> TaskRecord:
        if state not in {
            TaskState.PLANNING, TaskState.RUNNING, TaskState.WAITING,
            TaskState.TESTING, TaskState.READY_FOR_REVIEW,
        }:
            raise ValueError("Estado de estágio inválido")
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self._assert_worker_owns(row, worker_id)
            lease = row["lease_expires_at"] if state in ACTIVE_LEASE_STATES else None
            conn.execute(
                "UPDATE tasks SET state=?, lease_expires_at=?, updated_at=? WHERE id=?",
                (state.value, lease, now, task_id),
            )
            self._event(conn, task_id, "STAGE_CHANGED", state.value, worker_id)
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def renew_lease(self, task_id: str, worker_id: str, lease_seconds: int = 120) -> TaskRecord:
        now = time.time()
        expires = now + max(15, int(lease_seconds))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self._assert_worker_owns(row, worker_id)
            if row["state"] not in {s.value for s in ACTIVE_LEASE_STATES}:
                conn.execute("ROLLBACK")
                raise RuntimeError("Tarefa não está em estágio com lease")
            conn.execute(
                "UPDATE tasks SET lease_expires_at=?, updated_at=? WHERE id=?",
                (expires, now, task_id),
            )
            self._event(conn, task_id, "LEASE_RENEWED", row["state"], worker_id, {"lease_expires_at": expires})
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def checkpoint(self, task_id: str, worker_id: str, data: dict[str, Any]) -> TaskRecord:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self._assert_worker_owns(row, worker_id)
            conn.execute(
                "UPDATE tasks SET checkpoint_json=?, checkpoint_at=?, updated_at=? WHERE id=?",
                (self._json(data), now, now, task_id),
            )
            self._event(conn, task_id, "CHECKPOINT", row["state"], worker_id)
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def fail_task(
        self,
        task_id: str,
        worker_id: str,
        error: str,
        transient: bool = True,
        retry_after_seconds: int = 30,
    ) -> TaskRecord:
        now = time.time()
        safe_error = str(error or "unknown error")[:1500]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self._assert_worker_owns(row, worker_id)
            attempts = int(row["attempts"])
            can_retry = transient and attempts < int(row["max_attempts"])
            state = TaskState.WAITING if can_retry else TaskState.PAUSED
            available_at = now + max(1, int(retry_after_seconds)) if can_retry else now
            conn.execute(
                """
                UPDATE tasks
                SET state=?, assigned_worker=NULL, lease_expires_at=NULL,
                    available_at=?, last_error=?, updated_at=?
                WHERE id=?
                """,
                (state.value, available_at, safe_error, now, task_id),
            )
            self._event(
                conn, task_id, "FAILED_ATTEMPT", state.value, worker_id,
                {"transient": bool(transient), "attempt": attempts},
            )
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def release_waiting_tasks(self, now: float | None = None) -> int:
        # `now` here only selects which WAITING tasks have reached their retry
        # window. A task that is released becomes immediately claimable, so its
        # available_at is set to the real current time (not the injected now).
        select_now = time.time() if now is None else float(now)
        real_now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id FROM tasks WHERE state=? AND available_at<=? AND approved=1",
                (TaskState.WAITING.value, select_now),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE tasks SET state=?, available_at=?, updated_at=? WHERE id=?",
                    (TaskState.QUEUED.value, real_now, real_now, row["id"]),
                )
                self._event(conn, row["id"], "RETRY_QUEUED", TaskState.QUEUED.value)
            conn.execute("COMMIT")
            return len(rows)

    def ready_for_review(self, task_id: str, worker_id: str, summary: dict[str, Any] | None = None) -> TaskRecord:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self._assert_worker_owns(row, worker_id)
            conn.execute(
                """
                UPDATE tasks
                SET state=?, lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (TaskState.READY_FOR_REVIEW.value, now, task_id),
            )
            self._event(conn, task_id, "READY_FOR_REVIEW", TaskState.READY_FOR_REVIEW.value, worker_id, summary or {})
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def complete_task(self, task_id: str, actor: str = "alex", result: dict[str, Any] | None = None) -> TaskRecord:
        return self._set_terminal(task_id, TaskState.COMPLETED, actor, result)

    def _set_terminal(
        self,
        task_id: str,
        state: TaskState,
        actor: str,
        detail: dict[str, Any] | None,
    ) -> TaskRecord:
        if state not in TERMINAL_STATES:
            raise ValueError("Estado terminal inválido")
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                raise KeyError(task_id)
            conn.execute(
                """
                UPDATE tasks
                SET state=?, assigned_worker=NULL, lease_expires_at=NULL, updated_at=?
                WHERE id=?
                """,
                (state.value, now, task_id),
            )
            self._event(conn, task_id, state.value, state.value, actor, detail or {})
            conn.execute("COMMIT")
        return self.get_task(task_id)

    def recover_stale_leases(self, now: float | None = None) -> int:
        now = time.time() if now is None else float(now)
        recovered = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE state IN (?,?,?)
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at<=?
                """,
                (
                    TaskState.PLANNING.value,
                    TaskState.RUNNING.value,
                    TaskState.TESTING.value,
                    now,
                ),
            ).fetchall()
            for row in rows:
                attempts = int(row["attempts"])
                if attempts >= int(row["max_attempts"]):
                    state = TaskState.PAUSED
                else:
                    state = TaskState.QUEUED
                conn.execute(
                    """
                    UPDATE tasks
                    SET state=?, assigned_worker=NULL, lease_expires_at=NULL,
                        available_at=?, updated_at=?, last_error=?
                    WHERE id=?
                    """,
                    (
                        state.value, now, now,
                        "Worker lease expired; task recovered automatically.",
                        row["id"],
                    ),
                )
                self._event(
                    conn, row["id"], "LEASE_EXPIRED_RECOVERY", state.value,
                    row["assigned_worker"],
                    {"attempts": attempts},
                )
                recovered += 1
            conn.execute("COMMIT")
        self.release_waiting_tasks(now=now)
        return recovered

    def get_task(self, task_id: str) -> TaskRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return self._row_to_task(row)

    def list_tasks(self, states: Iterable[TaskState | str] | None = None, limit: int = 200) -> list[TaskRecord]:
        with self._connect() as conn:
            if states:
                values = [s.value if isinstance(s, TaskState) else str(s) for s in states]
                marks = ",".join("?" for _ in values)
                rows = conn.execute(
                    f"SELECT * FROM tasks WHERE state IN ({marks}) ORDER BY priority DESC, created_at ASC LIMIT ?",
                    (*values, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def events(self, task_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq,event_type,state,worker_id,detail_json,created_at
                FROM task_events WHERE task_id=? ORDER BY seq ASC LIMIT ?
                """,
                (task_id, int(limit)),
            ).fetchall()
        return [
            {
                "seq": row["seq"],
                "event_type": row["event_type"],
                "state": row["state"],
                "worker_id": row["worker_id"],
                "detail": self._loads(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _assert_worker_owns(row: sqlite3.Row | None, worker_id: str) -> None:
        if not row:
            raise KeyError("task")
        if row["assigned_worker"] != worker_id:
            raise RuntimeError("Worker não possui lease desta tarefa")

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            title=row["title"],
            kind=row["kind"],
            state=row["state"],
            priority=int(row["priority"]),
            payload=self._loads(row["payload_json"], {}),
            required_capabilities=self._loads(row["capabilities_json"], []),
            requires_approval=bool(row["requires_approval"]),
            approved=bool(row["approved"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            assigned_worker=row["assigned_worker"],
            lease_expires_at=row["lease_expires_at"],
            available_at=float(row["available_at"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_error=row["last_error"],
            checkpoint=self._loads(row["checkpoint_json"], None),
            checkpoint_at=row["checkpoint_at"],
        )

    @staticmethod
    def to_dict(task: TaskRecord) -> dict[str, Any]:
        return asdict(task)
