from __future__ import annotations

import json
from pathlib import Path

from core.obsidian_memory import ObsidianMemoryManager
from memory.second_brain_composition import (
    build_shared_second_brain,
    get_central_memory_status,
)


class _EmptySource:
    def search(self, _query: str, limit: int = 5) -> list[dict]:
        return []



def test_vault_status_counts_only_verifiable_safe_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "safe.md").write_text("# Nota\nconteúdo verificável", encoding="utf-8")
    (vault / "api_keys.md").write_text("OPENAI_API_KEY=sk-super-secret", encoding="utf-8")
    (vault / "private.md").write_text("password: hunter2", encoding="utf-8")

    manager = ObsidianMemoryManager(vault)

    status = manager.get_vault_status()

    assert status == {
        "status": "available",
        "available": True,
        "note_count": 1,
        "last_sync": None,
        "degraded": False,
    }
    assert "sk-super-secret" not in json.dumps(status)
    assert manager.search_notes("conteúdo") == [
        {
            "title": "safe",
            "path": "safe.md",
            "snippet": "# Nota\nconteúdo verificável",
        }
    ]


def test_last_sync_is_process_local_and_secret_writes_are_rejected(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = ObsidianMemoryManager(vault)

    assert manager.save_memory("api key", "OPENAI_API_KEY=sk-super-secret") is None
    assert manager.count_notes() == 0

    status = manager.mark_synchronized("2026-09-18T13:00:00+00:00")

    assert status["last_sync"] == "2026-09-18T13:00:00+00:00"
    assert status["note_count"] == 0
    assert not (vault / "Zara-Memoria").exists()


def test_unavailable_vault_is_explicitly_degraded(tmp_path: Path) -> None:
    manager = ObsidianMemoryManager(tmp_path / "disconnected-vault")

    status = manager.status()

    assert status["status"] == "unavailable"
    assert status["available"] is False
    assert status["note_count"] == 0
    assert status["degraded"] is True
    assert manager.search_notes("qualquer coisa") == []


def test_composition_exposes_live_central_memory_status_without_new_truth(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "canonical.md"
    note.write_text("# Fonte canônica\nA nota continua no vault", encoding="utf-8")
    manager = ObsidianMemoryManager(vault)

    brain = build_shared_second_brain(
        user_memory=_EmptySource(),
        lab_store=_EmptySource(),
        project_memory=_EmptySource(),
        obsidian=manager,
        obsidian_index_db=tmp_path / "derived" / "index.sqlite3",
    )

    status = brain.get_central_memory_status()
    assert status["status"] == "available"
    assert status["vault_status"] == "available"
    assert status["available"] is True
    assert status["note_count"] == 1
    assert status["last_sync"] is not None
    assert status["degraded"] is False
    assert brain.central_memory_status == status
    assert "Fonte canônica" not in json.dumps(status, ensure_ascii=False)

    # O status é derivado ao vivo: desconectar o vault não reescreve a fonte
    # nem transforma o cache em uma falsa confirmação de disponibilidade.
    disconnected = vault.with_name("disconnected-vault")
    vault.rename(disconnected)
    degraded = get_central_memory_status(brain, obsidian=manager)

    assert degraded["status"] == "degraded"
    assert degraded["vault_status"] == "unavailable"
    assert degraded["available"] is False
    assert degraded["note_count"] == 0
    assert degraded["degraded"] is True
    assert note.exists() is False
    assert not (tmp_path / "derived" / "index.sqlite3").read_bytes() == b""
