from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from core.lab_v1.candidate_source import CandidateSource, CandidateSourceError


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    _write(
        workspace / "core" / "calculator.py",
        "def add(left: int, right: int) -> int:\n    return left - right\n",
    )
    _write(workspace / "core" / "helper.py", "VALUE = 42\n")
    _write(workspace / "core" / "hermes_bridge.py", "SECRET = True\n")
    return workspace


def test_prepare_snapshots_real_files_and_records_manifest(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_calculator.py"],
        support_paths=["core"],
        python_executable=Path(sys.executable),
    )

    snapshot = candidate.prepare()

    copied = candidate.source_root / "core" / "calculator.py"
    assert copied.read_text(encoding="utf-8") == (
        workspace / "core" / "calculator.py"
    ).read_text(encoding="utf-8")
    assert not (candidate.source_root / "core" / "hermes_bridge.py").exists()
    assert not (candidate.source_root / "tests" / "test_calculator.py").exists()
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    calculator = next(item for item in manifest["files"] if item["path"] == "core/calculator.py")
    missing_test = next(
        item for item in manifest["files"] if item["path"] == "tests/test_calculator.py"
    )
    assert calculator["original_path"] == str(workspace / "core" / "calculator.py")
    assert calculator["before_sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
    assert calculator["editable"] is True
    assert missing_test["before_sha256"] is None
    assert missing_test["exists"] is False
    assert snapshot.files == len(manifest["files"])


def test_context_is_bounded_and_only_reads_snapshot(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    (workspace / "core" / "calculator.py").write_text("PRODUCTION_CHANGED = True\n", encoding="utf-8")

    context = candidate.read_context(max_chars=200)

    assert "return left - right" in context["core/calculator.py"]
    with pytest.raises(CandidateSourceError, match="CONTEXT_LIMIT"):
        candidate.read_context(max_chars=5)
    with pytest.raises(CandidateSourceError, match="not snapshotted"):
        candidate.read_context(["core/other.py"])


def test_snapshot_can_be_resumed_without_trusting_new_authority(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    sandbox = tmp_path / "sandbox"
    first = CandidateSource(
        workspace,
        sandbox,
        ["core/calculator.py", "tests/test_calculator.py"],
        support_paths=["core"],
        python_executable=Path(sys.executable),
    )
    first.prepare()
    first.apply_edits(
        [
            {
                "path": "core/calculator.py",
                "content": "def add(left: int, right: int) -> int:\n    return left + right\n",
            },
            {
                "path": "tests/test_calculator.py",
                "content": "def test_placeholder():\n    assert True\n",
            },
        ]
    )

    resumed = CandidateSource(
        workspace,
        sandbox,
        ["core/calculator.py", "tests/test_calculator.py"],
        support_paths=["core"],
        python_executable=Path(sys.executable),
    )
    snapshot = resumed.resume()

    assert snapshot.files >= 3
    assert "return left + right" in resumed.read_context()["core/calculator.py"]
    with pytest.raises(CandidateSourceError, match="MANIFEST_BINDING_MISMATCH"):
        CandidateSource(
            workspace,
            sandbox,
            ["core/helper.py"],
            support_paths=["core"],
            python_executable=Path(sys.executable),
        ).resume()


def test_apply_edits_changes_only_sandbox_and_returns_diff_evidence(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    original = (workspace / "core" / "calculator.py").read_bytes()
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_calculator.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    result = candidate.apply_edits(
        [
            {
                "path": "core/calculator.py",
                "content": "def add(left: int, right: int) -> int:\n    return left + right\n",
            },
            {
                "path": "tests/test_calculator.py",
                "content": "from core.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            },
        ]
    )

    assert (workspace / "core" / "calculator.py").read_bytes() == original
    assert not (workspace / "tests" / "test_calculator.py").exists()
    assert result.files_changed == 2
    assert result.source_files_changed == 1
    assert result.lines_added > 0 and result.lines_deleted > 0
    assert "--- a/core/calculator.py" in result.diff
    assert "+    return left + right" in result.diff
    assert result.hashes["core/calculator.py"]["before_sha256"] != result.hashes[
        "core/calculator.py"
    ]["after_sha256"]


@pytest.mark.parametrize("bad_path", ["../outside.py", "/outside.py", "C:/outside.py"])
def test_paths_outside_workspace_are_rejected(tmp_path: Path, bad_path: str) -> None:
    workspace = _fixture_workspace(tmp_path)
    with pytest.raises(CandidateSourceError, match="PATH_FORBIDDEN"):
        CandidateSource(
            workspace,
            tmp_path / "sandbox",
            [bad_path],
            python_executable=Path(sys.executable),
        )


def test_test_only_and_noop_edits_are_rejected_before_any_write(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_calculator.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits(
            [{"path": "tests/test_calculator.py", "content": "def test_one(): assert True\n"}]
        )
    assert not (candidate.source_root / "tests" / "test_calculator.py").exists()

    current = (candidate.source_root / "core" / "calculator.py").read_text(encoding="utf-8")
    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits([{"path": "core/calculator.py", "content": current}])


def test_support_files_are_read_only_and_hermes_is_excluded(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py"],
        support_paths=["core"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    with pytest.raises(CandidateSourceError, match="not editable"):
        candidate.apply_edits([{"path": "core/helper.py", "content": "VALUE = 0\n"}])
    assert not (candidate.source_root / "core" / "hermes_bridge.py").exists()


def test_symlink_swap_cannot_redirect_an_edit_to_production(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    sandbox_file = candidate.source_root / "core" / "calculator.py"
    sandbox_file.unlink()
    try:
        os.symlink(workspace / "core" / "calculator.py", sandbox_file)
    except OSError:
        pytest.skip("symlink unavailable on this Windows account")
    production_before = (workspace / "core" / "calculator.py").read_bytes()

    with pytest.raises(CandidateSourceError, match="SYMLINK_FORBIDDEN"):
        candidate.apply_edits(
            [
                {
                    "path": "core/calculator.py",
                    "content": "def add(left, right): return left + right\n",
                }
            ]
        )
    assert (workspace / "core" / "calculator.py").read_bytes() == production_before


def test_real_pytest_proves_before_failure_and_after_pass_in_sandbox(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    original = (workspace / "core" / "calculator.py").read_bytes()
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_calculator.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    candidate.apply_edits(
        [
            {
                "path": "core/calculator.py",
                "content": "def add(left: int, right: int) -> int:\n    return left + right\n",
            },
            {
                "path": "tests/test_calculator.py",
                "content": "from core.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            },
        ]
    )

    before = candidate.run_pytest_baseline(["tests/test_calculator.py"], timeout_seconds=20)
    after = candidate.run_pytest(["tests/test_calculator.py"], timeout_seconds=20)

    assert before.exit_code != 0
    assert "FAILED" in before.stdout
    assert before.counts == {"collected": 1, "passed": 0, "failed": 1, "errors": 0,
                             "skipped": 0, "xfailed": 0, "xpassed": 0}
    assert after.exit_code == 0
    assert "passed" in after.stdout
    assert after.counts == {"collected": 1, "passed": 1, "failed": 0, "errors": 0,
                            "skipped": 0, "xfailed": 0, "xpassed": 0}
    assert before.test_hashes == after.test_hashes
    assert before.command[:3] == [str(Path(sys.executable).resolve()), "-I", "-c"]
    assert after.timed_out is False
    assert (workspace / "core" / "calculator.py").read_bytes() == original
    assert not (workspace / "tests" / "test_calculator.py").exists()


def test_pytest_rejects_unapproved_tests_and_bad_timeout(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    _write(workspace / "tests" / "test_existing.py", "def test_ok(): assert True\n")
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_existing.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    with pytest.raises(CandidateSourceError, match="TEST_NOT_AUTHORIZED"):
        candidate.run_pytest(["tests/other.py"])
    with pytest.raises(CandidateSourceError, match="TIMEOUT_LIMIT"):
        candidate.run_pytest(["tests/test_existing.py"], timeout_seconds=0)


def test_readonly_support_test_is_runnable_but_cannot_be_edited(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    test_path = workspace / "tests" / "test_existing_pipeline.py"
    _write(test_path, "from core.calculator import add\n\ndef test_existing_behavior():\n    assert add(5, 3) == 2\n")
    original_test = test_path.read_bytes()
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py"],
        support_paths=["tests/test_existing_pipeline.py"],
        readonly_test_paths=["tests/test_existing_pipeline.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    result = candidate.run_pytest(["tests/test_existing_pipeline.py"], timeout_seconds=20)

    assert result.exit_code == 0
    assert result.counts["collected"] == result.counts["passed"] == 1
    assert result.test_hashes["tests/test_existing_pipeline.py"]
    with pytest.raises(CandidateSourceError, match="not editable"):
        candidate.apply_edits([{"path": "tests/test_existing_pipeline.py", "content": "def test_lie(): assert True\n"}])
    assert test_path.read_bytes() == original_test


def test_generated_test_cannot_write_to_production_workspace(tmp_path: Path) -> None:
    workspace = _fixture_workspace(tmp_path)
    forbidden = workspace / "written-by-test.txt"
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_escape.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    candidate.apply_edits(
        [
            {
                "path": "core/calculator.py",
                "content": "def add(left: int, right: int) -> int:\n    return left + right\n",
            },
            {
                "path": "tests/test_escape.py",
                "content": (
                    "from pathlib import Path\n\n"
                    "def test_escape():\n"
                    f"    Path({str(forbidden)!r}).write_text('forbidden')\n"
                ),
            },
        ]
    )

    result = candidate.run_pytest(["tests/test_escape.py"], timeout_seconds=20)

    assert result.exit_code != 0
    assert "SANDBOX_WRITE_FORBIDDEN" in result.stdout + result.stderr
    assert not forbidden.exists()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "import socket\n\ndef test_network():\n    socket.create_connection(('127.0.0.1', 9))\n",
            "NETWORK_FORBIDDEN",
        ),
        (
            "import subprocess\n\ndef test_process():\n    subprocess.run(['cmd', '/c', 'exit', '0'])\n",
            "PROCESS_EXECUTION_FORBIDDEN",
        ),
    ],
)
def test_generated_test_cannot_open_provider_network_or_process(
    tmp_path: Path, body: str, expected: str
) -> None:
    workspace = _fixture_workspace(tmp_path)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        ["core/calculator.py", "tests/test_escape.py"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    candidate.apply_edits(
        [
            {
                "path": "core/calculator.py",
                "content": "def add(left: int, right: int) -> int:\n    return left + right\n",
            },
            {"path": "tests/test_escape.py", "content": body},
        ]
    )

    result = candidate.run_pytest(["tests/test_escape.py"], timeout_seconds=20)

    assert result.exit_code != 0
    assert expected in result.stdout + result.stderr
