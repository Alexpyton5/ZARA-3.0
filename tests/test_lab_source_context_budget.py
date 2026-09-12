"""The engine must not lie to itself about why a source step died.

Two defects, proved here together because they are the same incident:

1. ``core/lab_v1/source_mission.py`` asked ``read_context`` for the observed
   source with a 24 000 character budget. ``core/lab_v1/service.py`` alone is
   over 50 000 characters, so any mission that needed it raised
   ``CandidateSourceError("CONTEXT_LIMIT")``.
2. That exception landed in the generic ``except Exception`` of
   ``MissionController.tick``, which marked the step ``RECONCILE`` and blocked
   the mission with ``UNCERTAIN_EFFECT`` and no stored reason. A deterministic
   budget error became indistinguishable from a half-applied real action.

Fix under test: the failure is classified and persisted (Part A), and an
oversized file is delivered as an explicitly marked partial view with a
whole-file structure index instead of killing the step (Part B).

Nothing here touches the real Lab database or the owner's workspace: every path
lives in ``tmp_path`` and ``tests/conftest.py`` redirects ``ZARA3_HOME``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.lab_v1.candidate_source import (
    _PARTIAL_VIEW_MARKER,
    CandidateSource,
    CandidateSourceError,
    bounded_source_view,
    structure_index,
)
from core.lab_v1.mission_controller import classify_step_failure

REAL_SERVICE = Path(__file__).resolve().parents[1] / "core" / "lab_v1" / "service.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _candidate(tmp_path: Path, files: dict[str, str], *, allowed: list[str] | None = None) -> CandidateSource:
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    for relative, content in files.items():
        _write(workspace / relative, content)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        allowed if allowed is not None else list(files),
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    return candidate


def _padding(marker: str, chars: int) -> str:
    """Filler that is real Python and carries no words from any focus query."""
    body = []
    written = 0
    index = 0
    while written < chars:
        line = f"def {marker}_filler_{index}():\n    return {index}\n\n"
        body.append(line)
        written += len(line)
        index += 1
    return "".join(body)


# ---------------------------------------------------------------------------
# Scenario 1 - a file under the ceiling behaves exactly as before.
# ---------------------------------------------------------------------------

def test_small_file_is_delivered_complete_and_unmarked(tmp_path: Path) -> None:
    source = "def add(left, right):\n    return left + right\n"
    candidate = _candidate(tmp_path, {"core/calculator.py": source})

    for mode in ("error", "outline"):
        context = candidate.read_context(["core/calculator.py"], max_chars=24_000, on_overflow=mode)
        assert context["core/calculator.py"] == source, mode
        assert _PARTIAL_VIEW_MARKER not in context["core/calculator.py"], mode
        assert "OMITTED" not in context["core/calculator.py"], mode


# ---------------------------------------------------------------------------
# Scenario 2 - past the ceiling the old path died; the new path survives.
# ---------------------------------------------------------------------------

def test_file_over_the_ceiling_no_longer_kills_the_step(tmp_path: Path) -> None:
    source = _padding("big", 30_000)
    assert len(source) > 24_000
    candidate = _candidate(tmp_path, {"core/big.py": source})

    # The historical contract is intact, and is exactly the bug being fixed.
    with pytest.raises(CandidateSourceError, match="CONTEXT_LIMIT"):
        candidate.read_context(["core/big.py"], max_chars=24_000)

    view = candidate.read_context(["core/big.py"], max_chars=24_000, on_overflow="outline")["core/big.py"]

    assert _PARTIAL_VIEW_MARKER in view
    assert "THIS IS A PARTIAL VIEW" in view
    assert str(len(source)) in view  # the real size is stated
    assert "OMITTED" in view
    assert len(view) <= 24_000


def test_a_partial_view_can_never_be_written_back_as_the_whole_file(tmp_path: Path) -> None:
    source = _padding("big", 30_000)
    candidate = _candidate(tmp_path, {"core/big.py": source})
    view = candidate.read_context(["core/big.py"], max_chars=24_000, on_overflow="outline")["core/big.py"]

    with pytest.raises(CandidateSourceError, match="PARTIAL_VIEW_CONTENT_FORBIDDEN"):
        candidate.apply_edits([{"path": "core/big.py", "content": view}])

    assert (candidate.source_root / "core" / "big.py").read_text(encoding="utf-8") == source


# ---------------------------------------------------------------------------
# Scenario 3 - the real file that reproduced the incident.
# ---------------------------------------------------------------------------

def test_real_service_module_fits_the_budget_with_index_and_relevant_region(tmp_path: Path) -> None:
    source = REAL_SERVICE.read_text(encoding="utf-8")
    assert len(source) > 24_000, "fixture must stay the real oversized module"
    candidate = _candidate(tmp_path, {"core/lab_v1/service.py": source})

    with pytest.raises(CandidateSourceError, match="CONTEXT_LIMIT"):
        candidate.read_context(["core/lab_v1/service.py"], max_chars=24_000)

    view = candidate.read_context(
        ["core/lab_v1/service.py"], max_chars=24_000, on_overflow="outline",
        focus="capture_runtime_failure capability gap",
    )["core/lab_v1/service.py"]

    assert len(view) <= 24_000
    assert _PARTIAL_VIEW_MARKER in view
    # Whole-file structure index: every real definition is nameable.
    entries = structure_index(source, "core/lab_v1/service.py")
    assert len(entries) > 20
    assert "STRUCTURE INDEX" in view
    for entry in entries[:5]:
        assert f"L{entry['line']} " in view
    assert "def capture_runtime_failure" in view  # index entry
    # And the body of the region the focus points at is really present.
    body = view.split("### SOURCE (real line numbers, file order):", 1)[1]
    assert "def capture_runtime_failure" in body


# ---------------------------------------------------------------------------
# Scenario 4 - relevance is not "the first N characters".
# ---------------------------------------------------------------------------

def test_relevant_regions_at_start_middle_and_end_all_survive(tmp_path: Path) -> None:
    """The three targets sit at roughly 16%, 43% and 76% of the file, so none of
    them can be reached by the head/middle/tail fallback: only real relevance
    ranking puts all three in the delivered context."""
    first = "def wake_gate_normalises_utterance():\n    return 'brilho wake gate'\n\n"
    second = "def wake_gate_middle_probe():\n    return 'brilho wake gate middle'\n\n"
    third = "def wake_gate_tail_probe():\n    return 'brilho wake gate tail'\n\n"
    source = (_padding("alpha", 6_000) + first + _padding("beta", 10_000) + second
              + _padding("gamma", 12_000) + third + _padding("delta", 8_000))
    candidate = _candidate(tmp_path, {"core/spread.py": source})

    view = candidate.read_context(
        ["core/spread.py"], max_chars=12_000, on_overflow="outline",
        focus="wake gate probe brilho",
    )["core/spread.py"]

    body = view.split("### SOURCE (real line numbers, file order):", 1)[1]
    assert "wake_gate_normalises_utterance" in body, "first relevant region lost"
    assert "wake_gate_middle_probe" in body, "middle relevant region lost"
    assert "wake_gate_tail_probe" in body, "last relevant region lost"
    assert len(view) <= 12_000


def test_head_middle_and_tail_are_covered_even_without_a_focus(tmp_path: Path) -> None:
    source = _padding("alpha", 40_000)
    candidate = _candidate(tmp_path, {"core/spread.py": source})

    view = bounded_source_view("core/spread.py", source, 8_000, None)
    body = view.split("### SOURCE (real line numbers, file order):", 1)[1]
    total_lines = len(source.splitlines())

    assert "--- lines 1-" in body
    assert f"-{total_lines} ---" in body  # a region reaching the last real line
    assert candidate.source_root.is_dir()


# ---------------------------------------------------------------------------
# Scenario 5 - a different real error stays itself.
# ---------------------------------------------------------------------------

def test_a_non_budget_error_is_never_labelled_context_limit(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path, {"core/calculator.py": "VALUE = 1\n"})

    with pytest.raises(CandidateSourceError, match="not snapshotted") as absent:
        candidate.read_context(["core/does_not_exist.py"], max_chars=24_000, on_overflow="outline")
    with pytest.raises(CandidateSourceError, match="PATH_FORBIDDEN") as forbidden:
        candidate.read_context(["../escape.py"], max_chars=24_000, on_overflow="outline")

    for exc in (absent.value, forbidden.value):
        classified = classify_step_failure(exc)
        assert classified["kind"] == "UNCLASSIFIED_STEP_ERROR"
        assert classified["deterministic"] is False
        assert classified["uncertain_effect"] is True
        assert classified["blocker"] is None  # the controller keeps its safe default
        assert classified["error_code"] != "CONTEXT_LIMIT"


# ---------------------------------------------------------------------------
# Part A - the classification itself.
# ---------------------------------------------------------------------------

def test_context_limit_is_classified_as_deterministic_and_effect_free() -> None:
    classified = classify_step_failure(CandidateSourceError("CONTEXT_LIMIT"))

    assert classified["kind"] == "CONTEXT_BUDGET_EXCEEDED"
    assert classified["error_type"] == "CandidateSourceError"
    assert classified["error_code"] == "CONTEXT_LIMIT"
    assert classified["deterministic"] is True
    assert classified["effect"] == "NONE_NOTHING_EXECUTED"
    assert classified["uncertain_effect"] is False
    assert classified["blocker"] == "CONTEXT_BUDGET_EXCEEDED"


def test_an_arbitrary_exception_keeps_the_conservative_unknown_effect() -> None:
    classified = classify_step_failure(RuntimeError("disk exploded mid-write"))

    assert classified["kind"] == "UNCLASSIFIED_STEP_ERROR"
    assert classified["error_type"] == "RuntimeError"
    assert classified["deterministic"] is False
    assert classified["effect"] == "UNKNOWN"
    assert classified["message"] == "disk exploded mid-write"
    assert classified["blocker"] is None


def test_a_lookalike_message_from_another_class_is_not_a_budget_failure() -> None:
    classified = classify_step_failure(ValueError("CONTEXT_LIMIT"))

    assert classified["deterministic"] is False
    assert classified["kind"] == "UNCLASSIFIED_STEP_ERROR"


def _failing_mission(tmp_path: Path, error: Exception):
    """A real MissionController over an isolated database whose step raises."""
    from core.lab_v1.domain import AgentProfile, Session, Task, Team, TeamMembership
    from core.lab_v1.mission_controller import ExecutionScope, MissionController, MissionStep
    from core.lab_v1.store import LabStore

    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team("team", "Test Team"))
    store.save_agent(AgentProfile("agent", "Worker", "fake", "fake"))
    store.save_membership(TeamMembership("member", "team", "agent"))
    store.save_session(Session("session", "team", "Read an oversized module"))
    store.save_task(Task("task1", "session", "Read source", "Read the observed source",
                         "agent", assigned_agent_id="agent", acceptance="context is delivered"))
    scope = ExecutionScope(("provider:fake/fake",), ("model.invoke",),
                           authorization_state="POLICY_AUTHORIZED", authorization_ref="test-policy")
    controller = MissionController(store)
    controller.plan("session", [MissionStep("one", "task1", "INVOKE", (), "model.invoke",
                                            ("provider:fake/fake",))], scope=scope)

    class Ports:
        def execute(self, dispatch):
            raise error

        def verify(self, dispatch, receipt):  # pragma: no cover - never reached
            raise AssertionError("execution failed; verification must not run")

    return controller, "session", Ports()


def test_the_controller_persists_the_named_failure_on_the_step(tmp_path: Path) -> None:
    """The blocker and the reason survive in the mission document."""
    controller, session_id, ports = _failing_mission(
        tmp_path, CandidateSourceError("CONTEXT_LIMIT: budget 24000 exhausted")
    )
    snapshot = controller.tick(session_id, ports)

    assert snapshot["blocker"] == "CONTEXT_BUDGET_EXCEEDED"
    failure = snapshot["steps"][0]["failure"]
    assert failure["kind"] == "CONTEXT_BUDGET_EXCEEDED"
    assert failure["error_type"] == "CandidateSourceError"
    assert failure["uncertain_effect"] is False
    assert failure["effect"] == "NONE_NOTHING_EXECUTED"
    assert "budget 24000 exhausted" in failure["message"]
    assert snapshot["last_failure"] == failure


def test_the_controller_still_reports_unknown_effects_as_uncertain(tmp_path: Path) -> None:
    controller, session_id, ports = _failing_mission(tmp_path, RuntimeError("half-written file"))
    snapshot = controller.tick(session_id, ports)

    assert snapshot["blocker"] == "UNCERTAIN_EFFECT"
    assert snapshot["steps"][0]["status"] == "RECONCILE"
    failure = snapshot["steps"][0]["failure"]
    assert failure["kind"] == "UNCLASSIFIED_STEP_ERROR"
    assert failure["uncertain_effect"] is True
    assert failure["message"] == "half-written file"
