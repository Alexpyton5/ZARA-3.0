from pathlib import Path
import pytest

import importlib.util
import sys

_MODULE_PATH = Path(__file__).parents[1] / "core" / "obsidian_memory.py"
_SPEC = importlib.util.spec_from_file_location("sandbox_obsidian_memory", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["sandbox_obsidian_memory"] = _MODULE
_SPEC.loader.exec_module(_MODULE)
ObsidianMemoryManager = _MODULE.ObsidianMemoryManager
from core.lab_v1.agent_continuity import HandoffCheckpoint


def test_sync_uses_stable_identity_and_is_idempotent(tmp_path: Path):
    manager = ObsidianMemoryManager(tmp_path / "vault")
    (tmp_path / "vault").mkdir()
    first = manager.sync_memory("lab:s1:e1", "Lição", "conteúdo")
    second = manager.sync_memory("lab:s1:e1", "Lição", "conteúdo")
    assert first.status == "written"
    assert second.status == "unchanged"
    assert first.path == second.path
    assert len(list((tmp_path / "vault" / "Zara-Memoria").glob("*.md"))) == 1


def test_sync_reports_unavailable_and_retries_after_vault_returns(tmp_path: Path):
    vault = tmp_path / "vault"
    manager = ObsidianMemoryManager(vault)
    assert manager.sync_memory("lab:s1:e2", "Retry", "ok").status == "unavailable"
    vault.mkdir()
    assert manager.sync_memory("lab:s1:e2", "Retry", "ok").status == "written"


def test_sync_preserves_human_edit_and_leaves_traceable_conflict(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_memory("lab:s1:e3", "Human", "canonical")
    path = Path(first.path)
    path.write_text(path.read_text(encoding="utf-8") + "\nedição humana\n", encoding="utf-8")
    result = manager.sync_memory("lab:s1:e3", "Human", "canonical atualizado")
    assert result.status == "conflict"
    assert "edição humana" in path.read_text(encoding="utf-8")
    conflict = Path(result.conflict_path)
    assert conflict.exists()
    text = conflict.read_text(encoding="utf-8")
    assert "zara_conflict: true" in text
    assert "lab:s1:e3" in text


def _handoff() -> HandoffCheckpoint:
    return HandoffCheckpoint(
        "REVIEWER", "artifact:diff-1", ("evidence:test-1",),
        {"model": "terra", "run_id": "run:1"},
    )


def test_sync_handoff_uses_artifact_identity_and_is_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_handoff(_handoff(), "Mission")
    second = manager.sync_handoff(_handoff(), "Mission")
    assert first.status == "written"
    assert second.status == "unchanged"
    assert first.identity == second.identity == "handoff:artifact:diff-1"
    body = Path(first.path).read_text(encoding="utf-8")
    assert "evidence:test-1" in body and "run:1" in body


def test_sync_handoff_retries_after_vault_is_unavailable(tmp_path: Path):
    vault = tmp_path / "vault"
    manager = ObsidianMemoryManager(vault)
    assert manager.sync_handoff(_handoff(), "Mission").status == "unavailable"
    vault.mkdir()
    assert manager.sync_handoff(_handoff(), "Mission").status == "written"


def test_sync_handoff_preserves_human_edit_and_tracks_conflict(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_handoff(_handoff(), "Mission")
    path = Path(first.path)
    edited = path.read_text(encoding="utf-8").replace(
        "zara_sync_hash:", "zara_sync_hash: human-edit-\n# zara_sync_hash:"
    ) + "\nnota humana\n"
    path.write_text(edited, encoding="utf-8")
    result = manager.sync_handoff(_handoff(), "Mission")
    assert result.status == "conflict"
    assert "nota humana" in path.read_text(encoding="utf-8")
    assert "zara_conflict: true" in Path(result.conflict_path).read_text(encoding="utf-8")


def test_identity_keeps_same_note_when_topic_changes_and_updates_canonical_body(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_memory("lab:s1:e4", "Primeiro tópico", "versão 1")
    second = manager.sync_memory("lab:s1:e4", "Outro tópico", "versão 2")
    assert second.status == "written"
    assert second.path == first.path
    assert len(list((vault / "Zara-Memoria").glob("*.md"))) == 1
    text = Path(first.path).read_text(encoding="utf-8")
    assert "title: Outro tópico" in text
    assert "versão 2" in text


def test_legacy_topic_hash_name_is_reused_without_duplicate(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_memory("lab:s1:e5", "Legado", "conteúdo")
    legacy = Path(first.path).with_name("Legado-" + Path(first.path).stem.rsplit("-", 1)[1] + ".md")
    Path(first.path).rename(legacy)
    result = manager.sync_memory("lab:s1:e5", "Novo", "conteúdo atualizado")
    assert result.path == str(legacy)
    assert len(list((vault / "Zara-Memoria").glob("*.md"))) == 1
    assert "conteúdo atualizado" in legacy.read_text(encoding="utf-8")


def test_conflict_artifact_tracks_latest_canonical_version(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    first = manager.sync_memory("lab:s1:e6", "Conflito", "v1")
    path = Path(first.path)
    path.write_text(path.read_text(encoding="utf-8") + "\nedicão humana\n", encoding="utf-8")
    conflict = manager.sync_memory("lab:s1:e6", "Conflito", "v2")
    assert conflict.status == "conflict"
    latest = manager.sync_memory("lab:s1:e6", "Conflito", "v3")
    assert latest.status == "conflict"
    assert "v3" in Path(latest.conflict_path).read_text(encoding="utf-8")
    assert "v2" not in Path(latest.conflict_path).read_text(encoding="utf-8")


def test_repeated_conflicts_keep_original_and_preserve_human_conflict_notes(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)
    original = manager.sync_memory('stable', 'Title', 'v1')
    path = Path(original.path)
    path.write_text(path.read_text(encoding='utf-8') + '\nhuman original\n', encoding='utf-8')
    first = manager.sync_memory('stable', 'Title', 'v2')
    conflict = Path(first.conflict_path)
    conflict.write_text(conflict.read_text(encoding='utf-8') + '\nhuman conflict\n', encoding='utf-8')
    for value in ('v3', 'v4', 'v4'):
        result = manager.sync_memory('stable', 'Renamed', value)
        assert result.path == original.path
        assert value in Path(result.conflict_path).read_text(encoding='utf-8')
    assert 'human original' in path.read_text(encoding='utf-8')
    assert 'human conflict' in conflict.read_text(encoding='utf-8')
    assert not list(path.parent.glob('*.conflict.conflict.md'))


@pytest.mark.parametrize('edit', ['metadata', 'whitespace', 'identity'])
def test_any_human_edit_is_preserved_on_canonical_update(tmp_path, edit):
    manager = ObsidianMemoryManager(tmp_path)
    first = manager.sync_memory('edit-proof', 'Title', 'v1')
    path = Path(first.path)
    original = path.read_text(encoding='utf-8')
    if edit == 'metadata':
        edited = original.replace('title: Title', 'title: Human title')
    elif edit == 'whitespace':
        edited = original + '  \n'
    else:
        edited = original.replace('zara_sync_identity:', 'human_identity:')
    path.write_text(edited, encoding='utf-8')
    result = manager.sync_memory('edit-proof', 'Title', 'v2')
    assert result.status == 'conflict'
    assert result.path == first.path
    assert path.read_text(encoding='utf-8') == edited
    assert 'v2' in Path(result.conflict_path).read_text(encoding='utf-8')


def test_metadata_only_canonical_update_keeps_identity(tmp_path):
    manager = ObsidianMemoryManager(tmp_path)
    first = manager.sync_memory('rename', 'Old', 'same body', category='Lab')
    second = manager.sync_memory('rename', 'New', 'same body', category='Lessons')
    assert second.status == 'written'
    assert second.path == first.path
    text = Path(second.path).read_text(encoding='utf-8')
    assert 'title: New' in text and 'category: Lessons' in text
    assert manager.sync_memory('rename', 'New', 'same body', category='Lessons').status == 'unchanged'
