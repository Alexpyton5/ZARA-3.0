"""A draft the local executor refused is feedback, not an unknown effect.

Observed on 2026-09-10 (LAB-12, mission ``session_874d5dea5215``): the worker
returned a test-only edit, ``CandidateSource.apply_edits`` refused it with
``SOURCE_CHANGE_REQUIRED``, and the mission dead-ended on ``UNCERTAIN_EFFECT``
without ever reaching the independent reviewer.

``apply_edits`` evaluates the complete candidate BEFORE performing its first
write, so that refusal means nothing landed. These tests pin both halves of the
correction:

1. the refusal is classified deterministically, with effect
   ``NONE_NOTHING_EXECUTED`` and blocker ``PATCH_DRAFT_REJECTED``;
2. the rule itself is NOT relaxed - a test-only edit is still refused.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.lab_v1.candidate_source import CandidateSource, CandidateSourceError
from core.lab_v1.mission_controller import classify_step_failure


TEST_ONLY_EDIT = [
    {"path": "tests/test_calculator.py", "content": "def test_add():\n    assert True\n"},
]


def _candidate() -> CandidateSource:
    root = Path(tempfile.mkdtemp(prefix="draft-rejection-"))
    workspace = root / "workspace"
    (workspace / "core").mkdir(parents=True)
    (workspace / "core" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "core" / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    candidate = CandidateSource(
        workspace, root / "sandbox",
        ["core/calculator.py", "tests/test_calculator.py"],
        python_executable=Path("python"),
    )
    candidate.prepare()
    return candidate


# --------------------------------------------------------------------------
# 1. The refusal is a known fact, not an uncertain effect.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code",
    ["SOURCE_CHANGE_REQUIRED", "ANCHOR_NOT_FOUND", "ANCHOR_AMBIGUOUS",
     "PARTIAL_VIEW_CONTENT_FORBIDDEN", "EDIT_SCHEMA"],
)
def test_a_refused_draft_is_deterministic_and_names_its_blocker(code: str) -> None:
    classified = classify_step_failure(CandidateSourceError(code + ": detail"))

    assert classified["kind"] == "PATCH_DRAFT_REJECTED"
    assert classified["blocker"] == "PATCH_DRAFT_REJECTED"
    assert classified["deterministic"] is True
    assert classified["effect"] == "NONE_NOTHING_EXECUTED"
    assert classified["uncertain_effect"] is False
    assert classified["error_code"] == code


def test_a_context_budget_failure_keeps_its_own_classification() -> None:
    classified = classify_step_failure(CandidateSourceError("CONTEXT_LIMIT: budget spent"))

    assert classified["kind"] == "CONTEXT_BUDGET_EXCEEDED"
    assert classified["blocker"] == "CONTEXT_BUDGET_EXCEEDED"


def test_a_genuinely_unknown_effect_stays_uncertain() -> None:
    """The conservative default must survive: a half-written file is unknown."""
    classified = classify_step_failure(RuntimeError("disk died mid-write"))

    assert classified["kind"] == "UNCLASSIFIED_STEP_ERROR"
    assert classified["blocker"] is None
    assert classified["uncertain_effect"] is True
    assert classified["effect"] == "UNKNOWN"


def test_a_lookalike_message_from_another_class_is_not_a_draft_rejection() -> None:
    classified = classify_step_failure(ValueError("SOURCE_CHANGE_REQUIRED"))

    assert classified["kind"] == "UNCLASSIFIED_STEP_ERROR"
    assert classified["uncertain_effect"] is True


# --------------------------------------------------------------------------
# 2. Naming the refusal must not weaken it.
# --------------------------------------------------------------------------

def test_the_rule_itself_is_unchanged_a_test_only_edit_is_still_refused() -> None:
    candidate = _candidate()

    with pytest.raises(CandidateSourceError, match="SOURCE_CHANGE_REQUIRED"):
        candidate.apply_edits(TEST_ONLY_EDIT)

    # And nothing was written: the source file is still the untouched baseline.
    assert (candidate.source_root / "core" / "calculator.py").read_text(
        encoding="utf-8") == "def add(a, b):\n    return a - b\n"
    assert not (candidate.source_root / "tests" / "test_calculator.py").exists()


def test_a_draft_touching_real_source_is_still_accepted() -> None:
    candidate = _candidate()

    changed = candidate.apply_edits([
        {"path": "core/calculator.py", "content": "def add(a, b):\n    return a + b\n"},
        *TEST_ONLY_EDIT,
    ])

    assert "core/calculator.py" in str(changed)
    assert (candidate.source_root / "core" / "calculator.py").read_text(
        encoding="utf-8") == "def add(a, b):\n    return a + b\n"
