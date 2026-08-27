from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from brain.store import (
    BrainStore,
    Citation,
    Compartment,
    default_source_vaults,
    preview_import,
)


def write_note(vault: Path, relative: str, content: str) -> Path:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_default_sources_cover_the_three_existing_vaults():
    sources = default_source_vaults()
    assert set(sources) == {
        "obsidian_legacy",
        "zara3_obsidian_bridge",
        "zara3_project_memory",
    }


def test_compartment_enum():
    assert Compartment.MEMORY.value == "memory"
    assert Compartment.KNOWLEDGE.value == "knowledge"
    assert Compartment.SKILL.value == "skill"
    assert Compartment.MEMORY.display_name == "MEMORY"
    assert Compartment.KNOWLEDGE.display_name == "KNOWLEDGE"
    assert Compartment.SKILL.display_name == "SKILL"


def test_ingestion_note_index_search_and_citation(tmp_path):
    source = tmp_path / "source"
    original = write_note(
        source,
        "projects/zara.md",
        "# Projeto ZARA\n\nA decisão foi manter a memória local e citável.",
    )
    brain = BrainStore(tmp_path / "brain")

    report = brain.import_vault(source, "project_memory", Compartment.MEMORY)

    assert report.imported == 1
    assert report.compartment == "memory"
    assert original.exists(), "import must never move or delete the source"
    hits = brain.search("memória local", compartment=Compartment.MEMORY)
    assert len(hits) == 1
    citation = hits[0]
    assert citation.title == "Projeto ZARA"
    assert citation.source_label == "project_memory"
    assert citation.source_path == "projects/zara.md"
    assert "memória local" in citation.excerpt
    assert citation.compartment == "memory"
    canonical = brain.root / "vault" / "memory" / citation.note_path
    assert canonical.read_bytes() == original.read_bytes()
    assert citation.sha256 == hashlib.sha256(original.read_bytes()).hexdigest()


def test_search_ranks_by_relevance_not_alphabetically_by_excerpt(tmp_path):
    """AUDITORIA_2026-08-27 item 2.2: o merge entre compartimentos resortia o
    resultado alfabeticamente pelo texto do trecho, jogando fora o bm25 real
    que o SQL ja tinha calculado. Os titulos/conteudo abaixo sao escolhidos de
    proposito para que a ordem alfabetica do trecho seja o OPOSTO da ordem de
    relevancia real, entao o teste so passa com o bm25 de verdade em uso.
    """
    source = tmp_path / "source"
    write_note(
        source,
        "aardvark.md",
        "# Aardvark\n\nEste documento cita framboesa uma unica vez, de passagem.",
    )
    write_note(
        source,
        "zebra.md",
        "# Zebra\n\nframboesa framboesa framboesa framboesa é o assunto inteiro deste texto.",
    )
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "project_memory", Compartment.MEMORY)

    hits = brain.search("framboesa", compartment=Compartment.MEMORY)

    assert [c.title for c in hits] == ["Zebra", "Aardvark"], (
        "resultado mais relevante (mais ocorrencias) tem de vir primeiro, "
        "nao o que vem primeiro em ordem alfabetica de trecho"
    )


def test_knowledge_compartment_import(tmp_path):
    source = tmp_path / "source"
    original = write_note(
        source,
        "articles/llm.md",
        "# LLMs\n\nEste artigo explica como funcionam os modelos de linguagem.",
    )
    brain = BrainStore(tmp_path / "brain")

    report = brain.import_vault(source, "articles", Compartment.KNOWLEDGE)

    assert report.imported == 1
    assert report.compartment == "knowledge"
    hits = brain.search("modelos de linguagem", compartment=Compartment.KNOWLEDGE)
    assert len(hits) == 1
    assert hits[0].compartment == "knowledge"
    canonical = brain.root / "vault" / "knowledge" / hits[0].note_path
    assert canonical.read_bytes() == original.read_bytes()


def test_skill_compartment_import(tmp_path):
    source = tmp_path / "source"
    original = write_note(
        source,
        "skills/deploy.md",
        "# Como fazer deploy\n\nPasso 1: Build o projeto.\nPasso 2: Rode os testes.\nPasso 3: Deploy para produção.",
    )
    brain = BrainStore(tmp_path / "brain")

    report = brain.import_vault(source, "deploy_skill", Compartment.SKILL)

    assert report.imported == 1
    assert report.compartment == "skill"
    hits = brain.search("deploy produção", compartment=Compartment.SKILL)
    assert len(hits) == 1
    assert hits[0].compartment == "skill"
    canonical = brain.root / "vault" / "skill" / hits[0].note_path
    assert canonical.read_bytes() == original.read_bytes()


def test_dedup_keeps_one_note_and_two_provenances(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    content = "# Mesma decisão\n\nNão duplicar conteúdo idêntico."
    write_note(a, "one.md", content)
    write_note(b, "nested/two.md", content)
    brain = BrainStore(tmp_path / "brain")

    first = brain.import_vault(a, "vault_a", Compartment.MEMORY)
    second = brain.import_vault(b, "vault_b", Compartment.MEMORY)

    assert first.imported == 1
    assert second.deduplicated == 1
    assert len(list(brain.compartment_dirs[Compartment.MEMORY].rglob("*.md"))) == 1
    hits = brain.search("conteúdo idêntico", limit=10, compartment=Compartment.MEMORY)
    assert {(hit.source_label, hit.source_path) for hit in hits} == {
        ("vault_a", "one.md"),
        ("vault_b", "nested/two.md"),
    }


def test_cross_compartment_dedup(tmp_path):
    """Same content in different compartments should be stored separately per compartment."""
    mem_source = tmp_path / "mem"
    know_source = tmp_path / "know"
    content = "# Decisão compartilhada\n\nConteúdo que aparece em duas gavetas."
    write_note(mem_source, "mem.md", content)
    write_note(know_source, "know.md", content)
    brain = BrainStore(tmp_path / "brain")

    mem_report = brain.import_vault(mem_source, "mem_source", Compartment.MEMORY)
    know_report = brain.import_vault(know_source, "know_source", Compartment.KNOWLEDGE)

    assert mem_report.imported == 1
    assert know_report.imported == 1
    # Should have notes in both compartments
    mem_notes = list(brain.compartment_dirs[Compartment.MEMORY].rglob("*.md"))
    know_notes = list(brain.compartment_dirs[Compartment.KNOWLEDGE].rglob("*.md"))
    assert len(mem_notes) == 1
    assert len(know_notes) == 1
    # Different paths
    assert mem_notes[0] != know_notes[0]

    # Rebuilding from the manifest must preserve both drawers.  Older manifests
    # keyed only by hash and silently lost one of these identical documents.
    brain.index_path.unlink()
    assert brain.rebuild_index() == 2
    assert len(brain.search("duas gavetas", compartment=Compartment.MEMORY)) == 1
    assert len(brain.search("duas gavetas", compartment=Compartment.KNOWLEDGE)) == 1


def test_manifest_lists_a_deduplicated_document_once_per_compartment(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    content = "# Uma nota\n\nMesmo conteúdo, duas proveniências."
    write_note(first, "one.md", content)
    write_note(second, "two.md", content)
    brain = BrainStore(tmp_path / "brain")

    brain.import_vault(first, "first", Compartment.MEMORY)
    brain.import_vault(second, "second", Compartment.MEMORY)

    manifest = brain.manifest()
    assert len(manifest["documents"]) == 1
    assert len(manifest["compartments"]["memory"]) == 1


def test_secret_note_is_manifested_but_never_copied_or_indexed(tmp_path):
    source = tmp_path / "source"
    write_note(source, "private.md", "# Login\napi_key = «redacted:sk-…»")
    brain = BrainStore(tmp_path / "brain")

    report = brain.import_vault(source, "private_source", Compartment.MEMORY)

    assert report.blocked_secrets == 1
    assert list(brain.compartment_dirs[Compartment.MEMORY].rglob("*.md")) == []
    assert brain.search("Login", compartment=Compartment.MEMORY) == []
    item = brain.manifest()["sources"]["private_source"]["items"]["private.md"]
    assert item["status"] == "blocked_secret"


def test_index_is_rebuildable_from_manifest_and_notes(tmp_path):
    source = tmp_path / "source"
    write_note(source, "decision.md", "# Arquitetura\n\nÍndice descartável e reconstruível.")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "decisions", Compartment.MEMORY)
    brain.index_path.unlink()

    assert brain.rebuild_index() == 1
    hits = brain.search("reconstruível", compartment=Compartment.MEMORY)
    assert len(hits) == 1
    assert hits[0].source_path == "decision.md"
    assert hits[0].compartment == "memory"


def test_tampered_canonical_note_is_not_reindexed(tmp_path):
    source = tmp_path / "source"
    write_note(source, "safe.md", "# Original\n\nConteúdo íntegro.")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "source", Compartment.MEMORY)
    manifest = brain.manifest()
    item = next(iter(manifest["documents"].values()))
    (brain.root / "vault" / "memory" / item["note_path"]).write_text("alterado", encoding="utf-8")
    brain.index_path.unlink()

    assert brain.rebuild_index() == 0
    assert brain.search("alterado", compartment=Compartment.MEMORY) == []


def test_manifest_has_hash_and_provenance_without_note_content(tmp_path):
    source = tmp_path / "source"
    write_note(source, "fact.md", "# Fato\n\nConteúdo que fica apenas na nota.")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "facts", Compartment.MEMORY)

    manifest_text = brain.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    item = manifest["sources"]["facts"]["items"]["fact.md"]
    assert len(item["sha256"]) == 64
    assert item["note_path"].startswith("notes/")
    assert item["compartment"] == "memory"
    assert "Conteúdo que fica" not in manifest_text

    with sqlite3.connect(brain.index_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM memory_provenance").fetchone()[0] == 1


def test_missing_source_is_honest_and_has_no_side_effect_on_source(tmp_path):
    missing = tmp_path / "does-not-exist"
    brain = BrainStore(tmp_path / "brain")
    report = brain.import_vault(missing, "missing", Compartment.MEMORY)
    assert report.missing is True
    assert not missing.exists()


def test_preview_reports_sources_totals_duplicates_secrets_and_ignored(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    shared = "# Decisão\n\nUsar uma fonte canônica."
    write_note(first, "a.md", shared)
    write_note(first, "copy.md", shared)
    write_note(first, "secret.md", "# Privado\ntoken = abcdefghijklmnop")
    write_note(second, "same.md", shared)
    write_note(second, "unique.md", "# Outra\n\nNota exclusiva.")
    (first / "ignored.txt").write_text("não indexar", encoding="utf-8")
    missing = tmp_path / "missing"

    preview = preview_import({"first": first, "second": second, "missing": missing})

    by_name = {item.source_label: item for item in preview.sources}
    assert by_name["first"].exists is True
    assert by_name["first"].markdown_files == 3
    assert by_name["first"].unique_hashes == 2
    assert by_name["first"].duplicate_files == 1
    assert len(by_name["first"].duplicate_hashes) == 1
    assert by_name["first"].blocked_secrets == 1
    assert by_name["first"].ignored_files == 1
    assert by_name["missing"].exists is False
    assert preview.existing_sources == 2
    assert preview.missing_sources == 1
    assert preview.markdown_files == 5
    assert preview.markdown_bytes == sum(
        path.stat().st_size for path in first.glob("*.md")
    ) + sum(path.stat().st_size for path in second.glob("*.md"))
    assert preview.unique_hashes == 3
    assert preview.duplicate_files == 2
    assert next(iter(preview.duplicate_hashes.values())) == 3
    assert preview.blocked_secrets == 1
    assert not missing.exists()


def test_preview_performs_zero_writes(tmp_path):
    source = tmp_path / "source"
    write_note(source, "note.md", "# Somente leitura\n\nNada deve mudar.")
    brain_root = tmp_path / "never-created-brain"
    before = {
        path.relative_to(source).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }

    preview = BrainStore(brain_root).preview_import({"source": source})

    after = {
        path.relative_to(source).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }
    assert preview.markdown_files == 1
    assert before == after
    assert not brain_root.exists()


def test_preview_ignores_symlink_without_following_it(tmp_path, monkeypatch):
    source, outside = tmp_path / "source", tmp_path / "outside"
    source.mkdir()
    target = write_note(outside, "private.md", "# Fora\n\nNão deve ser lida.")
    link = source / "linked.md"
    try:
        link.symlink_to(target)
    except OSError:
        # Windows often denies symlink creation without Developer Mode. Model
        # the same Path contract so this security branch is still mandatory.
        link = write_note(source, "linked.md", "must be ignored")
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: self == link or original_is_symlink(self),
        )

    preview = preview_import({"source": source})

    item = preview.sources[0]
    assert item.markdown_files == 0
    assert item.symlinks == 1
    assert item.ignored_files == 1
    assert preview.symlinks == 1


def test_search_across_all_compartments(tmp_path):
    """Search without compartment filter should search all."""
    mem = tmp_path / "mem"
    know = tmp_path / "know"
    skill = tmp_path / "skill"
    write_note(mem, "mem.md", "# Memória\n\nFato importante sobre o usuário.")
    write_note(know, "know.md", "# Conhecimento\n\nArtigo sobre Python.")
    write_note(skill, "skill.md", "# Skill\n\nComo configurar o ambiente.")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(mem, "mem_src", Compartment.MEMORY)
    brain.import_vault(know, "know_src", Compartment.KNOWLEDGE)
    brain.import_vault(skill, "skill_src", Compartment.SKILL)

    hits = brain.search("importante", limit=10)
    assert len(hits) == 1
    assert hits[0].compartment == "memory"

    hits = brain.search("Python", limit=10)
    assert len(hits) == 1
    assert hits[0].compartment == "knowledge"

    hits = brain.search("configurar", limit=10)
    assert len(hits) == 1
    assert hits[0].compartment == "skill"


def test_get_compartment_stats(tmp_path):
    source = tmp_path / "source"
    write_note(source, "a.md", "# A\n\nConteúdo A")
    write_note(source, "b.md", "# B\n\nConteúdo B")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "src", Compartment.MEMORY)

    stats = brain.get_compartment_stats()
    assert "memory" in stats
    assert "knowledge" in stats
    assert "skill" in stats
    assert stats["memory"]["documents"] == 2
    assert stats["memory"]["note_files"] == 2
    assert stats["knowledge"]["documents"] == 0
    assert stats["skill"]["documents"] == 0


def test_auto_compartment_detection(tmp_path):
    """Test that compartment is auto-detected when not specified."""
    skill_source = tmp_path / "skill_src"
    write_note(skill_source, "deploy.md", "# Deploy\n\nPasso 1: Build.\nPasso 2: Test.\nPasso 3: Deploy.")
    brain = BrainStore(tmp_path / "brain")
    # Don't specify compartment - should auto-detect as SKILL
    report = brain.import_vault(skill_source, "deploy_docs")
    # The heuristic looks for "passo" and "como" in content
    # Since we have "Passo" in content, it should go to SKILL
    assert report.compartment == "skill"

    know_source = tmp_path / "know_src"
    write_note(know_source, "paper.md", "# Paper\n\nEste artigo PDF explica o conceito.")
    report2 = brain.import_vault(know_source, "papers")
    # "artigo" and "PDF" should trigger KNOWLEDGE
    assert report2.compartment == "knowledge"

    mem_source = tmp_path / "mem_src"
    write_note(mem_source, "pref.md", "# Preferência\n\nO usuário gosta de café.")
    report3 = brain.import_vault(mem_source, "prefs")
    # Default to MEMORY
    assert report3.compartment == "memory"


def test_citation_includes_compartment(tmp_path):
    source = tmp_path / "source"
    write_note(source, "note.md", "# Título\n\nConteúdo para busca.")
    brain = BrainStore(tmp_path / "brain")
    brain.import_vault(source, "src", Compartment.KNOWLEDGE)

    hits = brain.search("busca", compartment=Compartment.KNOWLEDGE)
    assert len(hits) == 1
    assert isinstance(hits[0], Citation)
    assert hits[0].compartment == "knowledge"
