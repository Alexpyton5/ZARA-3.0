"""Deterministic, cache-backed web research primitives for ZARA.

This module deliberately stops at source collection.  It does not call an LLM,
compose an answer, or infer publication dates.  Callers receive numbered source
records whose URL and content digest can be verified locally.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

DEFAULT_CACHE_TTL_SECONDS = 15 * 60
DEFAULT_MAX_RESULTS = 5
_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref_src",
    }
)


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""

    return datetime.now(UTC)


def _require_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _datetime_to_text(value: datetime) -> str:
    return _require_utc(value, "datetime").isoformat().replace("+00:00", "Z")


def _datetime_from_text(value: str, field_name: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO-8601 datetime") from exc
    return _require_utc(parsed, field_name)


def _optional_datetime(value: Any, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _require_utc(value, field_name)
    if isinstance(value, str):
        return _datetime_from_text(value, field_name)
    raise TypeError(f"{field_name} must be a datetime, ISO-8601 string, or None")


def canonicalize_url(url: str) -> str:
    """Return a stable HTTP(S) URL suitable for cache keys and deduplication."""

    raw = str(url or "").strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("A canonical URL must be an absolute HTTP(S) URL")

    try:
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("URL contains an invalid host or port") from exc

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"

    # Preserve URL path semantics while normalizing escaping and an empty root.
    path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.casefold()
        if normalized_key.startswith("utm_") or normalized_key in _TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query_items.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def content_sha256(content: str) -> str:
    """Return the lowercase SHA-256 hex digest for source content."""

    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One fetched source, with enough provenance to verify a citation."""

    citation_number: int
    url: str
    canonical_url: str
    title: str
    content: str
    content_hash: str
    retrieved_at: datetime
    published_at: datetime | None = None
    snippet: str = ""
    etag: str | None = None
    last_modified: str | None = None
    from_cache: bool = False

    def __post_init__(self) -> None:
        if self.citation_number < 0:
            raise ValueError("citation_number cannot be negative")
        canonical = canonicalize_url(self.canonical_url or self.url)
        if canonical != self.canonical_url:
            raise ValueError("canonical_url must already be canonicalized")
        digest = content_sha256(self.content)
        if digest != self.content_hash:
            raise ValueError("content_hash does not match content")
        object.__setattr__(self, "retrieved_at", _require_utc(self.retrieved_at, "retrieved_at"))
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _require_utc(self.published_at, "published_at"),
            )

    @property
    def citation(self) -> str:
        return f"[{self.citation_number}]"

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "citation_number": self.citation_number,
            "citation": self.citation,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "snippet": self.snippet,
            "content_hash": self.content_hash,
            "retrieved_at": _datetime_to_text(self.retrieved_at),
            "published_at": (
                _datetime_to_text(self.published_at) if self.published_at is not None else None
            ),
            "etag": self.etag,
            "last_modified": self.last_modified,
            "from_cache": self.from_cache,
        }
        if include_content:
            data["content"] = self.content
        return data


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Source-only research output with consecutive, verifiable citations."""

    query: str
    sources: tuple[SourceRecord, ...]
    retrieved_at: datetime
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query cannot be empty")
        object.__setattr__(self, "retrieved_at", _require_utc(self.retrieved_at, "retrieved_at"))
        expected = tuple(range(1, len(self.sources) + 1))
        actual = tuple(source.citation_number for source in self.sources)
        if actual != expected:
            raise ValueError("source citations must be consecutive and start at 1")

    @property
    def citations(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "number": source.citation_number,
                "marker": source.citation,
                "title": source.title,
                "url": source.url,
                "canonical_url": source.canonical_url,
                "content_hash": source.content_hash,
                "retrieved_at": _datetime_to_text(source.retrieved_at),
                "published_at": (
                    _datetime_to_text(source.published_at)
                    if source.published_at is not None
                    else None
                ),
            }
            for source in self.sources
        )

    def source_for_citation(self, number: int) -> SourceRecord:
        if number < 1 or number > len(self.sources):
            raise KeyError(f"Unknown citation: [{number}]")
        return self.sources[number - 1]

    def verify_citation(
        self,
        number: int,
        *,
        url: str | None = None,
        content_hash: str | None = None,
    ) -> bool:
        """Verify a citation marker against optional URL and digest evidence."""

        try:
            source = self.source_for_citation(number)
        except KeyError:
            return False
        if content_sha256(source.content) != source.content_hash:
            return False
        if canonicalize_url(source.url) != source.canonical_url:
            return False
        if url is not None and canonicalize_url(url) != source.canonical_url:
            return False
        return content_hash is None or content_hash.casefold() == source.content_hash.casefold()

    def verify_citations(self) -> bool:
        canonical_urls: set[str] = set()
        content_hashes: set[str] = set()
        for source in self.sources:
            if not self.verify_citation(source.citation_number):
                return False
            if source.canonical_url in canonical_urls or source.content_hash in content_hashes:
                return False
            canonical_urls.add(source.canonical_url)
            content_hashes.add(source.content_hash)
        return True

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        return {
            "query": self.query,
            "retrieved_at": _datetime_to_text(self.retrieved_at),
            "sources": [
                source.to_dict(include_content=include_content) for source in self.sources
            ],
            "citations": list(self.citations),
            "warnings": list(self.warnings),
        }

    def to_json(self, *, include_content: bool = True) -> str:
        return json.dumps(
            self.to_dict(include_content=include_content),
            ensure_ascii=False,
            indent=2,
        )


@dataclass(frozen=True, slots=True)
class CacheLookup:
    record: SourceRecord
    is_fresh: bool
    age_seconds: float


class SQLiteWebCache:
    """Small injectable SQLite cache for fetched web sources."""

    def __init__(
        self,
        database: str | Path | sqlite3.Connection = ":memory:",
        *,
        ttl_seconds: int | float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        if float(ttl_seconds) < 0:
            raise ValueError("ttl_seconds cannot be negative")
        self.ttl_seconds = float(ttl_seconds)
        self._lock = threading.RLock()
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        if isinstance(database, sqlite3.Connection):
            self._connection = database
        else:
            database_text = str(database)
            if database_text != ":memory:":
                Path(database_text).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(database_text, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS realtime_web_cache (
                    canonical_url TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    published_at TEXT,
                    etag TEXT,
                    last_modified TEXT
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_realtime_web_hash "
                "ON realtime_web_cache(content_hash)"
            )

    def lookup(self, url: str, *, now: datetime | None = None) -> CacheLookup | None:
        canonical_url = canonicalize_url(url)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM realtime_web_cache WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()
        if row is None:
            return None
        record = self._row_to_record(row)
        observed_at = _require_utc(now or utc_now(), "now")
        age = max(0.0, (observed_at - record.retrieved_at).total_seconds())
        return CacheLookup(record=record, is_fresh=age <= self.ttl_seconds, age_seconds=age)

    def get(self, url: str, *, now: datetime | None = None) -> SourceRecord | None:
        """Return a source only while it remains within the configured TTL."""

        lookup = self.lookup(url, now=now)
        return lookup.record if lookup is not None and lookup.is_fresh else None

    def put(self, record: SourceRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO realtime_web_cache (
                    canonical_url, url, title, snippet, content, content_hash,
                    retrieved_at, published_at, etag, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    url = excluded.url,
                    title = excluded.title,
                    snippet = excluded.snippet,
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    retrieved_at = excluded.retrieved_at,
                    published_at = excluded.published_at,
                    etag = excluded.etag,
                    last_modified = excluded.last_modified
                """,
                (
                    record.canonical_url,
                    record.url,
                    record.title,
                    record.snippet,
                    record.content,
                    record.content_hash,
                    _datetime_to_text(record.retrieved_at),
                    (
                        _datetime_to_text(record.published_at)
                        if record.published_at is not None
                        else None
                    ),
                    record.etag,
                    record.last_modified,
                ),
            )

    def revalidate(
        self,
        record: SourceRecord,
        *,
        retrieved_at: datetime,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> SourceRecord:
        refreshed = replace(
            record,
            citation_number=0,
            retrieved_at=_require_utc(retrieved_at, "retrieved_at"),
            etag=etag or record.etag,
            last_modified=last_modified or record.last_modified,
            from_cache=True,
        )
        self.put(refreshed)
        return refreshed

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM realtime_web_cache")

    def close(self) -> None:
        if self._owns_connection:
            with self._lock:
                self._connection.close()

    def __enter__(self) -> SQLiteWebCache:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SourceRecord:
        published_at = (
            _datetime_from_text(row["published_at"], "published_at")
            if row["published_at"]
            else None
        )
        return SourceRecord(
            citation_number=0,
            url=row["url"],
            canonical_url=row["canonical_url"],
            title=row["title"],
            snippet=row["snippet"],
            content=row["content"],
            content_hash=row["content_hash"],
            retrieved_at=_datetime_from_text(row["retrieved_at"], "retrieved_at"),
            published_at=published_at,
            etag=row["etag"],
            last_modified=row["last_modified"],
            from_cache=True,
        )


class _ActionResultLike(Protocol):
    success: bool
    output: str
    error: str
    data: Any


SearchCallable = Callable[..., _ActionResultLike]
FetchCallable = Callable[..., _ActionResultLike]
ClockCallable = Callable[[], datetime]


class RealtimeWebResearch:
    """Collect current web sources through injected, read-only actions."""

    def __init__(
        self,
        *,
        search_action: SearchCallable | None = None,
        fetch_action: FetchCallable | None = None,
        cache: SQLiteWebCache | None = None,
        clock: ClockCallable = utc_now,
    ) -> None:
        if search_action is None or fetch_action is None:
            from core.actions.web import web_fetch_action, web_search_action

            search_action = search_action or web_search_action
            fetch_action = fetch_action or web_fetch_action
        self.search_action = search_action
        self.fetch_action = fetch_action
        self.cache = cache or SQLiteWebCache()
        self.clock = clock

    def research(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        region: str = "wt-wt",
        force_refresh: bool = False,
    ) -> ResearchResult:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise ValueError("query cannot be empty")
        limit = max(1, min(int(max_results), 20))
        started_at = _require_utc(self.clock(), "clock result")
        search_result = self.search_action(
            normalized_query,
            max_results=limit,
            region=region,
        )
        if not search_result.success:
            raise RuntimeError(search_result.error or "Web search failed")

        candidates = self._search_candidates(search_result)
        sources: list[SourceRecord] = []
        warnings: list[str] = []
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()

        for candidate in candidates:
            if len(sources) >= limit:
                break
            raw_url = str(candidate.get("url") or "").strip()
            try:
                requested_url = canonicalize_url(raw_url)
            except ValueError as exc:
                warnings.append(f"Skipped invalid URL {raw_url!r}: {exc}")
                continue
            if requested_url in seen_urls:
                continue

            try:
                source = self._get_source(
                    candidate,
                    requested_url=requested_url,
                    now=_require_utc(self.clock(), "clock result"),
                    force_refresh=force_refresh,
                )
            except Exception as exc:
                warnings.append(f"Failed to fetch {requested_url}: {exc}")
                continue

            if source.canonical_url in seen_urls or source.content_hash in seen_hashes:
                continue
            seen_urls.add(source.canonical_url)
            seen_hashes.add(source.content_hash)
            sources.append(replace(source, citation_number=len(sources) + 1))

        return ResearchResult(
            query=normalized_query,
            sources=tuple(sources),
            retrieved_at=started_at,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _search_candidates(result: _ActionResultLike) -> list[Mapping[str, Any]]:
        data = result.data
        raw_results: Any = data.get("results") if isinstance(data, Mapping) else None
        if raw_results is None and result.output:
            try:
                parsed = json.loads(result.output)
            except (TypeError, json.JSONDecodeError):
                parsed = []
            raw_results = parsed.get("results") if isinstance(parsed, Mapping) else parsed
        if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes)):
            return []
        return [item for item in raw_results if isinstance(item, Mapping)]

    def _get_source(
        self,
        candidate: Mapping[str, Any],
        *,
        requested_url: str,
        now: datetime,
        force_refresh: bool,
    ) -> SourceRecord:
        cached = self.cache.lookup(requested_url, now=now)
        if cached is not None and cached.is_fresh and not force_refresh:
            return replace(cached.record, citation_number=0, from_cache=True)

        request_headers: dict[str, str] = {}
        if cached is not None:
            if cached.record.etag:
                request_headers["If-None-Match"] = cached.record.etag
            if cached.record.last_modified:
                request_headers["If-Modified-Since"] = cached.record.last_modified

        fetch_result = self.fetch_action(requested_url, headers=request_headers or None)
        status = self._fetch_status(fetch_result)
        response_headers = self._fetch_headers(fetch_result)
        if status == 304 and cached is not None:
            return self.cache.revalidate(
                cached.record,
                retrieved_at=now,
                etag=self._header(response_headers, "etag"),
                last_modified=self._header(response_headers, "last-modified"),
            )
        if not fetch_result.success:
            raise RuntimeError(fetch_result.error or "Web fetch failed")

        response_data = fetch_result.data if isinstance(fetch_result.data, Mapping) else {}
        response_url = str(response_data.get("url") or requested_url)
        canonical_url = canonicalize_url(response_url)
        content = str(fetch_result.output or "")
        record = SourceRecord(
            citation_number=0,
            url=response_url,
            canonical_url=canonical_url,
            title=str(candidate.get("title") or canonical_url),
            snippet=str(candidate.get("snippet") or ""),
            content=content,
            content_hash=content_sha256(content),
            retrieved_at=now,
            # Publication time is accepted only when the provider explicitly supplies it.
            published_at=_optional_datetime(candidate.get("published_at"), "published_at"),
            etag=self._header(response_headers, "etag"),
            last_modified=self._header(response_headers, "last-modified"),
            from_cache=False,
        )
        self.cache.put(record)
        return record

    @staticmethod
    def _fetch_status(result: _ActionResultLike) -> int | None:
        if isinstance(result.data, Mapping):
            try:
                return int(result.data.get("status"))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _fetch_headers(result: _ActionResultLike) -> Mapping[str, Any]:
        if isinstance(result.data, Mapping):
            headers = result.data.get("headers")
            if isinstance(headers, Mapping):
                return headers
        return {}

    @staticmethod
    def _header(headers: Mapping[str, Any], name: str) -> str | None:
        expected = name.casefold()
        for raw_name, raw_value in headers.items():
            if str(raw_name).casefold() == expected and raw_value not in (None, ""):
                return str(raw_value)
        return None


# Compatibility-friendly alias: both names describe the same injected cache.
SQLiteResearchCache = SQLiteWebCache


__all__ = [
    "CacheLookup",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_MAX_RESULTS",
    "RealtimeWebResearch",
    "ResearchResult",
    "SQLiteResearchCache",
    "SQLiteWebCache",
    "SourceRecord",
    "canonicalize_url",
    "content_sha256",
    "utc_now",
]
