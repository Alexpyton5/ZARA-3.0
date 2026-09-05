from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.project_hygiene import main, scan_project_root


def test_classifies_known_root_candidates_without_reading_contents(tmp_path: Path) -> None:
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "debug_import.py").write_text("TOP_SECRET", encoding="utf-8")
    (tmp_path / "module.py.bak").write_text("DO_NOT_PRINT", encoding="utf-8")
    (tmp_path / "%TEMPvoz.txt").write_text("PRIVATE", encoding="utf-8")
    (tmp_path / "main.py").write_text("KEEP", encoding="utf-8")

    found = scan_project_root(tmp_path)

    assert [(item.path, item.category) for item in found] == [
        ("%TEMPvoz.txt", "temporary"),
        (".pytest_cache", "cache"),
        ("debug_import.py", "debug-helper"),
        ("module.py.bak", "backup"),
    ]


def test_scan_is_non_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "core"
    nested.mkdir()
    (nested / "debug_private.py").write_text("secret", encoding="utf-8")

    assert scan_project_root(tmp_path) == []


def test_json_report_never_contains_file_contents(tmp_path: Path, capsys) -> None:
    (tmp_path / "debug_secret.py").write_text("API_TOKEN_SHOULD_NOT_LEAK", encoding="utf-8")

    assert main(["--root", str(tmp_path), "--json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["verdict"] == "dry_run_only"
    assert payload["mutated"] is False
    assert payload["candidates"][0]["path"] == "debug_secret.py"
    assert "API_TOKEN_SHOULD_NOT_LEAK" not in output


@pytest.mark.parametrize("flag", ["--delete", "--move", "--apply", "--remove"])
def test_mutating_flags_are_refused(tmp_path: Path, flag: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), flag])
    assert exc_info.value.code == 2


def test_missing_root_fails_closed(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"
    assert main(["--root", str(missing), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "error"


def test_scan_does_not_change_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "debug_keep.py"
    candidate.write_bytes(b"unchanged")

    scan_project_root(tmp_path)

    assert candidate.read_bytes() == b"unchanged"
