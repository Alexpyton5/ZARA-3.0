"""Independent research discovery inbox for Lab v1.

The inbox deliberately has no provider, network, frontend, or application
memory dependency.  It stores JSON-safe provenance records in SQLite and can
also be used in-memory for tests and small experiments.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from math import isfinite
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping
from urllib.parse import urlsplit


# A bounded excerpt keeps provenance records useful without allowing source
# pages (or accidental full-page captures) to become an unbounded data sink.
DEFAULT_EXCERPT_LIMIT = 2_000
MAX_EXCERPT_LENGTH = DEFAULT_EXCERPT_LIMIT


class ResearchInboxError(ValueError):
    """Base error for invalid research inbox input."""


class InvalidSourceURL(ResearchInboxError):
    """Raised when a discovery does not use an absolute HTTP(S) URL."""


class ExcerptTooLong(ResearchInboxError):
    """Raised when an excerpt exceeds the configured character limit."""


class InvalidResearchStatus(ResearchInboxError):
    """Raised when a status is not part of the inbox lifecycle."""


class InvalidRelevance(ResearchInboxError):
    """Raised when relevance is not a finite numeric value."""


class ResearchStatus(str, Enum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    ADOPTED = "ADOPTED"


RESEARCH_STATUSES = tuple(status.value for status in ResearchStatus)
INBOX_STATUSES = RESEARCH_STATUSES
VALID_STATUSES = RESEARCH_STATUSES


_FIELDS = (
    "source_url",
    "title",
    "excerpt",
    "captured_at",
    "researcher",
    "relevance",
    "evidence_hash",
    "status",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_source_url(source_url: str) -> str:
    if not isinstance(source_url, str):
        raise InvalidSourceURL("source_url must be a string")
    value = source_url.strip()
    if not value:
        raise InvalidSourceURL("source_url must not be empty")
    if any(character.isspace() for character in value):
        raise InvalidSourceURL("source_url must not contain whitespace")

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidSourceURL("source_url must use HTTP or HTTPS")
    # urlsplit accepts strings such as ``https://`` without raising.  An
    # absolute URL needs a host; accessing hostname also catches malformed
    # bracketed IPv6 hosts.
    try:
        hostname = parsed.hostname
    except ValueError as exc:
        raise InvalidSourceURL("source_url has an invalid host") from exc
    if not parsed.netloc or not hostname:
        raise InvalidSourceURL("source_url must include a host")

    # Scheme names are case-insensitive.  Preserve the rest of the URL so
    # paths and query values retain their source spelling.
    return parsed._replace(scheme=scheme).geturl()


def _normalize_excerpt(excerpt: str, limit: int) -> str:
    if not isinstance(excerpt, str):
        raise ResearchInboxError("excerpt must be a string")
    if len(excerpt) > limit:
        raise ExcerptTooLong(
            f"excerpt exceeds the configured limit of {limit} characters"
        )
    return excerpt


def _normalize_captured_at(captured_at: str | datetime | None) -> str:
    if captured_at is None:
        return _utc_now()
    if isinstance(captured_at, datetime):
        value = captured_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if not isinstance(captured_at, str):
        raise ResearchInboxError("captured_at must be an ISO string or datetime")
    value = captured_at.strip()
    if not value:
        raise ResearchInboxError("captured_at must not be empty")
    return value


def _normalize_relevance(relevance: Any) -> int | float:
    if isinstance(relevance, bool):
        raise InvalidRelevance("relevance must be numeric")
    if not isinstance(relevance, (int, float)):
        raise InvalidRelevance("relevance must be numeric")
    value = float(relevance)
    if not isfinite(value):
        raise InvalidRelevance("relevance must be finite")
    # Keep integer inputs JSON-friendly while SQLite still stores a numeric
    # value.  Equality with a float remains intuitive for callers.
    return int(relevance) if isinstance(relevance, int) else value


def _normalize_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ResearchInboxError(f"{field} must be a string")
    return value


def _coerce_status(status: str | ResearchStatus) -> str:
    if isinstance(status, ResearchStatus):
        return status.value
    if isinstance(status, str):
        candidate = status.strip().upper()
        if candidate in VALID_STATUSES:
            return candidate
    raise InvalidResearchStatus(
        f"status must be one of: {', '.join(VALID_STATUSES)}"
    )


def _make_evidence_hash(
    *,
    source_url: str,
    title: str,
    excerpt: str,
    captured_at: str,
    researcher: str,
    relevance: int | float,
) -> str:
    """Create a deterministic SHA-256 provenance hash when one is omitted."""
    payload = {
        "source_url": source_url,
        "title": title,
        "excerpt": excerpt,
        "captured_at": captured_at,
        "researcher": researcher,
        "relevance": relevance,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ResearchInboxStore:
    """Small independent store for research discoveries.

    ``source_url`` and ``evidence_hash`` are both unique.  Inserting a record
    that collides with either one is idempotent and returns the already stored
    record; the original provenance and status are never silently replaced.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        excerpt_limit: int = DEFAULT_EXCERPT_LIMIT,
        max_excerpt_length: int | None = None,
    ) -> None:
        if max_excerpt_length is not None:
            excerpt_limit = max_excerpt_length
        if isinstance(excerpt_limit, bool) or not isinstance(excerpt_limit, int):
            raise ResearchInboxError("excerpt_limit must be a positive integer")
        if excerpt_limit <= 0:
            raise ResearchInboxError("excerpt_limit must be a positive integer")

        self.excerpt_limit = excerpt_limit
        self._lock = threading.RLock()
        self._memory_connection: sqlite3.Connection | None = None
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            database_path = Path(db_path).expanduser()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
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
        return connection

    def _close(self, connection: sqlite3.Connection) -> None:
        if connection is not self._memory_connection:
            connection.close()

    def close(self) -> None:
        with self._lock:
            if self._memory_connection is not None:
                self._memory_connection.close()
                self._memory_connection = None

    def __enter__(self) -> "ResearchInboxStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_inbox (
                    inbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    researcher TEXT NOT NULL,
                    relevance REAL NOT NULL,
                    evidence_hash TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('NEW', 'REVIEWED', 'REJECTED', 'ADOPTED'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_inbox_status "
                "ON research_inbox (status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_inbox_captured_at "
                "ON research_inbox (captured_at)"
            )
            connection.commit()
        finally:
            self._close(connection)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "source_url": str(row["source_url"]),
            "title": str(row["title"]),
            "excerpt": str(row["excerpt"]),
            "captured_at": str(row["captured_at"]),
            "researcher": str(row["researcher"]),
            "relevance": row["relevance"],
            "evidence_hash": str(row["evidence_hash"]),
            "status": str(row["status"]),
        }

    def _prepare_item(
        self,
        source_url: str,
        title: str,
        excerpt: str,
        captured_at: str | datetime | None,
        researcher: str,
        relevance: Any,
        evidence_hash: str | None,
        status: str | ResearchStatus,
    ) -> dict[str, Any]:
        normalized_url = _normalize_source_url(source_url)
        normalized_title = _normalize_text(title, "title")
        normalized_excerpt = _normalize_excerpt(excerpt, self.excerpt_limit)
        normalized_captured_at = _normalize_captured_at(captured_at)
        normalized_researcher = _normalize_text(researcher, "researcher")
        normalized_relevance = _normalize_relevance(relevance)
        if evidence_hash is None:
            normalized_hash = _make_evidence_hash(
                source_url=normalized_url,
                title=normalized_title,
                excerpt=normalized_excerpt,
                captured_at=normalized_captured_at,
                researcher=normalized_researcher,
                relevance=normalized_relevance,
            )
        else:
            if not isinstance(evidence_hash, str) or not evidence_hash.strip():
                raise ResearchInboxError("evidence_hash must not be empty")
            normalized_hash = evidence_hash.strip()
        return {
            "source_url": normalized_url,
            "title": normalized_title,
            "excerpt": normalized_excerpt,
            "captured_at": normalized_captured_at,
            "researcher": normalized_researcher,
            "relevance": normalized_relevance,
            "evidence_hash": normalized_hash,
            "status": _coerce_status(status),
        }

    def add_discovery(
        self,
        source_url: str | Mapping[str, Any],
        title: str = "",
        excerpt: str = "",
        captured_at: str | datetime | None = None,
        researcher: str = "",
        relevance: int | float = 0.0,
        evidence_hash: str | None = None,
        status: str | ResearchStatus = ResearchStatus.NEW,
        **fields: Any,
    ) -> dict[str, Any]:
        """Insert a discovery, or return the existing item on URL/hash collision.

        A mapping may be supplied as the first argument.  ``captured_at`` is
        generated in UTC when omitted and ``evidence_hash`` is generated with
        SHA-256 when omitted, making the method convenient for local callers
        while retaining an explicit provenance field in every returned item.
        """
        if isinstance(source_url, Mapping):
            incoming = dict(source_url)
            source_url = incoming.pop("source_url", incoming.pop("url", None))
            if source_url is None:
                raise InvalidSourceURL("source_url is required")
            title = incoming.pop("title", title)
            excerpt = incoming.pop("excerpt", excerpt)
            captured_at = incoming.pop("captured_at", captured_at)
            researcher = incoming.pop("researcher", researcher)
            relevance = incoming.pop("relevance", relevance)
            evidence_hash = incoming.pop("evidence_hash", evidence_hash)
            status = incoming.pop("status", status)
            fields = {**incoming, **fields}
        if fields:
            # Keep the public schema narrow: accepting aliases here prevents
            # accidental metadata columns while making a typo visible.
            unknown = ", ".join(sorted(fields))
            raise ResearchInboxError(f"unknown research inbox field(s): {unknown}")

        item = self._prepare_item(
            source_url,
            title,
            excerpt,
            captured_at,
            researcher,
            relevance,
            evidence_hash,
            status,
        )
        connection = self._connect()
        try:
            with self._lock:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO research_inbox (
                        source_url, title, excerpt, captured_at, researcher,
                        relevance, evidence_hash, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(item[field] for field in _FIELDS),
                )
                connection.commit()
                row = connection.execute(
                    """
                    SELECT * FROM research_inbox
                    WHERE source_url = ? OR evidence_hash = ?
                    ORDER BY inbox_id ASC
                    LIMIT 1
                    """,
                    (item["source_url"], item["evidence_hash"]),
                ).fetchone()
        finally:
            self._close(connection)
        if row is None:  # defensive; INSERT OR IGNORE plus lookup is atomic here
            raise RuntimeError("research inbox insertion did not produce a record")
        return self._row_to_dict(row)

    # Short aliases make the independent component easy to embed.
    add = add_discovery
    register = add_discovery
    capture = add_discovery
    enqueue = add_discovery
    create = add_discovery

    def get(self, source_url: str) -> dict[str, Any] | None:
        """Return an item by source URL, or ``None`` if absent."""
        normalized_url = _normalize_source_url(source_url)
        connection = self._connect()
        try:
            with self._lock:
                row = connection.execute(
                    "SELECT * FROM research_inbox WHERE source_url = ?",
                    (normalized_url,),
                ).fetchone()
        finally:
            self._close(connection)
        return None if row is None else self._row_to_dict(row)

    get_discovery = get
    get_item = get

    def get_by_hash(self, evidence_hash: str) -> dict[str, Any] | None:
        if not isinstance(evidence_hash, str) or not evidence_hash.strip():
            raise ResearchInboxError("evidence_hash must not be empty")
        connection = self._connect()
        try:
            with self._lock:
                row = connection.execute(
                    "SELECT * FROM research_inbox WHERE evidence_hash = ?",
                    (evidence_hash.strip(),),
                ).fetchone()
        finally:
            self._close(connection)
        return None if row is None else self._row_to_dict(row)

    def list_items(
        self,
        status: str | ResearchStatus | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        normalized_status = None if status is None else _coerce_status(status)
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
        ):
            raise ResearchInboxError("limit must be a non-negative integer or None")
        query = "SELECT * FROM research_inbox"
        parameters: list[Any] = []
        if normalized_status is not None:
            query += " WHERE status = ?"
            parameters.append(normalized_status)
        query += " ORDER BY inbox_id DESC"
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

    list_all = list_items
    list = list_items

    def update_status(
        self,
        source_url_or_hash: str,
        status: str | ResearchStatus,
    ) -> dict[str, Any] | None:
        """Update one item by URL or evidence hash without creating a row."""
        if not isinstance(source_url_or_hash, str) or not source_url_or_hash.strip():
            raise ResearchInboxError("source_url_or_hash must not be empty")
        normalized_status = _coerce_status(status)
        key = source_url_or_hash.strip()
        connection = self._connect()
        try:
            with self._lock:
                row = connection.execute(
                    """
                    SELECT inbox_id FROM research_inbox
                    WHERE source_url = ? OR evidence_hash = ?
                    ORDER BY inbox_id ASC
                    LIMIT 1
                    """,
                    (key, key),
                ).fetchone()
                if row is None:
                    return None
                connection.execute(
                    "UPDATE research_inbox SET status = ? WHERE inbox_id = ?",
                    (normalized_status, row["inbox_id"]),
                )
                connection.commit()
                updated = connection.execute(
                    "SELECT * FROM research_inbox WHERE inbox_id = ?",
                    (row["inbox_id"],),
                ).fetchone()
        finally:
            self._close(connection)
        return None if updated is None else self._row_to_dict(updated)

    set_status = update_status
    review = update_status

    def count(self, status: str | ResearchStatus | None = None) -> int:
        normalized_status = None if status is None else _coerce_status(status)
        connection = self._connect()
        try:
            with self._lock:
                if normalized_status is None:
                    row = connection.execute(
                        "SELECT COUNT(*) FROM research_inbox"
                    ).fetchone()
                else:
                    row = connection.execute(
                        "SELECT COUNT(*) FROM research_inbox WHERE status = ?",
                        (normalized_status,),
                    ).fetchone()
        finally:
            self._close(connection)
        return int(row[0])

    def __len__(self) -> int:
        return self.count()


# Friendly names for callers that do not need the storage detail in their code.
ResearchInbox = ResearchInboxStore
InboxStore = ResearchInboxStore


__all__ = [
    "DEFAULT_EXCERPT_LIMIT",
    "ExcerptTooLong",
    "INBOX_STATUSES",
    "InboxStore",
    "InvalidRelevance",
    "InvalidResearchStatus",
    "InvalidSourceURL",
    "MAX_EXCERPT_LENGTH",
    "RESEARCH_STATUSES",
    "ResearchInbox",
    "ResearchInboxError",
    "ResearchInboxStore",
    "ResearchStatus",
    "VALID_STATUSES",
]
