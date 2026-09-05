r"""
ZARA Project Memory (ZARA-PROJECT-MEMORY-001).

Memoria DO PROJETO (separada da User Memory): historia da ZARA que nao
depende da conversa do ChatGPT. Persiste Mentor Charter, Architecture,
Decisions, Current State, Roadmap.

Layout (spec do Mentor):
  %LOCALAPPDATA%\ZARA3\data\project-memory\
      project_memory.db
      mentor_context_latest.md
      vault\          (arquivos markdown do projeto)
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from core.paths import user_data_dir


def _detect_real_obsidian_vault() -> Path | None:
    """Read Obsidian's own config to find Alex's real vault, instead of
    guessing a path. Returns None if Obsidian was never opened or the
    config is unreadable — callers must treat that as "no mirror available",
    never as an error."""
    config_path = Path.home() / "AppData" / "Roaming" / "obsidian" / "obsidian.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        vaults = data.get("vaults", {})
        if not vaults:
            return None
        most_recent = max(vaults.values(), key=lambda v: v.get("ts", 0))
        vault_path = Path(most_recent["path"])
        return vault_path if vault_path.is_dir() else None
    except Exception:
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_docs (
    key TEXT PRIMARY KEY,          -- charter | architecture | decisions | state | roadmap
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mentor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS project_context_docs (
    project_id TEXT NOT NULL,
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (project_id, key)
);
CREATE TABLE IF NOT EXISTS project_context_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_project_id TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

_SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_CONTEXT_PRIORITY = {
    "state": 900,
    "decisions": 800,
    "architecture": 700,
    "roadmap": 600,
    "charter": 500,
}


class ContextDatum:
    """Um item candidato ao envelope de contexto do projeto.

    ZARA-CONTEXT-BUDGET-001: `build_project_context` referenciava esta
    classe e `build_context_envelope` sem nenhuma das duas existir em
    lugar nenhum do projeto -- `NameError` garantido em qualquer chamada
    real. Reconstruído a partir do contrato exato definido pelos testes em
    tests/test_project_context_control.py (nenhuma suposição além do que
    os testes já provam).
    """

    __slots__ = ("key", "value", "priority", "required")

    def __init__(self, key: str, value, *, priority: int = 0, required: bool = False):
        self.key = key
        self.value = value
        self.priority = priority
        self.required = required

    def _encoded_size(self) -> int:
        return len(json.dumps({"key": self.key, "value": self.value}, ensure_ascii=False).encode("utf-8"))


class ContextEnvelope:
    """Resultado de `build_context_envelope`: o que coube no orçamento de bytes."""

    __slots__ = ("items", "omitted", "used_bytes", "degraded")

    def __init__(self, items: list[ContextDatum], omitted: list[ContextDatum], used_bytes: int, degraded: bool):
        self.items = items
        self.omitted = omitted
        self.used_bytes = used_bytes
        self.degraded = degraded

    def to_json(self) -> str:
        return json.dumps(
            {
                "items": [{"key": item.key, "value": item.value} for item in self.items],
                "omitted": [{"key": item.key} for item in self.omitted],
                "used_bytes": self.used_bytes,
                "degraded": self.degraded,
            },
            ensure_ascii=False,
        )


def build_context_envelope(*, memory: tuple[ContextDatum, ...], budget_bytes: int) -> ContextEnvelope:
    """Ordena por (obrigatório primeiro, depois prioridade decrescente) e
    inclui greedily até o orçamento. Itens `required=True` sempre entram,
    mesmo que estourem o orçamento sozinhos -- omitir o project_id, por
    exemplo, tornaria o envelope inútil independente do tamanho.
    """
    ordered = sorted(memory, key=lambda datum: (not datum.required, -datum.priority))
    items: list[ContextDatum] = []
    omitted: list[ContextDatum] = []
    used_bytes = 0
    for datum in ordered:
        size = datum._encoded_size()
        if datum.required or used_bytes + size <= budget_bytes:
            items.append(datum)
            used_bytes += size
        else:
            omitted.append(datum)
    return ContextEnvelope(items=items, omitted=omitted, used_bytes=used_bytes, degraded=bool(omitted))


class ProjectContextError(ValueError):
    """Selecao ou identificador de projeto invalido ou incompleto."""


def _normalize_id(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise ProjectContextError(f"{label} precisa ser texto")
    normalized = value.strip().casefold()
    if not _SAFE_ID.fullmatch(normalized):
        raise ProjectContextError(
            f"{label} invalido: use 1-64 caracteres ASCII alfanumericos, ponto, hifen ou sublinhado"
        )
    return normalized


class ProjectMemory:
    def __init__(self, base_dir: Path | None = None, obsidian_vault_dir: Path | None = None):
        self.base_dir = base_dir or (user_data_dir() / "data" / "project-memory")
        self.db_path = self.base_dir / "project_memory.db"
        self.vault_dir = self.base_dir / "vault"
        self.context_file = self.base_dir / "mentor_context_latest.md"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        # ZARA-OBSIDIAN-REAL-2026-08-27: espelha a memoria do projeto no cofre
        # real do Obsidian do Alex (achado em obsidian.json), numa subpasta
        # dedicada pra nao se misturar com o resto do que tem la. Melhor
        # esforco: se o cofre nao existir (HD externo desconectado, cofre
        # mudou de lugar), a memoria interna da Zara continua funcionando
        # normalmente, so o espelho fica pra tras.
        self.obsidian_vault_dir = obsidian_vault_dir or _detect_real_obsidian_vault()
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # ---- documentos do projeto ----

    def save_doc(self, key: str, title: str, content: str) -> None:
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO project_docs (key, title, content, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET title=excluded.title, "
                "content=excluded.content, updated_at=excluded.updated_at",
                (key, title, content, now),
            )
            conn.commit()
        # espelha no vault (markdown legivel)
        safe = key.replace(" ", "_")
        (self.vault_dir / f"{safe}.md").write_text(content, encoding="utf-8")
        self._mirror_to_obsidian(safe, title, content)

    def _mirror_to_obsidian(self, safe_key: str, title: str, content: str) -> None:
        """Best-effort mirror to Alex's real Obsidian vault. Never raises —
        a missing/disconnected vault must not break Zara's own memory."""
        if self.obsidian_vault_dir is None:
            return
        try:
            zara_folder = self.obsidian_vault_dir / "Zara-Memoria"
            zara_folder.mkdir(parents=True, exist_ok=True)
            frontmatter = f"---\ntitle: {title}\nfonte: memoria de projeto da Zara\n---\n\n"
            (zara_folder / f"{safe_key}.md").write_text(frontmatter + content, encoding="utf-8")
        except OSError:
            pass

    def append_decision(self, decision: str) -> None:
        """Append a decision to the project decisions log."""
        current = self.get_doc("decisions")
        if current is None:
            new_content = "# Diário de Decisões do Projeto\n\n"
        else:
            new_content = current["content"]
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        new_content += f"- [{timestamp}] {decision}\n"
        self.save_doc("decisions", "Diário de Decisões do Projeto", new_content)

    def get_doc(self, key: str) -> dict | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM project_docs WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def list_docs(self) -> list[str]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute("SELECT key FROM project_docs").fetchall()
        return [r["key"] for r in rows]

    # ---- contexto isolado por projeto ----

    def save_project_doc(self, project_id: str, key: str, title: str, content: str) -> None:
        """Persiste um documento no escopo de um projeto, sem tocar no legado global."""
        project = _normalize_id(project_id, label="project_id")
        doc_key = _normalize_id(key, label="key")
        if not isinstance(title, str) or not title.strip():
            raise ProjectContextError("title precisa ser texto nao vazio")
        if not isinstance(content, str):
            raise ProjectContextError("content precisa ser texto")
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO project_context_docs "
                "(project_id, key, title, content, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(project_id, key) DO UPDATE SET "
                "title=excluded.title, content=excluded.content, updated_at=excluded.updated_at",
                (project, doc_key, title.strip(), content, now),
            )
            conn.commit()
            project_vault = self.vault_dir / "projects" / project
            project_vault.mkdir(parents=True, exist_ok=True)
            (project_vault / f"{doc_key}.md").write_text(content, encoding="utf-8")

    def get_project_doc(self, project_id: str, key: str) -> dict | None:
        project = _normalize_id(project_id, label="project_id")
        doc_key = _normalize_id(key, label="key")
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT project_id, key, title, content, updated_at "
                "FROM project_context_docs WHERE project_id=? AND key=?",
                (project, doc_key),
            ).fetchone()
        return dict(row) if row else None

    def list_project_docs(self, project_id: str) -> list[str]:
        project = _normalize_id(project_id, label="project_id")
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT key FROM project_context_docs WHERE project_id=? ORDER BY key",
                (project,),
            ).fetchall()
        return [row["key"] for row in rows]

    def list_projects(self) -> list[str]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT DISTINCT project_id FROM project_context_docs ORDER BY project_id"
            ).fetchall()
        return [row["project_id"] for row in rows]

    def activate_project(self, project_id: str) -> str:
        """Seleciona um projeto existente; erro de digitacao nao cria contexto vazio."""
        project = _normalize_id(project_id, label="project_id")
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM project_context_docs WHERE project_id=? LIMIT 1",
                (project,),
            ).fetchone()
            if not exists:
                raise ProjectContextError(f"projeto sem documentos: {project}")
            conn.execute(
                "INSERT INTO project_context_state (id, active_project_id, updated_at) "
                "VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "active_project_id=excluded.active_project_id, updated_at=excluded.updated_at",
                (project, now),
            )
            conn.commit()
        return project

    def get_active_project(self) -> str | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT active_project_id FROM project_context_state WHERE id=1"
            ).fetchone()
        return str(row["active_project_id"]) if row else None

    def build_project_context(
        self,
        project_id: str | None = None,
        *,
        keys: tuple[str, ...] | None = None,
        budget_bytes: int = 4096,
    ) -> ContextEnvelope:
        """Monta contexto limitado contendo somente documentos de um projeto.

        Sem ``project_id`` explicito, usa o projeto ativo persistido. A selecao
        explicita nao altera o ativo. Chaves solicitadas que nao existem falham
        fechadas, evitando um prompt parcial apresentado como completo.
        """
        selected = (
            _normalize_id(project_id, label="project_id")
            if project_id is not None
            else self.get_active_project()
        )
        if selected is None:
            raise ProjectContextError("nenhum projeto ativo")

        requested: tuple[str, ...] | None = None
        if keys is not None:
            requested = tuple(_normalize_id(key, label="key") for key in keys)
            if len(set(requested)) != len(requested):
                raise ProjectContextError("keys contem duplicatas")

        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT key, title, content FROM project_context_docs "
                "WHERE project_id=? ORDER BY key",
                (selected,),
            ).fetchall()
        documents = {row["key"]: row for row in rows}
        if not documents:
            raise ProjectContextError(f"projeto sem documentos: {selected}")
        ordered_keys = requested if requested is not None else tuple(sorted(documents))
        missing = [key for key in ordered_keys if key not in documents]
        if missing:
            raise ProjectContextError("documentos ausentes: " + ", ".join(missing))

        data = [ContextDatum("project_id", selected, priority=1000, required=True)]
        for index, key in enumerate(ordered_keys):
            row = documents[key]
            priority = _CONTEXT_PRIORITY.get(key, 100 - index)
            data.append(
                ContextDatum(
                    f"project_doc:{key}",
                    {"title": row["title"], "content": row["content"]},
                    priority=priority,
                )
            )
        return build_context_envelope(memory=tuple(data), budget_bytes=budget_bytes)

    # ---- contexto do mentor ----

    def save_mentor_context(self, content: str) -> None:
        """Escreve mentor_context_latest.md (fonte da verdade para o proximo turno)."""
        self.context_file.write_text(content, encoding="utf-8")

    def load_mentor_context(self) -> str:
        if self.context_file.exists():
            return self.context_file.read_text(encoding="utf-8")
        return ""

    # ---- eventos do mentor ----

    def record_mentor_event(self, task_id: str, status: str, summary: str = "") -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO mentor_events (ts, task_id, status, summary) VALUES (?,?,?,?)",
                (time.time(), task_id[:64], status[:16], summary[:500]),
            )
            conn.commit()

    def recent_events(self, limit: int = 20) -> list[dict]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM mentor_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def create_project_memory(base_dir: Path | None = None) -> ProjectMemory:
    return ProjectMemory(base_dir=base_dir)
