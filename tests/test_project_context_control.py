from __future__ import annotations

import json

import pytest

from memory.project_memory import ProjectContextError, ProjectMemory


def test_active_project_is_persisted_and_context_is_isolated(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    memory.save_project_doc("zara", "state", "Estado", "somente-zara")
    memory.save_project_doc("outro", "state", "Estado", "segredo-outro-projeto")

    assert memory.activate_project("ZARA") == "zara"
    envelope = memory.build_project_context(keys=("state",), budget_bytes=700)
    payload = json.loads(envelope.to_json())

    assert payload["items"][0]["key"] == "project_id"
    assert payload["items"][0]["value"] == "zara"
    assert "somente-zara" in envelope.to_json()
    assert "segredo-outro-projeto" not in envelope.to_json()
    assert ProjectMemory(base_dir=tmp_path).get_active_project() == "zara"


def test_explicit_project_does_not_mutate_active_selection(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    memory.save_project_doc("zara", "state", "Estado", "zara")
    memory.save_project_doc("outro", "state", "Estado", "outro")
    memory.activate_project("zara")

    envelope = memory.build_project_context("outro", keys=("state",), budget_bytes=700)

    assert envelope.items[0].value == "outro"
    assert memory.get_active_project() == "zara"


def test_budget_keeps_required_project_id_and_reports_omitted_doc(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    memory.save_project_doc("zara", "state", "Estado", "x" * 2_000)
    memory.activate_project("zara")

    envelope = memory.build_project_context(budget_bytes=260)

    assert envelope.used_bytes <= 260
    assert [(item.key, item.value) for item in envelope.items] == [("project_id", "zara")]
    assert [item.key for item in envelope.omitted] == ["project_doc:state"]
    assert envelope.degraded is True


def test_unknown_project_or_requested_doc_fails_closed(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    with pytest.raises(ProjectContextError, match="nenhum projeto ativo"):
        memory.build_project_context()
    with pytest.raises(ProjectContextError, match="sem documentos"):
        memory.activate_project("nao-existe")

    memory.save_project_doc("zara", "state", "Estado", "ok")
    with pytest.raises(ProjectContextError, match="documentos ausentes: roadmap"):
        memory.build_project_context("zara", keys=("roadmap",))


def test_project_and_document_ids_reject_path_traversal(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)

    with pytest.raises(ProjectContextError, match="project_id invalido"):
        memory.save_project_doc("../zara", "state", "Estado", "x")
    with pytest.raises(ProjectContextError, match="key invalido"):
        memory.save_project_doc("zara", "../state", "Estado", "x")

    assert not (tmp_path.parent / "zara").exists()


def test_project_inventory_is_deterministic_and_scoped(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    memory.save_project_doc("zeta", "roadmap", "Roadmap", "Z")
    memory.save_project_doc("alpha", "state", "Estado", "A")
    memory.save_project_doc("alpha", "architecture", "Arquitetura", "B")

    assert memory.list_projects() == ["alpha", "zeta"]
    assert memory.list_project_docs("alpha") == ["architecture", "state"]
    assert memory.get_project_doc("zeta", "roadmap")["content"] == "Z"
    assert memory.get_project_doc("zeta", "state") is None


def test_legacy_api_closes_sqlite_handles_on_windows(tmp_path) -> None:
    memory = ProjectMemory(base_dir=tmp_path)
    memory.save_doc("decisions", "Decisoes", "conteudo")

    assert memory.get_doc("decisions")["content"] == "conteudo"
    assert memory.list_docs() == ["decisions"]

    moved = tmp_path / "project_memory.moved.db"
    memory.db_path.rename(moved)
    moved.rename(memory.db_path)
