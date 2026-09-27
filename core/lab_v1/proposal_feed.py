"""Persistent proposal feed for the Lab.

The module deliberately depends only on the Python standard library.  A
:class:`ProposalFeedStore` instance stores proposals in SQLite when given a
filesystem path and can also be used with ``":memory:"`` in tests.

The public methods return plain dictionaries/lists containing only JSON-safe
values.  The database is an implementation detail: callers never receive a
``sqlite3.Row``, enum, datetime, or connection object.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import suppress
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Final


class ProposalState(str, Enum):
    """States supported by the Lab proposal lifecycle."""

    PROPOSED = "PROPOSED"
    DISCUSSING = "DISCUSSING"
    CANDIDATE = "CANDIDATE"
    TESTED = "TESTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVATED = "ACTIVATED"


# A tuple is useful for stable API/documentation output; the frozenset is used
# for validation without allowing callers to mutate the set.
PROPOSAL_STATES: Final[tuple[str, ...]] = tuple(state.value for state in ProposalState)
VALID_STATES: Final[frozenset[str]] = frozenset(PROPOSAL_STATES)


class ProposalFeedError(ValueError):
    """Base error for invalid proposal-feed input."""


class InvalidProposalState(ProposalFeedError):
    """Raised when a state is not one of :data:`PROPOSAL_STATES`."""


_MISSING: Final[object] = object()
_RESERVED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "proposal_id",
        "id",
        "title",
        "name",
        "description",
        "summary",
        "state",
        "status",
        "evidence_refs",
        "created_at",
        "updated_at",
        "metadata",
    }
)


def _utc_now() -> str:
    """Return a sortable, timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Convert common Python values into values accepted by ``json.dumps``.

    Evidence references and optional metadata are persisted as JSON.  Being
    conservative here means all public return values remain JSON-safe even if
    a caller supplies a tuple, enum, date, or a custom scalar.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    # A string representation is preferable to leaking a non-serializable
    # object or failing after the proposal has already been written.
    return str(value)


def _json_loads(value: str, default: Any) -> Any:
    """Decode a JSON column, returning ``default`` for malformed old data."""

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return _json_safe(decoded)


def _coerce_state(state: str | ProposalState) -> str:
    """Validate and normalize a proposal state to its wire representation."""

    if isinstance(state, ProposalState):
        return state.value
    if not isinstance(state, str):
        raise InvalidProposalState(
            f"state must be one of {', '.join(PROPOSAL_STATES)}"
        )
    normalized = state.strip().upper().replace("-", "_").replace(" ", "_")
    if normalized not in VALID_STATES:
        raise InvalidProposalState(
            f"unknown proposal state {state!r}; expected one of "
            f"{', '.join(PROPOSAL_STATES)}"
        )
    return normalized


def _normalize_evidence_refs(evidence_refs: Any) -> list[Any]:
    """Normalize evidence refs to a JSON-safe list without splitting strings."""

    if evidence_refs is None:
        return []
    if isinstance(evidence_refs, (str, bytes)):
        values: Iterable[Any] = [
            evidence_refs.decode("utf-8", errors="replace")
            if isinstance(evidence_refs, bytes)
            else evidence_refs
        ]
    elif isinstance(evidence_refs, Iterable):
        values = evidence_refs
    else:
        values = [evidence_refs]
    return [_json_safe(value) for value in values]


def _validate_proposal_id(proposal_id: Any) -> str:
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ProposalFeedError("proposal_id must be a non-empty string")
    return proposal_id.strip()


class ProposalFeedStore:
    """SQLite-backed store for proposals in the Lab.

    Parameters
    ----------
    db_path:
        SQLite path.  Supplying a filesystem path makes the feed persistent
        across store instances.  ``":memory:"`` is supported for isolated
        tests.  The default is an in-memory store so importing or constructing
        the module never touches an active application database.
    path:
        Keyword alias for ``db_path``.

    Registration is idempotent by ``proposal_id``: a second registration
    returns the existing proposal and does not reset its state or timestamps.
    State changes are explicit through :meth:`update_state`.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        path: str | Path | None = None,
    ) -> None:
        if path is not None:
            if db_path != ":memory:":
                raise TypeError("pass either db_path or path, not both")
            db_path = path

        self.db_path = str(db_path)
        self._lock = RLock()
        self._memory_connection: sqlite3.Connection | None = None

        if self.db_path != ":memory:":
            db_file = Path(self.db_path).expanduser()
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_file)

        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """Open the SQLite connection used by the store.

        This intentionally remains a small, overridable method.  It gives
        tests and embedders one connection seam while keeping all public
        operations independent of a global database or provider.
        """

        if self.db_path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(
                    self.db_path, timeout=30, check_same_thread=False
                )
            connection = self._memory_connection
        else:
            connection = sqlite3.connect(
                self.db_path, timeout=30, check_same_thread=False
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _close(self, connection: sqlite3.Connection) -> None:
        """Close file-backed connections while retaining the memory handle."""

        if connection is not self._memory_connection:
            connection.close()

    def close(self) -> None:
        """Close an in-memory connection, if one exists.

        File-backed operations use short-lived connections and therefore have
        nothing to close here.  Calling ``close`` more than once is harmless.
        """

        with self._lock:
            if self._memory_connection is not None:
                self._memory_connection.close()
                self._memory_connection = None

    def __enter__(self) -> "ProposalFeedStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_proposals_state "
                "ON proposals (state)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_proposals_updated_at "
                "ON proposals (updated_at)"
            )
            connection.commit()
        finally:
            self._close(connection)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a database row into a JSON-safe public representation."""

        metadata = _json_loads(row["metadata"], {})
        if not isinstance(metadata, dict):
            metadata = {}

        result: dict[str, Any] = {
            "proposal_id": str(row["proposal_id"]),
            "title": str(row["title"]),
            "description": str(row["description"]),
            "state": str(row["state"]),
            "evidence_refs": _normalize_evidence_refs(
                _json_loads(row["evidence_refs"], [])
            ),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        # Preserve optional caller fields at the top level.  Avoid allowing
        # metadata to overwrite the stable feed contract.
        for key, value in metadata.items():
            if key not in result:
                result[key] = _json_safe(value)
        return result

    def register_proposal(
        self,
        proposal_id: str | Mapping[str, Any] | None = None,
        title: str = "",
        description: str = "",
        *,
        state: str | ProposalState | None = None,
        evidence_refs: Any = None,
        summary: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Register a proposal, returning the inserted or existing record.

        ``proposal_id`` may also be a mapping, which is convenient when a Lab
        proposal already exists as a JSON-like object.  ``summary`` is treated
        as a description alias and is also retained in the returned record.
        Additional fields are stored as JSON metadata.
        """

        if isinstance(proposal_id, Mapping):
            incoming = dict(proposal_id)
            proposal_id = incoming.pop("proposal_id", incoming.pop("id", None))
            title = incoming.pop("title", incoming.pop("name", title))
            description = incoming.pop(
                "description", incoming.get("summary", description)
            )
            if state is None:
                state = incoming.pop("state", incoming.pop("status", None))
            else:
                incoming.pop("state", None)
                incoming.pop("status", None)
            if evidence_refs is None:
                evidence_refs = incoming.pop("evidence_refs", None)
            else:
                incoming.pop("evidence_refs", None)
            if summary is None and "summary" in incoming:
                summary = str(incoming["summary"])
            fields = {**incoming, **fields}

        # Allow ``register_proposal(proposal={...})`` without making the
        # normal, explicit proposal_id call cumbersome.
        if proposal_id is None and "proposal" in fields:
            proposal = fields.pop("proposal")
            if not isinstance(proposal, Mapping):
                raise ProposalFeedError("proposal must be a mapping")
            return self.register_proposal(
                proposal,
                title=title,
                description=description,
                state=state,
                evidence_refs=evidence_refs,
                summary=summary,
                metadata=metadata,
                **fields,
            )

        normalized_id = _validate_proposal_id(proposal_id)
        normalized_state = (
            _coerce_state(state) if state is not None else ProposalState.PROPOSED.value
        )
        safe_refs = _normalize_evidence_refs(evidence_refs)
        safe_metadata: dict[str, Any] = {}
        if metadata is not None:
            if not isinstance(metadata, Mapping):
                raise ProposalFeedError("metadata must be a mapping")
            safe_metadata.update(_json_safe(metadata))
        safe_metadata.update(
            {
                key: _json_safe(value)
                for key, value in fields.items()
                if key not in _RESERVED_FIELDS
            }
        )
        if summary is not None:
            safe_metadata["summary"] = str(summary)

        now = _utc_now()
        connection = self._connect()
        try:
            with self._lock:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO proposals (
                        proposal_id, title, description, state, evidence_refs,
                        metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_id,
                        str(title),
                        str(description),
                        normalized_state,
                        json.dumps(safe_refs, ensure_ascii=False),
                        json.dumps(safe_metadata, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id = ?",
                    (normalized_id,),
                ).fetchone()
        finally:
            self._close(connection)

        # The INSERT and SELECT happen in one locked operation, so this is
        # defensive only (and makes the return contract explicit).
        if row is None:
            raise RuntimeError("proposal registration did not produce a record")
        return self._row_to_dict(row)

    # Short aliases keep the independent module pleasant to use while the
    # explicit method above remains the canonical API.
    add_proposal = register_proposal
    create_proposal = register_proposal
    register = register_proposal
    add = register_proposal

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        """Return one proposal by ID, or ``None`` when it does not exist."""

        normalized_id = _validate_proposal_id(proposal_id)
        connection = self._connect()
        try:
            with self._lock:
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id = ?",
                    (normalized_id,),
                ).fetchone()
        finally:
            self._close(connection)
        return None if row is None else self._row_to_dict(row)

    get = get_proposal

    def list_proposals(
        self,
        state: str | ProposalState | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List proposals, newest first, optionally filtered by state."""

        normalized_state = None if state is None else _coerce_state(state)
        if limit is not None and (isinstance(limit, bool) or limit < 0):
            raise ProposalFeedError("limit must be a non-negative integer or None")
        if limit is not None and not isinstance(limit, int):
            raise ProposalFeedError("limit must be a non-negative integer or None")

        query = "SELECT * FROM proposals"
        parameters: list[Any] = []
        if normalized_state is not None:
            query += " WHERE state = ?"
            parameters.append(normalized_state)
        query += " ORDER BY created_at DESC, proposal_id DESC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        connection = self._connect()
        try:
            with self._lock:
                rows = connection.execute(query, parameters).fetchall()
        finally:
            self._close(connection)
        return [self._row_to_dict(row) for row in rows]

    list_all = list_proposals
    list = list_proposals

    def update_state(
        self,
        proposal_id: str,
        state: str | ProposalState,
    ) -> dict[str, Any] | None:
        """Change a proposal's state and return the updated JSON-safe record.

        ``None`` is returned for an unknown ``proposal_id``; no row is created
        accidentally by a state update.
        """

        normalized_id = _validate_proposal_id(proposal_id)
        normalized_state = _coerce_state(state)
        connection = self._connect()
        try:
            with self._lock:
                existing = connection.execute(
                    "SELECT proposal_id FROM proposals WHERE proposal_id = ?",
                    (normalized_id,),
                ).fetchone()
                if existing is None:
                    return None
                connection.execute(
                    "UPDATE proposals SET state = ?, updated_at = ? "
                    "WHERE proposal_id = ?",
                    (normalized_state, _utc_now(), normalized_id),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id = ?",
                    (normalized_id,),
                ).fetchone()
        finally:
            self._close(connection)
        return None if row is None else self._row_to_dict(row)

    set_state = update_state
    change_state = update_state
    transition = update_state

    def count(self, state: str | ProposalState | None = None) -> int:
        """Return the number of stored proposals, optionally by state."""

        normalized_state = None if state is None else _coerce_state(state)
        connection = self._connect()
        try:
            with self._lock:
                if normalized_state is None:
                    row = connection.execute("SELECT COUNT(*) FROM proposals").fetchone()
                else:
                    row = connection.execute(
                        "SELECT COUNT(*) FROM proposals WHERE state = ?",
                        (normalized_state,),
                    ).fetchone()
        finally:
            self._close(connection)
        return int(row[0])


# Names commonly used by callers; all point to the same implementation.
ProposalStore = ProposalFeedStore
ProposalFeed = ProposalFeedStore

__all__ = [
    "InvalidProposalState",
    "PROPOSAL_STATES",
    "ProposalFeed",
    "ProposalFeedError",
    "ProposalFeedStore",
    "ProposalState",
    "ProposalStore",
    "VALID_STATES",
]
