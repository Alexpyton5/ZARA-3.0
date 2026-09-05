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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from memory.project_memory import _detect_real_obsidian_vault

_ZARA_SUBFOLDER = "Zara-Memoria"
_SNIPPET_RADIUS_CHARS = 120


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
        return self.vault_path is not None and self.vault_path.is_dir()

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
