"""ZARA-OBSIDIAN-MEMORY-001 (Alex, 2026-08-28)

Peça ISOLADA, não plugada em nenhum caminho de produção ainda.

Antes de escrever isto: já existe `memory/project_memory.py::_detect_real_obsidian_vault`
(lê o `obsidian.json` de verdade em vez de adivinhar caminho) e
`core/obsidian_bridge.py::ObsidianBridge` (vault SANDBOX próprio da Zara,
separado do cofre real). Este módulo REUSA a detecção real de vault já
existente -- não inventa um segundo jeito de achar o cofre do Alex -- e
escreve na MESMA subpasta `Zara-Memoria` que `project_memory.py` já usa,
pra não fragmentar o conteúdo da Zara em pastas concorrentes dentro do
cofre real dele.

search_notes(): read-only, nunca escreve nada.
save_memory(): best-effort. Cofre desconectado (HD externo, por exemplo)
devolve None em vez de levantar -- a Zara não pode quebrar por causa de um
cofre indisponível.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from memory.project_memory import _detect_real_obsidian_vault

_ZARA_SUBFOLDER = "Zara-Memoria"
_SNIPPET_RADIUS_CHARS = 120
_PROJECT_MEMORY_MAX_FILES = 128
_PROJECT_MEMORY_MAX_ENTRIES = 4096
_PROJECT_MEMORY_MAX_FILE_BYTES = 256_000
_PROJECT_MEMORY_MAX_TOTAL_BYTES = 2_000_000
_PROJECT_MEMORY_MAX_MATCHES = 4
_PROJECT_MEMORY_MAX_SNIPPET_CHARS = 1_200
_PROJECT_MEMORY_STOPWORDS = frozenset({
    "para", "com", "uma", "uns", "das", "dos", "que", "por", "como", "mais", "menos",
    "esta", "esse", "essa", "sobre", "entre", "quando", "onde", "the", "and", "for",
    "from", "with", "that", "this", "into", "your", "have", "what", "which",
})
_PROJECT_MEMORY_SECRET_RE = re.compile(
    r"(?i)(?:\b(?:[A-Z0-9]+_)?(?:API[_ -]?KEY|ACCESS[_ -]?TOKEN|REFRESH[_ -]?TOKEN|"
    r"SECRET(?:[_ -]?ACCESS[_ -]?KEY)?|PASSWORD|PASSWD|TOKEN|CREDENTIALS?)\b"
    r"\s*[:=]\s*['\"]?[^\s'\"]{8,}|\bbearer\s+[A-Za-z0-9._~+/-]{12,}|"
    r"\b(?:nvapi-|sk-(?:proj-|ant-|live_)?|gh[pousr]_|github_pat_|xox[baprs]-|"
    r"sk_live_|rk_live_|AIza|ya29\.|hf_|pypi-|npm_)"
    r"[A-Za-z0-9_./+=-]{12,}|-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


@dataclass(frozen=True, slots=True)
class NoteMatch:
    title: str
    path: str
    snippet: str


class ObsidianMemoryManager:
    """Aponta pro cofre real do Obsidian: `vault_path` explícito (testes) >
    `OBSIDIAN_VAULT_PATH` (env) > detecção real via obsidian.json."""

    def __init__(self, vault_path: Path | str | None = None):
        if vault_path is not None:
            self.vault_path: Path | None = Path(vault_path)
        else:
            env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
            self.vault_path = Path(env_path) if env_path else _detect_real_obsidian_vault()

    @property
    def available(self) -> bool:
        try:
            return self.vault_path is not None and self.vault_path.is_dir()
        except OSError:
            return False

    def search_notes(self, query: str) -> list[dict]:
        """Varre recursivamente as notas .md do cofre (case-insensitive) e
        devolve título + caminho relativo + trecho de contexto de cada nota
        que contém a query. [] se o cofre não estiver disponível ou a query
        for vazia -- nunca levanta exceção."""
        if not self.available:
            return []
        needle = str(query or "").strip().lower()
        if not needle:
            return []

        matches: list[dict] = []
        for md_path in self.vault_path.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            index = text.lower().find(needle)
            if index == -1:
                continue
            start = max(0, index - _SNIPPET_RADIUS_CHARS)
            end = min(len(text), index + len(needle) + _SNIPPET_RADIUS_CHARS)
            snippet = text[start:end].strip()
            match = NoteMatch(title=md_path.stem, path=str(md_path.relative_to(self.vault_path)), snippet=snippet)
            matches.append({"title": match.title, "path": match.path, "snippet": match.snippet})
        return matches

    @staticmethod
    def _normalize_project_text(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()

    def _project_memory_files(self) -> list[tuple[Path, float, int]]:
        """Return Markdown metadata from the ZARA project-memory folder only.

        The rest of Alex's Obsidian vault is deliberately outside the Lab's
        retrieval boundary. Symlinks and paths resolving outside this folder
        are ignored.
        """
        if not self.available:
            return []
        try:
            vault = self.vault_path.resolve(strict=True)
        except (OSError, RuntimeError):
            return []
        folder = self.vault_path / _ZARA_SUBFOLDER
        if folder.is_symlink() or not folder.is_dir():
            return []
        try:
            root = folder.resolve(strict=True)
            root.relative_to(vault)
        except (OSError, ValueError):
            return []

        rows: list[tuple[Path, float, int]] = []
        entries_seen = 0
        try:
            for current, directories, filenames in os.walk(folder, followlinks=False):
                directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
                for name in filenames:
                    entries_seen += 1
                    if entries_seen > _PROJECT_MEMORY_MAX_ENTRIES:
                        break
                    path = Path(current) / name
                    if path.suffix.casefold() != ".md" or path.is_symlink():
                        continue
                    try:
                        resolved = path.resolve(strict=True)
                        resolved.relative_to(root)
                        if not resolved.is_file():
                            continue
                        stat = resolved.stat()
                        rows.append((resolved, stat.st_mtime, stat.st_size))
                    except (OSError, RuntimeError, ValueError):
                        continue
                if entries_seen > _PROJECT_MEMORY_MAX_ENTRIES:
                    break
        except (OSError, RuntimeError):
            return []
        rows.sort(key=lambda row: (row[1], str(row[0]).casefold()), reverse=True)
        return rows[:_PROJECT_MEMORY_MAX_FILES]

    def project_memory_status(self) -> dict:
        """Describe connection and freshness without exposing a local path."""
        checked_at = time.time()
        if not self.available:
            return {
                "state": "UNAVAILABLE", "source": "Obsidian · Zara-Memoria",
                "notes_count": 0, "checked_at": checked_at,
                "latest_updated_at": None, "read_mode": "LIVE_READ",
            }
        rows = self._project_memory_files()
        return {
            "state": "CONNECTED" if rows else "CONNECTED_EMPTY",
            "source": "Obsidian · Zara-Memoria",
            "notes_count": len(rows), "checked_at": checked_at,
            "latest_updated_at": max((row[1] for row in rows), default=None),
            "read_mode": "LIVE_READ",
        }

    def search_project_memory(self, query: str, *, limit: int = _PROJECT_MEMORY_MAX_MATCHES) -> list[dict]:
        """Find bounded, relevant snippets only in `Zara-Memoria`.

        This is a live read, not a persisted index. Notes with credential-like
        material are excluded as a whole; the event/UI receives only source
        metadata, never the note body.
        """
        if not self.available:
            return []
        normalized_query = self._normalize_project_text(str(query or '')[:12_000])
        terms = [term for term in re.findall(r"[a-z0-9_]{3,}", normalized_query)
                 if term not in _PROJECT_MEMORY_STOPWORDS]
        terms = list(dict.fromkeys(terms))[:32]
        if not terms:
            return []

        scored: list[tuple[int, float, dict]] = []
        bytes_read = 0
        try:
            vault = self.vault_path.resolve(strict=True)
        except (OSError, RuntimeError):
            return []
        for path, modified_at, size in self._project_memory_files():
            if size <= 0 or size > _PROJECT_MEMORY_MAX_FILE_BYTES:
                continue
            if bytes_read + size > _PROJECT_MEMORY_MAX_TOTAL_BYTES:
                break
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            bytes_read += size
            if _PROJECT_MEMORY_SECRET_RE.search(raw):
                continue

            title = path.stem
            normalized_title = self._normalize_project_text(title)
            normalized_body = self._normalize_project_text(raw)
            title_score = sum(4 for term in terms if term in normalized_title)
            body_score = sum(min(4, normalized_body.count(term)) for term in terms)
            score = title_score + body_score
            if score <= 0:
                continue

            lines = raw.splitlines()
            line_scores = [
                sum(min(3, self._normalize_project_text(line).count(term)) for term in terms)
                for line in lines
            ]
            if line_scores and max(line_scores) > 0:
                center = line_scores.index(max(line_scores))
                snippet = "\n".join(lines[max(0, center - 1):center + 3]).strip()
            else:
                snippet = raw.strip()[:_PROJECT_MEMORY_MAX_SNIPPET_CHARS]
            if len(snippet) > _PROJECT_MEMORY_MAX_SNIPPET_CHARS:
                snippet = snippet[:_PROJECT_MEMORY_MAX_SNIPPET_CHARS - 1].rstrip() + "…"
            try:
                relative_path = str(path.relative_to(vault)).replace("\\", "/")
            except ValueError:
                continue
            scored.append((score, modified_at, {
                "title": title[:160], "path": relative_path,
                "updated_at": modified_at, "snippet": snippet,
            }))

        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        try:
            bounded_limit = max(1, min(int(limit), _PROJECT_MEMORY_MAX_MATCHES))
        except (TypeError, ValueError, OverflowError):
            bounded_limit = _PROJECT_MEMORY_MAX_MATCHES
        return [row[2] for row in scored[:bounded_limit]]

    def save_memory(self, topic: str, content: str, category: str = "Geral") -> str | None:
        """Cria ou anexa uma nota markdown com timestamp na subpasta
        Zara-Memoria do cofre real. Devolve o caminho salvo, ou None se o
        cofre não estiver disponível (best-effort, nunca levanta)."""
        if not self.available:
            return None

        clean_topic = re.sub(r"[^\w\- ]+", "", str(topic or "").strip()) or "sem-titulo"
        safe_name = clean_topic.replace(" ", "_")[:80]
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n---\n**{timestamp}** ({category})\n\n{content}\n"

        try:
            folder = self.vault_path / _ZARA_SUBFOLDER
            folder.mkdir(parents=True, exist_ok=True)
            note_path = folder / f"{safe_name}.md"
            if note_path.exists():
                with note_path.open("a", encoding="utf-8") as handle:
                    handle.write(entry)
            else:
                frontmatter = (
                    f"---\ntitle: {clean_topic}\ncategory: {category}\n"
                    "fonte: Zara ObsidianMemoryManager\n---\n"
                )
                note_path.write_text(frontmatter + entry, encoding="utf-8")
            return str(note_path)
        except OSError:
            return None


def get_system_context(
    query: str,
    *,
    vault_path: Path | str | None = None,
    scan_dirs: tuple[Path, ...] | None = None,
) -> dict:
    """Cruza notas do cofre com nomes de arquivo/pasta do PC (Desktop,
    Documents, Downloads por padrão) que batem com a query. Correspondência
    textual simples, sem IA, sem recursão profunda (varredura rasa por
    desempenho e segurança)."""
    manager = ObsidianMemoryManager(vault_path=vault_path)
    notes = manager.search_notes(query)

    needle = str(query or "").strip().lower()
    dirs_to_scan = scan_dirs or (
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
    )
    file_matches: list[str] = []
    if needle:
        for directory in dirs_to_scan:
            if not Path(directory).is_dir():
                continue
            try:
                for entry in Path(directory).iterdir():
                    if needle in entry.name.lower():
                        file_matches.append(str(entry))
            except OSError:
                continue

    return {"notes": notes, "files": file_matches}
