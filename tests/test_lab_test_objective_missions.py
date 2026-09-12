"""A mission whose objective IS a test file must be able to finish.

Observed 2026-09-10 (LAB-14, session_3eef24967dc3): the owner asked for a flaky
test to be repaired. Two rules that are individually correct made that mission
unwinnable together:

* ``SourceMission.verify`` refuses a draft that does not touch the mission's
  regression test (``REAL_REGRESSION_TEST_REQUIRED``) and does not touch the
  mission's own scope (``REAL_SOURCE_REQUIRED``);
* ``CandidateSource.apply_edits`` refused any candidate in which no NON-test
  file changed (``SOURCE_CHANGE_REQUIRED: test-only or no-op edit``).

When the scope itself is a test file, every draft that satisfies the first rule
violates the second. The mission burned its repair budget oscillating between
the two and died on ``REPAIR_LIMIT_AFTER_REPLAN`` before any real work started.

These tests pin the fix AND the protection it must not weaken:

1. production objective + test-only edit  -> still refused (the original rule);
2. test objective + edit of that test     -> accepted;
3. test objective, worker edits some OTHER test instead -> still refused;
4. mixed objective (production + test), test-only edit  -> still refused.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.lab_v1.candidate_source import CandidateSource, CandidateSourceError

FLAKY_TEST = (
    "import time\n"
    "\n"
    "\n"
    "def test_background_task_failure_is_visible_and_loop_survives():\n"
    "    time.sleep(0.01)\n"
    "    assert True\n"
)
REPAIRED_TEST = (
    "import time\n"
    "\n"
    "\n"
    "def test_background_task_failure_is_visible_and_loop_survives():\n"
    "    deadline = time.monotonic() + 2.0\n"
    "    while time.monotonic() < deadline:\n"
    "        break\n"
    "    assert True\n"
)
REGRESSION_TEST = "def test_regression():\n    assert True\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    _write(workspace / "core" / "calculator.py", "def add(a, b):\n    return a - b\n")
    _write(workspace / "tests" / "test_lab_policy_facade.py", FLAKY_TEST)
    return workspace


def _candidate(tmp_path: Path, *, allowed, objective, name="sandbox") -> CandidateSource:
    candidate = CandidateSource(
        _workspace(tmp_path),
        tmp_path / name,
        allowed,
        objective_paths=objective,
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    return candidate


# 1. The original protection, unchanged: the mission is about production code,
#    so a test-only candidate is the worker dodging the work.
def test_production_objective_still_refuses_a_test_only_edit(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=["core/calculator.py", "tests/test_zara_mission_regression.py"],
        objective=["core/calculator.py"],
    )

    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits(
            [{"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST}]
        )

    # Refused before the first write: nothing landed.
    assert not (candidate.source_root / "tests" / "test_zara_mission_regression.py").exists()
    assert (candidate.source_root / "core" / "calculator.py").read_text(
        encoding="utf-8") == "def add(a, b):\n    return a - b\n"


# 2. The mission the owner actually asked for: the objective IS the test file,
#    so editing it (plus the required regression test) is the correct patch.
def test_test_objective_accepts_editing_only_test_files(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=["tests/test_lab_policy_facade.py", "tests/test_zara_mission_regression.py"],
        objective=["tests/test_lab_policy_facade.py"],
    )

    result = candidate.apply_edits([
        {"path": "tests/test_lab_policy_facade.py", "content": REPAIRED_TEST},
        {"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST},
    ])

    assert result.files_changed == 2
    # Truthful evidence: zero production files changed, and the mission's own
    # objective file did change. Nothing pretends a module was touched.
    assert result.source_files_changed == 0
    assert result.objective_files_changed == 1
    assert (candidate.source_root / "tests" / "test_lab_policy_facade.py").read_text(
        encoding="utf-8") == REPAIRED_TEST
    assert result.to_dict()["objective_files_changed"] == 1


# 3. The escape hatch stays shut: a test objective does not license editing ANY
#    test file. The objective file itself has to change.
def test_test_objective_refuses_edits_that_avoid_the_objective_test(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=["tests/test_lab_policy_facade.py", "tests/test_zara_mission_regression.py"],
        objective=["tests/test_lab_policy_facade.py"],
    )

    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits(
            [{"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST}]
        )

    assert not (candidate.source_root / "tests" / "test_zara_mission_regression.py").exists()


# 4. The LAB-14 objective verbatim: the owner named a test AND a module and said
#    "fix the test OR the timed mechanism". Both are in the mission scope, so the
#    branch the owner explicitly offered must be reachable.
def test_mixed_objective_accepts_fixing_the_named_test(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=[
            "core/calculator.py",
            "tests/test_lab_policy_facade.py",
            "tests/test_zara_mission_regression.py",
        ],
        objective=["tests/test_lab_policy_facade.py", "core/calculator.py"],
    )

    result = candidate.apply_edits([
        {"path": "tests/test_lab_policy_facade.py", "content": REPAIRED_TEST},
        {"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST},
    ])

    assert result.objective_files_changed == 1
    assert result.source_files_changed == 0


# 4b. Same mixed objective, but the worker touches neither named file - only the
#     mandatory regression test. That is the dodge, and it stays refused.
def test_mixed_objective_refuses_edits_that_touch_no_objective_file(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=[
            "core/calculator.py",
            "tests/test_lab_policy_facade.py",
            "tests/test_zara_mission_regression.py",
        ],
        objective=["tests/test_lab_policy_facade.py", "core/calculator.py"],
    )

    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits(
            [{"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST}]
        )

    assert (candidate.source_root / "tests" / "test_lab_policy_facade.py").read_text(
        encoding="utf-8") == FLAKY_TEST


# 5. No objective declared (legacy meta, older sessions) behaves exactly as the
#    engine did before this change.
def test_missing_objective_keeps_the_legacy_rule(tmp_path: Path) -> None:
    candidate = _candidate(
        tmp_path,
        allowed=["tests/test_lab_policy_facade.py", "tests/test_zara_mission_regression.py"],
        objective=(),
    )

    with pytest.raises(CandidateSourceError, match="test-only or no-op edit"):
        candidate.apply_edits(
            [{"path": "tests/test_lab_policy_facade.py", "content": REPAIRED_TEST}]
        )


# 7. The whole composition: the owner asks for a flaky test to be fixed, the
#    scope selector makes that test the mission objective, and the candidate
#    built from that meta accepts the test-only patch the mission requires.
#    Before this change this exact meta could not produce ANY acceptable patch:
#    the verifier demanded the regression test plus a source_paths file, and
#    both of them were test files, so apply_edits refused every draft.
def test_flaky_test_mission_end_to_end_scope_and_apply(tmp_path: Path) -> None:
    import types

    from core.lab_v1.source_mission import prepare_source

    workspace = _workspace(tmp_path)
    _write(workspace / "tests" / "test_zara_mission_regression.py", REGRESSION_TEST)
    _write(workspace / "memory" / "__init__.py", "")
    engine = types.SimpleNamespace(
        policy=types.SimpleNamespace(document={"workspace": str(workspace)})
    )

    meta = prepare_source(
        engine,
        tmp_path / "mission-sandbox",
        "Corrija o teste flaky em tests/test_lab_policy_facade.py no codigo da ZARA",
    )

    assert meta["source_paths"] == ["tests/test_lab_policy_facade.py"]
    assert meta["test_paths"] == ["tests/test_zara_mission_regression.py"]

    # Built exactly as SourceMission.__init__ builds it.
    candidate = CandidateSource(
        Path(meta["workspace"]),
        Path(meta["sandbox"]),
        meta["allowed_paths"],
        support_paths=meta["support_paths"],
        objective_paths=meta["source_paths"],
        python_executable=Path(sys.executable),
    )
    candidate.prepare()

    # The only patch shape SourceMission.verify accepts for this mission:
    # every test_paths file, plus at least one source_paths file.
    result = candidate.apply_edits([
        {"path": "tests/test_lab_policy_facade.py", "content": REPAIRED_TEST},
        {"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST + "\n"},
    ])

    assert result.objective_files_changed == 1
    assert result.source_files_changed == 0


# 6. The objective cannot name a file the mission may not edit.
def test_objective_outside_the_editable_boundary_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CandidateSourceError, match="OBJECTIVE_PATH_NOT_EDITABLE"):
        CandidateSource(
            _workspace(tmp_path),
            tmp_path / "sandbox",
            ["core/calculator.py"],
            objective_paths=["core/helper.py"],
            python_executable=Path(sys.executable),
        )
