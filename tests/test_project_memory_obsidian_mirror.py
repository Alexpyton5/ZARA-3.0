"""AUDITORIA_2026-08-27: memoria do projeto passa a espelhar no cofre real
do Obsidian do Alex (achado via obsidian.json), nao mais num "cofre" isolado
que o ObsidianBridge criava sozinho e que ninguem via."""
from __future__ import annotations

from pathlib import Path

from memory.project_memory import ProjectMemory, _detect_real_obsidian_vault


def test_detect_real_obsidian_vault_reads_config(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    real_vault = tmp_path / "MeuCofre"
    real_vault.mkdir(parents=True)
    config_dir = fake_home / "AppData" / "Roaming" / "obsidian"
    config_dir.mkdir(parents=True)
    (config_dir / "obsidian.json").write_text(
        '{"vaults":{"abc":{"path":"' + str(real_vault).replace("\\", "\\\\") + '","ts":123}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("memory.project_memory.Path.home", lambda: fake_home)

    assert _detect_real_obsidian_vault() == real_vault


def test_detect_real_obsidian_vault_returns_none_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr("memory.project_memory.Path.home", lambda: tmp_path / "no_obsidian_here")

    assert _detect_real_obsidian_vault() is None


def test_save_doc_mirrors_into_real_obsidian_vault(tmp_path):
    real_vault = tmp_path / "MeuCofre"
    real_vault.mkdir()
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=real_vault)

    pm.save_doc("arquitetura", "Arquitetura da Zara", "conteudo de teste")

    mirrored = real_vault / "Zara-Memoria" / "arquitetura.md"
    assert mirrored.exists()
    assert "conteudo de teste" in mirrored.read_text(encoding="utf-8")
    assert "Arquitetura da Zara" in mirrored.read_text(encoding="utf-8")


def test_save_doc_never_raises_when_obsidian_vault_is_gone(tmp_path):
    """Se o cofre nao existe (HD desconectado, cofre movido), a memoria da
    Zara continua funcionando — o espelho e melhor-esforco, nunca bloqueante."""
    disconnected_drive = Path("Z:/unidade-que-nao-existe/cofre")
    pm = ProjectMemory(base_dir=tmp_path / "pm", obsidian_vault_dir=disconnected_drive)

    pm.save_doc("arquitetura", "Arquitetura da Zara", "conteudo")

    assert pm.get_doc("arquitetura")["content"] == "conteudo"
