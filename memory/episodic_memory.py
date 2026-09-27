"""Private, dependency-free episodic memory for ZARA."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import sys
import uuid
from array import array
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


try:
    from core.paths import memory_dir as _memory_dir
    DATABASE_PATH = _memory_dir() / "zara_episodes.sqlite3"
except Exception:
    DATABASE_PATH = _base_dir() / "memory" / "zara_episodes.sqlite3"
VECTOR_SIZE = 256
MAX_EPISODE_CHARS = 1_200
_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "") if len(token) > 1]


def _embed(text: str) -> array:
    """Create a deterministic local vector without downloading a model."""
    vector = array("f", [0.0]) * VECTOR_SIZE
    tokens = _tokens(text)
    for index, token in enumerate(tokens):
        features = (token, f"{tokens[index - 1]}:{token}" if index else token)
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % VECTOR_SIZE
            vector[bucket] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        for index, value in enumerate(vector):
            vector[index] = value / magnitude
    return vector


def _cosine(left: array, right: array) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


class EpisodicMemory:
    """Stores compact local episodes and ranks them with vector similarity."""

    def __init__(self, path: Path = DATABASE_PATH) -> None:
        self.path = path
        self._lock = Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL,
                vector BLOB NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodes_created_at ON episodes(created_at DESC)"
        )
        return connection

    def add(
        self,
        content: str,
        *,
        kind: str = "session_summary",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        content = " ".join((content or "").split())[:MAX_EPISODE_CHARS]
        if not content:
            return None
        episode_id = uuid.uuid4().hex
        vector = _embed(content)
        payload = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO episodes (id, created_at, kind, content, metadata, vector) VALUES (?, ?, ?, ?, ?, ?)",
                (episode_id, created_at, kind[:48], content, payload, vector.tobytes()),
            )
            connection.commit()
        return episode_id

    def remove(self, episode_id: str, *, kind: str | None = None) -> bool:
        """Remove one identified episode, optionally restricted to its kind."""
        identifier = str(episode_id or "").strip()
        if not identifier:
            return False
        with self._lock, closing(self._connect()) as connection:
            if kind is None:
                cursor = connection.execute("DELETE FROM episodes WHERE id = ?", (identifier,))
            else:
                cursor = connection.execute(
                    "DELETE FROM episodes WHERE id = ? AND kind = ?",
                    (identifier, str(kind)[:48]),
                )
            connection.commit()
            return cursor.rowcount > 0

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        query_vector = _embed(query)
        if not any(query_vector):
            return []
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, created_at, kind, content, metadata, vector FROM episodes ORDER BY created_at DESC LIMIT 250"
            ).fetchall()
        ranked: list[dict[str, Any]] = []
        query_tokens = set(_tokens(query))
        for episode_id, created_at, kind, content, metadata, raw_vector in rows:
            vector = array("f")
            vector.frombytes(raw_vector)
            if len(vector) != VECTOR_SIZE:
                continue
            lexical_overlap = len(query_tokens.intersection(_tokens(content))) / max(1, len(query_tokens))
            score = _cosine(query_vector, vector) + (0.35 * lexical_overlap)
            if score <= 0.04:
                continue
            try:
                metadata_value = json.loads(metadata)
            except json.JSONDecodeError:
                metadata_value = {}
            ranked.append(
                {
                    "id": episode_id,
                    "created_at": created_at,
                    "kind": kind,
                    "content": content,
                    "metadata": metadata_value,
                    "score": round(score, 4),
                }
            )
        ranked.sort(key=lambda item: (item["score"], item["created_at"]), reverse=True)
        return ranked[:max(1, min(limit, 10))]

    def context(self, query: str, limit: int = 3, max_chars: int = 700) -> str:
        matches = self.search(query, limit=limit)
        if not matches:
            return ""
        lines = ["[MEMÓRIAS EPISÓDICAS LOCAIS — use apenas quando forem relevantes]"]
        for match in matches:
            date = str(match["created_at"])[:10]
            lines.append(f"- {date}: {match['content']}")
        return "\n".join(lines)[:max_chars]

    def clear(self) -> int:
        """Remove local episodes after an explicit user request."""
        with self._lock, closing(self._connect()) as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])
            connection.execute("DELETE FROM episodes")
            connection.commit()
        return count


_default_store = EpisodicMemory()


def record_episode(content: str, *, kind: str = "session_summary", metadata: dict[str, Any] | None = None) -> str | None:
    """Best-effort persistence so existing memory behavior remains available."""
    try:
        return _default_store.add(content, kind=kind, metadata=metadata)
    except Exception as exc:
        print(f"[EpisodicMemory] Could not save episode: {exc}")
        return None


def remove_episode(episode_id: str, *, kind: str | None = None) -> bool:
    """Remove a single episode from the local store; never clear unrelated memory."""
    return _default_store.remove(episode_id, kind=kind)


def episodic_context(query: str, limit: int = 3, max_chars: int = 700) -> str:
    """Return relevant local episodes without exposing database details."""
    try:
        return _default_store.context(query, limit=limit, max_chars=max_chars)
    except Exception as exc:
        print(f"[EpisodicMemory] Could not retrieve episodes: {exc}")
        return ""


def clear_episodic_memory(*, strict: bool = False) -> int:
    """Best-effort clearing for the privacy controls in the interface."""
    try:
        return _default_store.clear()
    except Exception as exc:
        print(f"[EpisodicMemory] Could not clear episodes: {exc}")
        if strict:
            raise
        return 0
