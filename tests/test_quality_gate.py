from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import quality_gate


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    return tmp_path


def _baseline(path: Path, nodeids: list[str]) -> None:
    quality_gate.write_baseline(path / quality_gate.BASELINE_NAME, nodeids)


def _read_report(capsys) -> dict:
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {
        "schema",
        "verdict",
        "reason",
        "collect_exit",
        "test_exit",
        "baseline_count",
        "current_count",
        "missing_nodeids",
        "added_nodeids",
    }
    return report


def test_collect_parser_keeps_only_real_nodeids() -> None:
    output = "\n".join(
        [
            "warning: foo::bar",
            "tests\\test_a.py::TestGroup::test_one[param]",
            "tests/test_b.py::test_two",
            "2 tests collected in 0.1s",
        ]
    )
    assert quality_gate._parse_pytest_collect_output(output) == [
        "tests/test_a.py::TestGroup::test_one[param]",
        "tests/test_b.py::test_two",
    ]


def test_pytest_commands_are_fixed_to_tests_and_project_root(project: Path) -> None:
    completed = subprocess.CompletedProcess([], 0, "tests/test_a.py::test_a\n", "")
    with patch("tools.quality_gate.subprocess.run", return_value=completed) as run:
        quality_gate.collect_tests(project)
        quality_gate.execute_tests(project)
    collect_call, execute_call = run.call_args_list
    assert collect_call.args[0][-5:] == ["tests", "--collect-only", "-q", "-o", "addopts="]
    assert execute_call.args[0][-5:] == ["pytest", "tests", "-q", "-o", "addopts="]
    assert collect_call.kwargs["cwd"] == project
    assert execute_call.kwargs["cwd"] == project


@pytest.mark.parametrize("arguments", [["tests/test_one.py"], ["--ignore=tests"], ["--init-baseline", "extra"]])
def test_every_extra_argument_is_rejected_without_running_pytest(project: Path, arguments: list[str], capsys) -> None:
    with patch("tools.quality_gate.collect_tests") as collect:
        assert quality_gate.main(arguments, project) == 2
    collect.assert_not_called()
    assert _read_report(capsys)["reason"] == "invalid_argument"


def test_normal_mode_fails_closed_when_baseline_is_missing(project: Path, capsys) -> None:
    with patch("tools.quality_gate.collect_tests", return_value=(0, ["tests/test_a.py::test_a"])), patch(
        "tools.quality_gate.execute_tests"
    ) as execute:
        assert quality_gate.main([], project) == 1
    execute.assert_not_called()
    report = _read_report(capsys)
    assert report["reason"] == "missing_baseline"
    assert report["test_exit"] is None


def test_missing_nodeid_fails_even_if_another_was_added(project: Path, capsys) -> None:
    _baseline(project, ["tests/test_a.py::test_a", "tests/test_b.py::test_b"])
    current = ["tests/test_a.py::test_a", "tests/test_c.py::test_c"]
    with patch("tools.quality_gate.collect_tests", return_value=(0, current)), patch(
        "tools.quality_gate.execute_tests"
    ) as execute:
        assert quality_gate.main([], project) == 1
    execute.assert_not_called()
    report = _read_report(capsys)
    assert report["missing_nodeids"] == ["tests/test_b.py::test_b"]
    assert report["added_nodeids"] == ["tests/test_c.py::test_c"]


def test_collection_error_has_complete_machine_report(project: Path, capsys) -> None:
    with patch("tools.quality_gate.collect_tests", return_value=(2, [])):
        assert quality_gate.main([], project) == 1
    report = _read_report(capsys)
    assert report["verdict"] == "fail"
    assert report["collect_exit"] == 2
    assert report["test_exit"] is None


def test_test_failure_never_updates_existing_baseline(project: Path, capsys) -> None:
    path = project / quality_gate.BASELINE_NAME
    nodeids = ["tests/test_a.py::test_a"]
    _baseline(project, nodeids)
    before = path.read_bytes()
    with patch("tools.quality_gate.collect_tests", return_value=(0, nodeids)), patch(
        "tools.quality_gate.execute_tests", return_value=1
    ):
        assert quality_gate.main([], project) == 1
    assert path.read_bytes() == before
    report = _read_report(capsys)
    assert report["reason"] == "test_failure"
    assert report["test_exit"] == 1


def test_init_baseline_runs_full_suite_before_writing(project: Path, capsys) -> None:
    path = project / quality_gate.BASELINE_NAME
    nodeids = ["tests/test_a.py::test_a"]
    with patch("tools.quality_gate.collect_tests", return_value=(0, nodeids)), patch(
        "tools.quality_gate.execute_tests", return_value=1
    ):
        assert quality_gate.main(["--init-baseline"], project) == 1
    assert not path.exists()
    assert _read_report(capsys)["reason"] == "test_failure"


def test_init_baseline_is_explicit_atomic_and_only_after_green(project: Path, capsys) -> None:
    nodeids = ["tests/test_b.py::test_b", "tests/test_a.py::test_a"]
    with patch("tools.quality_gate.collect_tests", return_value=(0, nodeids)), patch(
        "tools.quality_gate.execute_tests", return_value=0
    ):
        assert quality_gate.main(["--init-baseline"], project) == 0
    baseline = quality_gate.read_baseline(project / quality_gate.BASELINE_NAME)
    assert baseline == sorted(nodeids)
    assert list(project.glob(".*.tmp")) == []
    assert _read_report(capsys)["reason"] == "baseline_initialized"


def test_tampered_fingerprint_is_rejected(project: Path) -> None:
    path = project / quality_gate.BASELINE_NAME
    _baseline(project, ["tests/test_a.py::test_a"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["test_ids"] = ["tests/test_deleted.py::test_deleted"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(quality_gate.BaselineError, match="fingerprint"):
        quality_gate.read_baseline(path)


def test_normal_green_run_reports_additions(project: Path, capsys) -> None:
    baseline = ["tests/test_a.py::test_a"]
    current = [*baseline, "tests/test_b.py::test_b"]
    _baseline(project, baseline)
    with patch("tools.quality_gate.collect_tests", return_value=(0, current)), patch(
        "tools.quality_gate.execute_tests", return_value=0
    ):
        assert quality_gate.main([], project) == 0
    report = _read_report(capsys)
    assert report["verdict"] == "pass"
    assert report["added_nodeids"] == ["tests/test_b.py::test_b"]
