"""F3 contracts; every persistence path is injected under tmp_path."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.auto_repair import RepairMemory, resolve_segundo_cerebro
from core.obsidian_memory import ObsidianMemoryManager
from memory.project_memory import ProjectMemory, _detect_real_obsidian_vault, _resolve_obsidian_vault
from memory.second_brain_composition import build_shared_second_brain, render_second_brain_context
from memory.shared_second_brain import SharedSecondBrain


def test_detect_preserves_parent_but_resolver_uses_child(tmp_path, monkeypatch):
    parent = tmp_path / "vault"
    child = parent / "segundo-cerebro"
    child.mkdir(parents=True)
    home = tmp_path / "home"
    config = home / "AppData/Roaming/obsidian/obsidian.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"vaults": {"a": {"path": str(parent), "ts": 1}}}), encoding="utf-8")
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert _detect_real_obsidian_vault() == parent
    assert _resolve_obsidian_vault() == child


@pytest.mark.parametrize("has_child", [False, True])
def test_all_shared_owners_use_same_canonical_root(tmp_path, has_child):
    parent = tmp_path / "vault"
    parent.mkdir()
    expected = parent
    if has_child:
        expected = parent / "segundo-cerebro"
        expected.mkdir()
    manager = ObsidianMemoryManager(parent)
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=parent)
    brain = SharedSecondBrain(user_memory=None, lab_store=None, project_workspace=None,
                              obsidian_vault=parent, obsidian_index_db=tmp_path / "index.db")
    assert manager.vault_path == pm.obsidian_vault_dir == brain.obsidian_vault == expected
    assert resolve_segundo_cerebro(parent) == expected
    name = pm.record_shared_learning("crew confirmou tarefa segura")
    assert name and (expected / "aprendizados" / name).exists()
    if has_child:
        assert not (parent / "aprendizados").exists()


def test_env_priority_and_changed_root_in_same_project_memory(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(first))
    def unexpected_detection():
        raise AssertionError("valid env must win")
    monkeypatch.setattr("memory.project_memory._detect_real_obsidian_vault", unexpected_detection)
    pm = ProjectMemory(base_dir=tmp_path / "pm")
    before = pm.record_shared_learning("crew trabalho anterior")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(second))
    after = pm.record_shared_learning("crew trabalho atual")
    assert before and after
    assert (first / "aprendizados" / before).exists()
    assert (second / "aprendizados" / after).exists()
    assert not (first / "aprendizados" / after).exists()
    pm.save_doc("state", "Estado", "crew estado atual")
    assert (second / "Zara-Memoria/state.md").exists()
    assert not (first / "Zara-Memoria").exists()


def test_new_child_and_unavailable_explicit_root_are_checked_at_write(tmp_path, monkeypatch):
    parent = tmp_path / "vault"
    parent.mkdir()
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=parent)
    child = parent / "segundo-cerebro"
    child.mkdir()
    name = pm.record_shared_learning("crew depois do child")
    assert name and (child / "aprendizados" / name).exists()
    parent.rename(tmp_path / "offline")
    fallback = tmp_path / "other"
    fallback.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(fallback))
    assert pm.record_shared_learning("crew indisponivel") is None
    pm.save_doc("state", "Estado", "crew local preservado")
    assert pm.get_doc("state")["content"] == "crew local preservado"
    assert not parent.exists() and not list(fallback.iterdir())


@pytest.mark.parametrize("secret", [
    "senha do roteador: exemplo-privado", "Bearer exemplo-privado",
    "sk-1234567890abcdef", "hidden reasoning: exemplo privado",
])
@pytest.mark.parametrize("writer,field", [
    ("mirror", "title"), ("mirror", "content"), ("mirror", "key"),
    ("learning", "content"),
    ("repair", "title"), ("repair", "component"), ("repair", "error_text"),
    ("repair", "how_broke"), ("repair", "how_fixed"), ("repair", "verification"),
    ("save", "topic"), ("save", "content"), ("save", "category"),
    ("sync", "identity"), ("sync", "topic"), ("sync", "content"), ("sync", "category"),
])
def test_shared_writers_reject_secret_in_each_persisted_field(tmp_path, secret, writer, field):
    vault = tmp_path / "vault"
    vault.mkdir()
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=vault)
    manager = ObsidianMemoryManager(vault)
    if writer == "mirror":
        values = dict(key="state", title="Estado", content="crew seguro")
        values[field] = secret
        # Test the shared writer directly; local database persistence is a separate domain.
        pm._mirror_to_obsidian(values["key"], values["title"], values["content"])
    elif writer == "learning":
        assert pm.record_shared_learning(secret) is None
    elif writer == "repair":
        values = dict(title="Reparo", component="cache", error_text="erro",
                      how_broke="cache perdido", how_fixed="cache recuperado", verification="confirmado")
        values[field] = secret
        assert RepairMemory(vault).save_repair_note(**values) is None
    else:
        values = dict(topic="Estado", content="crew seguro", category="Lab")
        if writer == "sync":
            values["identity"] = "lab:example"
        values[field] = secret
        result = manager.sync_memory(**values) if writer == "sync" else manager.save_memory(**values)
        assert result.status == "unavailable" if writer == "sync" else result is None
    assert list(vault.iterdir()) == []


def test_composition_reads_child_fresh_but_omits_offline_cache(tmp_path):
    parent = tmp_path / "vault"
    child = parent / "segundo-cerebro"
    child.mkdir(parents=True)
    (parent / "outside.md").write_text("crew outsider", encoding="utf-8")
    note = child / "crew.md"
    note.write_text("crew plano azul", encoding="utf-8")
    manager = ObsidianMemoryManager(parent)
    brain = build_shared_second_brain(user_memory=None, obsidian=manager,
                                      obsidian_index_db=tmp_path / "index.db")
    assert brain.obsidian_vault == child
    assert "azul" in render_second_brain_context(brain, "crew")
    note.write_text("crew plano verde", encoding="utf-8")
    context = render_second_brain_context(brain, "crew")
    assert "verde" in context and "azul" not in context and "outsider" not in context
    parent.rename(tmp_path / "offline")
    # Preserve the facade's legacy degraded-cache contract.
    assert any(item["source"] == "obsidian" for item in brain.query("crew")["items"])
    assert render_second_brain_context(brain, "crew") == ""
    unavailable = SimpleNamespace(vault_path=tmp_path / "stale", available=False)
    rebuilt = build_shared_second_brain(user_memory=None, obsidian=unavailable,
                                        obsidian_index_db=tmp_path / "empty-index.db")
    assert rebuilt.obsidian_vault is None


def test_sensitive_human_tail_is_not_copied_to_conflict(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    saved = manager.sync_memory("lab:tail", "Estado", "crew v1")
    path = Path(saved.path)
    path.write_text(path.read_text(encoding="utf-8") + "\nedição humana\n", encoding="utf-8")
    first = manager.sync_memory("lab:tail", "Estado", "crew v2")
    conflict = Path(first.conflict_path)
    conflict.write_text(conflict.read_text(encoding="utf-8") + "\n# Human notes\nsenha do roteador: exemplo-privado\n", encoding="utf-8")
    prior = conflict.read_bytes()
    assert manager.sync_memory("lab:tail", "Estado", "crew v3").status == "unavailable"
    assert conflict.read_bytes() == prior
