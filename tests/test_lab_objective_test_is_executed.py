"""The mission's objective test file must actually be EXECUTED by the tests step.

Observed 2026-09-11 (LAB-15, session_bddba03ea7c4). The owner asked for a flaky
test to be repaired. Everything worked: the builder produced a real patch
(``objective_files_changed=1``), the ``tests`` step produced a real
before-fail/after-pass receipt, and the mission reached the independent
reviewer. The reviewer refused it - correctly - with a defect nobody had seen:

    the repaired test itself was never executed, not once.

``SourceMission.execute`` ran pytest on ``self.meta['test_paths']`` only, which
is the single fixed regression file ``tests/test_zara_mission_regression.py``.
When the mission's objective IS a test file, that file lives in ``source_paths``
and therefore never reached the pytest command line. The before-fail/after-pass
proof was real, but it was a proof about the WRONG file.

These tests pin the correction and the protection it must not weaken:

1. production objective -> the executed set does not change at all;
2. test objective       -> the objective test is executed TOO, and the fixed
                           regression test is still executed (added, not
                           replaced);
3. real subprocess pytest, before/after the correction, on the LAB-15 shape:
   without the correction the objective test contributes nothing (1 collected,
   0 failed on baseline); with it, the objective test really runs and its real
   failure against the original source is really reported.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from core.lab_v1.source_mission import SourceMission, prepare_source

# --- The LAB-15 shape, reduced to its mechanism --------------------------------
# Original production module: the background cycle is only observable by sleeping
# next to it, which is exactly what makes the test flaky.
TICKER_BEFORE = (
    "import time\n"
    "\n"
    "\n"
    "def run_background_cycle():\n"
    "    time.sleep(0.001)\n"
    "    return None\n"
)
# Patched production module: the cycle exposes a real counter, so the test can
# observe a fact instead of guessing a duration.
TICKER_AFTER = (
    "import time\n"
    "\n"
    "_background_tick_count = 0\n"
    "\n"
    "\n"
    "def background_tick_count():\n"
    "    return _background_tick_count\n"
    "\n"
    "\n"
    "def run_background_cycle():\n"
    "    global _background_tick_count\n"
    "    time.sleep(0.001)\n"
    "    _background_tick_count += 1\n"
    "    return None\n"
)
# The mission objective: the flaky test, before and after repair.  The repaired
# version FAILS against TICKER_BEFORE (no counter exists) and PASSES against
# TICKER_AFTER.  That is the whole point: if it is never executed, nobody can
# tell those two apart.
FLAKY_TEST_BEFORE = (
    "import time\n"
    "\n"
    "from core.ticker import run_background_cycle\n"
    "\n"
    "\n"
    "def test_background_task_failure_is_visible_and_loop_survives():\n"
    "    run_background_cycle()\n"
    "    time.sleep(0.04)\n"
    "    assert True\n"
)
# Written so the failure against the original source is an ASSERTION failure,
# not an import/collection error: SourceMission.verify demands a baseline with
# exit_code 1 and zero errors, so a collection error would not even be a usable
# before-state.  This is the receipt shape a real mission has to produce.
FLAKY_TEST_AFTER = (
    "from core import ticker\n"
    "\n"
    "\n"
    "def _tick_count():\n"
    "    reader = getattr(ticker, 'background_tick_count', None)\n"
    "    return reader() if reader is not None else None\n"
    "\n"
    "\n"
    "def test_background_task_failure_is_visible_and_loop_survives():\n"
    "    before = _tick_count()\n"
    "    assert before is not None, 'the background cycle exposes no observable count'\n"
    "    ticker.run_background_cycle()\n"
    "    assert _tick_count() == before + 1\n"
)
# The mandatory fixed regression file.  It passes on both sides on purpose: it is
# the control that proves a green run says NOTHING about the objective test.
REGRESSION_TEST = (
    "def test_regression_control():\n"
    "    assert True\n"
)

REGRESSION_PATH = "tests/test_zara_mission_regression.py"
OBJECTIVE_TEST_PATH = "tests/test_lab_policy_facade.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    _write(workspace / "core" / "ticker.py", TICKER_BEFORE)
    _write(workspace / "memory" / "__init__.py", "")
    _write(workspace / "tests" / OBJECTIVE_TEST_PATH.split("/")[-1], FLAKY_TEST_BEFORE)
    _write(workspace / REGRESSION_PATH, REGRESSION_TEST)
    return workspace


def _mission(tmp_path: Path, *, source_paths, tests=(REGRESSION_PATH,), name="sandbox") -> SourceMission:
    """A real SourceMission bound to a real CandidateSource.

    Only the persistence engine is faked; the candidate, its snapshot and its
    pytest subprocess are the production objects.
    """
    workspace = _workspace(tmp_path)
    tests = list(tests)
    meta = {
        "workspace": str(workspace),
        "sandbox": str(tmp_path / name),
        "allowed_paths": list(dict.fromkeys(list(source_paths) + tests)),
        "source_paths": list(source_paths),
        "test_paths": tests,
        "support_paths": ["core", "memory"],
        "snapshot_state": "PENDING",
    }
    metrics = {"source_work": meta}
    engine = types.SimpleNamespace(
        store=None,
        metrics=lambda sid: metrics,
        _metrics=lambda sid, **changes: None,
    )
    mission = SourceMission(engine, "session_test")
    # The lab's default interpreter is the workspace .venv, which does not exist
    # inside a tmp_path workspace.  The running interpreter is the real thing.
    mission.candidate.python_executable = Path(sys.executable).resolve()
    return mission


# 1. PRODUCTION OBJECTIVE -> nothing changes.
#    This is the common case (a mission about core/*.py).  The correction must be
#    invisible here or it is a behaviour change smuggled in as a bug fix.
def test_production_objective_executes_only_the_fixed_regression_test(tmp_path: Path) -> None:
    mission = _mission(tmp_path, source_paths=["core/ticker.py"])

    assert mission.test_nodeids() == [REGRESSION_PATH]
    assert mission.test_nodeids() == mission.meta["test_paths"]


# 2. TEST OBJECTIVE -> the objective test is ADDED, never substituted.
def test_test_objective_adds_the_objective_test_to_the_executed_set(tmp_path: Path) -> None:
    mission = _mission(tmp_path, source_paths=[OBJECTIVE_TEST_PATH])

    nodeids = mission.test_nodeids()
    assert nodeids == [REGRESSION_PATH, OBJECTIVE_TEST_PATH]
    # The fixed regression test stays mandatory: this is coverage that was
    # missing, not coverage that was traded away.
    assert REGRESSION_PATH in nodeids


# 2b. MIXED OBJECTIVE (the LAB-14/15 intent named a test AND a module): the test
#     file joins the run, the production module does not become a pytest target.
def test_mixed_objective_adds_only_the_test_file(tmp_path: Path) -> None:
    mission = _mission(tmp_path, source_paths=[OBJECTIVE_TEST_PATH, "core/ticker.py"])

    nodeids = mission.test_nodeids()
    assert nodeids == [REGRESSION_PATH, OBJECTIVE_TEST_PATH]
    assert "core/ticker.py" not in nodeids


# 2c. If the objective test is ALSO already in the fixed test list, it must not
#     be run twice: duplicated nodeids double the collected count and corrupt the
#     before/after count comparison in SourceMission.verify.
def test_an_objective_test_already_in_test_paths_is_not_duplicated(tmp_path: Path) -> None:
    mission = _mission(
        tmp_path,
        source_paths=[OBJECTIVE_TEST_PATH],
        tests=(REGRESSION_PATH, OBJECTIVE_TEST_PATH),
    )

    nodeids = mission.test_nodeids()
    assert nodeids == [REGRESSION_PATH, OBJECTIVE_TEST_PATH]
    assert len(nodeids) == len(set(nodeids))


# 3. The real thing: a real pytest subprocess, on the real candidate, twice.
#    The FIRST run uses the OLD nodeid set (the LAB-15 bug, reproduced literally)
#    and the SECOND uses the corrected one.  Same sandbox, same patch, same
#    source: the only difference is which files pytest was told to run.
@pytest.mark.sandbox
def test_real_pytest_proves_the_objective_test_was_not_running_and_now_runs(tmp_path: Path) -> None:
    # The LAB-15 mission scope verbatim: the flaky test AND the timed mechanism
    # it observes are both in the objective.
    mission = _mission(tmp_path, source_paths=[OBJECTIVE_TEST_PATH, "core/ticker.py"])
    candidate = mission.candidate
    candidate.prepare()

    # The patch a builder would produce for this mission: repair the objective
    # test AND the timed mechanism it observes, plus the mandatory regression file.
    result = candidate.apply_edits([
        {"path": OBJECTIVE_TEST_PATH, "content": FLAKY_TEST_AFTER},
        {"path": "core/ticker.py", "content": TICKER_AFTER},
        {"path": REGRESSION_PATH, "content": REGRESSION_TEST + "\n"},
    ])
    assert result.objective_files_changed == 2

    # --- BEFORE the correction: the old behaviour, verbatim. -------------------
    old_nodeids = list(mission.meta["test_paths"])
    old_baseline = candidate.run_pytest_baseline(old_nodeids, timeout_seconds=90)
    old_candidate = candidate.run_pytest(old_nodeids, timeout_seconds=90)

    # A perfectly green, perfectly meaningless receipt: one control test, and the
    # objective test never even collected.
    assert old_baseline.counts["collected"] == 1
    assert old_candidate.counts["collected"] == 1
    assert OBJECTIVE_TEST_PATH not in old_baseline.test_hashes
    assert OBJECTIVE_TEST_PATH not in old_candidate.test_hashes
    assert not any(OBJECTIVE_TEST_PATH in str(part) for part in old_candidate.command)

    # --- AFTER the correction: the objective test is really executed. ----------
    new_nodeids = mission.test_nodeids()
    assert new_nodeids == [REGRESSION_PATH, OBJECTIVE_TEST_PATH]
    new_baseline = candidate.run_pytest_baseline(new_nodeids, timeout_seconds=90)
    new_candidate = candidate.run_pytest(new_nodeids, timeout_seconds=90)

    assert OBJECTIVE_TEST_PATH in new_baseline.test_hashes
    assert OBJECTIVE_TEST_PATH in new_candidate.test_hashes
    assert new_baseline.counts["collected"] == 2
    assert new_candidate.counts["collected"] == 2

    # 4. The objective test's REAL failure against the original source is really
    #    reported - it does not pass hidden behind a green control test.
    #    And it is reported in exactly the shape SourceMission.verify demands of
    #    a baseline: exit_code 1, a real failure, no collection error.
    assert new_baseline.exit_code == 1
    assert new_baseline.counts["failed"] == 1
    assert new_baseline.counts["errors"] == 0
    assert new_baseline.counts["passed"] == 1
    assert "test_background_task_failure_is_visible_and_loop_survives" in (
        new_baseline.stdout + new_baseline.stderr
    )

    # ...and it really passes on the candidate.
    assert new_candidate.exit_code == 0
    assert new_candidate.counts["passed"] == 2
    assert new_candidate.counts["failed"] == 0


# 5. The production meta path: prepare_source + SourceMission.__init__, with the
#    owner's real sentence.  No hand-built meta anywhere in this test.
def test_flaky_mission_meta_from_the_owner_intent_executes_the_named_test(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    engine_policy = types.SimpleNamespace(document={"workspace": str(workspace)})
    scope_engine = types.SimpleNamespace(policy=engine_policy)

    meta = prepare_source(
        scope_engine,
        tmp_path / "mission-sandbox",
        "Corrija o teste flaky em tests/test_lab_policy_facade.py no codigo da ZARA",
    )
    assert meta["source_paths"] == [OBJECTIVE_TEST_PATH]
    assert meta["test_paths"] == [REGRESSION_PATH]

    metrics = {"source_work": meta}
    engine = types.SimpleNamespace(
        store=None,
        metrics=lambda sid: metrics,
        _metrics=lambda sid, **changes: None,
    )
    mission = SourceMission(engine, "session_test")

    assert mission.test_nodeids() == [REGRESSION_PATH, OBJECTIVE_TEST_PATH]
    # And the executed set is a set the executor will accept: every entry is an
    # authorised, existing test file inside the candidate.
    mission.candidate.python_executable = Path(sys.executable).resolve()
    mission.candidate.prepare()
    assert candidate_accepts(mission, mission.test_nodeids())


def candidate_accepts(mission: SourceMission, nodeids: list[str]) -> bool:
    """The executor's own authorisation check, used as the acceptance oracle."""
    return mission.candidate._validated_test_nodeids(nodeids) == nodeids
