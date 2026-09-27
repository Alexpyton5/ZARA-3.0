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
_SOURCE_AUDIT_FIELDS = ("source_access", "read_evidence", "provenance", "finding_validation", "memory")
_RECOMMENDATIONS = {"IMPLEMENTAR", "NAO_IMPLEMENTAR", "PRECISA_MAIS_INVESTIGACAO"}
_INTAKE_TRIGGERS = {"DAILY", "EVENT"}
_REFRESH_REASON_MAX_LENGTH = 300


def _normalize_question(question: str) -> str:
    return " ".join(str(question or "").split()).casefold()


def _question_hash(question: str) -> str:
    return hashlib.sha256(_normalize_question(question).encode("utf-8")).hexdigest()


def _validate_id(value: Any, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_REQUIRED")
    clean = " ".join(value.split())
    if len(clean) > max_length or "\x00" in clean:
        raise ValueError(f"{field}_INVALID")
    return clean


def _validate_question_identity(value: Any) -> str:
    return _validate_id(value, "QUESTION_IDENTITY", max_length=256)


def _validate_cycle_id(value: Any) -> str:
    return _validate_id(value, "CYCLE_ID", max_length=128)


def _validate_optional_text(value: Any, field: str, *, max_length: int = 256) -> str | None:
    if value is None:
        return None
    return _validate_id(value, field, max_length=max_length)


def _validate_optional_timestamp(value: Any, field: str) -> str | None:
    if value is None:
        return None
    clean = _validate_id(value, field, max_length=80)
    try:
        _ContractDateTime.fromisoformat(clean.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_INVALID") from exc
    return clean


def _validate_metadata(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field}_MUST_BE_DICT")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_INVALID") from exc
    return json.loads(encoded)


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
    host = _source_hostname(clean["source"])
    if host in {"example.com", "example.org", "example.net", "invalid", "test"} or host.endswith((".example", ".invalid", ".test")):
        raise ValueError("SOURCE_URL_FICTITIOUS")
    for field in _SOURCE_AUDIT_FIELDS:
        if field not in source:
            continue
        value = source[field]
        if field == "read_evidence":
            if not isinstance(value, (str, dict)) or not value:
                raise ValueError("READ_EVIDENCE_INVALID")
            clean[field] = " ".join(value.split()) if isinstance(value, str) else _validate_metadata(value, "READ_EVIDENCE")
        elif field == "source_access":
            clean[field] = _validate_metadata(value, "SOURCE_ACCESS")
        else:
            clean[field] = _validate_metadata(value, field.upper())
    clean.setdefault("source_access", {"status": "UNVERIFIED"})
    clean.setdefault("read_evidence", {"status": "UNVERIFIED", "excerpt": clean["evidence"]})
    clean.setdefault("provenance", {"source_url": clean["source"], "status": "RECORDED"})
    clean.setdefault("finding_validation", {"status": "UNVERIFIED"})
    clean.setdefault("memory", {"reusable": True, "status": "PERSISTED"})
    return clean


def _source_hostname(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""


class ResearchPipeline:
    """Persistent store for real research cycles, sharing the Lab's SQLite DB."""

    def __init__(self, store):
        self.store = store
        with store._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lab_research_cycles(
                    id TEXT PRIMARY KEY,
                    question_sha256 TEXT NOT NULL,
                    question_identity TEXT NOT NULL,
                    question TEXT NOT NULL,
                    document TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    parent_cycle TEXT,
                    evidence_valid_until TEXT,
                    refresh_reason TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            self._migrate_cycle_schema(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lab_research_cycles_identity "
                "ON lab_research_cycles(question_identity, created_at DESC)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lab_research_intakes(
                    id TEXT PRIMARY KEY,
                    question_sha256 TEXT NOT NULL UNIQUE,
                    day TEXT NOT NULL,
                    document TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )

    @staticmethod
    def _migrate_cycle_schema(conn) -> None:
        """Upgrade the original one-cycle-per-question table in place.

        Older checkouts declared ``question_sha256`` UNIQUE, which made a
        legitimate refresh cycle impossible.  The migration keeps every old
        row and turns the uniqueness rule into an application-level identity
        check, so the database can represent a parent/child refresh chain.
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(lab_research_cycles)")}
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='lab_research_cycles'"
        ).fetchone()
        table_sql = (sql_row[0] if sql_row else "").upper()
        if "question_identity" in columns and "UNIQUE" not in table_sql:
            return
        conn.execute("ALTER TABLE lab_research_cycles RENAME TO lab_research_cycles_legacy")
        conn.execute(
            """CREATE TABLE lab_research_cycles(
                id TEXT PRIMARY KEY,
                question_sha256 TEXT NOT NULL,
                question_identity TEXT NOT NULL,
                question TEXT NOT NULL,
                document TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                parent_cycle TEXT,
                evidence_valid_until TEXT,
                refresh_reason TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        legacy_rows = conn.execute("SELECT * FROM lab_research_cycles_legacy").fetchall()
        for row in legacy_rows:
            document = json.loads(row[3])
            identity = document.get("question_identity") or row[1]
            document.setdefault("question_identity", identity)
            document.setdefault("cycle_id", row[0])
            document.setdefault("parent_cycle", None)
            document.setdefault("evidence_valid_until", None)
            document.setdefault("refresh_reason", None)
            conn.execute(
                "INSERT INTO lab_research_cycles VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (row[0], row[1], identity, row[2], json.dumps(document, ensure_ascii=False),
                 row[4], document.get("parent_cycle"), document.get("evidence_valid_until"),
                 document.get("refresh_reason"), row[5], row[6]),
            )
        conn.execute("DROP TABLE lab_research_cycles_legacy")

    def admit_intake(
        self, question: str, *, trigger: str, daily_budget: int,
        event_id: str | None = None, observed_at: float | None = None,
    ) -> dict[str, Any]:
        """Queue a research question without performing research or calling a provider.

        The question hash is global and persistent, so a later daily scan cannot
        fork work already requested by an event. The daily cap applies to both
        entry points and is checked atomically with the insert.
        """
        clean_question = " ".join(str(question or "").split())
        if not clean_question:
            raise ValueError("QUESTION_REQUIRED")
        trigger = str(trigger or "").strip().upper()
        if trigger not in _INTAKE_TRIGGERS:
            raise ValueError("INTAKE_TRIGGER_INVALID")
        if type(daily_budget) is not int or daily_budget < 1:
            raise ValueError("DAILY_BUDGET_INVALID")
        stamp = float(observed_at if observed_at is not None else time.time())
        day = time.strftime("%Y-%m-%d", time.localtime(stamp))
        digest = _question_hash(clean_question)
        intake_id = "research-intake:" + digest[:20]
        document = {
            "question": clean_question, "trigger": trigger,
            "event_id": str(event_id).strip() if event_id else None,
            "day": day, "observed_at": stamp,
        }
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM lab_research_intakes WHERE question_sha256=?", (digest,)
            ).fetchone()
            if existing:
                return {**self._intake_row_to_dict(existing), "state": "DUPLICATE"}
            admitted = conn.execute(
                "SELECT COUNT(*) FROM lab_research_intakes WHERE day=?", (day,)
            ).fetchone()[0]
            if admitted >= daily_budget:
                return {"state": "DAILY_BUDGET_EXHAUSTED", "day": day,
                        "daily_budget": daily_budget, "question": clean_question}
            conn.execute(
                "INSERT INTO lab_research_intakes VALUES(?,?,?,?,?,?)",
                (intake_id, digest, day, json.dumps(document, ensure_ascii=False), stamp, stamp),
            )
            row = conn.execute("SELECT * FROM lab_research_intakes WHERE id=?", (intake_id,)).fetchone()
        return {**self._intake_row_to_dict(row), "state": "QUEUED"}

    def get_intake(self, intake_id: str) -> dict[str, Any] | None:
        with self.store._connect() as conn:
            row = conn.execute("SELECT * FROM lab_research_intakes WHERE id=?", (intake_id,)).fetchone()
        return self._intake_row_to_dict(row) if row else None

    def list_intakes(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lab_research_intakes ORDER BY created_at ASC LIMIT ?", (limit,)
            ).fetchall()
        return [self._intake_row_to_dict(row) for row in rows]

    def record_cycle(
        self,
        question: str,
        sources: list[dict],
        *,
        recommendation: str,
        implementation_candidate: str | None = None,
        question_identity: str | None = None,
        cycle_id: str | None = None,
        parent_cycle: str | None = None,
        evidence_valid_until: str | None = None,
        refresh_reason: str | None = None,
        provenance: dict[str, Any] | None = None,
        finding_validation: dict[str, Any] | None = None,
        memory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one research cycle. Returns the stored document.

        The default is idempotent: the latest cycle for the same
        ``question_identity`` is returned untouched.  A refresh is explicit
        (``refresh_reason`` plus an optional ``parent_cycle``), which creates
        a new child cycle while retaining the previous evidence in memory.
        """
        clean_question = " ".join(str(question or "").split())
        if not clean_question:
            raise ValueError("QUESTION_REQUIRED")
        digest = _question_hash(clean_question)
        identity = _validate_question_identity(question_identity or digest)
        requested_cycle_id = _validate_cycle_id(cycle_id) if cycle_id else None
        refresh_reason = _validate_optional_text(refresh_reason, "REFRESH_REASON",
                                                  max_length=_REFRESH_REASON_MAX_LENGTH)
        evidence_valid_until = _validate_optional_timestamp(
            evidence_valid_until, "EVIDENCE_VALID_UNTIL"
        )
        parent_cycle = _validate_optional_text(parent_cycle, "PARENT_CYCLE", max_length=128)
        if parent_cycle and not refresh_reason:
            raise ValueError("REFRESH_REASON_REQUIRED_FOR_PARENT_CYCLE")
        safe_provenance = _validate_metadata(provenance, "PROVENANCE")
        safe_finding_validation = _validate_metadata(finding_validation, "FINDING_VALIDATION")
        safe_memory = _validate_metadata(memory, "MEMORY")
        with self.store._connect() as conn:
            if requested_cycle_id:
                existing = conn.execute(
                    "SELECT * FROM lab_research_cycles WHERE id=?", (requested_cycle_id,)
                ).fetchone()
                if existing:
                    return self._row_to_dict(existing)
            existing = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE question_identity=? "
                "ORDER BY created_at DESC LIMIT 1", (identity,)
            ).fetchone()
        # Deduplication is authoritative unless the caller explicitly asks for
        # a refresh.  This keeps retries from failing or mutating old evidence.
        if existing and not refresh_reason:
            return self._row_to_dict(existing)
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
        stamp = time.time()
        if parent_cycle:
            with self.store._connect() as conn:
                parent = conn.execute(
                    "SELECT id, question_identity FROM lab_research_cycles WHERE id=?",
                    (parent_cycle,),
                ).fetchone()
            if parent is None:
                raise ValueError("PARENT_CYCLE_NOT_FOUND")
            if parent[1] != identity:
                raise ValueError("PARENT_CYCLE_QUESTION_MISMATCH")
        elif refresh_reason and existing:
            parent_cycle = existing["id"]
        cycle_id = requested_cycle_id or (
            "research:" + identity[:20] if not refresh_reason else
            "research:" + identity[:20] + ":" + hashlib.sha256(
                (refresh_reason + str(stamp)).encode("utf-8")
            ).hexdigest()[:12]
        )
        document = {
            "question": clean_question,
            "question_identity": identity,
            "cycle_id": cycle_id,
            "sources": clean_sources,
            "recommendation": recommendation,
            "implementation_candidate": (implementation_candidate or "").strip() or None,
            "source_count": len(clean_sources),
            "researched_at": stamp,
            "parent_cycle": parent_cycle,
            "evidence_valid_until": evidence_valid_until,
            "refresh_reason": refresh_reason,
            "provenance": safe_provenance or {"status": "UNVERIFIED"},
            "finding_validation": safe_finding_validation or {"status": "UNVERIFIED"},
            "memory": safe_memory or {"reusable": True, "status": "PERSISTED"},
        }
        with self.store._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO lab_research_cycles
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (cycle_id, digest, identity, clean_question,
                 json.dumps(document, ensure_ascii=False), recommendation, parent_cycle,
                 evidence_valid_until, refresh_reason, stamp, stamp),
            )
            row = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE id=?", (cycle_id,)
            ).fetchone()
        return self._row_to_dict(row)

    def get_cycle(self, question: str) -> dict[str, Any] | None:
        clean_question = " ".join(str(question or "").split())
        identity = _question_hash(clean_question)
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lab_research_cycles WHERE question_identity=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1", (identity,)
            ).fetchone()
            # Callers may use a stable domain identity (for example
            # ``usefulness-v1``) rather than the content hash.  The canonical
            # question column is the durable lookup key in that case.
            if row is None:
                row = conn.execute(
                    "SELECT * FROM lab_research_cycles WHERE question=? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT 1", (clean_question,)
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

    @staticmethod
    def _intake_row_to_dict(row) -> dict[str, Any]:
        document = json.loads(row["document"])
        document.update(id=row["id"], created_at=row["created_at"], updated_at=row["updated_at"])
        return document


# ---------------------------------------------------------------------------
# Safe URL -> evidence -> summary -> Obsidian contract
# ---------------------------------------------------------------------------
from collections.abc import Mapping as _ContractMapping, Sequence as _ContractSequence
from dataclasses import dataclass as _contract_dataclass, field as _contract_field
from datetime import datetime as _ContractDateTime, timezone as _ContractTimezone
from ipaddress import ip_address as _contract_ip_address
from typing import Protocol as _ContractProtocol
from urllib.parse import parse_qsl as _contract_parse_qsl, urlsplit as _contract_urlsplit, urlunsplit as _contract_urlunsplit
import re as _contract_re


class ResearchContractError(ValueError):
    pass


class URLContractError(ResearchContractError):
    pass


class EvidenceContractError(ResearchContractError):
    pass


class SummaryContractError(ResearchContractError):
    pass


class ObsidianContractError(ResearchContractError):
    pass


class ResearchObsidianSink(_ContractProtocol):
    def add_memory(self, title: str, content: str, tags: list[str] | None = None, category: str = "memories") -> str: ...


_CONTRACT_SECRET_KEY_RE = _contract_re.compile(r"(?:secret|token|password|passwd|api[_-]?key|access[_-]?key|private[_-]?key|authorization|credential|bearer)", _contract_re.IGNORECASE)
_CONTRACT_SECRET_VALUE_RE = _contract_re.compile(r"(?:-----BEGIN [^-]*PRIVATE KEY-----|\bBearer\s+\S+|\b(?:sk|gh[pousr]|xox[baprs])[-_][A-Za-z0-9._-]{8,})", _contract_re.IGNORECASE)
_CONTRACT_SHA256_RE = _contract_re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", _contract_re.IGNORECASE)
_CONTRACT_ID_RE = _contract_re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_CONTRACT_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
_CONTRACT_FICTITIOUS_HOSTS = frozenset({"example.com", "example.org", "example.net", "invalid", "test"})


def _contract_now() -> str:
    return _ContractDateTime.now(_ContractTimezone.utc).replace(microsecond=0).isoformat()


def _contract_text(value: Any, field: str, *, max_length: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchContractError(f"{field}_REQUIRED")
    result = " ".join(value.split())
    if "\x00" in result or len(result) > max_length:
        raise ResearchContractError(f"{field}_INVALID")
    if _CONTRACT_SECRET_VALUE_RE.search(result):
        raise ResearchContractError(f"{field}_SECRET_SHAPED")
    return result


def _contract_json(value: Any, *, field: str) -> Any:
    if isinstance(value, _ContractMapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ResearchContractError(f"{field}_KEY_INVALID")
            if _CONTRACT_SECRET_KEY_RE.search(key):
                raise ResearchContractError(f"{field}_SECRET_FIELD")
            result[key] = _contract_json(item, field=f"{field}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_contract_json(item, field=field) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        if isinstance(value, str) and _CONTRACT_SECRET_VALUE_RE.search(value):
            raise ResearchContractError(f"{field}_SECRET_SHAPED")
        return value
    if isinstance(value, float):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ResearchContractError(f"{field}_NOT_FINITE") from exc
        return value
    raise ResearchContractError(f"{field}_NOT_JSON_SAFE")


def _contract_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _CONTRACT_SHA256_RE.fullmatch(value.strip()):
        raise ResearchContractError(f"{field}_MUST_BE_SHA256")
    return value.strip().lower()


def _contract_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _CONTRACT_ID_RE.fullmatch(value.strip()):
        raise ResearchContractError(f"{field}_INVALID")
    return value.strip()


def _canonical_contract_url(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise URLContractError("URL_REQUIRED")
    raw = value.strip()
    if len(raw) > 2048 or any(char.isspace() for char in raw):
        raise URLContractError("URL_INVALID")
    try:
        parts = _contract_urlsplit(raw)
        scheme, host, port = parts.scheme.lower(), parts.hostname, parts.port
    except ValueError as exc:
        raise URLContractError("URL_INVALID") from exc
    if scheme not in {"http", "https"}:
        raise URLContractError("URL_SCHEME_NOT_ALLOWED")
    if not host or parts.username is not None or parts.password is not None:
        raise URLContractError("URL_CREDENTIALS_OR_HOST_INVALID")
    if parts.fragment:
        raise URLContractError("URL_FRAGMENT_NOT_ALLOWED")
    try:
        host_ascii = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise URLContractError("URL_HOST_INVALID") from exc
    # ``example.com`` is useful as a deterministic URL normalization fixture;
    # source ingestion applies the stricter fictitious-host rejection below.
    if (host_ascii in _CONTRACT_BLOCKED_HOSTS or host_ascii in (_CONTRACT_FICTITIOUS_HOSTS - {"example.com"})
            or any(host_ascii.endswith(suffix) for suffix in (".local", ".internal", ".lan", ".example", ".invalid", ".test"))):
        raise URLContractError("URL_LOCAL_HOST_NOT_ALLOWED")
    try:
        address = _contract_ip_address(host_ascii.strip("[]"))
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved):
        raise URLContractError("URL_NON_PUBLIC_ADDRESS_NOT_ALLOWED")
    for query_key, query_value in _contract_parse_qsl(parts.query, keep_blank_values=True):
        if _CONTRACT_SECRET_KEY_RE.search(query_key) or _CONTRACT_SECRET_VALUE_RE.search(query_value):
            raise URLContractError("URL_SECRET_QUERY_NOT_ALLOWED")
    netloc_host = f"[{host_ascii}]" if ":" in host_ascii and not host_ascii.startswith("[") else host_ascii
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = netloc_host if port is None or default_port else f"{netloc_host}:{port}"
    canonical = _contract_urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@_contract_dataclass(frozen=True)
class URLReference:
    url: str
    url_sha256: str
    title: str
    retrieved_at: str
    content_sha256: str | None = None
    artifact_ref: str | None = None
    metadata: Mapping[str, Any] = _contract_field(default_factory=dict)

    @classmethod
    def capture(cls, url: str, *, title: str | None = None, retrieved_at: str | None = None, content_sha256: str | None = None, artifact_ref: str | None = None, metadata: Mapping[str, Any] | None = None) -> "URLReference":
        canonical, digest = _canonical_contract_url(url)
        host = _contract_urlsplit(canonical).hostname or "source"
        return cls(canonical, digest, _contract_text(title or host, "title", max_length=300), _contract_text(retrieved_at or _contract_now(), "retrieved_at", max_length=80), None if content_sha256 is None else _contract_sha256(content_sha256, "content_sha256"), None if artifact_ref is None else _contract_text(artifact_ref, "artifact_ref", max_length=500), _contract_json(metadata or {}, field="metadata"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "URLReference":
        if not isinstance(value, _ContractMapping):
            raise URLContractError("URL_REFERENCE_MUST_BE_MAPPING")
        allowed = {"url", "title", "retrieved_at", "content_sha256", "artifact_ref", "metadata"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise URLContractError(f"URL_REFERENCE_UNKNOWN_FIELDS:{','.join(unknown)}")
        return cls.capture(value.get("url"), title=value.get("title"), retrieved_at=value.get("retrieved_at"), content_sha256=value.get("content_sha256"), artifact_ref=value.get("artifact_ref"), metadata=value.get("metadata"))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"url": self.url, "url_sha256": self.url_sha256, "title": self.title, "retrieved_at": self.retrieved_at}
        if self.content_sha256 is not None: result["content_sha256"] = self.content_sha256
        if self.artifact_ref is not None: result["artifact_ref"] = self.artifact_ref
        if self.metadata: result["metadata"] = dict(self.metadata)
        return result


@_contract_dataclass(frozen=True)
class EvidenceReceipt:
    evidence_id: str
    source: URLReference
    claim: str
    support: str
    captured_at: str
    locator: str | None = None

    @classmethod
    def create(cls, source: URLReference | Mapping[str, Any] | str, *, claim: str, support: str | None = None, quote: str | None = None, evidence_id: str | None = None, captured_at: str | None = None, locator: str | None = None) -> "EvidenceReceipt":
        reference = source if isinstance(source, URLReference) else URLReference.from_mapping(source) if isinstance(source, _ContractMapping) else URLReference.capture(source)
        safe_claim = _contract_text(claim, "claim", max_length=1000)
        safe_support = _contract_text(support if support is not None else quote, "support", max_length=1200)
        derived_id = "evidence:" + hashlib.sha256((reference.url_sha256 + "\n" + safe_claim + "\n" + safe_support).encode("utf-8")).hexdigest()[:20]
        return cls(_contract_id(evidence_id or derived_id, "evidence_id"), reference, safe_claim, safe_support, _contract_text(captured_at or _contract_now(), "captured_at", max_length=80), None if locator is None else _contract_text(locator, "locator", max_length=500))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceReceipt":
        if not isinstance(value, _ContractMapping): raise EvidenceContractError("EVIDENCE_MUST_BE_MAPPING")
        allowed = {"evidence_id", "source", "source_url", "url", "claim", "support", "quote", "captured_at", "locator"}
        unknown = sorted(set(value) - allowed)
        if unknown: raise EvidenceContractError(f"EVIDENCE_UNKNOWN_FIELDS:{','.join(unknown)}")
        source = value.get("source", value.get("source_url", value.get("url")))
        try: return cls.create(source, claim=value.get("claim"), support=value.get("support"), quote=value.get("quote"), evidence_id=value.get("evidence_id"), captured_at=value.get("captured_at"), locator=value.get("locator"))
        except ResearchContractError as exc: raise EvidenceContractError(str(exc)) from exc

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"evidence_id": self.evidence_id, "source": self.source.to_dict(), "claim": self.claim, "support": self.support, "captured_at": self.captured_at}
        if self.locator is not None: result["locator"] = self.locator
        return result


@_contract_dataclass(frozen=True)
class ResearchSummary:
    summary_id: str
    question: str
    summary: str
    evidence: tuple[EvidenceReceipt, ...]
    limitations: tuple[str, ...]
    created_at: str
    recommendation: str | None = None

    @classmethod
    def create(cls, question: str, evidence: Sequence[EvidenceReceipt | Mapping[str, Any]], *, summary: str, limitations: Sequence[str] = (), recommendation: str | None = None, summary_id: str | None = None, created_at: str | None = None) -> "ResearchSummary":
        if isinstance(evidence, (str, bytes)) or not isinstance(evidence, _ContractSequence) or not evidence: raise SummaryContractError("SUMMARY_EVIDENCE_REQUIRED")
        receipts: list[EvidenceReceipt] = []
        for item in evidence:
            receipt = item if isinstance(item, EvidenceReceipt) else EvidenceReceipt.from_mapping(item)
            if any(existing.evidence_id == receipt.evidence_id for existing in receipts): raise SummaryContractError("SUMMARY_EVIDENCE_IDS_MUST_BE_UNIQUE")
            receipts.append(receipt)
        if isinstance(limitations, (str, bytes)) or not isinstance(limitations, _ContractSequence): raise SummaryContractError("SUMMARY_LIMITATIONS_MUST_BE_LIST")
        clean_limitations = tuple(_contract_text(item, "limitation", max_length=500) for item in limitations)
        clean_question, clean_summary = _contract_text(question, "question", max_length=1000), _contract_text(summary, "summary", max_length=3000)
        clean_recommendation = None if recommendation is None else _contract_text(recommendation, "recommendation", max_length=500)
        derived_id = "summary:" + hashlib.sha256("\n".join([clean_question, clean_summary, *(item.evidence_id for item in receipts)]).encode("utf-8")).hexdigest()[:20]
        return cls(_contract_id(summary_id or derived_id, "summary_id"), clean_question, clean_summary, tuple(receipts), clean_limitations, _contract_text(created_at or _contract_now(), "created_at", max_length=80), clean_recommendation)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResearchSummary":
        if not isinstance(value, _ContractMapping): raise SummaryContractError("SUMMARY_MUST_BE_MAPPING")
        allowed = {"summary_id", "question", "summary", "evidence", "limitations", "created_at", "recommendation"}
        unknown = sorted(set(value) - allowed)
        if unknown: raise SummaryContractError(f"SUMMARY_UNKNOWN_FIELDS:{','.join(unknown)}")
        return cls.create(value.get("question"), value.get("evidence"), summary=value.get("summary"), limitations=value.get("limitations", ()), recommendation=value.get("recommendation"), summary_id=value.get("summary_id"), created_at=value.get("created_at"))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"summary_id": self.summary_id, "question": self.question, "summary": self.summary, "evidence": [item.to_dict() for item in self.evidence], "limitations": list(self.limitations), "created_at": self.created_at}
        if self.recommendation is not None: result["recommendation"] = self.recommendation
        return result


def _render_contract_summary(value: ResearchSummary) -> str:
    lines = ["# Research summary", "", f"**Question:** {value.question}", f"**Summary:** {value.summary}"]
    if value.recommendation: lines.append(f"**Recommendation:** {value.recommendation}")
    lines.extend(["", "## Evidence"])
    for item in value.evidence: lines.append(f"- [{item.evidence_id}]({item.source.url}) — {item.claim} ({item.support})")
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in value.limitations) if value.limitations else lines.append("- None recorded")
    lines.extend(["", f"_Created at: {value.created_at}; summary id: {value.summary_id}_"])
    return "\n".join(lines)


def publish_summary_to_obsidian(summary: ResearchSummary | Mapping[str, Any], sink: ResearchObsidianSink, *, title: str | None = None) -> dict[str, Any]:
    value = summary if isinstance(summary, ResearchSummary) else ResearchSummary.from_mapping(summary)
    add_memory = getattr(sink, "add_memory", None)
    if not callable(add_memory): raise ObsidianContractError("OBSIDIAN_SINK_REQUIRED")
    safe_title = _contract_text(title or f"Research summary {value.summary_id}", "title", max_length=300)
    try: node_id = add_memory(title=safe_title, content=_render_contract_summary(value), tags=["zara", "research", "evidence-backed"], category="knowledge")
    except Exception as exc: raise ObsidianContractError("OBSIDIAN_PUBLICATION_FAILED") from exc
    if not isinstance(node_id, str) or not node_id.strip(): raise ObsidianContractError("OBSIDIAN_NODE_ID_INVALID")
    return {"summary_id": value.summary_id, "obsidian_id": node_id.strip(), "published": True}


def _validate_source_contract(source: dict) -> dict:
    if not isinstance(source, dict): raise ValueError("SOURCE_MUST_BE_DICT")
    clean: dict[str, Any] = {}
    for field in _SOURCE_FIELDS:
        value = source.get(field)
        if not isinstance(value, str) or not value.strip(): raise ValueError(f"SOURCE_FIELD_REQUIRED:{field}")
        clean[field] = value.strip()
    if not (clean["source"].startswith("http://") or clean["source"].startswith("https://")): raise ValueError("SOURCE_MUST_BE_URL")
    canonical, source_sha256 = _canonical_contract_url(clean["source"])
    source_host = _contract_urlsplit(canonical).hostname or ""
    if source_host in _CONTRACT_FICTITIOUS_HOSTS or source_host.endswith((".example", ".invalid", ".test")):
        raise ValueError("SOURCE_URL_FICTITIOUS")
    clean["source"] = canonical
    audit = source.get("source_access", {"status": "UNVERIFIED"})
    if not isinstance(audit, _ContractMapping): raise ValueError("SOURCE_ACCESS_MUST_BE_DICT")
    audit = dict(audit)
    access_status = str(audit.get("status", "UNVERIFIED")).strip().upper()
    if access_status not in {"READ", "UNREAD", "FAILED", "UNVERIFIED"}:
        raise ValueError("SOURCE_ACCESS_STATUS_INVALID")
    if access_status == "FAILED": raise ValueError("SOURCE_ACCESS_FAILED")
    if access_status == "READ" and not (audit.get("retrieved_at") or source.get("read_evidence")):
        raise ValueError("READ_EVIDENCE_REQUIRED")
    clean["source_access"] = {**audit, "status": access_status}
    read_evidence = source.get("read_evidence", {"status": "UNVERIFIED", "excerpt": clean["evidence"]})
    if isinstance(read_evidence, str):
        read_evidence = {"status": "RECORDED", "excerpt": read_evidence.strip()}
    if not isinstance(read_evidence, _ContractMapping): raise ValueError("READ_EVIDENCE_INVALID")
    read_evidence = dict(read_evidence)
    if read_evidence.get("status", "UNVERIFIED").upper() == "READ" and not read_evidence.get("excerpt"):
        raise ValueError("READ_EVIDENCE_EXCERPT_REQUIRED")
    clean["read_evidence"] = read_evidence
    provenance = source.get("provenance", {})
    if not isinstance(provenance, _ContractMapping): raise ValueError("PROVENANCE_MUST_BE_DICT")
    clean["provenance"] = {**dict(provenance), "source_url": canonical, "url_sha256": source_sha256}
    finding_validation = source.get("finding_validation", {"status": "UNVERIFIED"})
    if not isinstance(finding_validation, _ContractMapping): raise ValueError("FINDING_VALIDATION_MUST_BE_DICT")
    finding_validation = dict(finding_validation)
    validation_status = str(finding_validation.get("status", "UNVERIFIED")).strip().upper()
    if validation_status not in {"VALIDATED", "UNVERIFIED", "REJECTED"}:
        raise ValueError("FINDING_VALIDATION_STATUS_INVALID")
    if validation_status == "REJECTED": raise ValueError("FINDING_VALIDATION_FAILED")
    clean["finding_validation"] = {**finding_validation, "status": validation_status}
    clean["memory"] = _validate_metadata(source.get("memory", {"reusable": True, "status": "PERSISTED"}), "MEMORY")
    return clean


_validate_source = _validate_source_contract
ResearchPipeline.publish_summary = lambda self, summary, sink, *, title=None: publish_summary_to_obsidian(summary, sink, title=title)

__all__ = ["MAX_SOURCES_PER_CYCLE", "ResearchPipeline", "ResearchContractError", "URLContractError", "EvidenceContractError", "SummaryContractError", "ObsidianContractError", "ResearchObsidianSink", "URLReference", "EvidenceReceipt", "ResearchSummary", "publish_summary_to_obsidian"]
