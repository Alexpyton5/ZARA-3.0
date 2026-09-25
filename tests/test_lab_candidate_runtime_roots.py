"""Real CandidateSource subprocess may use its own home and temp directories."""

from __future__ import annotations

import sys
from pathlib import Path

from core.lab_v1.candidate_source import CandidateSource


def test_runtime_home_and_temp_are_usable_without_exposing_production(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "core" / "calculator.py"
    source.parent.mkdir(parents=True)
    source.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    sandbox = workspace / ".lab-runtime" / "mission"
    candidate = CandidateSource(
        workspace,
        sandbox,
        ["core/calculator.py", "tests/test_runtime_roots.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    body = f'''
import os
from pathlib import Path

import pytest


def test_pytest_tmp_path_and_runtime_home(tmp_path):
    tmp_file = tmp_path / "pytest.txt"
    tmp_file.write_text("temporary", encoding="utf-8")
    assert tmp_file.read_text(encoding="utf-8") == "temporary"
    assert "pytest.txt" in os.listdir(tmp_path)
    assert any(entry.name == "pytest.txt" for entry in os.scandir(tmp_path))

    home = Path(os.environ["HOME"])
    home_file = home / "state.txt"
    home_file.write_text("state", encoding="utf-8")
    assert home_file.read_text(encoding="utf-8") == "state"
    assert "state.txt" in os.listdir(home)
    assert any(entry.name == "state.txt" for entry in os.scandir(home))


def test_production_source_remains_unreadable():
    with pytest.raises(PermissionError, match="PRODUCTION_READ_FORBIDDEN"):
        Path({str(source)!r}).read_text(encoding="utf-8")
    with pytest.raises(PermissionError, match="PRODUCTION_ENUMERATION_FORBIDDEN"):
        os.listdir({str(source.parent)!r})
    with pytest.raises(PermissionError, match="SANDBOX_WRITE_FORBIDDEN"):
        Path({str(source)!r}).write_text("tampered", encoding="utf-8")


def test_other_runtime_files_remain_unreadable():
    with pytest.raises(PermissionError, match="PRODUCTION_READ_FORBIDDEN"):
        Path({str(sandbox / 'manifest.json')!r}).read_text(encoding="utf-8")
    with pytest.raises(PermissionError, match="PRODUCTION_ENUMERATION_FORBIDDEN"):
        os.listdir({str(sandbox)!r})
'''
    candidate.apply_edits(
        [
            {"path": "core/calculator.py", "content": "def add(a, b):\n    return a + b\n"},
            {"path": "tests/test_runtime_roots.py", "content": body},
        ]
    )

    result = candidate.run_pytest(["tests/test_runtime_roots.py"], timeout_seconds=60)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.counts["passed"] == 3
    assert result.counts["failed"] == result.counts["errors"] == 0
    assert source.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"
