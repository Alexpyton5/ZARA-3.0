"""Deterministic, bounded read facade over ZARA's existing memory domains.

The only persistence owned here is an Obsidian search index.  Its SQLite path
is mandatory and injected by the Project Memory domain; this module does not
create another source-of-truth database.  Obsidian writes and human-edit
reconciliation remain the responsibility of ``ObsidianMemoryManager``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from memory.project_memory import _canonical_obsidian_vault

_MAX_NOTE_BYTES = 32_768
_MAX_FILE_BYTES = 1_048_576
_SECRET_PATH_PARTS = re.compile(
    r"(?:^|[._-])(\.env|api[_-]?keys?|credentials?|tokens?|keys?|secrets?)(?:$|[._-])",
    re.IGNORECASE,
)
_SECRET_CONTENT = re.compile(
    r"(?:api[_-]?key|client[_-]?secret|password|passwd|credential|access[_-]?token|"
    r"authorization\s*[:=]|bearer\s+[a-z0-9._-]{8,}|"
    r"(?:sk|gsk|nvapi)[_-][a-z0-9_-]{8,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)",
    re.IGNORECASE,
)
_PRIVATE_REASONING = re.compile(
    r"(?:private\s+(?:chain\s+of\s+thought|reasoning)|chain\s+of\s+thought|"
    r"racioc[ií]nio\s+privado|hidden\s+reasoning)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "as", "com", "da", "das", "de", "do", "dos", "e", "em", "eu",
    "faz", "meu", "meus", "minha", "minhas", "o", "os", "para", "por",
    "que", "quais", "sao", "ser", "uma", "um",
}
_SOURCE_ORDER = {"user_memory": 0, "lab_lesson": 1, "project_memory": 2, "obsidian": 3}


@runtime_checkable
class ProjectWorkspaceSource(Protocol):
    """Read-only injected Project Memory event feed.

    The facade treats this feed as a cache input, never as a source of truth:
    persistence and event ownership stay in ``memory.project_memory.ProjectMemory``.
    Its native ``recent_events`` rows contain ``id``, ``ts``, ``task_id``,
    ``status`` and ``summary``.  The optional search/list surfaces are legacy
    adapters and must remain metadata-only.
    """

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class _Candidate:
    source: str
    provenance: str
    timestamp: float
    text: str
    score: float

    def public(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "provenance": self.provenance,
            "timestamp": self.timestamp,
            "text": self.text,
        }


class SharedSecondBrain:
    """One query surface for User Memory, verified Lab lessons and projects."""

    def __init__(
        self,
        *,
        user_memory: Any,
        lab_store: Any,
        project_workspace: ProjectWorkspaceSource | Any,
        obsidian_vault: Path | str | None,
        obsidian_index_db: Path | str,
    ) -> None:
        self.user_memory = user_memory
        self.lab_store = lab_store
        self.project_workspace = project_workspace
        self.obsidian_vault = _canonical_obsidian_vault(obsidian_vault)
        self.obsidian_index_db = Path(obsidian_index_db)
        self.obsidian_index_db.parent.mkdir(parents=True, exist_ok=True)
        self._obsidian_degraded = not self._vault_available()
        self._sync_lock = threading.RLock()
        self._init_index()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.obsidian_index_db, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_index(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS obsidian_notes (
                    relative_path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )

    def _vault_available(self) -> bool:
        return self.obsidian_vault is not None and self.obsidian_vault.is_dir()

    def sync_obsidian(self) -> dict[str, int | bool]:
        """Explicit incremental index refresh; never requires Obsidian running."""
        with self._sync_lock:
            return self._sync_obsidian_locked()

    def _sync_obsidian_locked(self) -> dict[str, int | bool]:
        result: dict[str, int | bool] = {
            "indexed": 0,
            "unchanged": 0,
            "removed": 0,
            "excluded": 0,
            "degraded": False,
        }
        if not self._vault_available():
            self._obsidian_degraded = True
            result["degraded"] = True
            return result

        assert self.obsidian_vault is not None
        self._obsidian_degraded = False
        with self._connect() as conn:
            existing = {
                row["relative_path"]: row
                for row in conn.execute(
                    "SELECT relative_path, size, mtime_ns, sha256 FROM obsidian_notes"
                )
            }
            retained: set[str] = set()
            for path in sorted(self.obsidian_vault.rglob("*.md"), key=lambda p: p.as_posix().casefold()):
                try:
                    # Linked notes cannot expose files outside the shared vault.
                    path.resolve().relative_to(self.obsidian_vault.resolve())
                    relative = path.relative_to(self.obsidian_vault).as_posix()
                    stat = path.stat()
                except (OSError, ValueError):
                    result["excluded"] = int(result["excluded"]) + 1
                    continue
                if self._secret_path(relative) or stat.st_size > _MAX_FILE_BYTES:
                    result["excluded"] = int(result["excluded"]) + 1
                    continue
                try:
                    raw = path.read_bytes()
                    decoded = raw.decode("utf-8", errors="ignore")
                except OSError:
                    result["excluded"] = int(result["excluded"]) + 1
                    continue
                if self._sensitive(decoded):
                    result["excluded"] = int(result["excluded"]) + 1
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                prior = existing.get(relative)
                text = self._bounded_text(decoded)
                if prior and prior["sha256"] == digest:
                    conn.execute(
                        "UPDATE obsidian_notes SET size=?, mtime_ns=? WHERE relative_path=?",
                        (stat.st_size, stat.st_mtime_ns, relative),
                    )
                    retained.add(relative)
                    result["unchanged"] = int(result["unchanged"]) + 1
                    continue
                conn.execute(
                    """
                    INSERT INTO obsidian_notes(relative_path, size, mtime_ns, sha256, text)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(relative_path) DO UPDATE SET
                        size=excluded.size, mtime_ns=excluded.mtime_ns,
                        sha256=excluded.sha256, text=excluded.text
                    """,
                    (relative, stat.st_size, stat.st_mtime_ns, digest, text),
                )
                retained.add(relative)
                result["indexed"] = int(result["indexed"]) + 1

            stale = sorted(set(existing) - retained)
            if stale:
                conn.executemany(
                    "DELETE FROM obsidian_notes WHERE relative_path=?",
                    ((relative,) for relative in stale),
                )
                result["removed"] = len(stale)
        return result

    def query(self, text: str, budget_bytes: int = 4096, limit: int = 5) -> dict[str, Any]:
        """Return only traceable source material ranked by lexical relevance."""
        budget = int(budget_bytes)
        if budget < 96:
            raise ValueError("budget_bytes must be at least 96")
        cap = max(0, min(int(limit), 100))
        # Every conversational query sees edits made by another crew member.
        # SQLite is a derived cache, never a snapshot authoritative until restart.
        try:
            self._obsidian_sync_result = self.sync_obsidian()
        except Exception:
            self._obsidian_degraded = True
        tokens = self._tokens(text)
        degraded: list[str] = []
        candidates: list[_Candidate] = []
        pool = max(20, cap * 5)

        candidates.extend(self._user_candidates(text, tokens, pool, degraded))
        candidates.extend(self._lesson_candidates(tokens, pool, degraded))
        candidates.extend(self._project_candidates(text, tokens, pool, degraded))
        candidates.extend(self._obsidian_candidates(tokens))
        if self._obsidian_degraded:
            degraded.append("obsidian_unavailable")

        unique: dict[tuple[str, str], _Candidate] = {}
        for candidate in candidates:
            key = (candidate.source, candidate.provenance)
            current = unique.get(key)
            if current is None or candidate.score > current.score:
                unique[key] = candidate
        ranked = sorted(
            unique.values(),
            key=lambda item: (-item.score, _SOURCE_ORDER.get(item.source, 99), item.provenance),
        )[:cap]
        return self._fit_budget(ranked, budget, sorted(set(degraded)))

    def _user_candidates(
        self, query: str, tokens: set[str], limit: int, degraded: list[str]
    ) -> list[_Candidate]:
        try:
            rows = self.user_memory.search(query, limit=limit)
            if callable(getattr(self.user_memory, "list", None)):
                # UserMemoryCore's legacy search prefilters with exact tokens.
                # Merge its read-only listing so this facade can rank common
                # inflections (objetivo/objetivos, trabalho/trabalha) itself.
                rows = list(rows or []) + list(self.user_memory.list() or [])
        except Exception:
            degraded.append("user_memory_unavailable")
            return []
        output: list[_Candidate] = []
        seen: set[str] = set()
        for row in rows or []:
            identity = str(row.get("id") or row.get("ref") or id(row))
            if identity in seen or row.get("status") == "forgotten":
                continue
            seen.add(identity)
            fact = self._public_value(row.get("fact") or "")
            score = self._score(tokens, fact)
            timestamp = self._public_timestamp(row.get("updated_at") or row.get("created_at") or 0.0)
            if score <= 0 or fact is None or timestamp is None:
                continue
            ref = self._public_value(row.get("ref") or row.get("id") or "unknown")
            origin = self._public_value(row.get("source") or "unknown")
            if ref is None or origin is None:
                continue
            output.append(_Candidate(
                "user_memory",
                f"{origin}:{ref}",
                timestamp,
                fact,
                score,
            ))
        return output

    def _lesson_candidates(
        self, tokens: set[str], limit: int, degraded: list[str]
    ) -> list[_Candidate]:
        try:
            lessons = self.lab_store.list_lessons(limit=limit)
        except Exception:
            degraded.append("lab_memory_unavailable")
            return []
        output: list[_Candidate] = []
        for lesson in lessons or []:
            statement = self._public_value(self._field(lesson, "statement") or "")
            score = self._score(tokens, statement)
            timestamp = self._public_timestamp(self._field(lesson, "created_at") or 0.0)
            if score <= 0 or statement is None or timestamp is None:
                continue
            lesson_id = self._public_value(self._field(lesson, "id") or "unknown")
            evidence = self._public_value(self._field(lesson, "evidence_ref") or "unresolved")
            session = self._public_value(self._field(lesson, "source_session_id") or "none")
            if lesson_id is None or evidence is None or session is None:
                continue
            output.append(_Candidate(
                "lab_lesson",
                f"{lesson_id}|evidence:{evidence}|session:{session}",
                timestamp,
                statement,
                score,
            ))
        return output

    def _project_candidates(
        self, query: str, tokens: set[str], limit: int, degraded: list[str]
    ) -> list[_Candidate]:
        try:
            provider = self.project_workspace
            if callable(getattr(provider, "search", None)):
                events = provider.search(query, limit=limit)
            elif callable(getattr(provider, "recent_events", None)):
                events = provider.recent_events(limit=limit)
            elif callable(getattr(provider, "list_events", None)):
                events = provider.list_events(limit=limit)
            else:
                raise TypeError("project source has no supported read method")
        except Exception:
            degraded.append("project_memory_unavailable")
            return []
        output: list[_Candidate] = []
        for raw in events or []:
            event = raw if isinstance(raw, dict) else self._object_dict(raw)
            identity = self._public_value(event.get("id") or event.get("ref") or "unknown")
            if identity is None:
                continue
            # ProjectMemory.recent_events() is the production shape.  Its
            # summary is the factual record; do not invent a path or operation.
            if "summary" in event or "task_id" in event or "status" in event:
                task_id = self._public_value(event.get("task_id") or "unknown")
                status = self._public_value(event.get("status") or "unknown")
                summary = self._public_value(event.get("summary") or "")
                if task_id is None or status is None or summary is None:
                    continue
                timestamp = self._public_timestamp(event.get("ts") or event.get("timestamp") or 0.0)
                if timestamp is None:
                    continue
                project_text = " ".join(
                    part for part in (f"task={task_id}", f"status={status}", summary) if part
                )
                score = self._score(tokens, project_text)
                if score <= 0:
                    continue
                output.append(_Candidate(
                    "project_memory", f"event:{identity}|task:{task_id}",
                    timestamp, project_text, score,
                ))
                continue
            operation = self._public_value(event.get("type") or event.get("op") or "event")
            path = self._public_value(event.get("relative_path") or event.get("path") or "")
            digest = self._public_value(event.get("sha256") or event.get("hash") or "")
            if operation is None or path is None or digest is None:
                continue
            timestamp = self._public_timestamp(
                event.get("timestamp") or event.get("occurred_at") or event.get("ts") or 0.0
            )
            if timestamp is None:
                continue
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            safe_metadata = {
                key: value
                for raw_key, raw_value in sorted(metadata.items(), key=lambda pair: str(pair[0]))
                if (key := self._public_value(raw_key)) is not None
                and (value := self._public_value(raw_value)) is not None
            }
            fragments = [operation, path]
            fragments.extend(f"{key}={value}" for key, value in safe_metadata.items())
            project_text = " ".join(part for part in fragments if part).strip()
            score = self._score(tokens, project_text)
            if score <= 0 or self._sensitive(project_text):
                continue
            provenance = identity + (f"|sha256:{digest}" if digest else "")
            output.append(_Candidate(
                "project_memory",
                provenance,
                timestamp,
                project_text,
                score,
            ))
        return output

    def _obsidian_candidates(self, tokens: set[str]) -> list[_Candidate]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT relative_path, mtime_ns, sha256, text FROM obsidian_notes ORDER BY relative_path"
            ).fetchall()
        output: list[_Candidate] = []
        for row in rows:
            relative = self._public_value(row["relative_path"])
            digest = self._public_value(row["sha256"])
            note_text = self._public_value(row["text"])
            if relative is None or digest is None or note_text is None:
                continue
            searchable = f"{relative} {note_text}"
            score = self._score(tokens, searchable)
            if score <= 0:
                continue
            output.append(_Candidate(
                "obsidian",
                f"{relative}|sha256:{digest}",
                float(row["mtime_ns"]) / 1_000_000_000,
                note_text,
                score,
            ))
        return output

    @staticmethod
    def _fit_budget(candidates: list[_Candidate], budget: int, degraded: list[str]) -> dict[str, Any]:
        selected: list[dict[str, Any]] = []
        omitted = len(candidates)
        for candidate in candidates:
            tentative = selected + [candidate.public()]
            trial = SharedSecondBrain._with_size(tentative, omitted - 1, degraded)
            if SharedSecondBrain._encoded_size(trial) <= budget:
                selected = tentative
                omitted -= 1
        result = SharedSecondBrain._with_size(selected, omitted, degraded)
        while SharedSecondBrain._encoded_size(result) > budget and selected:
            selected.pop()
            omitted += 1
            result = SharedSecondBrain._with_size(selected, omitted, degraded)
        return result

    @staticmethod
    def _with_size(items: list[dict[str, Any]], omitted: int, degraded: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "items": items,
            "omitted": omitted,
            "degraded": degraded,
            "used_bytes": 0,
        }
        for _ in range(5):
            size = SharedSecondBrain._encoded_size(result)
            if result["used_bytes"] == size:
                break
            result["used_bytes"] = size
        return result

    @staticmethod
    def _encoded_size(value: dict[str, Any]) -> int:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    @staticmethod
    def _bounded_text(text: str) -> str:
        raw = "\n".join(line.rstrip() for line in text.splitlines()).strip().encode("utf-8")
        if len(raw) <= _MAX_NOTE_BYTES:
            return raw.decode("utf-8")
        return raw[:_MAX_NOTE_BYTES].decode("utf-8", errors="ignore")

    @staticmethod
    def _secret_path(path: str) -> bool:
        normalized = path.replace("\\", "/").casefold()
        return any(_SECRET_PATH_PARTS.search(part) for part in normalized.split("/"))

    @staticmethod
    def _sensitive(text: str) -> bool:
        return bool(_SECRET_CONTENT.search(text) or _PRIVATE_REASONING.search(text))

    @classmethod
    def _public_value(cls, value: Any) -> str | None:
        """Return a display-safe scalar, or suppress it completely.

        Every source-controlled field eventually reaches either text or
        provenance, so this gate is deliberately shared by all domains.
        """
        rendered = str(value or "").strip()
        if cls._sensitive(rendered) or cls._secret_path(rendered):
            return None
        return rendered

    @classmethod
    def _public_timestamp(cls, value: Any) -> float | None:
        rendered = cls._public_value(value)
        if rendered is None:
            return None
        try:
            timestamp = float(rendered)
        except (TypeError, ValueError):
            return None
        return timestamp if math.isfinite(timestamp) else None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        folded = unicodedata.normalize("NFKD", str(text or ""))
        folded = "".join(char for char in folded if not unicodedata.combining(char)).casefold()
        tokens: set[str] = set()
        for word in _WORD.findall(folded):
            if word in _STOP or len(word) < 3:
                continue
            word = {
                "project": "projet",
                "projects": "projet",
                "work": "trabalh",
                "working": "trabalh",
                "goal": "objetiv",
                "goals": "objetiv",
            }.get(word, word)
            for suffix in ("ando", "endo", "indo", "mente", "coes", "cao", "ados", "adas", "ido", "ada", "ado", "es", "os", "as", "o", "a"):
                if len(word) - len(suffix) >= 4 and word.endswith(suffix):
                    word = word[: -len(suffix)]
                    break
            tokens.add(word)
        return tokens

    @classmethod
    def _score(cls, query_tokens: set[str], candidate_text: str) -> float:
        if not query_tokens:
            return 0.0
        candidate_tokens = cls._tokens(candidate_text)
        overlap = query_tokens & candidate_tokens
        return len(overlap) / max(1, len(query_tokens))

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        return value.get(name) if isinstance(value, dict) else getattr(value, name, None)

    @staticmethod
    def _object_dict(value: Any) -> dict[str, Any]:
        if callable(getattr(value, "to_dict", None)):
            rendered = value.to_dict()
            return rendered if isinstance(rendered, dict) else {}
        names = ("id", "ref", "type", "op", "relative_path", "path", "timestamp", "occurred_at", "ts", "sha256", "hash", "metadata", "task_id", "status", "summary")
        return {name: getattr(value, name) for name in names if hasattr(value, name)}
