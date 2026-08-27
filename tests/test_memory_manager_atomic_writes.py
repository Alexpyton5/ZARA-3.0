"""AUDITORIA_2026-08-27 item 1.5 — memory/memory_manager.py escrevia
long_term.json (dado protegido) com write_text() direto, sem o padrao
temp+rename que o resto do projeto usa. Um crash no meio da escrita
corrompia o arquivo, e load_memory() tratava qualquer excecao — arquivo
ausente ou JSON corrompido — devolvendo memoria vazia em silencio.

Estes testes trancam: escrita atomica (via core.storage.atomic_write_json),
existencia de um backup de recuperacao, e a diferenciacao entre "nunca
existiu" (silencioso, ok) e "corrompido" (log visivel + tenta recuperar do
backup antes de zerar).
"""
from __future__ import annotations

import json

import pytest

from memory import memory_manager


@pytest.fixture(autouse=True)
def _isolated_memory_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_manager, "MEMORY_PATH", tmp_path / "long_term.json")
    monkeypatch.setattr(memory_manager, "MEMORY_BACKUP_PATH", tmp_path / "long_term.backup.json")
    yield


def test_save_memory_writes_atomically_and_leaves_no_temp_file(tmp_path):
    memory = memory_manager._empty_memory()
    memory["notes"]["oi"] = {"value": "ola", "updated": "2026-08-27"}

    memory_manager.save_memory(memory)

    assert memory_manager.MEMORY_PATH.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"escrita nao-atomica deixou arquivo temporario: {leftovers}"


def test_save_memory_also_writes_recovery_backup():
    memory = memory_manager._empty_memory()
    memory["notes"]["oi"] = {"value": "ola", "updated": "2026-08-27"}

    memory_manager.save_memory(memory)

    assert memory_manager.MEMORY_BACKUP_PATH.exists()
    backup = json.loads(memory_manager.MEMORY_BACKUP_PATH.read_text(encoding="utf-8"))
    assert backup["notes"]["oi"]["value"] == "ola"


def test_load_memory_missing_file_is_silent_empty():
    """Primeira execucao (arquivo nunca existiu) nao e corrupcao — nao deve logar erro."""
    assert memory_manager.MEMORY_PATH.exists() is False

    result = memory_manager.load_memory()

    assert result == memory_manager._empty_memory()


def test_load_memory_corrupted_json_recovers_from_backup(capsys):
    memory = memory_manager._empty_memory()
    memory["notes"]["importante"] = {"value": "nao pode sumir", "updated": "2026-08-27"}
    memory_manager.save_memory(memory)

    # Simula corrupcao do arquivo principal (ex.: processo morreu no meio da escrita).
    memory_manager.MEMORY_PATH.write_text("{not valid json!!", encoding="utf-8")

    result = memory_manager.load_memory()

    assert result["notes"]["importante"]["value"] == "nao pode sumir"
    assert "CORRUPTED" in capsys.readouterr().out


def test_load_memory_corrupted_json_without_backup_zeroes_but_logs(capsys):
    memory_manager.MEMORY_PATH.write_text("{not valid json!!", encoding="utf-8")
    assert memory_manager.MEMORY_BACKUP_PATH.exists() is False

    result = memory_manager.load_memory()

    assert result == memory_manager._empty_memory()
    assert "CORRUPTED" in capsys.readouterr().out


def test_pop_last_session_writes_atomically(monkeypatch):
    # save_session_summary tambem grava na memoria episodica; isso e uma
    # preocupacao separada (fora do escopo deste teste) e nao pode tocar dado
    # real do Alex durante a suite, entao vira no-op aqui.
    monkeypatch.setattr(
        "memory.episodic_memory.record_episode", lambda *a, **k: None
    )
    memory_manager.save_session_summary("Resumo de teste", language="pt")

    entry = memory_manager.pop_last_session()

    assert entry is not None
    assert entry["summary"] == "Resumo de teste"
    reloaded = json.loads(memory_manager.MEMORY_PATH.read_text(encoding="utf-8"))
    assert reloaded.get("sessions", []) == []
