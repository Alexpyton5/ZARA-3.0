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

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from memory.project_memory import _canonical_obsidian_vault, _resolve_obsidian_vault

_ZARA_SUBFOLDER = "Zara-Memoria"
_SNIPPET_RADIUS_CHARS = 120
_MAX_STATUS_NOTE_BYTES = 1_048_576
_SECRET_PATH_PARTS = re.compile(
    r"(?:^|[._-])(?:\.env|api[_-]?keys?|credentials?|tokens?|keys?|secrets?)(?:$|[._-])",
    re.IGNORECASE,
)
_SECRET_CONTENT = re.compile(
    r"(?:api[_-]?key|client[_-]?secret|password|passwd|credential|access[_-]?token|"
    r"(?:token|secret|senha)\s*[:=]|"
    r"authorization\s*[:=]|bearer\s+[a-z0-9._-]{8,}|"
    r"(?:sk|gsk|nvapi)[_-][a-z0-9_-]{8,}|-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"(?:chain[-_ ]?of[-_ ]?thought|private[-_ ]?(?:reasoning|thought)|"
    r"racioc[ií]nio\s+(?:privado|interno)))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NoteMatch:
    title: str
    path: str
    snippet: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Result of one reconciliable ZARA -> Obsidian projection."""

    status: str
    path: str | None = None
    identity: str | None = None
    conflict_path: str | None = None


class ObsidianMemoryManager:
    """Aponta pro cofre real do Obsidian: `vault_path` explícito (testes) >
    cadeia robusta `_resolve_obsidian_vault` (env > obsidian.json > varredura de perfis). Detecção real via obsidian.json."""

    def __init__(self, vault_path: Path | str | None = None):
        if vault_path is not None:
            self.vault_path: Path | None = _canonical_obsidian_vault(vault_path)
        else:
            # SUPERCREBRO-2026-09-29: cadeia robusta (env > obsidian.json do
            # usuario atual > varredura de C:/Users/*). O app roda como zoe;
            # sem isso o vault do Alex nunca era achado e o cerebro
            # compartilhado ficava em modo degradado.
            self.vault_path = _resolve_obsidian_vault()

    @property
    def available(self) -> bool:
        return self.vault_path is not None and self.vault_path.is_dir()

    @staticmethod
    def _utc_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @classmethod
    def _sensitive(cls, text: str) -> bool:
        from memory.second_brain_composition import is_safe_text
        from memory.shared_second_brain import SharedSecondBrain
        value = str(text or "")
        return bool(_SECRET_CONTENT.search(value) or SharedSecondBrain._sensitive(value)
                    or not is_safe_text(value))

    @staticmethod
    def _secret_path(relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        return any(_SECRET_PATH_PARTS.search(part) for part in normalized.split("/"))

    def _safe_note_paths(self):
        """Yield only readable, non-sensitive Markdown notes from the real vault.

        This is deliberately derived from the vault on demand.  It does not
        create an index or persist a second inventory of the owner's notes.
        """
        if not self.available:
            return
        assert self.vault_path is not None
        try:
            paths = self.vault_path.rglob("*.md")
            for md_path in paths:
                try:
                    relative = md_path.relative_to(self.vault_path).as_posix()
                    if self._secret_path(relative):
                        continue
                    raw = md_path.read_bytes()
                    if len(raw) > _MAX_STATUS_NOTE_BYTES:
                        continue
                    if self._sensitive(raw.decode("utf-8", errors="ignore")):
                        continue
                except (OSError, ValueError):
                    continue
                yield md_path
        except OSError:
            return

    def count_notes(self) -> int:
        """Count currently verifiable, safe Markdown notes in the real vault."""
        return sum(1 for _ in self._safe_note_paths())

    def get_vault_status(self) -> dict[str, object]:
        """Return a live, non-secret status snapshot of the real vault.

        ``last_sync`` is intentionally in-memory only: it records the last
        explicit status refresh/synchronization attempt, never a note body,
        path, credential, or alternate source of truth.
        """
        available = self.available
        note_count = self.count_notes() if available else 0
        degraded = not available
        last_sync = getattr(self, "_last_sync", None)
        return {
            "status": "available" if available else "unavailable",
            "available": available,
            "note_count": note_count,
            "last_sync": last_sync,
            "degraded": degraded,
        }

    def vault_status(self) -> dict[str, object]:
        """Compatibility alias for callers that use the domain name."""
        return self.get_vault_status()

    def status(self) -> dict[str, object]:
        """Short alias used by health/status consumers."""
        return self.get_vault_status()

    def mark_synchronized(self, timestamp: str | None = None) -> dict[str, object]:
        """Record an explicit sync attempt without persisting derived state."""
        self._last_sync = timestamp or self._utc_timestamp()
        return self.get_vault_status()

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
        for md_path in self._safe_note_paths():
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

    def save_memory(self, topic: str, content: str, category: str = "Geral") -> str | None:
        """Cria ou anexa uma nota markdown com timestamp na subpasta
        Zara-Memoria do cofre real. Devolve o caminho salvo, ou None se o
        cofre não estiver disponível (best-effort, nunca levanta)."""
        if not self.available:
            return None

        if any(self._sensitive(value) for value in (topic, content, category)):
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

    # ------------------------------------------------------------------
    # Durable, identity-based Lab projection
    # ------------------------------------------------------------------
    @staticmethod
    def _sync_identity(identity: str) -> str:
        return str(identity or "").strip()

    @staticmethod
    def _sync_hash(identity: str, title: str, content: str, category: str) -> str:
        import hashlib
        payload = "\n".join((identity, title, category, content))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _frontmatter(text: str) -> dict[str, str]:
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---", 4)
        if end < 0:
            return {}
        result: dict[str, str] = {}
        for line in text[4:end].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _sync_body(title: str, content: str, category: str, identity: str, digest: str) -> str:
        return (
            "---\n"
            f"title: {title}\n"
            f"category: {category}\n"
            f"zara_sync_identity: {identity}\n"
            f"zara_sync_hash: {digest}\n"
            "fonte: ZARA\n"
            "---\n\n"
            f"{content}\n"
        )

    def _sync_note_candidates(self, identity: str):
        folder = self.vault_path / _ZARA_SUBFOLDER  # type: ignore[operator]
        if not folder.is_dir():
            return []
        candidates = []
        for path in folder.glob("*.md"):
            # Conflict artifacts are projections, never canonical identities.
            if path.name.endswith(".conflict.md"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            meta = self._frontmatter(text)
            if meta.get("zara_sync_identity") == identity:
                candidates.append((path, text, meta))
        return candidates

    def sync_memory(self, identity: str, topic: str, content: str,
                    *, category: str = "Lab") -> SyncResult:
        """Reconcile one canonical fact without overwriting human edits."""
        identity = self._sync_identity(identity)
        title = str(topic or "").strip() or "Memoria Zara"
        body = str(content or "").strip()
        category = str(category or "Geral").strip() or "Geral"
        if not identity or any(self._sensitive(v) for v in (identity, title, body, category)):
            return SyncResult("unavailable", identity=identity or None)
        if not self.available:
            return SyncResult("unavailable", identity=identity)
        try:
            folder = self.vault_path / _ZARA_SUBFOLDER  # type: ignore[operator]
            folder.mkdir(parents=True, exist_ok=True)
            digest = self._sync_hash(identity, title, body, category)
            canonical = self._sync_body(title, body, category, identity, digest)
            candidates = self._sync_note_candidates(identity)
            if candidates:
                path, existing, meta = candidates[0]
            else:
                import hashlib
                suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
                safe = re.sub(r"[^\w-]+", "-", title, flags=re.UNICODE).strip("-")[:60] or "memoria"
                path = folder / f"{safe}-{suffix}.md"
                # Reuse an older topic-hash filename if it contains the same
                # identity marker, even when the title changed.
                existing = ""
                meta = {}
                for candidate in folder.glob("*.md"):
                    if candidate.name.endswith(".conflict.md"):
                        continue
                    try:
                        candidate_text = candidate.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    candidate_meta = self._frontmatter(candidate_text)
                    if (candidate_meta.get("zara_sync_identity") == identity
                            or candidate.stem.endswith(f"-{suffix}")):
                        path, existing, meta = candidate, candidate_text, self._frontmatter(candidate_text)
                        break
            if not existing:
                path.write_text(canonical, encoding="utf-8")
                return SyncResult("written", str(path), identity)
            if existing == canonical:
                return SyncResult("unchanged", str(path), identity)

            # A canonical note can be updated when its prior hash still
            # validates the stored identity/title/category/body.  This covers
            # topic/category changes without mistaking a human metadata edit
            # for a machine-owned note.
            header_match = re.match(r"^---\n.*?\n---\n", existing, flags=re.DOTALL)
            old_body_raw = existing[header_match.end():] if header_match else existing
            old_body_raw = old_body_raw.lstrip("\n")
            old_body = old_body_raw[:-1] if old_body_raw.endswith("\n") else old_body_raw
            old_title = meta.get("title", "")
            old_category = meta.get("category", "")
            old_identity = meta.get("zara_sync_identity", "")
            old_hash = meta.get("zara_sync_hash", "")
            prior_is_canonical = bool(old_hash) and old_hash == self._sync_hash(
                old_identity, old_title, old_body, old_category
            )
            if prior_is_canonical and old_identity == identity:
                path.write_text(canonical, encoding="utf-8")
                return SyncResult("written", str(path), identity)
            # Any unrecognised change means a human touched the note. Preserve
            # it and place the new canonical projection in a traceable sibling.
            conflict_path = path.with_suffix(".conflict.md")
            human_tail = ""
            if conflict_path.exists():
                old_conflict = conflict_path.read_text(encoding="utf-8")
                marker = "\n# Human notes\n"
                if marker in old_conflict:
                    human_tail = old_conflict.split(marker, 1)[1].strip()
                else:
                    # New conflict artifacts delimit the machine projection;
                    # anything after it is a human addition.  Keep support
                    # for older artifacts by treating their body as human
                    # only when it is not the stored projection.
                    projection_marker = "\n# Canonical projection\n"
                    if projection_marker in old_conflict:
                        tail = old_conflict.split(projection_marker, 1)[1]
                        if "\n# Human notes\n" in tail:
                            human_tail = tail.split("\n# Human notes\n", 1)[1].strip()
                        elif "\n\n" in tail:
                            human_tail = tail.split("\n\n", 1)[1].strip()
                    else:
                        old_conflict_body = old_conflict.split("\n---\n", 1)[-1].strip()
                        if old_conflict_body and old_conflict_body != body:
                            human_tail = old_conflict_body
            conflict = canonical.replace("zara_sync_hash: ", "zara_sync_hash: ", 1)
            conflict = conflict.replace("fonte: ZARA\n", "fonte: ZARA\nzara_conflict: true\n", 1)
            conflict += f"\n# Canonical projection\n{body}\n"
            if human_tail:
                conflict += f"\n# Human notes\n{human_tail}\n"
            # A preserved human tail can itself contain a credential.
            if self._sensitive(conflict):
                return SyncResult("unavailable", identity=identity)
            conflict_path.write_text(conflict, encoding="utf-8")
            return SyncResult("conflict", str(path), identity, str(conflict_path))
        except OSError:
            return SyncResult("unavailable", identity=identity)

    def sync_handoff(self, handoff, mission: str) -> SyncResult:
        artifact = str(getattr(handoff, "artifact_ref", "") or "").strip()
        identity = f"handoff:{artifact}" if artifact else "handoff:unknown"
        evidence = ", ".join(str(item) for item in (getattr(handoff, "evidence_refs", ()) or ()))
        provenance = getattr(handoff, "provenance", {}) or {}
        content = (
            f"Mission: {mission}\n"
            f"Stage: {getattr(handoff, 'stage', '')}\n"
            f"Artifact: {artifact}\n"
            f"Evidence: {evidence}\n"
            f"Provenance: {provenance}\n"
        )
        return self.sync_memory(identity, mission, content, category="Handoff")


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
