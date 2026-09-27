"""Pure evidence contracts for the Lab's real-work path.

The functions here deliberately receive persisted domain records and an
already-instantiated adapter.  They do not call providers, write the store, or
decide which role should be selected.  This keeps an attractive UI claim from
becoming evidence by itself.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import import_module
import math
import re
from typing import Any

from core.lab_v1.domain import RunState


class RealWorkContractError(ValueError):
    """A proposed plan or proof does not meet the real-work contract."""


class ReviewResponseContractError(RealWorkContractError):
    """The reviewer's OWN answer is malformed; it says nothing about the patch.

    Kept distinct so a caller can tell "the reviewer typed a bad envelope" from
    "the reviewed work was refused" and hand the defect back to the right worker.
    """


# A review rationale is long-form model prose over the whole diff, the test
# subprocess output and the preservation receipt.  Calibrated from the three
# real Opus reviews of mission ``session_ff9f6c94874e`` (3504, 4228 and 4411
# characters) and aligned with the architect's ``replan_repair`` rationale,
# which this pipeline already bounds at 6000.  The previous 2000 cut a genuine
# PASS in half and refused it as malformed.
REVIEW_RATIONALE_LIMIT = 6000


_BANNED_PLANNER_KEYS = frozenset({"final_answer", "content", "code", "solution", "fixture"})
_SOURCE_CAPABILITIES = {
    "source.patch": ("patch.json", "source_changed"),
    "source.tests": ("tests.json", "pytest"),
    "source.review": ("review.json", "independent_review"),
}
_TASK_KEYS = frozenset({
    "id", "title", "instruction", "objective", "role", "capability", "path",
    "depends_on", "risk", "repair_budget", "acceptance", "metadata",
})
_METADATA_KEYS = frozenset({"constraints", "estimated_complexity", "priority", "tags"})
_SCHEMA_EMBEDDED_ANSWER_KEYS = frozenset({"const", "default", "example", "examples", "enum"})
_SCALAR = (str, int, float, bool, type(None))
_PRODUCTION_ADAPTERS = frozenset({
    "core.lab_v1.providers.registry.AnthropicApiAdapter",
    "core.lab_v1.providers.nvidia.NvidiaApiAdapter",
    "core.lab_v1.providers.claude_cli.ClaudeCliAdapter",
    "core.lab_v1.providers.codex_app_server.CodexAppServerAdapter",
    "core.lab_v1.providers.harness.DeepSeekHarnessAdapter",
})


def _row(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise RealWorkContractError("A persisted record must be an object")
    return dict(value)


def _state(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _require_text(value: Any, label: str, *, limit: int = 4000,
                  error: type[RealWorkContractError] = RealWorkContractError) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise error(f"{label} must be bounded non-empty text of at most {limit} characters")
    return value.strip()


def _reject_artifact_payload(text: str, label: str) -> None:
    if "```" in text:
        raise RealWorkContractError(f"{label} cannot carry a code fence")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    artifact_lines = sum(bool(re.match(r"(?:def |class |import |from |return |[{\[]|<\?xml)", line)) for line in lines)
    if len(lines) > 1 and artifact_lines:
        raise RealWorkContractError(f"{label} cannot carry a multiline artifact answer")


def reject_planner_solution_material(value: Any, *, _path: str = "planner") -> None:
    """Reject final answers hidden anywhere in a planner envelope or metadata."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            folded = str(key).strip().casefold()
            if folded in _BANNED_PLANNER_KEYS:
                raise RealWorkContractError(f"{_path}.{key} is forbidden planner solution material")
            reject_planner_solution_material(child, _path=f"{_path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_planner_solution_material(child, _path=f"{_path}[{index}]")


def _validate_python_cases(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    if set(acceptance) != {"method", "cases"} or acceptance.get("method") != "python_cases":
        raise RealWorkContractError("python_cases accepts only method and cases")
    cases = acceptance.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise RealWorkContractError("python_cases needs 1 to 20 cases")
    normalized = []
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping) or set(case) != {"function", "args", "expected"}:
            raise RealWorkContractError(f"python case {index} is not a behavioral case")
        function = _require_text(case.get("function"), f"python case {index}.function", limit=120)
        args = case.get("args")
        expected = case.get("expected")
        if (not isinstance(args, list) or not isinstance(expected, _SCALAR)
                or (isinstance(expected, str) and len(expected) > 512)
                or (isinstance(expected, float) and not math.isfinite(expected))):
            raise RealWorkContractError(f"python case {index} needs list args and scalar expected")
        normalized.append({"function": function, "args": list(args), "expected": expected})
    return {"method": "python_cases", "cases": normalized}


def _validate_text_constraints(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"method", "min_chars", "max_chars", "required_sections"}
    if acceptance.get("method") != "constraints" or set(acceptance) - allowed:
        raise RealWorkContractError("text acceptance must use measurable constraints")
    minimum, maximum = acceptance.get("min_chars"), acceptance.get("max_chars")
    sections = acceptance.get("required_sections", [])
    if (not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1
            or minimum > maximum or maximum > 100_000
            or not isinstance(sections, list)
            or not all(isinstance(item, str) and re.fullmatch(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 /:&()_-]{0,79}", item.strip())
                       for item in sections)):
        raise RealWorkContractError("invalid text constraints")
    return {"method": "constraints", "min_chars": minimum, "max_chars": maximum,
            "required_sections": [item.strip() for item in sections]}


def _validate_json_schema(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    if set(acceptance) != {"method", "schema"} or acceptance.get("method") != "json_schema":
        raise RealWorkContractError("json acceptance must contain a schema")
    schema = acceptance.get("schema")
    if not isinstance(schema, Mapping) or not schema or len(repr(schema)) > 12_000:
        raise RealWorkContractError("json schema must be a bounded object")
    # A schema describes structure; constants/defaults/examples are a final
    # answer hidden in a schema-shaped envelope, not a postcondition.
    reject_planner_solution_material(schema, _path="acceptance.schema")
    _reject_schema_embedded_answers(schema)
    return {"method": "json_schema", "schema": dict(schema)}


def _reject_schema_embedded_answers(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in _SCHEMA_EMBEDDED_ANSWER_KEYS:
                raise RealWorkContractError("json schema cannot embed constants, defaults, enums, or examples")
            _reject_schema_embedded_answers(child)
    elif isinstance(value, list):
        for child in value:
            _reject_schema_embedded_answers(child)


def _validate_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, Mapping) or set(metadata) - _METADATA_KEYS:
        raise RealWorkContractError("planner metadata has unsupported fields")
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"constraints", "tags"}:
            if (not isinstance(value, list) or len(value) > 20
                    or not all(isinstance(item, str) and 0 < len(item.strip()) <= 160 for item in value)):
                raise RealWorkContractError(f"planner metadata {key} is invalid")
            result[key] = [item.strip() for item in value]
        elif key == "estimated_complexity":
            if value not in {"LOW", "MEDIUM", "HIGH"}:
                raise RealWorkContractError("planner metadata estimated_complexity is invalid")
            result[key] = value
        elif key == "priority":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                raise RealWorkContractError("planner metadata priority is invalid")
            result[key] = value
    return result


def _validate_source_acceptance(capability: str, acceptance: Mapping[str, Any]) -> dict[str, Any]:
    _, method = _SOURCE_CAPABILITIES[capability]
    if acceptance.get("method") != method or "expected" in acceptance:
        raise RealWorkContractError(f"{capability} requires {method} without expected output")
    allowed = {"method", "paths", "targets", "receipt_ids", "artifact_hashes"}
    if set(acceptance) - allowed:
        raise RealWorkContractError(f"{capability} acceptance has unsupported fields")
    return dict(acceptance)


def validate_planner_task(task: Any) -> dict[str, Any]:
    """Validate a bounded work request without accepting a ready-made answer.

    Source tasks are intentionally a closed V1 set.  They can request a patch,
    tests, or an independent review, but cannot provide the patch/test/review
    content in their planner payload.
    """
    reject_planner_solution_material(task)
    if not isinstance(task, Mapping) or set(task) - _TASK_KEYS:
        raise RealWorkContractError("planner task has unsupported fields")
    capability = task.get("capability")
    if capability not in {*_SOURCE_CAPABILITIES, "artifact.python", "artifact.text", "artifact.json"}:
        raise RealWorkContractError("planner task capability is not allowed")
    result = dict(task)
    for name in ("id", "title", "instruction"):
        result[name] = _require_text(task.get(name), name)
    _reject_artifact_payload(result["instruction"], "instruction")
    if "objective" in task:
        result["objective"] = _require_text(task["objective"], "objective")
        _reject_artifact_payload(result["objective"], "objective")
    if "metadata" in task:
        result["metadata"] = _validate_metadata(task["metadata"])
    if capability in _SOURCE_CAPABILITIES:
        required_path, _ = _SOURCE_CAPABILITIES[capability]
        if task.get("path") != required_path:
            raise RealWorkContractError(f"{capability} must write {required_path}")
    acceptance = task.get("acceptance")
    if not isinstance(acceptance, Mapping):
        raise RealWorkContractError("planner task requires acceptance")
    if capability == "artifact.python":
        result["acceptance"] = _validate_python_cases(acceptance)
    elif capability == "artifact.text":
        result["acceptance"] = _validate_text_constraints(acceptance)
    elif capability == "artifact.json":
        result["acceptance"] = _validate_json_schema(acceptance)
    else:
        result["acceptance"] = _validate_source_acceptance(capability, acceptance)
    return result


def factual_participant_report(runs: Iterable[Any], agents: Iterable[Any] = ()) -> dict[str, Any]:
    """Report only participants proved by persisted terminal Run records."""
    names = {_row(agent).get("id"): _row(agent).get("name") for agent in agents}
    participants = []
    for raw in runs:
        run = _row(raw)
        if _state(run.get("state")) not in {RunState.COMPLETED.value, RunState.FAILED.value}:
            continue
        required = ("id", "agent_id", "provider_id", "model", "started_at", "ended_at")
        if any(run.get(field) in (None, "") for field in required):
            raise RealWorkContractError("terminal Run lacks factual identity")
        participants.append({
            "agent_id": run["agent_id"], "agent_name": names.get(run["agent_id"]),
            "task_id": run.get("task_id"), "run_id": run["id"],
            "provider_id": run["provider_id"], "model": run["model"],
            "model_reported": run.get("model_reported"), "state": _state(run["state"]),
            "started_at": run["started_at"], "ended_at": run.get("ended_at"),
            "input_tokens": run.get("input_tokens"), "output_tokens": run.get("output_tokens"),
        })
    return {"participants": participants, "run_count": len(participants)}


def _terminal_run(value: Any, label: str) -> dict[str, Any]:
    run = _row(value)
    if _state(run.get("state")) != RunState.COMPLETED.value or not run.get("id") or not run.get("agent_id"):
        raise RealWorkContractError(f"{label} must be a completed persisted Run")
    return run


def validate_reviewer_result(
    result: Any, *, reviewer_run: Any, planner_run: Any, builder_runs: Iterable[Any],
    artifact_hashes: Iterable[str], test_receipt_ids: Iterable[str],
    expected_packet_id: str | None = None, expected_packet_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate an independent review tied to actual artifacts and test receipts."""
    review = _row(result)
    if set(review) != {"verdict", "rationale", "evidence_refs"} or review.get("verdict") not in {"PASS", "FAIL"}:
        raise ReviewResponseContractError("review result needs only verdict, rationale, and evidence_refs")
    reviewer, planner = _terminal_run(reviewer_run, "reviewer"), _terminal_run(planner_run, "planner")
    builders = [_terminal_run(run, "builder") for run in builder_runs]
    if not builders:
        raise RealWorkContractError("an independent review needs an actual builder Run")
    reviewer_resource = (reviewer.get("provider_id"), reviewer.get("model_reported") or reviewer.get("model"))
    for compared in [planner, *builders]:
        resource = (compared.get("provider_id"), compared.get("model_reported") or compared.get("model"))
        if reviewer.get("agent_id") == compared.get("agent_id") or reviewer_resource == resource:
            raise RealWorkContractError("reviewer is not independent of planner or builder")
    rationale = _require_text(review.get("rationale"), "review rationale",
                              limit=REVIEW_RATIONALE_LIMIT, error=ReviewResponseContractError)
    refs = review.get("evidence_refs")
    expected_ref_keys = {"artifact_hashes", "test_receipt_ids"}
    if expected_packet_id is not None or expected_packet_sha256 is not None:
        if not expected_packet_id or not expected_packet_sha256:
            raise RealWorkContractError("packet id and hash must be required together")
        expected_ref_keys |= {"packet_id", "packet_sha256"}
    if not isinstance(refs, Mapping) or set(refs) != expected_ref_keys:
        raise ReviewResponseContractError("review needs artifact hashes and test receipt ids")
    supplied_hashes, supplied_receipts = refs["artifact_hashes"], refs["test_receipt_ids"]
    actual_hashes, actual_receipts = set(artifact_hashes), set(test_receipt_ids)
    exact_refs_required = expected_packet_id is not None
    if (not isinstance(supplied_hashes, list) or not isinstance(supplied_receipts, list)
            or not supplied_hashes or not supplied_receipts
            or not all(isinstance(item, str) and item for item in supplied_hashes + supplied_receipts)
            or not all(isinstance(item, str) and item for item in actual_hashes | actual_receipts)
            or (set(supplied_hashes) != actual_hashes if exact_refs_required
                else not set(supplied_hashes) <= actual_hashes)
            or (set(supplied_receipts) != actual_receipts if exact_refs_required
                else not set(supplied_receipts) <= actual_receipts)):
        raise ReviewResponseContractError("review evidence does not reference actual artifacts and receipts")
    if expected_packet_id is not None and (refs.get("packet_id") != expected_packet_id
                                            or refs.get("packet_sha256") != expected_packet_sha256):
        raise ReviewResponseContractError("review evidence packet identity does not match")
    verified_refs = {"artifact_hashes": list(supplied_hashes), "test_receipt_ids": list(supplied_receipts)}
    if expected_packet_id is not None:
        verified_refs.update(packet_id=expected_packet_id, packet_sha256=expected_packet_sha256)
    return {"verdict": review["verdict"], "rationale": rationale,
            "evidence_refs": verified_refs,
            "reviewer_run_id": reviewer["id"]}


def _production_adapter_identity(adapter: Any) -> str:
    identity = f"{type(adapter).__module__}.{type(adapter).__qualname__}"
    if identity not in _PRODUCTION_ADAPTERS:
        raise RealWorkContractError("production proof requires an explicit real provider adapter class")
    module_name, class_name = identity.rsplit(".", 1)
    if type(adapter) is not getattr(import_module(module_name), class_name, None):
        raise RealWorkContractError("adapter identity is not the registered production class")
    if identity == "core.lab_v1.providers.codex_app_server.CodexAppServerAdapter":
        codex_module = import_module("core.lab_v1.providers.codex_app_server")
        if getattr(adapter, "rpc_factory", None) is not codex_module.CodexRpc:
            raise RealWorkContractError("Codex production proof requires the default official CodexRpc factory")
    return identity


def validate_production_proof(proof: Any, *, runs: Iterable[Any], adapter: Any) -> dict[str, Any]:
    """Require terminal provider evidence from a real adapter; mocks cannot pass.

    ``proof`` is intentionally only ``{"run_ids": [...]}``: success is derived
    from stored runs, never from a boolean supplied by a caller.
    """
    supplied = _row(proof)
    if set(supplied) != {"run_ids"} or not isinstance(supplied.get("run_ids"), list) or not supplied["run_ids"]:
        raise RealWorkContractError("production proof requires only non-empty run_ids")
    if len(set(supplied["run_ids"])) != len(supplied["run_ids"]):
        raise RealWorkContractError("production proof has duplicate run ids")
    identity = _production_adapter_identity(adapter)
    persisted = {_row(run).get("id"): _row(run) for run in runs}
    verified = []
    for run_id in supplied["run_ids"]:
        run = persisted.get(run_id)
        if run is None or _state(run.get("state")) != RunState.COMPLETED.value:
            raise RealWorkContractError("production proof references a non-completed persisted Run")
        required = ("session_id", "agent_id", "provider_id", "model", "provider_session_id", "started_at", "ended_at")
        if any(run.get(field) in (None, "") for field in required):
            raise RealWorkContractError("completed Run has insufficient provider evidence")
        reported = run.get("model_reported")
        if (run["provider_id"] != getattr(adapter, "id", None) or run["ended_at"] < run["started_at"]
                or (reported is not None and reported != run["model"])):
            raise RealWorkContractError("Run does not match the real adapter evidence")
        verified.append({key: run[key] for key in required} | {"model_reported": reported, "run_id": run_id})
    return {"adapter_identity": identity, "runs": verified}
