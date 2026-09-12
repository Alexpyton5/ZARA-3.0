"""A partially viewed file may only be changed by anchored edits.

The incident this file exists for was observed in a real Run, not imagined.
TASK 1 gave oversized modules a bounded partial view (``ZARA_PARTIAL_SOURCE_VIEW``)
so a mission would stop dying on ``CONTEXT_LIMIT``. But the patch protocol still
asked the worker for "the complete file". A real Sonnet worker was honest and
returned the truncated excerpt it had actually seen; the executor's
``PARTIAL_VIEW_CONTENT_FORBIDDEN`` lock caught it. The honesty was the worker's,
not the protocol's: a less scrupulous model would have invented the ranges it
never read, and the invention would have been byte-perfect enough to land.

So the protocol changes: after a partial view, a full-file rewrite is refused and
an anchored edit is required. An anchor is exact current source text that occurs
exactly once. It either matches or it is rejected - never guessed, never fuzzed.

Nothing here touches the real Lab database or the owner's workspace: every path
lives in ``tmp_path`` and ``tests/conftest.py`` redirects ``ZARA3_HOME``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The mission-level proof reuses the real engine fixture, so the protocol is
# exercised through MissionController/SourceMission and a real pytest
# subprocess, not through a reimplementation of them.
import test_lab_source_mission

from core.lab_v1.candidate_source import (
    _PARTIAL_VIEW_MARKER,
    CandidateSource,
    CandidateSourceError,
    is_partial_view,
    structure_index,
)

source_engine = test_lab_source_mission.source_engine

REAL_SERVICE = Path(__file__).resolve().parents[1] / "core" / "lab_v1" / "service.py"

BUDGET = 24_000


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _candidate(tmp_path: Path, files: dict[str, str]) -> CandidateSource:
    workspace = tmp_path / "workspace"
    _write(workspace / "core" / "__init__.py", "")
    for relative, content in files.items():
        _write(workspace / relative, content)
    candidate = CandidateSource(
        workspace,
        tmp_path / "sandbox",
        list(files),
        python_executable=Path(sys.executable),
    )
    candidate.prepare()
    return candidate


def _padding(marker: str, chars: int) -> str:
    """Filler that is real Python and repeats no anchor used by a test."""
    body = []
    written = 0
    index = 0
    while written < chars:
        line = f"def {marker}_filler_{index}():\n    return {index}\n\n"
        body.append(line)
        written += len(line)
        index += 1
    return "".join(body)


def _current(candidate: CandidateSource, relative: str) -> str:
    return (candidate.source_root / relative).read_text(encoding="utf-8")


def _unique_top_level_signature(text: str, relative: str) -> str:
    for entry in structure_index(text, relative):
        if entry["depth"] == 0 and entry["signature"].startswith(("def ", "class ")):
            line = entry["signature"]
            if text.count(line + "\n") == 1:
                return line
    raise AssertionError("fixture has no unique top-level definition to anchor on")


# ---------------------------------------------------------------------------
# 1 - a file that fits keeps the old contract exactly.
# ---------------------------------------------------------------------------

def test_complete_view_still_allows_a_full_file_rewrite(tmp_path: Path) -> None:
    source = "def add(left, right):\n    return left + right\n"
    candidate = _candidate(tmp_path, {"core/calculator.py": source})

    view = candidate.read_context(["core/calculator.py"], max_chars=BUDGET, on_overflow="outline")
    assert view["core/calculator.py"] == source
    assert not is_partial_view(view["core/calculator.py"])
    assert candidate.context_views()["core/calculator.py"]["partial"] is False

    rewritten = "def add(left, right):\n    return int(left) + int(right)\n"
    result = candidate.apply_edits([{"path": "core/calculator.py", "content": rewritten}])

    assert _current(candidate, "core/calculator.py") == rewritten
    assert result.source_files_changed == 1
    assert result.edits_applied == [
        {"path": "core/calculator.py", "mode": "full_rewrite", "edits": []}
    ]


# ---------------------------------------------------------------------------
# 2 and 10 - past the ceiling, a full rewrite is refused. Both roads into the
# refusal are proved: the pasted excerpt (marker present) and the paraphrase
# (marker gone, unseen ranges still unseen).
# ---------------------------------------------------------------------------

def test_partial_view_refuses_a_full_file_rewrite(tmp_path: Path) -> None:
    source = _padding("big", 30_000)
    assert len(source) > BUDGET
    candidate = _candidate(tmp_path, {"core/big.py": source})
    view = candidate.read_context(["core/big.py"], max_chars=BUDGET, on_overflow="outline")["core/big.py"]
    assert is_partial_view(view)

    # Road 1: the worker pastes the excerpt back. Existing TASK 1 lock.
    with pytest.raises(CandidateSourceError, match="PARTIAL_VIEW_CONTENT_FORBIDDEN"):
        candidate.apply_edits([{"path": "core/big.py", "content": view}])

    # Road 2: the worker retypes only what it saw, so the marker is gone.
    # TASK 1 could not see this one; the ledger can.
    laundered = "\n".join(line for line in view.splitlines() if not line.startswith(("###", "---")))
    assert _PARTIAL_VIEW_MARKER not in laundered
    with pytest.raises(CandidateSourceError, match="PARTIAL_VIEW_CONTENT_FORBIDDEN") as refused:
        candidate.apply_edits([{"path": "core/big.py", "content": laundered}])
    assert "delivered as a partial view" in str(refused.value)
    assert "anchored_edits" in str(refused.value)

    # Neither attempt touched a byte.
    assert _current(candidate, "core/big.py") == source


# ---------------------------------------------------------------------------
# 3 - the real ~50 000 character module, end to end.
# ---------------------------------------------------------------------------

def test_real_service_module_accepts_an_anchored_edit_end_to_end(tmp_path: Path) -> None:
    source = REAL_SERVICE.read_text(encoding="utf-8")
    assert len(source) > 24_000, "fixture must stay the real oversized module"
    relative = "core/lab_v1/service.py"
    candidate = _candidate(tmp_path, {relative: source})

    view = candidate.read_context([relative], max_chars=BUDGET, on_overflow="outline",
                                  focus="capture_runtime_failure capability gap")[relative]
    assert is_partial_view(view)
    with pytest.raises(CandidateSourceError, match="PARTIAL_VIEW_CONTENT_FORBIDDEN"):
        candidate.apply_edits([{"path": relative, "content": source}])

    signature = _unique_top_level_signature(source, relative)
    result = candidate.apply_edits([{
        "path": relative,
        "anchored_edits": [{"find": signature + "\n",
                            "replace": "# ZARA-LAB-10 anchored insertion\n" + signature + "\n"}],
    }])

    after = _current(candidate, relative)
    expected = source.replace(signature + "\n", "# ZARA-LAB-10 anchored insertion\n" + signature + "\n", 1)
    assert after == expected
    assert len(after) == len(source) + len("# ZARA-LAB-10 anchored insertion\n")
    assert result.source_files_changed == 1
    assert "+# ZARA-LAB-10 anchored insertion" in result.diff
    applied = result.edits_applied[0]
    assert applied["mode"] == "anchored"
    assert applied["edits"][0]["preserved_prefix_chars"] + applied["edits"][0]["preserved_suffix_chars"] == (
        len(source) - len(signature) - 1
    )


# ---------------------------------------------------------------------------
# 4, 5, 6 and 11 - start, middle and end, each proved byte for byte.
# ---------------------------------------------------------------------------

@pytest.fixture
def spread(tmp_path: Path) -> tuple[CandidateSource, str]:
    """One oversized file with three unique, well separated landmarks."""
    source = (
        "HEAD_MARKER = 'start of file'\n\n"
        + _padding("alpha", 14_000)
        + "MIDDLE_MARKER = 'middle of file'\n\n"
        + _padding("beta", 14_000)
        + "TAIL_MARKER = 'end of file'\n"
    )
    candidate = _candidate(tmp_path, {"core/spread.py": source})
    delivered = candidate.read_context(["core/spread.py"], max_chars=BUDGET,
                                       on_overflow="outline")["core/spread.py"]
    assert is_partial_view(delivered), "the fixture must exercise the partial-view path"
    assert candidate.context_views()["core/spread.py"]["partial"] is True
    return candidate, source


@pytest.mark.parametrize(
    "find, replace",
    [
        ("HEAD_MARKER = 'start of file'", "HEAD_MARKER = 'start of file, edited'"),
        ("MIDDLE_MARKER = 'middle of file'", "MIDDLE_MARKER = 'middle of file, edited'"),
        ("TAIL_MARKER = 'end of file'", "TAIL_MARKER = 'end of file, edited'"),
    ],
    ids=["start", "middle", "end"],
)
def test_anchored_edit_at_any_position_preserves_every_other_byte(
    spread: tuple[CandidateSource, str], find: str, replace: str
) -> None:
    candidate, source = spread
    start = source.index(find)
    end = start + len(find)

    result = candidate.apply_edits([
        {"path": "core/spread.py", "anchored_edits": [{"find": find, "replace": replace}]}
    ])

    after = _current(candidate, "core/spread.py")
    # The postcondition, stated as bytes and not as a summary: the head and the
    # tail of the real file are identical, character for character.
    assert after[:start] == source[:start]
    assert after[start:start + len(replace)] == replace
    assert after[start + len(replace):] == source[end:]
    assert len(after) == len(source) - len(find) + len(replace)
    assert result.source_files_changed == 1
    record = result.edits_applied[0]["edits"][0]
    assert (record["start"], record["end"]) == (start, end)
    assert record["preserved_prefix_chars"] == start
    assert record["preserved_suffix_chars"] == len(source) - end


def test_ranges_the_worker_never_saw_survive_the_edit(spread: tuple[CandidateSource, str]) -> None:
    """The strongest form of "no silent truncation": the bytes inside the
    OMITTED ranges were never delivered to any model, and are still there."""
    candidate, source = spread
    view = candidate.read_context(["core/spread.py"], max_chars=BUDGET,
                                  on_overflow="outline")["core/spread.py"]
    lines = source.splitlines(keepends=True)
    omitted: list[str] = []
    for line in view.splitlines():
        if line.startswith("--- OMITTED lines "):
            span = line.split("--- OMITTED lines ", 1)[1].split(" ", 1)[0]
            first, _, last = span.partition("-")
            omitted.append("".join(lines[int(first) - 1:int(last)]))
    assert omitted, "the fixture must actually omit ranges"
    # The anchor is inside a region the worker really received, which is the
    # only kind of anchor a worker could honestly produce.
    anchor = "HEAD_MARKER = 'start of file'"
    assert anchor in view.split("### SOURCE (real line numbers, file order):", 1)[1]
    assert not any(anchor in chunk for chunk in omitted)

    candidate.apply_edits([{
        "path": "core/spread.py",
        "anchored_edits": [{"find": anchor, "replace": "HEAD_MARKER = 'start of file, edited'"}],
    }])

    after = _current(candidate, "core/spread.py")
    for chunk in omitted:
        assert chunk in after, "a range the worker never read was dropped"
    assert sum(len(chunk) for chunk in omitted) > 5_000


# ---------------------------------------------------------------------------
# 7 - an ambiguous anchor is never resolved by guessing.
# ---------------------------------------------------------------------------

def test_an_ambiguous_anchor_is_rejected_instead_of_guessed(spread) -> None:
    candidate, source = spread
    repeated = "    return 0\n"
    assert source.count(repeated) > 1

    with pytest.raises(CandidateSourceError, match="ANCHOR_AMBIGUOUS") as rejected:
        candidate.apply_edits([
            {"path": "core/spread.py", "anchored_edits": [{"find": repeated, "replace": "    return 1\n"}]}
        ])

    assert str(source.count(repeated)) in str(rejected.value)
    assert "occurrences" in str(rejected.value)
    assert _current(candidate, "core/spread.py") == source


def test_extending_an_ambiguous_anchor_until_it_is_unique_is_accepted(spread) -> None:
    candidate, source = spread
    unique = "def alpha_filler_7():\n    return 7\n"
    assert source.count(unique) == 1

    candidate.apply_edits([
        {"path": "core/spread.py",
         "anchored_edits": [{"find": unique, "replace": "def alpha_filler_7():\n    return 700\n"}]}
    ])

    assert _current(candidate, "core/spread.py") == source.replace(
        unique, "def alpha_filler_7():\n    return 700\n", 1)


# ---------------------------------------------------------------------------
# 8 - an anchor that does not exist in the real source.
# ---------------------------------------------------------------------------

def test_an_absent_anchor_is_rejected_with_an_explicit_replan_instruction(spread) -> None:
    candidate, source = spread

    with pytest.raises(CandidateSourceError, match="ANCHOR_NOT_FOUND") as rejected:
        candidate.apply_edits([{
            "path": "core/spread.py",
            "anchored_edits": [{"find": "def function_the_model_imagined():\n    pass\n",
                                "replace": "def function_the_model_imagined():\n    return 1\n"}],
        }])

    message = str(rejected.value)
    assert "not in the current source" in message
    assert "replan" in message
    assert "nothing was applied" in message
    assert _current(candidate, "core/spread.py") == source


def test_a_batch_is_all_or_nothing_when_a_later_anchor_is_absent(spread) -> None:
    """The first anchor is real; the second is not. Nothing may land."""
    candidate, source = spread

    with pytest.raises(CandidateSourceError, match="ANCHOR_NOT_FOUND"):
        candidate.apply_edits([{
            "path": "core/spread.py",
            "anchored_edits": [
                {"find": "HEAD_MARKER = 'start of file'", "replace": "HEAD_MARKER = 'edited'"},
                {"find": "NEVER_EXISTED_MARKER", "replace": "x"},
            ],
        }])

    assert _current(candidate, "core/spread.py") == source


# ---------------------------------------------------------------------------
# 9 - the source moved after the worker planned against it.
# ---------------------------------------------------------------------------

def test_source_drift_after_planning_is_rejected_even_when_the_anchor_matches(spread) -> None:
    candidate, source = spread
    planned = candidate.context_views()["core/spread.py"]["sha256"]

    # Someone else changed the candidate between planning and applying. The
    # worker's anchor is still findable, which is exactly the dangerous case.
    drifted = source.replace("TAIL_MARKER = 'end of file'", "TAIL_MARKER = 'changed by someone else'")
    (candidate.source_root / "core" / "spread.py").write_text(drifted, encoding="utf-8")

    with pytest.raises(CandidateSourceError, match="SOURCE_DRIFT") as rejected:
        candidate.apply_edits([{
            "path": "core/spread.py",
            "anchored_edits": [{"find": "HEAD_MARKER = 'start of file'",
                                "replace": "HEAD_MARKER = 'start of file, edited'"}],
        }])

    message = str(rejected.value)
    assert planned[:12] in message
    assert "replan" in message
    assert _current(candidate, "core/spread.py") == drifted, "the drifted state must be untouched"

    # A fresh read re-binds the plan to the real bytes, and the edit lands.
    candidate.read_context(["core/spread.py"], max_chars=BUDGET, on_overflow="outline")
    candidate.apply_edits([{
        "path": "core/spread.py",
        "anchored_edits": [{"find": "HEAD_MARKER = 'start of file'",
                            "replace": "HEAD_MARKER = 'start of file, edited'"}],
    }])
    assert _current(candidate, "core/spread.py") == drifted.replace(
        "HEAD_MARKER = 'start of file'", "HEAD_MARKER = 'start of file, edited'")


# ---------------------------------------------------------------------------
# Schema guards that keep the two shapes from blurring into each other.
# ---------------------------------------------------------------------------

def test_an_edit_must_choose_exactly_one_shape(spread) -> None:
    candidate, source = spread
    both = {"path": "core/spread.py", "content": source,
            "anchored_edits": [{"find": "HEAD_MARKER", "replace": "HEAD"}]}
    neither = {"path": "core/spread.py"}

    for edit in (both, neither):
        with pytest.raises(CandidateSourceError, match="exactly one of content or anchored_edits"):
            candidate.apply_edits([edit])
    assert _current(candidate, "core/spread.py") == source


def test_an_empty_or_whitespace_anchor_is_refused(spread) -> None:
    candidate, source = spread
    for anchor in ("", "   \n"):
        with pytest.raises(CandidateSourceError, match="ANCHOR_EMPTY"):
            candidate.apply_edits([
                {"path": "core/spread.py", "anchored_edits": [{"find": anchor, "replace": "x = 1\n"}]}
            ])
    assert _current(candidate, "core/spread.py") == source


def test_an_anchored_edit_that_breaks_python_syntax_is_refused(spread) -> None:
    candidate, source = spread
    with pytest.raises(CandidateSourceError, match="ANCHORED_EDIT_SYNTAX"):
        candidate.apply_edits([{
            "path": "core/spread.py",
            "anchored_edits": [{"find": "HEAD_MARKER = 'start of file'", "replace": "HEAD_MARKER = ("}],
        }])
    assert _current(candidate, "core/spread.py") == source


# ---------------------------------------------------------------------------
# Mission level: the protocol as SourceMission really runs it.
# ---------------------------------------------------------------------------

def _oversized_example(workspace: Path) -> str:
    """Make the mission's observed module genuinely bigger than its budget."""
    source = (_padding("legacy", 60_000) + "def twice(n):\n    return n + 2\n")
    (workspace / "core" / "example.py").write_text(source, encoding="utf-8")
    return source


def _builder_reply(edits: list[dict]) -> str:
    return json.dumps({"edits": edits, "summary": "Unit fixture implementation, not a real contribution."})


def _patch_builder(source_engine, monkeypatch, edits: list[dict]) -> None:
    adapter = source_engine.runtime.registry.get("unit-only")
    original = adapter.complete
    from core.lab_v1.domain import Availability, ProviderResult

    def replaced(**kwargs):
        if kwargs["model"] != "builder":
            return original(**kwargs)
        return ProviderResult(True, text=_builder_reply(edits), availability=Availability.AVAILABLE,
                              model_reported="builder", provider_session_id="unit-fixture",
                              input_tokens=1, output_tokens=1)

    monkeypatch.setattr(adapter, "complete", replaced)


REGRESSION_TEST = (
    "from core.example import twice\n"
    "def test_behavior():\n"
    "    assert twice(3) == 6\n"
    "    assert twice(-2) == -4\n"
    "    assert twice(0) == 0\n"
)


def test_mission_applies_an_anchored_edit_to_a_partially_viewed_module(source_engine, monkeypatch):
    workspace = Path(source_engine.policy.document["workspace"])
    source = _oversized_example(workspace)
    _patch_builder(source_engine, monkeypatch, [
        {"path": "core/example.py",
         "anchored_edits": [{"find": "def twice(n):\n    return n + 2\n",
                             "replace": "def twice(n):\n    return n * 2\n"}]},
        {"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST},
    ])

    sid = source_engine.start("Corrija a ZARA core/example.py: twice deve duplicar também negativos.")["session_id"]
    result = source_engine.run(sid)

    meta = source_engine.metrics(sid)["source_work"]
    assert result["state"] == "COMPLETED", [
        (a.kind, a.body[:600]) for a in source_engine.store.list_artifacts(sid)
        if a.kind == "SOURCE_VERIFICATION"
    ]
    assert meta["partial_view_paths"] == ["core/example.py"]
    assert meta["change_evidence"]["source_files_changed"] == 1
    modes = {item["path"]: item["mode"] for item in meta["change_evidence"]["edits_applied"]}
    assert modes["core/example.py"] == "anchored"
    assert modes["tests/test_zara_mission_regression.py"] == "full_rewrite"
    assert meta["test_evidence"]["baseline"]["exit_code"] == 1
    assert meta["test_evidence"]["candidate"]["exit_code"] == 0

    candidate_text = (Path(meta["sandbox"]) / "source" / "core" / "example.py").read_text(encoding="utf-8")
    assert candidate_text == source.replace("return n + 2", "return n * 2")
    # Production is untouched, as always.
    assert (workspace / "core" / "example.py").read_text(encoding="utf-8") == source


def test_mission_refuses_a_full_rewrite_of_a_partially_viewed_module(source_engine, monkeypatch):
    workspace = Path(source_engine.policy.document["workspace"])
    source = _oversized_example(workspace)
    _patch_builder(source_engine, monkeypatch, [
        {"path": "core/example.py", "content": "def twice(n):\n    return n * 2\n"},
        {"path": "tests/test_zara_mission_regression.py", "content": REGRESSION_TEST},
    ])

    sid = source_engine.start("Corrija a ZARA core/example.py: twice deve duplicar também negativos.")["session_id"]
    result = source_engine.run(sid)

    assert result["state"] != "COMPLETED"
    failures = [json.loads(a.body) for a in source_engine.store.list_artifacts(sid)
                if a.kind == "SOURCE_VERIFICATION"]
    assert any("PARTIAL_VIEW_CONTENT_FORBIDDEN" in item.get("error", "") for item in failures), failures
    # The 60 000 characters the worker never read are still in the candidate.
    assert (Path(source_engine.metrics(sid)["source_work"]["sandbox"]) / "source" / "core" / "example.py"
            ).read_text(encoding="utf-8") == source
