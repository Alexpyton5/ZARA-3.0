from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from dataclasses import dataclass
from pathlib import Path

import pytest

from memory.shared_second_brain import SharedSecondBrain


def _real_project_memory_class():
    root = Path(r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002")
    sys.path.insert(0, str(root))
    try:
        spec = spec_from_file_location("zara_real_project_memory", root / "memory" / "project_memory.py")
        assert spec and spec.loader
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ProjectMemory
    finally:
        sys.path.remove(str(root))


class FakeUserMemory:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, fact: str, **metadata) -> None:
        self.rows.append({"id": f"user-{len(self.rows) + 1}", "fact": fact, **metadata})

    def search(self, _query: str, *, limit: int = 5) -> list[dict]:
        return self.rows[:limit]

    def list(self) -> list[dict]:
        return list(self.rows)


@dataclass(frozen=True)
class FakeLesson:
    id: str
    statement: str
    evidence_ref: str
    source_session_id: str
    created_at: float


class FakeLabStore:
    def __init__(self, lessons: list[FakeLesson]) -> None:
        self.lessons = lessons

    def list_lessons(self, limit: int = 100) -> list[FakeLesson]:
        return self.lessons[:limit]


class FakeProjectWorkspaceMemory:
    def __init__(self, events: list[dict]) -> None:
        self.events = events

    def search(self, _query: str, limit: int = 5) -> list[dict]:
        return self.events[:limit]


@pytest.fixture
def seeded_sources(tmp_path):
    user = FakeUserMemory()
    user.add(
        "Alex trabalha criando a assistente ZARA.",
        source="owner_confirmed",
        ref="conversation:work",
        status="confirmed",
        confidence=1.0,
        updated_at=1_790_000_001.0,
    )
    user.add(
        "O objetivo de Alex é tornar a ZARA uma assistente confiável.",
        source="owner_confirmed",
        ref="conversation:goals",
        status="confirmed",
        confidence=1.0,
        updated_at=1_790_000_002.0,
    )
    lab = FakeLabStore([
        FakeLesson(
            id="lesson:proof",
            statement="Só afirmar sucesso quando houver pós-condição observada.",
            evidence_ref="event:evidence:proof",
            source_session_id="session-zara",
            created_at=1_790_000_003.0,
        )
    ])
    projects = FakeProjectWorkspaceMemory([
        {
            "id": "project-event-1",
            "type": "project.updated",
            "path": "ZARA/ROADMAP.md",
            "timestamp": 1_790_000_004.0,
            "sha256": "a" * 64,
            "metadata": {"project": "ZARA", "status": "active"},
        }
    ])
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Trabalho.md").write_text(
        "# Trabalho\nAlex desenvolve a ZARA e pesquisa automação pessoal.", encoding="utf-8"
    )
    (vault / "Objetivos.md").write_text(
        "# Objetivos\nConstruir uma assistente confiável com memória compartilhada.", encoding="utf-8"
    )
    (vault / "Projetos.md").write_text(
        "# Projetos\nZARA é o projeto principal em andamento.", encoding="utf-8"
    )
    (vault / "Receitas.md").write_text("# Receitas\nBolo de cenoura.", encoding="utf-8")
    (vault / "api_keys.md").write_text("OPENAI_API_KEY=sk-super-secret", encoding="utf-8")
    return user, lab, projects, vault


def _brain(tmp_path: Path, seeded_sources, *, vault: Path | None = None) -> SharedSecondBrain:
    user, lab, projects, seeded_vault = seeded_sources
    return SharedSecondBrain(
        user_memory=user,
        lab_store=lab,
        project_workspace=projects,
        obsidian_vault=seeded_vault if vault is None else vault,
        obsidian_index_db=tmp_path / "project-memory" / "obsidian-index.db",
    )


@pytest.mark.parametrize(
    "question, expected_sources",
    [
        ("que trabalho Alex faz?", {"user_memory", "obsidian"}),
        ("quais são meus objetivos?", {"user_memory", "obsidian"}),
        ("em que projetos estou trabalhando?", {"project_memory", "obsidian"}),
        ("quando afirmar sucesso?", {"lab_lesson"}),
    ],
)
def test_shared_queries_are_deterministic_and_traceable(
    tmp_path, seeded_sources, question, expected_sources
):
    brain = _brain(tmp_path, seeded_sources)
    assert brain.sync_obsidian()["indexed"] == 4

    first = brain.query(question, budget_bytes=4096, limit=5)
    second = brain.query(question, budget_bytes=4096, limit=5)

    assert first == second
    assert expected_sources <= {item["source"] for item in first["items"]}
    assert all(set(item) == {"source", "provenance", "timestamp", "text"} for item in first["items"])
    assert all(item["provenance"] for item in first["items"])
    assert "Bolo de cenoura" not in json.dumps(first, ensure_ascii=False)
    assert "sk-super-secret" not in json.dumps(first, ensure_ascii=False)


def test_restart_returns_same_items_and_references(tmp_path, seeded_sources):
    brain = _brain(tmp_path, seeded_sources)
    brain.sync_obsidian()
    before = brain.query("projetos ZARA", limit=10)

    restarted = _brain(tmp_path, seeded_sources)
    after = restarted.query("projetos ZARA", limit=10)

    assert after["items"] == before["items"]


def test_sync_is_explicit_incremental_and_only_changed_markdown_is_reindexed(
    tmp_path, seeded_sources
):
    brain = _brain(tmp_path, seeded_sources)
    first = brain.sync_obsidian()
    second = brain.sync_obsidian()
    vault = seeded_sources[3]
    note = vault / "Projetos.md"
    time.sleep(0.01)
    note.write_text("# Projetos\nZARA e Atlas estão em andamento.", encoding="utf-8")
    os.utime(note, None)
    third = brain.sync_obsidian()

    assert first == {"indexed": 4, "unchanged": 0, "removed": 0, "excluded": 1, "degraded": False}
    assert second["indexed"] == 0 and second["unchanged"] == 4
    assert third["indexed"] == 1 and third["unchanged"] == 3

    with sqlite3.connect(brain.obsidian_index_db) as conn:
        row = conn.execute(
            "SELECT relative_path, size, mtime_ns, sha256, text FROM obsidian_notes WHERE relative_path=?",
            ("Projetos.md",),
        ).fetchone()
    assert row[0] == "Projetos.md"
    assert row[1] > 0 and row[2] > 0 and len(row[3]) == 64
    assert "Atlas" in row[4]


def test_sync_rehashes_same_size_and_same_mtime_content_change(tmp_path, seeded_sources):
    brain = _brain(tmp_path, seeded_sources)
    brain.sync_obsidian()
    note = seeded_sources[3] / "Projetos.md"
    original_stat = note.stat()
    original = note.read_text(encoding="utf-8")
    replacement = original.replace("principal", "essencial")
    assert len(replacement.encode("utf-8")) == len(original.encode("utf-8"))
    note.write_text(replacement, encoding="utf-8")
    os.utime(note, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    result = brain.sync_obsidian()

    assert result["indexed"] == 1
    items = brain.query("projetos essencial", limit=10)["items"]
    assert any(item["source"] == "obsidian" and "essencial" in item["text"] for item in items)


def test_query_respects_complete_serialized_byte_budget(tmp_path, seeded_sources):
    brain = _brain(tmp_path, seeded_sources)
    brain.sync_obsidian()

    context = brain.query("ZARA objetivos trabalho projetos", budget_bytes=420, limit=20)

    assert len(json.dumps(context, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 420
    assert context["omitted"] > 0


def test_unavailable_vault_keeps_cached_results_and_marks_degraded(tmp_path, seeded_sources):
    brain = _brain(tmp_path, seeded_sources)
    brain.sync_obsidian()
    cached = brain.query("projetos ZARA", limit=10)
    vault = seeded_sources[3]
    unavailable = vault.with_name("disconnected-vault")
    vault.rename(unavailable)

    restarted = SharedSecondBrain(
        user_memory=seeded_sources[0],
        lab_store=seeded_sources[1],
        project_workspace=seeded_sources[2],
        obsidian_vault=vault,
        obsidian_index_db=brain.obsidian_index_db,
    )
    sync = restarted.sync_obsidian()
    result = restarted.query("projetos ZARA", limit=10)

    assert sync["degraded"] is True
    assert result["items"] == cached["items"]
    assert "obsidian_unavailable" in result["degraded"]


def test_private_reasoning_and_secret_named_or_secret_content_notes_are_never_persisted(
    tmp_path, seeded_sources
):
    vault = seeded_sources[3]
    (vault / "credentials.md").write_text("login admin password hunter2", encoding="utf-8")
    (vault / "thinking.md").write_text(
        "private chain of thought: hidden reasoning about Alex", encoding="utf-8"
    )
    brain = _brain(tmp_path, seeded_sources)

    brain.sync_obsidian()

    with sqlite3.connect(brain.obsidian_index_db) as conn:
        paths = {row[0] for row in conn.execute("SELECT relative_path FROM obsidian_notes")}
    assert "credentials.md" not in paths
    assert "thinking.md" not in paths


def test_project_provider_exposes_metadata_only_and_never_private_content(tmp_path, seeded_sources):
    seeded_sources[2].events[0]["content"] = "private implementation detail"
    brain = _brain(tmp_path, seeded_sources)

    result = brain.query("projetos ZARA", limit=10)
    project_item = next(item for item in result["items"] if item["source"] == "project_memory")

    assert "private implementation detail" not in json.dumps(project_item)
    assert "project-event-1" in project_item["provenance"]
    assert "ZARA/ROADMAP.md" in project_item["text"]


def test_real_project_memory_recent_events_shape_is_factual_and_cache_only(tmp_path, seeded_sources):
    ProjectMemory = _real_project_memory_class()
    project_memory = ProjectMemory(base_dir=tmp_path / "actual-project-memory")
    project_memory.record_mentor_event(
        "shared-brain", "passed", "Summary from the Project Memory event"
    )
    brain = SharedSecondBrain(
        user_memory=seeded_sources[0],
        lab_store=seeded_sources[1],
        project_workspace=project_memory,
        obsidian_vault=seeded_sources[3],
        obsidian_index_db=tmp_path / "injected-cache" / "obsidian-index.db",
    )

    result = brain.query("project memory summary", limit=10)
    item = next(item for item in result["items"] if item["source"] == "project_memory")

    assert "task=shared-brain" in item["text"]
    assert "status=passed" in item["text"]
    assert "Summary from the Project Memory event" in item["text"]
    assert item["provenance"].startswith("event:")


@pytest.mark.parametrize("field,value", [
    ("source", "Bearer top-secret-token"),
    ("ref", "credentials/private"),
])
def test_user_provenance_never_leaks_sensitive_fields(tmp_path, seeded_sources, field, value):
    seeded_sources[0].rows[0][field] = value
    result = _brain(tmp_path, seeded_sources).query("trabalho ZARA", limit=10)
    assert value not in json.dumps(result, ensure_ascii=False)


def test_lesson_and_project_fields_never_leak_sensitive_values(tmp_path, seeded_sources):
    seeded_sources[1].lessons = [FakeLesson(
        "lesson:private", "Sucesso exige prova observada.", "Bearer token-12345678", "session-zara", 1.0
    )]
    seeded_sources[2].events = [{
        "id": "event-1", "ts": 2.0, "task_id": "secret/project", "status": "passed",
        "summary": "Authorization: secret-value",
    }]
    result = _brain(tmp_path, seeded_sources).query("sucesso prova authorization", limit=10)
    rendered = json.dumps(result, ensure_ascii=False)
    assert "Bearer token-12345678" not in rendered
    assert "secret/project" not in rendered
    assert "Authorization: secret-value" not in rendered


def test_facade_ranks_user_memory_itself_when_legacy_search_misses_inflection(
    tmp_path, seeded_sources
):
    seeded_sources[0].search = lambda _query, *, limit=5: []
    brain = _brain(tmp_path, seeded_sources)

    result = brain.query("quais são meus objetivos?", limit=5)

    assert any(item["source"] == "user_memory" for item in result["items"])

