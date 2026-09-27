#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes para snapshot_zara.py - exportacao e restore seguro.
"""

import json
import shutil
import tempfile
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# This one-shot export script was intentionally archived as historical tooling
# (see _quarentena/organizacao-2026-09-17/MOVIMENTACOES.txt). Keep the tests
# discoverable for provenance, but do not make the active suite depend on an
# unsupported root-level module.
snapshot_zara = pytest.importorskip(
    "snapshot_zara",
    reason="snapshot_zara.py foi arquivado como ferramenta histórica; não faz parte do runtime ativo",
)


def test_redact_api_keys_file():
    """Testa redacao de api_keys.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "api_keys.json"
        dst = tmp / "api_keys_redacted.json"

        # Cria arquivo com chaves reais
        src.write_text(json.dumps({
            "gemini_api_key": "AIzaSyRealKey123456789",
            "groq_api_key": "gsk_RealKey123456789012",
            "nvidia_api_key": "nvapi_RealKey123456789012345",
            "zai_api_key": "real-zai-key",
            "telegram_bot_token": "123456:ABC-DEF",
            "safe_key": "valor_seguro",
        }), encoding="utf-8")

        ok = snapshot_zara.redact_api_keys_file(src, dst)
        assert ok, "Redacao deve retornar True em sucesso"

        content = json.loads(dst.read_text(encoding="utf-8"))
        assert content["gemini_api_key"] == "«redacted»"
        assert content["groq_api_key"] == "«redacted»"
        assert content["nvidia_api_key"] == "«redacted»"
        assert content["zai_api_key"] == "«redacted»"
        assert content["telegram_bot_token"] == "«redacted»"
        assert content["safe_key"] == "valor_seguro", "Chave nao sensivel deve ser mantida"


def test_redact_api_keys_file_failure_no_fallback():
    """Testa que falha na redacao NAO faz fallback copiando original."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "api_keys.json"
        dst = tmp / "api_keys_redacted.json"

        # Arquivo JSON invalido
        src.write_text("{ invalid json }", encoding="utf-8")

        ok = snapshot_zara.redact_api_keys_file(src, dst)
        assert not ok, "Deve retornar False em falha"
        assert not dst.exists(), "NAO deve criar arquivo de fallback"


def test_is_sensitive_filename():
    """Testa deteccao de nomes de arquivos sensiveis."""
    assert snapshot_zara.is_sensitive_filename("api_keys.json")
    assert snapshot_zara.is_sensitive_filename("api_keys.json.bak")
    assert snapshot_zara.is_sensitive_filename("api_keys.json.backup")
    assert snapshot_zara.is_sensitive_filename("secret.txt")
    assert snapshot_zara.is_sensitive_filename("credentials.json")
    assert snapshot_zara.is_sensitive_filename("password.txt")
    assert snapshot_zara.is_sensitive_filename("token.json")
    assert snapshot_zara.is_sensitive_filename("api_keys.json.antes-do-telegram")
    assert snapshot_zara.is_sensitive_filename("api_keys.json.bak-antes-ponte-ceo")
    assert snapshot_zara.is_sensitive_filename("api_keys.json.bak_20260807_195729")

    assert not snapshot_zara.is_sensitive_filename("config.py")
    assert not snapshot_zara.is_sensitive_filename("base.py")
    assert not snapshot_zara.is_sensitive_filename("skill_manifest.json")


def test_is_cache_or_build():
    """Testa deteccao de caches e builds."""
    assert snapshot_zara.is_cache_or_build("__pycache__")
    assert snapshot_zara.is_cache_or_build("module.cpython-311.pyc")
    assert snapshot_zara.is_cache_or_build("test.pyc")
    assert snapshot_zara.is_cache_or_build(".pytest_cache")
    assert snapshot_zara.is_cache_or_build(".mypy_cache")
    assert snapshot_zara.is_cache_or_build(".ruff_cache")

    assert not snapshot_zara.is_cache_or_build("config.py")
    assert not snapshot_zara.is_cache_or_build("module.py")


def test_should_exclude_file():
    """Testa exclusao combinada."""
    # api_keys.json principal NAO deve ser excluido (deve ser redigido)
    assert not snapshot_zara.should_exclude_file("api_keys.json")
    assert snapshot_zara.should_exclude_file("__pycache__")
    assert snapshot_zara.should_exclude_file("test.pyc")
    assert not snapshot_zara.should_exclude_file("config.py")


def test_path_traversal_protection():
    """Testa protecao contra path traversal no restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        base = tmp / "target"
        base.mkdir()

        # Tenta traversal
        assert not snapshot_zara._is_safe_path(base, base / ".." / "outside")
        assert not snapshot_zara._is_safe_path(base, base / "subdir" / ".." / ".." / "outside")
        assert snapshot_zara._is_safe_path(base, base / "inside")
        assert snapshot_zara._is_safe_path(base, base / "subdir" / "file.txt")


def test_export_creates_safe_snapshot():
    """Testa que exportacao cria snapshot sem segredos e sem caches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        project_root = tmp / "project"
        project_root.mkdir()

        # Cria estrutura minima
        (project_root / "config").mkdir()
        (project_root / "config" / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "AIzaSyTest123", "safe": "value"}),
            encoding="utf-8"
        )
        (project_root / "config" / "api_keys.json.bak").write_text(
            json.dumps({"gemini_api_key": "AIzaSyBackup123"}),
            encoding="utf-8"
        )
        (project_root / "config" / "__pycache__").mkdir()
        (project_root / "config" / "test.pyc").write_text("compiled", encoding="utf-8")
        (project_root / "data").mkdir()
        (project_root / "data" / "test.txt").write_text("data", encoding="utf-8")
        (project_root / "memory").mkdir()
        (project_root / "lembretes").mkdir()
        (project_root / "skills").mkdir()
        (project_root / "integrations").mkdir()
        (project_root / "core" / "identity").mkdir(parents=True)
        (project_root / "core" / "initiative").mkdir(parents=True)
        (project_root / "core" / "perception").mkdir(parents=True)
        (project_root / "core" / "lab_coordinator.py").write_text("# lab", encoding="utf-8")
        (project_root / "core" / "autonomy_lab_bridge.py").write_text("# bridge", encoding="utf-8")
        (project_root / "core" / "capability_registry.py").write_text("# caps", encoding="utf-8")

        # Monkey-patch PROJECT_ROOT para o teste
        original_root = snapshot_zara.PROJECT_ROOT
        snapshot_zara.PROJECT_ROOT = project_root

        try:
            snapshot_dir = tmp / "snapshot"
            ok = snapshot_zara.export_cerebro(snapshot_dir)
            assert ok, "Exportacao deve retornar True"

            # Verifica que api_keys.json foi redigido (NAO excluido - e o arquivo principal)
            api_keys = snapshot_dir / "config" / "api_keys.json"
            assert api_keys.exists(), "api_keys.json principal deve existir"
            content = json.loads(api_keys.read_text(encoding="utf-8"))
            assert content["gemini_api_key"] == "«redacted»"
            assert content["safe"] == "value"

            # Verifica que backups foram EXCLUIDOS
            assert not (snapshot_dir / "config" / "api_keys.json.bak").exists()
            assert not (snapshot_dir / "config" / "__pycache__").exists()
            assert not (snapshot_dir / "config" / "test.pyc").exists()

            # Verifica que caches em outros diretorios foram excluidos
            for cache in snapshot_dir.rglob("__pycache__"):
                assert False, f"Cache nao deve existir: {cache}"
            for pyc in snapshot_dir.rglob("*.pyc"):
                assert False, f".pyc nao deve existir: {pyc}"

            # Verifica manifesto
            manifest = snapshot_dir / "MANIFEST.json"
            assert manifest.exists()
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            assert "contents" in manifest_data
            assert "snapshot_time" in manifest_data

        finally:
            snapshot_zara.PROJECT_ROOT = original_root


def test_verify_export_detects_leaks():
    """Testa que verify_export detecta vazamentos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()

        # Cria config com api_keys.json NAO redigido
        config_dir = snapshot_dir / "config"
        config_dir.mkdir()
        (config_dir / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "AIzaSyLeakedKey123"}),
            encoding="utf-8"
        )

        # Cria memoria com chave
        memory_dir = snapshot_dir / "memory"
        memory_dir.mkdir()
        (memory_dir / "mem.json").write_text('{"key": "AIzaSyInMemory"}', encoding="utf-8")

        ok = snapshot_zara.verify_export(snapshot_dir)
        assert not ok, "Deve detectar vazamento"


def test_verify_export_passes_clean():
    """Testa que verify_export passa em snapshot limpo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()

        config_dir = snapshot_dir / "config"
        config_dir.mkdir()
        (config_dir / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "«redacted»", "safe": "value"}, ensure_ascii=False),
            encoding="utf-8"
        )

        memory_dir = snapshot_dir / "memory"
        memory_dir.mkdir()
        (memory_dir / "mem.json").write_text('{"key": "valor_seguro"}', encoding="utf-8")

        ok = snapshot_zara.verify_export(snapshot_dir)
        assert ok, "Deve passar em snapshot limpo"


def test_restore_dry_run():
    """Testa restore em dry-run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()
        target_dir = tmp / "target"
        target_dir.mkdir()

        # Cria snapshot simples
        (snapshot_dir / "config").mkdir()
        (snapshot_dir / "config" / "test.txt").write_text("content", encoding="utf-8")
        (snapshot_dir / "MANIFEST.json").write_text(json.dumps({
            "snapshot_time": "2026-01-01T00:00:00",
            "source": "test",
            "contents": ["config", "config/test.txt"],
            "note": "test"
        }), encoding="utf-8")

        ok = snapshot_zara.restore_snapshot(snapshot_dir, target_dir, dry_run=True)
        assert ok
        # Em dry-run nao deve criar arquivos
        assert not (target_dir / "config").exists()


def test_restore_dry_run_with_nonexistent_target():
    """Testa restore em dry-run com destino inexistente (deve criar)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()
        target_dir = tmp / "target_nonexistent"  # nao existe

        # Cria snapshot simples
        (snapshot_dir / "config").mkdir()
        (snapshot_dir / "config" / "test.txt").write_text("content", encoding="utf-8")
        (snapshot_dir / "MANIFEST.json").write_text(json.dumps({
            "snapshot_time": "2026-01-01T00:00:00",
            "source": "test",
            "contents": ["config", "config/test.txt"],
            "note": "test"
        }), encoding="utf-8")

        ok = snapshot_zara.restore_snapshot(snapshot_dir, target_dir, dry_run=True)
        assert ok


def test_restore_real():
    """Testa restore real."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()
        target_dir = tmp / "target"
        target_dir.mkdir()

        (snapshot_dir / "config").mkdir()
        (snapshot_dir / "config" / "test.txt").write_text("content", encoding="utf-8")
        (snapshot_dir / "MANIFEST.json").write_text(json.dumps({
            "snapshot_time": "2026-01-01T00:00:00",
            "source": "test",
            "contents": ["config", "config/test.txt"],
            "note": "test"
        }), encoding="utf-8")

        ok = snapshot_zara.restore_snapshot(snapshot_dir, target_dir, dry_run=False)
        assert ok
        assert (target_dir / "config" / "test.txt").exists()
        assert (target_dir / "config" / "test.txt").read_text(encoding="utf-8") == "content"


def test_restore_blocks_path_traversal():
    """Testa que restore bloqueia path traversal mesmo se arquivo nao existe no snapshot."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot_dir = tmp / "snapshot"
        snapshot_dir.mkdir()
        target_dir = tmp / "target"
        target_dir.mkdir()

        # Manifesto com path traversal - arquivo NAO existe no snapshot
        (snapshot_dir / "MANIFEST.json").write_text(json.dumps({
            "snapshot_time": "2026-01-01T00:00:00",
            "source": "test",
            "contents": ["config", "../../../etc/passwd"],
            "note": "test"
        }), encoding="utf-8")

        ok = snapshot_zara.restore_snapshot(snapshot_dir, target_dir, dry_run=False)
        assert not ok, "Deve bloquear path traversal"


def test_audit_moves_insecure_snapshots():
    """Testa que auditoria move snapshots inseguros para quarantena."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshots_base = tmp / "snapshots"
        snapshots_base.mkdir()
        quarantine = tmp / "_quarentena" / "snapshots-inseguros"

        # Cria snapshot inseguro
        bad_snap = snapshots_base / "bad_snapshot"
        bad_snap.mkdir()
        (bad_snap / "config").mkdir()
        (bad_snap / "config" / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "AIzaSyLeaked123"}),
            encoding="utf-8"
        )
        (bad_snap / "config" / "__pycache__").mkdir()

        # Cria snapshot seguro (api_keys.json redigido)
        good_snap = snapshots_base / "good_snapshot"
        good_snap.mkdir()
        (good_snap / "config").mkdir()
        (good_snap / "config" / "api_keys.json").write_text(
            json.dumps({"gemini_api_key": "«redacted»"}, ensure_ascii=False),
            encoding="utf-8"
        )

        moved = snapshot_zara.audit_existing_snapshots(snapshots_base, quarantine)
        assert moved == 1
        assert not bad_snap.exists(), "Snapshot inseguro deve ser movido"
        assert (quarantine / "bad_snapshot").exists(), "Deve estar na quarantena"
        assert good_snap.exists(), "Snapshot seguro deve permanecer"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
