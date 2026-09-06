from __future__ import annotations

from core.actions.files import (
    files_copy_action,
    files_create_folder_action,
    files_move_action,
    files_open_latest_action,
    files_organize_by_extension_action,
    files_rename_action,
    files_search_action,
    files_text_summary_action,
    files_write_action,
)
from core.action_registry import get_registry


def test_create_folder_makes_new_directory_and_verifies_it(tmp_path):
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True
    try:
        target = tmp_path / "TesteZaraMissao"

        result = files_create_folder_action(str(target))

        assert result.success is True
        assert target.is_dir()
        assert result.data["already_existed"] is False
    finally:
        registry.medium_risk_open = original_medium_risk


def test_create_folder_is_idempotent_when_it_already_exists(tmp_path):
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True
    try:
        target = tmp_path / "JaExiste"
        target.mkdir()

        result = files_create_folder_action(str(target))

        assert result.success is True
        assert result.data["already_existed"] is True
    finally:
        registry.medium_risk_open = original_medium_risk


def test_create_folder_refuses_when_a_file_occupies_the_name(tmp_path):
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True
    try:
        target = tmp_path / "nota.txt"
        target.write_text("x")

        result = files_create_folder_action(str(target))

        assert result.success is False
    finally:
        registry.medium_risk_open = original_medium_risk


def test_open_latest_skips_newer_executable_and_requires_window_proof(tmp_path, monkeypatch):
    safe = tmp_path / "relatorio.pdf"
    unsafe = tmp_path / "instalador.exe"
    safe.write_bytes(b"pdf")
    unsafe.write_bytes(b"exe")
    unsafe.touch()
    opened = []
    # Mock os.startfile to track what gets opened
    monkeypatch.setattr("os.startfile", lambda path: opened.append(path))
    monkeypatch.setattr("core.actions.files._window_snapshot", lambda: {})
    monkeypatch.setattr(
        "core.actions.files._confirm_file_window",
        lambda target, before: {"hwnd": 10, "process": "reader.exe", "window_title": target.name, "new_window": True, "title_changed": True},
    )

    result = files_open_latest_action(str(tmp_path))

    assert result.success is True
    assert opened == [str(safe)]
    assert result.data["name"] == "relatorio.pdf"
    assert result.data["status"] == "OPEN_CONFIRMED"


def test_open_latest_never_claims_success_without_window_proof(tmp_path, monkeypatch):
    target = tmp_path / "nota.txt"
    target.write_text("ok", encoding="utf-8")
    # Mock os.startfile to do nothing (don't actually open files)
    monkeypatch.setattr("os.startfile", lambda path: None)
    monkeypatch.setattr("core.actions.files._window_snapshot", lambda: {})
    monkeypatch.setattr("core.actions.files._confirm_file_window", lambda target, before: None)

    result = files_open_latest_action(str(tmp_path))

    assert result.success is False
    assert result.data["status"] == "POSTCONDITION_FAILED"


def test_write_create_append_and_explicit_overwrite(tmp_path):
    # Enable MEDIUM risk for file mutation actions
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True

    try:
        target = tmp_path / "nota.txt"

        assert files_write_action(str(target), "Olá").success
        assert not files_write_action(str(target), "perdido").success
        assert files_write_action(str(target), " ZARA", append=True).success
        assert target.read_text(encoding="utf-8") == "Olá ZARA"
        assert files_write_action(str(target), "novo", overwrite=True).success
        assert target.read_text(encoding="utf-8") == "novo"
    finally:
        # Restore original settings
        registry.medium_risk_open = original_medium_risk


def test_copy_move_and_rename_never_replace_existing_destination(tmp_path):
    # Enable MEDIUM risk for file mutation actions
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True

    try:
        source = tmp_path / "origem.txt"
        source.write_text("conteúdo", encoding="utf-8")
        occupied = tmp_path / "ocupado.txt"
        occupied.write_text("preservar", encoding="utf-8")

        assert not files_copy_action(str(source), str(occupied), overwrite=True).success
        assert occupied.read_text(encoding="utf-8") == "preservar"
        copied = tmp_path / "copia.txt"
        assert files_copy_action(str(source), str(copied)).success
        assert copied.read_text(encoding="utf-8") == "conteúdo"

        assert not files_move_action(str(copied), str(occupied), overwrite=True).success
        assert copied.exists()
        renamed = files_rename_action(str(copied), "renomeado.txt")
        assert renamed.success
        assert (tmp_path / "renomeado.txt").read_text(encoding="utf-8") == "conteúdo"
    finally:
        # Restore original settings
        registry.medium_risk_open = original_medium_risk


def test_sensitive_paths_are_blocked_and_search_skips_secret_content(tmp_path):
    sensitive = tmp_path / "credentials" / "token.json"
    sensitive.parent.mkdir()
    sensitive.write_text("SECRET_NEEDLE", encoding="utf-8")
    public = tmp_path / "public.txt"
    public.write_text("PUBLIC_NEEDLE", encoding="utf-8")

    assert not files_write_action(str(sensitive), "overwrite", overwrite=True).success
    result = files_search_action("NEEDLE", str(tmp_path))
    assert result.success
    assert result.data["count"] == 1
    assert result.data["matches"][0]["file"] == "public.txt"


def test_text_summary_is_bounded_and_deterministic(tmp_path):
    target = tmp_path / "nota.txt"
    target.write_text("linha um\n\nlinha dois com ZARA\n", encoding="utf-8")

    result = files_text_summary_action(str(target), max_preview_lines=2)

    assert result.success
    assert result.data["lines"] == 3
    assert result.data["words"] == 6
    assert result.data["preview"] == ["linha um", "linha dois com ZARA"]


def test_organize_by_extension_never_deletes_or_replaces(tmp_path):
    # Enable MEDIUM risk for file mutation actions
    registry = get_registry()
    original_medium_risk = registry.medium_risk_open
    registry.medium_risk_open = True

    try:
        (tmp_path / "a.txt").write_text("A", encoding="utf-8")
        (tmp_path / "b.md").write_text("B", encoding="utf-8")
        occupied = tmp_path / "txt" / "a.txt"
        occupied.parent.mkdir()
        occupied.write_text("preservar", encoding="utf-8")

        preview = files_organize_by_extension_action(str(tmp_path), dry_run=True)
        result = files_organize_by_extension_action(str(tmp_path), dry_run=False)

        assert preview.success and preview.data["moved"] == 0
        assert result.success and result.data["deleted"] == 0
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A"
        assert occupied.read_text(encoding="utf-8") == "preservar"
        assert (tmp_path / "md" / "b.md").read_text(encoding="utf-8") == "B"
    finally:
        # Restore original settings
        registry.medium_risk_open = original_medium_risk
