"""Safe, incremental project file index with auditable local events.

The index stores metadata only (never file contents) and excludes credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


SECRET_NAMES = {".env", ".env.local", "api_keys.json", "credentials.json", "secrets.json"}
SECRET_PARTS = {"secret", "secrets", "credential", "credentials", "token", "password", "apikey", "api_key"}
IGNORED_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", "artifacts"}
SUPPORTED_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ts", ".tsx", ".js", ".jsx", ".html", ".css"}


@dataclass(frozen=True)
class IndexedFile:
    relative_path: str
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class ScanResult:
    changed: tuple[IndexedFile, ...]
    removed: tuple[str, ...]


def _secret(path: Path) -> bool:
    parts = {part.casefold() for part in path.parts}
    name = path.name.casefold()
    return name in SECRET_NAMES or any(part in SECRET_PARTS for part in parts) or any(
        part.startswith(".env") for part in parts
    )


class ProjectIndexer:
    def __init__(self, root: str | os.PathLike[str], *, state_path=None, event_sink: Callable[[dict[str, Any]], None] | None = None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("project root must be a directory")
        self.state_path = Path(state_path).resolve() if state_path else self.root / ".zara-project-index.json"
        self.event_sink = event_sink
        self._entries: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data.get("entries", {}) if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _emit(self, event_type: str, relative_path: str) -> None:
        if self.event_sink:
            self.event_sink({"type": event_type, "path": relative_path})

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".project-index-", suffix=".tmp", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "root": str(self.root), "entries": self._entries}, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.state_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def scan(self) -> ScanResult:
        current: dict[str, IndexedFile] = {}
        for path in self.root.rglob("*"):
            if (not path.is_file() or path.resolve() == self.state_path
                    or any(part in IGNORED_DIRS for part in path.relative_to(self.root).parts) or _secret(path)):
                continue
            if path.suffix.casefold() not in SUPPORTED_SUFFIXES:
                continue
            relative = path.relative_to(self.root).as_posix()
            stat = path.stat()
            # Content hash remains the authoritative change marker.  Windows
            # can preserve size and mtime for two rapid writes, so metadata
            # alone cannot safely decide that a file is unchanged.
            previous = self._entries.get(relative)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            current[relative] = IndexedFile(relative, stat.st_size, stat.st_mtime_ns, digest)
        changed = tuple(item for name, item in sorted(current.items()) if self._entries.get(name) != item.__dict__)
        removed = tuple(sorted(set(self._entries) - set(current)))
        for item in changed:
            self._emit("project.file_indexed", item.relative_path)
        for name in removed:
            self._emit("project.file_removed", name)
        self._entries = {name: item.__dict__ for name, item in current.items()}
        self._save()
        return ScanResult(changed, removed)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: dict(value) for name, value in self._entries.items()}
