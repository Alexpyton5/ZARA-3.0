"""Durable, provider-independent admission for idempotent Lab commands."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

_MAX_ID_LENGTH = 200
_MAX_COMMAND_LENGTH = 200
_MAX_PAYLOAD_BYTES = 64 * 1024


class IdempotencyConflict(ValueError):
    """A request id was reused for a different command or payload."""


@dataclass(frozen=True)
class OperationAck:
    request_id: str
    operation_id: str
    command: str
    payload_sha256: str
    accepted_at: float
    accepted: bool = True
    newly_admitted: bool = field(default=True, compare=False, repr=False)


@dataclass(frozen=True)
class AdmittedOperation:
    operation_id: str
    request_id: str
    command: str
    payload_json: str
    payload_sha256: str
    state: str
    admitted_at: float


@dataclass(frozen=True)
class OperationStatus:
    operation_id: str
    request_id: str
    command: str
    state: str
    result: dict[str, Any] | None = None
    finished_at: float | None = None


class OperationLedger:
    """Atomically persist an admitted operation and its stable acknowledgement."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lab_admitted_operations (
                    operation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    command TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state = 'ADMITTED'),
                    admitted_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lab_operation_outbox (
                    operation_id TEXT PRIMARY KEY
                        REFERENCES lab_admitted_operations(operation_id),
                    state TEXT NOT NULL
                        CHECK(state IN ('PENDING', 'DISPATCHING', 'DONE')),
                    claimed_at REAL,
                    worker_pid INTEGER,
                    worker_started_at REAL,
                    dispatch_authorized_at REAL
                );
                CREATE TABLE IF NOT EXISTS lab_operation_results (
                    operation_id TEXT PRIMARY KEY
                        REFERENCES lab_admitted_operations(operation_id),
                    state TEXT NOT NULL
                        CHECK(state IN ('COMPLETED', 'FAILED', 'INTERRUPTED')),
                    result_json TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    finished_at REAL NOT NULL,
                    publication_state TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK(publication_state IN ('PENDING', 'PUBLISHING', 'PUBLISHED')),
                    publisher_pid INTEGER,
                    publisher_started_at REAL,
                    published_at REAL
                );
                CREATE TABLE IF NOT EXISTS lab_operation_event_outbox (
                    operation_id TEXT PRIMARY KEY
                        REFERENCES lab_operation_results(operation_id),
                    state TEXT NOT NULL
                        CHECK(state IN ('PENDING', 'PUBLISHING', 'PUBLISHED')),
                    claimed_at REAL,
                    publisher_pid INTEGER,
                    publisher_started_at REAL,
                    published_at REAL
                );
                INSERT OR IGNORE INTO lab_operation_outbox(operation_id, state)
                SELECT operation_id, 'PENDING' FROM lab_admitted_operations;
                INSERT OR IGNORE INTO lab_operation_event_outbox(operation_id, state)
                SELECT operation_id, 'PENDING' FROM lab_operation_results;
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(lab_operation_outbox)")
            }
            if "worker_pid" not in columns:
                connection.execute(
                    "ALTER TABLE lab_operation_outbox ADD COLUMN worker_pid INTEGER"
                )
            if "worker_started_at" not in columns:
                connection.execute(
                    "ALTER TABLE lab_operation_outbox ADD COLUMN worker_started_at REAL"
                )
            if "dispatch_authorized_at" not in columns:
                # Rows created by an older version were immediately eligible.
                # Preserve that meaning during migration. New IPC admissions
                # explicitly opt into the held state in ``admit`` below.
                connection.execute(
                    "ALTER TABLE lab_operation_outbox ADD COLUMN dispatch_authorized_at REAL"
                )
                connection.execute(
                    """
                    UPDATE lab_operation_outbox
                    SET dispatch_authorized_at=COALESCE(
                        claimed_at,
                        (SELECT admitted_at FROM lab_admitted_operations o
                         WHERE o.operation_id=lab_operation_outbox.operation_id)
                    )
                    WHERE dispatch_authorized_at IS NULL
                    """
                )
            result_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(lab_operation_results)")
            }
            if "publication_state" not in result_columns:
                connection.execute(
                    "ALTER TABLE lab_operation_results ADD COLUMN publication_state TEXT NOT NULL DEFAULT 'PENDING'"
                )
            if "publisher_pid" not in result_columns:
                connection.execute(
                    "ALTER TABLE lab_operation_results ADD COLUMN publisher_pid INTEGER"
                )
            if "publisher_started_at" not in result_columns:
                connection.execute(
                    "ALTER TABLE lab_operation_results ADD COLUMN publisher_started_at REAL"
                )
            if "published_at" not in result_columns:
                connection.execute(
                    "ALTER TABLE lab_operation_results ADD COLUMN published_at REAL"
                )

    @staticmethod
    def _required_text(value: str, *, label: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required")
        normalized = value.strip()
        if len(normalized) > maximum:
            raise ValueError(f"{label} is too long")
        return normalized

    @staticmethod
    def _canonical_payload(payload: Any) -> tuple[str, str]:
        try:
            canonical_text = json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except ValueError as exc:
            raise ValueError("Payload numbers must be finite") from exc
        except (TypeError, OverflowError) as exc:
            raise ValueError("Payload must be JSON-compatible") from exc
        canonical = canonical_text.encode("utf-8")
        if len(canonical) > _MAX_PAYLOAD_BYTES:
            raise ValueError("Payload is too large")
        return canonical_text, hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _row_to_ack(row: sqlite3.Row) -> OperationAck:
        return OperationAck(
            request_id=row["request_id"],
            operation_id=row["operation_id"],
            command=row["command"],
            payload_sha256=row["payload_sha256"],
            accepted_at=row["admitted_at"],
        )

    @staticmethod
    def _row_to_operation(row: sqlite3.Row) -> AdmittedOperation:
        return AdmittedOperation(
            operation_id=row["operation_id"],
            request_id=row["request_id"],
            command=row["command"],
            payload_json=row["payload_json"],
            payload_sha256=row["payload_sha256"],
            state=row["state"],
            admitted_at=row["admitted_at"],
        )

    @staticmethod
    def _insert_operation(
        connection: sqlite3.Connection, operation: AdmittedOperation
    ) -> None:
        connection.execute(
            """
            INSERT INTO lab_admitted_operations (
                operation_id, request_id, command, payload_json,
                payload_sha256, state, admitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation.operation_id,
                operation.request_id,
                operation.command,
                operation.payload_json,
                operation.payload_sha256,
                operation.state,
                operation.admitted_at,
            ),
        )

    @staticmethod
    def _before_commit(_connection: sqlite3.Connection) -> None:
        """Test seam for proving rollback at the final transaction boundary."""

    def admit(
        self,
        request_id: str,
        command: str,
        payload: Any,
        *,
        dispatch_authorized: bool = True,
    ) -> OperationAck:
        """Persist an operation and its stable acknowledgement atomically.

        Direct/internal callers retain the historical immediately-dispatchable
        behavior. IPC callers pass ``dispatch_authorized=False`` so another
        process cannot claim the row while the acknowledgement is still being
        written to the transport. ``authorize_dispatch`` is the sole durable
        transition that releases such a row.
        """
        request_id = self._required_text(
            request_id, label="Request id", maximum=_MAX_ID_LENGTH
        )
        command = self._required_text(
            command, label="Command", maximum=_MAX_COMMAND_LENGTH
        )
        payload_json, payload_sha256 = self._canonical_payload(payload)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM lab_admitted_operations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is not None:
                existing = self._row_to_ack(row)
                if (
                    existing.command != command
                    or existing.payload_sha256 != payload_sha256
                ):
                    raise IdempotencyConflict(
                        f"Idempotency conflict for request id {request_id}"
                    )
                connection.commit()
                return OperationAck(
                    request_id=existing.request_id,
                    operation_id=existing.operation_id,
                    command=existing.command,
                    payload_sha256=existing.payload_sha256,
                    accepted_at=existing.accepted_at,
                    newly_admitted=False,
                )

            ack = OperationAck(
                request_id=request_id,
                operation_id=f"operation:{uuid.uuid4()}",
                command=command,
                payload_sha256=payload_sha256,
                accepted_at=time.time(),
            )
            operation = AdmittedOperation(
                operation_id=ack.operation_id,
                request_id=ack.request_id,
                command=ack.command,
                payload_json=payload_json,
                payload_sha256=ack.payload_sha256,
                state="ADMITTED",
                admitted_at=ack.accepted_at,
            )
            self._insert_operation(connection, operation)
            connection.execute(
                """
                INSERT INTO lab_operation_outbox(
                    operation_id, state, dispatch_authorized_at
                ) VALUES(?, 'PENDING', ?)
                """,
                (
                    operation.operation_id,
                    time.time() if dispatch_authorized else None,
                ),
            )
            self._before_commit(connection)
            connection.commit()
            return ack
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, request_id: str) -> OperationAck | None:
        if not isinstance(request_id, str) or not request_id.strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lab_admitted_operations WHERE request_id = ?",
                (request_id.strip(),),
            ).fetchone()
        return self._row_to_ack(row) if row is not None else None

    def get_operation(self, operation_id: str) -> AdmittedOperation | None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lab_admitted_operations WHERE operation_id = ?",
                (operation_id.strip(),),
            ).fetchone()
        return self._row_to_operation(row) if row is not None else None

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM lab_admitted_operations"
            ).fetchone()
        return int(row["total"])

    def pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM lab_operation_outbox WHERE state='PENDING'"
            ).fetchone()
        return int(row["total"])

    def pending_operation_ids(self, limit: int = 200) -> list[str]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT q.operation_id FROM lab_operation_outbox q
                JOIN lab_admitted_operations o ON o.operation_id=q.operation_id
                WHERE q.state='PENDING' AND q.dispatch_authorized_at IS NOT NULL
                ORDER BY o.admitted_at, o.operation_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["operation_id"]) for row in rows]

    def authorize_dispatch(self, operation_id: str) -> bool:
        """Durably release one admitted operation after its transport ACK.

        The transition is idempotent. ``True`` means the operation is pending
        and eligible (whether this call or an earlier replay authorized it).
        Terminal or already-claimed operations return ``False`` because there
        is no pending dispatch to release.
        """
        operation_id = self._required_text(
            operation_id, label="Operation id", maximum=_MAX_ID_LENGTH
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT q.state, q.dispatch_authorized_at
                FROM lab_operation_outbox q
                WHERE q.operation_id=?
                """,
                (operation_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown operation")
            if row["state"] != "PENDING":
                connection.commit()
                return False
            if row["dispatch_authorized_at"] is None:
                connection.execute(
                    """
                    UPDATE lab_operation_outbox
                    SET dispatch_authorized_at=?
                    WHERE operation_id=? AND state='PENDING'
                      AND dispatch_authorized_at IS NULL
                    """,
                    (time.time(), operation_id),
                )
            connection.commit()
            return True
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim(self, operation_id: str | None = None) -> AdmittedOperation | None:
        """Claim one pending outbox item once, before any external effect."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if operation_id is None:
                row = connection.execute(
                    """
                    SELECT o.* FROM lab_admitted_operations o
                    JOIN lab_operation_outbox q ON q.operation_id=o.operation_id
                    WHERE q.state='PENDING' AND q.dispatch_authorized_at IS NOT NULL
                    ORDER BY o.admitted_at, o.operation_id LIMIT 1
                    """
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT o.* FROM lab_admitted_operations o
                    JOIN lab_operation_outbox q ON q.operation_id=o.operation_id
                    WHERE o.operation_id=? AND q.state='PENDING'
                      AND q.dispatch_authorized_at IS NOT NULL
                    """,
                    (str(operation_id).strip(),),
                ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE lab_operation_outbox
                SET state='DISPATCHING', claimed_at=?, worker_pid=?, worker_started_at=?
                WHERE operation_id=? AND state='PENDING'
                """,
                (
                    time.time(),
                    os.getpid(),
                    psutil.Process(os.getpid()).create_time(),
                    row["operation_id"],
                ),
            )
            connection.commit()
            return self._row_to_operation(row)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _row_to_status(row: sqlite3.Row) -> OperationStatus:
        result_json = row["result_json"]
        return OperationStatus(
            operation_id=row["operation_id"],
            request_id=row["request_id"],
            command=row["command"],
            state=(
                row["result_state"]
                or ("ADMITTED" if row["outbox_state"] == "PENDING" else row["outbox_state"])
            ),
            result=json.loads(result_json) if result_json is not None else None,
            finished_at=(
                float(row["finished_at"]) if row["finished_at"] is not None else None
            ),
        )

    def operation_status(self, operation_id: str) -> OperationStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT o.operation_id, o.request_id, o.command,
                       q.state AS outbox_state, r.state AS result_state,
                       r.result_json, r.finished_at
                FROM lab_admitted_operations o
                JOIN lab_operation_outbox q ON q.operation_id=o.operation_id
                LEFT JOIN lab_operation_results r ON r.operation_id=o.operation_id
                WHERE o.operation_id=?
                """,
                (str(operation_id).strip(),),
            ).fetchone()
        return self._row_to_status(row) if row is not None else None

    def finish(
        self, operation_id: str, state: str, result: dict[str, Any]
    ) -> OperationStatus:
        """Persist one immutable terminal result and close its outbox item."""
        if state not in {"COMPLETED", "FAILED", "INTERRUPTED"}:
            raise ValueError("Invalid terminal operation state")
        if not isinstance(result, dict):
            raise ValueError("Operation result must be an object")
        result_json, result_sha256 = self._canonical_payload(result)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT state, result_sha256 FROM lab_operation_results WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if existing is not None:
                if existing["state"] != state or existing["result_sha256"] != result_sha256:
                    raise ValueError("Operation already has a different terminal result")
                connection.commit()
                status = self.operation_status(operation_id)
                assert status is not None
                return status
            outbox = connection.execute(
                "SELECT state FROM lab_operation_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if outbox is None:
                raise ValueError("Unknown operation")
            if outbox["state"] != "DISPATCHING":
                raise ValueError("Operation was not claimed for dispatch")
            finished_at = time.time()
            connection.execute(
                """
                INSERT INTO lab_operation_results(
                    operation_id, state, result_json, result_sha256, finished_at,
                    publication_state
                ) VALUES(?, ?, ?, ?, ?, 'PENDING')
                """,
                (operation_id, state, result_json, result_sha256, finished_at),
            )
            connection.execute(
                "UPDATE lab_operation_outbox SET state='DONE' WHERE operation_id=?",
                (operation_id,),
            )
            connection.execute(
                """
                INSERT INTO lab_operation_event_outbox(operation_id, state)
                VALUES(?, 'PENDING')
                """,
                (operation_id,),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        status = self.operation_status(operation_id)
        assert status is not None
        return status

    def claim_result_publications(self, limit: int = 200) -> list[OperationStatus]:
        """Claim terminal-result events so live publishers cannot duplicate them."""
        limit = max(1, min(int(limit), 200))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT operation_id FROM lab_operation_results
                WHERE publication_state='PENDING'
                ORDER BY finished_at, operation_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
            operation_ids = [str(row["operation_id"]) for row in rows]
            if operation_ids:
                placeholders = ",".join("?" for _ in operation_ids)
                connection.execute(
                    f"""
                    UPDATE lab_operation_results
                    SET publication_state='PUBLISHING', publisher_pid=?,
                        publisher_started_at=?
                    WHERE operation_id IN ({placeholders})
                      AND publication_state='PENDING'
                    """,
                    (
                        os.getpid(),
                        psutil.Process(os.getpid()).create_time(),
                        *operation_ids,
                    ),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return [
            status
            for operation_id in operation_ids
            if (status := self.operation_status(operation_id)) is not None
        ]

    def claim_event_publications(
        self, operation_id: str | None = None, limit: int = 200
    ) -> list[OperationStatus]:
        """Claim terminal results for the canonical Lab event stream."""
        limit = max(1, min(int(limit), 200))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if operation_id is None:
                rows = connection.execute(
                    """
                    SELECT operation_id FROM lab_operation_event_outbox
                    WHERE state='PENDING'
                    ORDER BY operation_id LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT operation_id FROM lab_operation_event_outbox
                    WHERE operation_id=? AND state='PENDING'
                    """,
                    (str(operation_id).strip(),),
                ).fetchall()
            operation_ids = [str(row["operation_id"]) for row in rows]
            if operation_ids:
                placeholders = ",".join("?" for _ in operation_ids)
                connection.execute(
                    f"""
                    UPDATE lab_operation_event_outbox
                    SET state='PUBLISHING', claimed_at=?, publisher_pid=?,
                        publisher_started_at=?
                    WHERE operation_id IN ({placeholders}) AND state='PENDING'
                    """,
                    (
                        time.time(),
                        os.getpid(),
                        psutil.Process(os.getpid()).create_time(),
                        *operation_ids,
                    ),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return [
            status
            for item_id in operation_ids
            if (status := self.operation_status(item_id)) is not None
        ]

    def publish_result_event(
        self,
        operation_id: str,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        occurred_at: float,
    ) -> bool:
        """Insert the canonical event and close its outbox in one transaction."""
        event_id = f"operation-result:{operation_id}"
        payload_json, _payload_sha256 = self._canonical_payload(payload)
        process_started_at = psutil.Process(os.getpid()).create_time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            claim = connection.execute(
                """
                SELECT state, publisher_pid, publisher_started_at
                FROM lab_operation_event_outbox WHERE operation_id=?
                """,
                (operation_id,),
            ).fetchone()
            if claim is None:
                raise ValueError("Operation result has no event publication")
            if claim["state"] == "PUBLISHED":
                connection.commit()
                return False
            if (
                claim["state"] != "PUBLISHING"
                or claim["publisher_pid"] != os.getpid()
                or abs(float(claim["publisher_started_at"]) - process_started_at) >= 0.01
            ):
                raise ValueError("Operation result was not claimed for event publication")
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO events(
                    id, type, session_id, entity_id, payload, occurred_at
                ) VALUES(?, 'operation.result', ?, ?, ?, ?)
                """,
                (event_id, session_id, operation_id, payload_json, occurred_at),
            ).rowcount == 1
            existing = connection.execute(
                "SELECT type, session_id, entity_id, payload FROM events WHERE id=?",
                (event_id,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("Operation event insert did not produce a durable row")
            if (
                existing["type"] != "operation.result"
                or existing["session_id"] != session_id
                or existing["entity_id"] != operation_id
                or json.loads(existing["payload"]) != payload
            ):
                raise ValueError("Operation event id already records different facts")
            changed = connection.execute(
                """
                UPDATE lab_operation_event_outbox
                SET state='PUBLISHED', published_at=?
                WHERE operation_id=? AND state='PUBLISHING'
                  AND publisher_pid=? AND publisher_started_at=?
                """,
                (time.time(), operation_id, os.getpid(), process_started_at),
            ).rowcount
            if changed != 1:
                raise RuntimeError("Operation event publication claim was lost")
            connection.commit()
            return inserted
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release_event_publication(self, operation_id: str) -> None:
        process_started_at = psutil.Process(os.getpid()).create_time()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE lab_operation_event_outbox
                SET state='PENDING', claimed_at=NULL, publisher_pid=NULL,
                    publisher_started_at=NULL
                WHERE operation_id=? AND state='PUBLISHING'
                  AND publisher_pid=? AND publisher_started_at=?
                """,
                (operation_id, os.getpid(), process_started_at),
            )

    def event_publication_state(self, operation_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state FROM lab_operation_event_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        return str(row["state"]) if row is not None else None

    def mark_result_published(self, operation_id: str) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE lab_operation_results
                SET publication_state='PUBLISHED', published_at=?
                WHERE operation_id=? AND publication_state='PUBLISHING'
                """,
                (time.time(), operation_id),
            ).rowcount
        if changed != 1:
            raise ValueError("Operation result was not claimed for publication")

    def release_result_publication(self, operation_id: str) -> None:
        process_started_at = psutil.Process(os.getpid()).create_time()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE lab_operation_results
                SET publication_state='PENDING', publisher_pid=NULL,
                    publisher_started_at=NULL
                WHERE operation_id=? AND publication_state='PUBLISHING'
                  AND publisher_pid=? AND publisher_started_at=?
                """,
                (operation_id, os.getpid(), process_started_at),
            )

    def _reconcile_result_publications(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT operation_id, publisher_pid, publisher_started_at
                FROM lab_operation_results WHERE publication_state='PUBLISHING'
                """
            ).fetchall()
            for row in rows:
                if self._worker_is_alive(
                    row["publisher_pid"], row["publisher_started_at"]
                ):
                    continue
                connection.execute(
                    """
                    UPDATE lab_operation_results
                    SET publication_state='PENDING', publisher_pid=NULL,
                        publisher_started_at=NULL
                    WHERE operation_id=? AND publication_state='PUBLISHING'
                    """,
                    (row["operation_id"],),
                )

    def _reconcile_event_publications(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT operation_id, publisher_pid, publisher_started_at
                FROM lab_operation_event_outbox WHERE state='PUBLISHING'
                """
            ).fetchall()
            for row in rows:
                if self._worker_is_alive(
                    row["publisher_pid"], row["publisher_started_at"]
                ):
                    continue
                connection.execute(
                    """
                    UPDATE lab_operation_event_outbox
                    SET state='PENDING', claimed_at=NULL, publisher_pid=NULL,
                        publisher_started_at=NULL
                    WHERE operation_id=? AND state='PUBLISHING'
                    """,
                    (row["operation_id"],),
                )

    @staticmethod
    def _worker_is_alive(worker_pid: int | None, worker_started_at: float | None) -> bool:
        if worker_pid is None or worker_started_at is None:
            return False
        try:
            process = psutil.Process(int(worker_pid))
            return process.is_running() and abs(process.create_time() - float(worker_started_at)) < 0.01
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except psutil.AccessDenied:
            return True

    def reconcile_interrupted(self) -> list[OperationStatus]:
        """Close only claims whose owning OS process is proven dead."""
        self._reconcile_result_publications()
        self._reconcile_event_publications()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT operation_id, worker_pid, worker_started_at
                FROM lab_operation_outbox
                WHERE state='DISPATCHING' ORDER BY claimed_at, operation_id
                """
            ).fetchall()
        recovered = []
        for row in rows:
            if self._worker_is_alive(row["worker_pid"], row["worker_started_at"]):
                continue
            recovered.append(
                self.finish(
                    row["operation_id"],
                    "INTERRUPTED",
                    {
                        "success": False,
                        "code": "DISPATCH_OUTCOME_UNKNOWN",
                        "error": (
                            "O processo foi interrompido após iniciar o despacho; "
                            "o efeito não será repetido automaticamente."
                        ),
                    },
                )
            )
        return recovered
