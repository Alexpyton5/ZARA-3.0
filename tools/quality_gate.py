"""Fail-closed quality gate for the complete ZARA test suite."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

BASELINE_SCHEMA = "zara.quality-gate-baseline.v1"
REPORT_SCHEMA = "zara.quality-gate-report.v1"
BASELINE_NAME = ".quality_gate_baseline.json"


class BaselineError(ValueError):
    pass


def _fingerprint(test_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(test_ids).encode("utf-8")).hexdigest()


def _parse_pytest_collect_output(output: str) -> list[str]:
    nodeids: set[str] = set()
    for line in output.splitlines():
        candidate = line.strip().replace("\\", "/")
        if candidate.startswith("tests/") and "::" in candidate:
            nodeids.add(candidate)
    return sorted(nodeids)


def _run_pytest(
    project_root: Path,
    *,
    collect_only: bool,
    timeout_seconds: int,
) -> tuple[int, str]:
    command = [sys.executable, "-m", "pytest", "tests"]
    if collect_only:
        command.append("--collect-only")
    command.extend(["-q", "-o", "addopts="])
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return 124, output
    except OSError as exc:
        return 125, str(exc)
    return result.returncode, result.stdout + result.stderr


def collect_tests(project_root: Path) -> tuple[int, list[str]]:
    exit_code, output = _run_pytest(project_root, collect_only=True, timeout_seconds=300)
    return exit_code, _parse_pytest_collect_output(output)


def execute_tests(project_root: Path) -> int:
    exit_code, _ = _run_pytest(project_root, collect_only=False, timeout_seconds=1800)
    return exit_code


def read_baseline(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (json.JSONDecodeError, OSError) as exc:
        raise BaselineError("baseline ilegivel") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "test_ids", "fingerprint"}:
        raise BaselineError("formato de baseline invalido")
    if payload["schema"] != BASELINE_SCHEMA:
        raise BaselineError("schema de baseline invalido")
    test_ids = payload["test_ids"]
    if (
        not isinstance(test_ids, list)
        or not test_ids
        or any(not isinstance(item, str) or not item.startswith("tests/") or "::" not in item for item in test_ids)
        or test_ids != sorted(set(test_ids))
    ):
        raise BaselineError("lista de nodeids invalida")
    fingerprint = payload["fingerprint"]
    if not isinstance(fingerprint, str) or fingerprint != _fingerprint(test_ids):
        raise BaselineError("fingerprint do baseline nao confere")
    return test_ids


def write_baseline(path: Path, test_ids: Sequence[str]) -> None:
    normalized = sorted(set(test_ids))
    if not normalized:
        raise BaselineError("baseline vazio recusado")
    payload = {
        "schema": BASELINE_SCHEMA,
        "test_ids": normalized,
        "fingerprint": _fingerprint(normalized),
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _report(
    *,
    verdict: str,
    reason: str,
    collect_exit: int | None = None,
    test_exit: int | None = None,
    baseline_count: int | None = None,
    current_count: int = 0,
    missing_nodeids: Sequence[str] = (),
    added_nodeids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "verdict": verdict,
        "reason": reason,
        "collect_exit": collect_exit,
        "test_exit": test_exit,
        "baseline_count": baseline_count,
        "current_count": current_count,
        "missing_nodeids": list(missing_nodeids),
        "added_nodeids": list(added_nodeids),
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None, project_root: Path | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--init-baseline"]):
        _emit(_report(verdict="fail", reason="invalid_argument"))
        return 2
    initialize = arguments == ["--init-baseline"]
    root = (Path(__file__).resolve().parent.parent if project_root is None else Path(project_root)).resolve()
    if not root.is_dir() or not (root / "tests").is_dir():
        _emit(_report(verdict="fail", reason="invalid_project_root"))
        return 2

    collect_exit, current_ids = collect_tests(root)
    if collect_exit != 0 or not current_ids:
        _emit(
            _report(
                verdict="fail",
                reason="collection_error" if collect_exit != 0 else "empty_collection",
                collect_exit=collect_exit,
                current_count=len(current_ids),
            )
        )
        return 1

    baseline_path = root / BASELINE_NAME
    baseline_ids: list[str] | None = None
    if not initialize:
        try:
            baseline_ids = read_baseline(baseline_path)
        except FileNotFoundError:
            _emit(
                _report(
                    verdict="fail",
                    reason="missing_baseline",
                    collect_exit=collect_exit,
                    current_count=len(current_ids),
                )
            )
            return 1
        except BaselineError:
            _emit(
                _report(
                    verdict="fail",
                    reason="invalid_baseline",
                    collect_exit=collect_exit,
                    current_count=len(current_ids),
                )
            )
            return 1

    baseline_set = set(baseline_ids or ())
    current_set = set(current_ids)
    missing = sorted(baseline_set - current_set)
    added = sorted(current_set - baseline_set)
    if missing:
        _emit(
            _report(
                verdict="fail",
                reason="missing_tests",
                collect_exit=collect_exit,
                baseline_count=len(baseline_ids or ()),
                current_count=len(current_ids),
                missing_nodeids=missing,
                added_nodeids=added,
            )
        )
        return 1

    test_exit = execute_tests(root)
    if test_exit != 0:
        _emit(
            _report(
                verdict="fail",
                reason="test_failure",
                collect_exit=collect_exit,
                test_exit=test_exit,
                baseline_count=None if initialize else len(baseline_ids or ()),
                current_count=len(current_ids),
                added_nodeids=added,
            )
        )
        return 1

    if initialize:
        try:
            write_baseline(baseline_path, current_ids)
        except (BaselineError, OSError):
            _emit(
                _report(
                    verdict="fail",
                    reason="baseline_write_error",
                    collect_exit=collect_exit,
                    test_exit=test_exit,
                    current_count=len(current_ids),
                )
            )
            return 1
        reason = "baseline_initialized"
        baseline_count = len(current_ids)
        added = []
    else:
        reason = "passed"
        baseline_count = len(baseline_ids or ())

    _emit(
        _report(
            verdict="pass",
            reason=reason,
            collect_exit=collect_exit,
            test_exit=test_exit,
            baseline_count=baseline_count,
            current_count=len(current_ids),
            added_nodeids=added,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
