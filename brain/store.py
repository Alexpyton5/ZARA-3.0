"""Minimal reversible store for the Cérebro do Alex.

Three compartments (gavetas):
- MEMORY: fatos, decisões, preferências, identidade, relacionamentos, desejos, notas
- KNOWLEDGE: PDFs, vídeos, sites, conteúdo externo importado
- SKILL: procedimentos, how-to, skills, workflows

Markdown is the canonical, human-readable data. SQLite is only a derived search
index and can be rebuilt at any time. Imports copy safe notes and never modify
or remove their source vaults.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
import time
from array import array
from contextlib import closing
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

try:
    from ollama import Client as OllamaClient
    _OLLAMA_AVAILABLE = True
except Exception:
    _OLLAMA_AVAILABLE = False
    import urllib.request

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:api[_ -]?key|chave[_ -]?de[_ -]?api|password|senha|secret|"
        r"access[_ -]?token|refresh[_ -]?token|token|authorization)\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{8,}"),
    re.compile(r"\b(?:sk-|ghp_|github_pat_|gsk_|nvapi-)[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_SEARCH_TOKEN = re.compile(r"[\wÀ-ÿ]{2,}", re.UNICODE)
_ALLOWED_SUFFIXES = {".md"}


class Compartment(StrEnum):
    """As três gavetas do BrainStore."""

    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"

    @property
    def display_name(self) -> str:
        return self.value.upper()

    @property
    def description(self) -> str:
        return {
            Compartment.MEMORY: "Fatos, decisões, preferências, identidade, relacionamentos, desejos, notas",
            Compartment.KNOWLEDGE: "PDFs, vídeos, sites, conteúdo externo importado",
            Compartment.SKILL: "Procedimentos, how-to, skills, workflows",
        }[self]


def _default_root() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return local / "ZARA3" / "data" / "brain"


def default_source_vaults() -> dict[str, Path]:
    """Known legacy vaults. Merely returning these paths has no side effects."""
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return {
        "obsidian_legacy": local / "ZARA" / "vault" / "context",
        "zara3_obsidian_bridge": local / "ZARA3" / "vault",
        "zara3_project_memory": local / "ZARA3" / "data" / "project-memory" / "vault",
    }


def _has_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _embed(text: str) -> array:
    """Get embedding from Ollama's nomic-embed-text model."""
    try:
        if _OLLAMA_AVAILABLE:
            client = OllamaClient()
            response = client.embeddings(model='nomic-embed-text', prompt=text)
            vector = array('f', response['embedding'])
        else:
            import urllib.request
            import json
            url = "http://localhost:11434/api/embeddings"
            data = json.dumps({"model": "nomic-embed-text", "prompt": text})
            data = data.encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            response = urllib.request.urlopen(req)
            result = json.load(response)
            vector = array('f', result['embedding'])
    except Exception as exc:
        # Return zero vector on failure
        vector = array('f', [0.0] * 768)

    # Normalize the vector
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        for index, value in enumerate(vector):
            vector[index] = value / magnitude
    return vector


def _cosine(left: array, right: array) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        temporary = Path(handle.name)
    temporary.replace(path)


@dataclass(frozen=True)
class Citation:
    title: str
    excerpt: str
    note_path: str
    source_label: str
    source_path: str
    sha256: str
    compartment: str  # MEMORY | KNOWLEDGE | SKILL


@dataclass(frozen=True)
class ImportReport:
    source_label: str
    source_root: str
    imported: int
    deduplicated: int
    blocked_secrets: int
    skipped: int
    compartment: str
    missing: bool = False


@dataclass(frozen=True)
class SourcePreview:
    source_label: str
    source_root: str
    exists: bool
    markdown_files: int
    markdown_bytes: int
    unique_hashes: int
    duplicate_files: int
    duplicate_hashes: dict[str, int]
    ignored_files: int
    blocked_secrets: int
    symlinks: int


@dataclass(frozen=True)
class ImportPreview:
    sources: tuple[SourcePreview, ...]
    existing_sources: int
    missing_sources: int
    markdown_files: int
    markdown_bytes: int
    unique_hashes: int
    duplicate_files: int
    duplicate_hashes: dict[str, int]
    ignored_files: int
    blocked_secrets: int
    symlinks: int


def preview_import(sources: dict[str, Path | str] | None = None) -> ImportPreview:
    """Inventory vaults without creating, copying or modifying anything.

    Duplicate counts are content-based. Per-source counts describe duplicates
    inside that source; consolidated counts also detect the same note appearing
    in different vaults.
    """
    selected = sources if sources is not None else default_source_vaults()
    previews: list[SourcePreview] = []
    all_hashes: dict[str, int] = {}

    for label, raw_root in selected.items():
        root = Path(raw_root)
        if not root.is_dir():
            previews.append(
                SourcePreview(label, str(root), False, 0, 0, 0, 0, {}, 0, 0, 0)
            )
            continue

        markdown_files = markdown_bytes = ignored = blocked = symlinks = 0
        source_hashes: dict[str, int] = {}
        for candidate in sorted(root.rglob("*")):
            if candidate.is_symlink():
                symlinks += 1
                ignored += 1
                continue
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if any(part.startswith(".") for part in relative.parts):
                ignored += 1
                continue
            if candidate.suffix.lower() not in _ALLOWED_SUFFIXES:
                ignored += 1
                continue
            try:
                raw = candidate.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                ignored += 1
                continue

            markdown_files += 1
            markdown_bytes += len(raw)
            digest = hashlib.sha256(raw).hexdigest()
            source_hashes[digest] = source_hashes.get(digest, 0) + 1
            all_hashes[digest] = all_hashes.get(digest, 0) + 1
            if _has_secret(text):
                blocked += 1

        duplicate_hashes = {
            digest: count for digest, count in source_hashes.items() if count > 1
        }
        previews.append(
            SourcePreview(
                source_label=label,
                source_root=str(root),
                exists=True,
                markdown_files=markdown_files,
                markdown_bytes=markdown_bytes,
                unique_hashes=len(source_hashes),
                duplicate_files=sum(count - 1 for count in duplicate_hashes.values()),
                duplicate_hashes=duplicate_hashes,
                ignored_files=ignored,
                blocked_secrets=blocked,
                symlinks=symlinks,
            )
        )

    consolidated_duplicates = {
        digest: count for digest, count in all_hashes.items() if count > 1
    }
    return ImportPreview(
        sources=tuple(previews),
        existing_sources=sum(item.exists for item in previews),
        missing_sources=sum(not item.exists for item in previews),
        markdown_files=sum(item.markdown_files for item in previews),
        markdown_bytes=sum(item.markdown_bytes for item in previews),
        unique_hashes=len(all_hashes),
        duplicate_files=sum(count - 1 for count in consolidated_duplicates.values()),
        duplicate_hashes=consolidated_duplicates,
        ignored_files=sum(item.ignored_files for item in previews),
        blocked_secrets=sum(item.blocked_secrets for item in previews),
        symlinks=sum(item.symlinks for item in previews),
    )


class BrainStore:
    """Canonical Markdown notes plus a disposable SQLite FTS5 index per compartment."""

    # Schema version for the database
    SCHEMA_VERSION = 3

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self.index_path = self.root / "brain.db"
        self.manifest_path = self.root / "manifest.json"
        # Each compartment has its own notes directory
        self.compartment_dirs: dict[Compartment, Path] = {
            compartment: self.root / "vault" / compartment.value / "notes"
            for compartment in Compartment
        }

    @staticmethod
    def preview_import(
        sources: dict[str, Path | str] | None = None,
    ) -> ImportPreview:
        return preview_import(sources)

    def initialize(self) -> None:
        """Create all compartment directories and ensure database schema."""
        for compartment_dir in self.compartment_dirs.values():
            compartment_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if not self.manifest_path.exists():
            _atomic_json(
                self.manifest_path,
                self._empty_manifest(),
            )
        else:
            # Loading also upgrades the reversible manifest before any import.
            self._load_manifest()

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        """Create tables for all three compartments with FTS5 and vector storage."""
        with closing(self._connect()) as connection:
            # Create tables for each compartment
            for compartment in Compartment:
                table = compartment.value
                connection.executescript(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table}_documents (
                        sha256 TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        note_path TEXT NOT NULL UNIQUE,
                        indexed_at REAL NOT NULL,
                        vector BLOB
                    );
                    CREATE TABLE IF NOT EXISTS {table}_provenance (
                        source_label TEXT NOT NULL,
                        source_root TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        sha256 TEXT NOT NULL REFERENCES {table}_documents(sha256),
                        imported_at REAL NOT NULL,
                        PRIMARY KEY (source_label, source_path)
                    );
                    CREATE VIRTUAL TABLE IF NOT EXISTS {table}_fts USING fts5(
                        title, content, sha256 UNINDEXED, tokenize='unicode61 remove_diacritics 2'
                    );
                    """
                )

            # Manifest metadata table
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS manifest_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _empty_manifest(self) -> dict:
        return {
            "version": self.SCHEMA_VERSION,
            "sources": {},
            "documents": {},
            "compartments": {c.value: [] for c in Compartment},
        }

    @staticmethod
    def _document_key(compartment: Compartment | str, digest: str) -> str:
        value = compartment.value if isinstance(compartment, Compartment) else str(compartment)
        return f"{value}:{digest}"

    @staticmethod
    def _valid_digest(value: object) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    def _normalize_manifest(self, raw: dict) -> tuple[dict, bool]:
        """Upgrade v1/v2 manifests and remove duplicate document references."""
        if not isinstance(raw, dict):
            raise ValueError("brain manifest root must be an object")
        sources = raw.get("sources") if isinstance(raw.get("sources"), dict) else {}
        documents: dict[str, dict] = {}

        raw_documents = raw.get("documents")
        if isinstance(raw_documents, dict):
            for old_key, old_item in raw_documents.items():
                if not isinstance(old_item, dict):
                    continue
                compartment = str(old_item.get("compartment", "memory"))
                if compartment not in {item.value for item in Compartment}:
                    compartment = Compartment.MEMORY.value
                digest = old_item.get("sha256")
                if not self._valid_digest(digest):
                    digest = str(old_key).rsplit(":", 1)[-1]
                if not self._valid_digest(digest):
                    continue
                item = dict(old_item)
                item["sha256"] = digest
                item["compartment"] = compartment
                documents[self._document_key(compartment, digest)] = item

        # Old manifests keyed documents only by hash, so identical content in a
        # second compartment was overwritten.  Provenance still contains enough
        # information to reconstruct the missing composite entry.
        for source in sources.values():
            if not isinstance(source, dict) or not isinstance(source.get("items"), dict):
                continue
            for source_item in source["items"].values():
                if not isinstance(source_item, dict):
                    continue
                if source_item.get("status") not in {"imported", "deduplicated"}:
                    continue
                digest = source_item.get("sha256")
                compartment = str(source_item.get("compartment", "memory"))
                if not self._valid_digest(digest) or compartment not in {
                    item.value for item in Compartment
                }:
                    continue
                key = self._document_key(compartment, digest)
                if key in documents:
                    continue
                note_path = str(source_item.get("note_path", ""))
                canonical = self.root / "vault" / compartment / note_path
                documents[key] = {
                    "sha256": digest,
                    "note_path": note_path,
                    "size": canonical.stat().st_size if canonical.is_file() else 0,
                    "compartment": compartment,
                }

        normalized = {
            "version": self.SCHEMA_VERSION,
            "sources": sources,
            "documents": documents,
            "compartments": {
                compartment.value: sorted(
                    {
                        item["sha256"]
                        for item in documents.values()
                        if item.get("compartment") == compartment.value
                    }
                )
                for compartment in Compartment
            },
        }
        return normalized, normalized != raw

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return self._empty_manifest()
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest, changed = self._normalize_manifest(raw)
        if changed:
            self._save_manifest(manifest)
        return manifest

    def _save_manifest(self, manifest: dict) -> None:
        _atomic_json(self.manifest_path, manifest)

    def _determine_compartment(self, source_label: str, content: str) -> Compartment:
        """Determine which compartment a note belongs to based on source and content."""
        # Heuristic based on source label and content
        label_lower = source_label.lower()
        content_lower = content.lower()

        # SKILL compartment: procedures, how-to, skills
        skill_keywords = ["skill", "procedure", "howto", "how-to", "workflow", "passo", "procedimento", "tutorial"]
        if any(kw in label_lower for kw in skill_keywords):
            return Compartment.SKILL
        if any(kw in content_lower for kw in skill_keywords) and (
            "passo" in content_lower or "como " in content_lower or "procedimento" in content_lower
        ):
            return Compartment.SKILL

        # KNOWLEDGE compartment: external content, pdfs, videos, websites
        knowledge_keywords = ["pdf", "video", "youtube", "site", "web", "artigo", "paper", "documento", "fonte externa"]
        if any(kw in label_lower for kw in knowledge_keywords):
            return Compartment.KNOWLEDGE
        if any(kw in content_lower for kw in knowledge_keywords):
            return Compartment.KNOWLEDGE

        # Default to MEMORY for personal facts, decisions, preferences
        return Compartment.MEMORY

    def import_vault(
        self, source: Path | str, source_label: str, compartment: Compartment | str | None = None
    ) -> ImportReport:
        """Copy safe Markdown notes into the canonical vault with provenance.

        Files containing likely credentials are not copied. Identical content is
        stored once per compartment while retaining every source reference in
        the manifest/index.

        If compartment is not specified, it's determined heuristically.
        """
        self.initialize()
        source_root = Path(source).resolve()
        if not source_root.is_dir():
            comp = compartment.value if isinstance(compartment, Compartment) else (compartment or "memory")
            return ImportReport(
                source_label, str(source_root), 0, 0, 0, 0, comp, missing=True
            )
        if not source_label.strip() or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", source_label):
            raise ValueError("source_label must be a safe identifier")

        manifest = self._load_manifest()
        source_manifest = {"root": str(source_root), "scanned_at": time.time(), "items": {}}
        imported = deduplicated = blocked = skipped = 0

        for candidate in sorted(source_root.rglob("*")):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative = candidate.relative_to(source_root)
            if any(part.startswith(".") for part in relative.parts) or candidate.suffix.lower() not in _ALLOWED_SUFFIXES:
                skipped += 1
                continue
            try:
                raw = candidate.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                skipped += 1
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if _has_secret(text):
                blocked += 1
                source_manifest["items"][relative.as_posix()] = {
                    "status": "blocked_secret",
                    "sha256": digest,
                }
                continue

            # Determine compartment for this note
            if isinstance(compartment, Compartment):
                note_compartment = compartment
            elif isinstance(compartment, str):
                note_compartment = Compartment(compartment)
            else:
                note_compartment = self._determine_compartment(source_label, text)

            note_relative = Path("notes") / digest[:2] / f"{digest}.md"
            note_path = self.root / "vault" / note_compartment.value / note_relative
            already_present = note_path.exists()
            note_path.parent.mkdir(parents=True, exist_ok=True)
            if not already_present:
                shutil.copyfile(candidate, note_path)
                imported += 1
            else:
                if hashlib.sha256(note_path.read_bytes()).hexdigest() != digest:
                    raise RuntimeError(f"canonical note hash mismatch: {note_path}")
                deduplicated += 1

            title = self._title(text, candidate.stem)
            source_manifest["items"][relative.as_posix()] = {
                "status": "deduplicated" if already_present else "imported",
                "sha256": digest,
                "note_path": note_relative.as_posix(),
                "compartment": note_compartment.value,
            }
            document_key = self._document_key(note_compartment, digest)
            manifest["documents"][document_key] = {
                "sha256": digest,
                "note_path": note_relative.as_posix(),
                "size": len(raw),
                "compartment": note_compartment.value,
            }
            compartment_documents = manifest["compartments"][note_compartment.value]
            if digest not in compartment_documents:
                compartment_documents.append(digest)
            self._upsert_document(
                compartment=note_compartment,
                digest=digest,
                title=title,
                content=text,
                note_path=note_relative.as_posix(),
                source_label=source_label,
                source_root=str(source_root),
                source_path=relative.as_posix(),
            )

        manifest["sources"][source_label] = source_manifest
        self._save_manifest(manifest)
        # Return the actual compartment used for the last note (or first if multiple)
        # Since all notes in a single import_vault call use the same compartment logic,
        # we can track it. For simplicity, use the compartment of the first imported note.
        if imported > 0 or deduplicated > 0:
            # Find the compartment from the first item in source_manifest
            for item in source_manifest["items"].values():
                if "compartment" in item:
                    comp_value = item["compartment"]
                    break
            else:
                comp_value = compartment.value if isinstance(compartment, Compartment) else (compartment or "auto")
        else:
            comp_value = compartment.value if isinstance(compartment, Compartment) else (compartment or "auto")
        return ImportReport(
            source_label, str(source_root), imported, deduplicated, blocked, skipped, comp_value
        )

    def _upsert_document(
        self,
        *,
        compartment: Compartment,
        digest: str,
        title: str,
        content: str,
        note_path: str,
        source_label: str,
        source_root: str,
        source_path: str,
    ) -> None:
        now = time.time()
        table = compartment.value
        # Compute embedding for semantic search
        vector = _embed(content)
        vector_bytes = vector.tobytes()
        with closing(self._connect()) as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO {table}_documents(sha256,title,content,note_path,indexed_at,vector) "
                "VALUES(?,?,?,?,?,?)",
                (digest, title, content, note_path, now, vector_bytes),
            )
            connection.execute(f"DELETE FROM {table}_fts WHERE sha256=?", (digest,))
            connection.execute(
                f"INSERT INTO {table}_fts(title,content,sha256) VALUES(?,?,?)",
                (title, content, digest),
            )
            connection.execute(
                f"INSERT OR REPLACE INTO {table}_provenance(source_label,source_root,source_path,sha256,imported_at) "
                "VALUES(?,?,?,?,?)",
                (source_label, source_root, source_path, digest, now),
            )
            connection.commit()

    @staticmethod
    def _title(content: str, fallback: str) -> str:
        for line in content.splitlines():
            value = line.strip()
            if value.startswith("# "):
                return value[2:].strip()[:160] or fallback[:160]
        return fallback[:160]

    def rebuild_index(self) -> int:
        """Recreate disposable search tables from manifest + canonical notes."""
        self.initialize()
        manifest = self._load_manifest()
        with closing(self._connect()) as connection:
            for compartment in Compartment:
                table = compartment.value
                connection.execute(f"DELETE FROM {table}_fts")
                connection.execute(f"DELETE FROM {table}_provenance")
                connection.execute(f"DELETE FROM {table}_documents")
            connection.commit()

        count = 0
        for document_key, item in manifest.get("documents", {}).items():
            compartment_str = item.get("compartment", "memory")
            try:
                compartment = Compartment(compartment_str)
            except ValueError:
                compartment = Compartment.MEMORY

            digest = item.get("sha256") or str(document_key).rsplit(":", 1)[-1]
            if not self._valid_digest(digest):
                continue
            note_relative = str(item.get("note_path", ""))
            note_path = self.root / "vault" / compartment.value / note_relative
            if not note_path.is_file():
                continue
            raw = note_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                continue
            text = raw.decode("utf-8")
            title = self._title(text, note_path.stem)
            provenances: list[tuple[str, str, str]] = []
            for label, source in manifest.get("sources", {}).items():
                for source_path, source_item in source.get("items", {}).items():
                    if (
                        source_item.get("sha256") == digest
                        and source_item.get("compartment", "memory") == compartment.value
                        and source_item.get("status") in {"imported", "deduplicated"}
                    ):
                        provenances.append((label, str(source.get("root", "")), source_path))
            if not provenances:
                continue
            for label, source_root, source_path in provenances:
                self._upsert_document(
                    compartment=compartment,
                    digest=digest,
                    title=title,
                    content=text,
                    note_path=note_relative,
                    source_label=label,
                    source_root=source_root,
                    source_path=source_path,
                )
            count += 1

        return count

    def search(
        self, query: str, limit: int = 5, compartment: Compartment | str | None = None
    ) -> list[Citation]:
        """Search across all compartments or a specific one."""
        self.initialize()
        tokens = _SEARCH_TOKEN.findall(query or "")
        if not tokens:
            return []
        expression = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:12])

        compartments = [Compartment(compartment)] if isinstance(compartment, str) else (
            [compartment] if isinstance(compartment, Compartment) else list(Compartment)
        )

        ranked_results: list[tuple[float, Citation]] = []
        for comp in compartments:
            table = comp.value
            sql = f"""
                SELECT d.title, d.content, d.note_path, d.sha256,
                       p.source_label, p.source_path, bm25({table}_fts) AS rank
                FROM {table}_fts
                JOIN {table}_documents d ON d.sha256={table}_fts.sha256
                JOIN {table}_provenance p ON p.sha256=d.sha256
                WHERE {table}_fts MATCH ?
                ORDER BY rank, p.source_label, p.source_path
                LIMIT ?
            """
            with closing(self._connect()) as connection:
                rows = connection.execute(sql, (expression, max(1, min(limit, 20)))).fetchall()
            for row in rows:
                ranked_results.append(
                    (
                        row["rank"],
                        Citation(
                            title=row["title"],
                            excerpt=self._excerpt(row["content"], tokens),
                            note_path=row["note_path"],
                            source_label=row["source_label"],
                            source_path=row["source_path"],
                            sha256=row["sha256"],
                            compartment=comp.value,
                        ),
                    )
                )

        # AUDITORIA_2026-08-27 item 2.2: SQLite's bm25() returns a lower (more
        # negative) score for a better match, so ascending sort is relevance
        # order. The old code discarded `rank` entirely and sorted the merged
        # cross-compartment list alphabetically by excerpt text.
        ranked_results.sort(key=lambda pair: pair[0])
        return [citation for _, citation in ranked_results[:limit]]

    def search_semantic(self, query: str, limit: int = 5, compartment: Compartment | str | None = None) -> list[Citation]:
        """Semantic search using vector embeddings across compartments."""
        self.initialize()
        query_vector = _embed(query)
        if not any(query_vector):
            return []

        compartments = [Compartment(compartment)] if isinstance(compartment, str) else (
            [compartment] if isinstance(compartment, Compartment) else list(Compartment)
        )

        all_results: list[tuple[Citation, float]] = []
        for comp in compartments:
            table = comp.value
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    f"SELECT d.title, d.content, d.note_path, d.sha256, d.vector, "
                    f"p.source_label, p.source_path FROM {table}_documents d "
                    f"JOIN {table}_provenance p ON p.sha256=d.sha256"
                ).fetchall()
                
                for row in rows:
                    if row['vector'] is None:
                        continue
                    stored_vector = array('f')
                    stored_vector.frombytes(row['vector'])
                    if len(stored_vector) != 768:
                        continue
                    similarity = _cosine(query_vector, stored_vector)
                    if similarity > 0.3:  # Similarity threshold
                        citation = Citation(
                            title=row['title'],
                            excerpt=self._excerpt(row['content'], _SEARCH_TOKEN.findall(query or "")),
                            note_path=row['note_path'],
                            source_label=row['source_label'],
                            source_path=row['source_path'],
                            sha256=row['sha256'],
                            compartment=comp.value,
                        )
                        all_results.append((citation, similarity))

        # Sort by similarity descending
        all_results.sort(key=lambda x: x[1], reverse=True)
        return [citation for citation, _ in all_results[:limit]]

    def search_semantic_compartment(self, compartment: Compartment | str, query: str, limit: int = 5) -> list[Citation]:
        """Semantic search within a specific compartment."""
        return self.search_semantic(query, limit, compartment)

    @staticmethod
    def _excerpt(content: str, tokens: list[str], width: int = 240) -> str:
        folded = content.casefold()
        positions = [folded.find(token.casefold()) for token in tokens]
        positions = [position for position in positions if position >= 0]
        center = min(positions) if positions else 0
        start = max(0, center - width // 3)
        return " ".join(content[start : start + width].split())

    def manifest(self) -> dict:
        self.initialize()
        return self._load_manifest()

    def report_as_dict(self, report: ImportReport) -> dict:
        return asdict(report)

    def get_compartment_stats(self) -> dict[str, dict]:
        """Get statistics for each compartment."""
        stats = {}
        for compartment in Compartment:
            table = compartment.value
            with closing(self._connect()) as connection:
                doc_count = connection.execute(f"SELECT COUNT(*) FROM {table}_documents").fetchone()[0]
                prov_count = connection.execute(f"SELECT COUNT(*) FROM {table}_provenance").fetchone()[0]
            notes_dir = self.compartment_dirs[compartment]
            note_files = list(notes_dir.rglob("*.md")) if notes_dir.exists() else []
            stats[compartment.value] = {
                "display_name": compartment.display_name,
                "description": compartment.description,
                "documents": doc_count,
                "provenance_entries": prov_count,
                "note_files": len(note_files),
            }
        return stats

    def search_compartment(self, compartment: Compartment | str, query: str, limit: int = 5) -> list[Citation]:
        """Search within a specific compartment."""
        return self.search(query, limit, compartment)
