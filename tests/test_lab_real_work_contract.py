from __future__ import annotations

import pytest

from core.lab_v1.domain import AgentProfile, Run, RunState
from core.lab_v1.real_work_contract import (
    RealWorkContractError,
    factual_participant_report,
    reject_planner_solution_material,
    validate_planner_task,
    validate_production_proof,
    validate_reviewer_result,
)


def _run(run_id: str, agent: str, provider: str, model: str, *, state=RunState.COMPLETED, task_id="task"):
    return Run(id=run_id, session_id="session", agent_id=agent, provider_id=provider, model=model,
               model_reported=f"reported-{model}", provider_session_id=f"provider-{run_id}", task_id=task_id,
               state=state, started_at=10.0, ended_at=11.0, input_tokens=2, output_tokens=3)


def _source_task(capability: str):
    path, method = {"source.patch": ("patch.json", "source_changed"),
                    "source.tests": ("tests.json", "pytest"),
                    "source.review": ("review.json", "independent_review")}[capability]
    return {"id": "one", "title": "Change one file", "instruction": "Make a focused source change.",
            "role": "BUILDER", "capability": capability, "path": path,
            "acceptance": {"method": method}}


@pytest.mark.parametrize("capability", ["source.patch", "source.tests", "source.review"])
def test_source_tasks_use_the_closed_real_work_allowlist(capability):
    assert validate_planner_task(_source_task(capability))["capability"] == capability


def test_planner_rejects_solution_material_at_any_depth_and_code_answer_payloads():
    task = _source_task("source.patch")
    task["metadata"] = {"inner": {"solution": "do this"}}
    with pytest.raises(RealWorkContractError):
        validate_planner_task(task)
    with pytest.raises(RealWorkContractError):
        reject_planner_solution_material({"tasks": [{"metadata": {"content": "answer"}}]})
    task = _source_task("source.patch")
    task["instruction"] = "Implement it:\n```python\ndef answer(): pass\n```"
    with pytest.raises(RealWorkContractError):
        validate_planner_task(task)


def test_planner_allows_scalar_behavioral_cases_but_not_exact_output():
    task = {"id": "py", "title": "Increment", "instruction": "Implement increment behavior.",
            "capability": "artifact.python", "acceptance": {"method": "python_cases", "cases": [
                {"function": "increment", "args": [1], "expected": 2}]}}
    assert validate_planner_task(task)["acceptance"]["cases"][0]["expected"] == 2
    task["acceptance"]["cases"][0]["expected"] = {"whole": "artifact"}
    with pytest.raises(RealWorkContractError):
        validate_planner_task(task)
    task = _source_task("source.patch"); task["acceptance"]["expected"] = "entire patch"
    with pytest.raises(RealWorkContractError):
        validate_planner_task(task)


def test_planner_accepts_measurable_text_and_json_postconditions_only():
    text = {"id": "text", "title": "Report", "instruction": "Write a report.", "capability": "artifact.text",
            "acceptance": {"method": "constraints", "min_chars": 10, "max_chars": 200,
                           "required_sections": ["Evidence"]}}
    assert validate_planner_task(text)["acceptance"]["method"] == "constraints"
    payload = {"id": "json", "title": "Data", "instruction": "Emit structured data.", "capability": "artifact.json",
               "acceptance": {"method": "json_schema", "schema": {"type": "object", "required": ["id"]}}}
    assert validate_planner_task(payload)["acceptance"]["method"] == "json_schema"
    payload["acceptance"]["schema"]["default"] = {"a": "hidden final answer"}
    with pytest.raises(RealWorkContractError):
        validate_planner_task(payload)
    text["acceptance"]["required_sections"] = ["This is a complete paragraph pretending to be a heading, with far too many words."]
    with pytest.raises(RealWorkContractError):
        validate_planner_task(text)


def test_participant_report_uses_only_actual_terminal_runs_without_roles():
    finished = _run("run-ok", "builder", "codex", "model-a")
    failed = _run("run-fail", "reviewer", "claude", "model-b", state=RunState.FAILED)
    active = _run("run-active", "ignored", "codex", "model-c", state=RunState.STARTED)
    agents = [AgentProfile("builder", "Builder", "codex", "model-a"),
              AgentProfile("reviewer", "Reviewer", "claude", "model-b")]
    report = factual_participant_report([finished, failed, active], agents)
    assert report["run_count"] == 2
    assert {item["run_id"] for item in report["participants"]} == {"run-ok", "run-fail"}
    assert "role" not in report["participants"][0]
    assert report["participants"][0]["task_id"] == "task"


def test_reviewer_must_be_independent_and_reference_persisted_evidence():
    planner = _run("plan", "planner", "codex", "plan-model")
    builder = _run("build", "builder", "claude", "build-model")
    reviewer = _run("review", "reviewer", "nvidia", "review-model")
    result = {"verdict": "PASS", "rationale": "The receipt and hash match.",
              "evidence_refs": {"artifact_hashes": ["sha256:a"], "test_receipt_ids": ["receipt:1"]}}
    verified = validate_reviewer_result(result, reviewer_run=reviewer, planner_run=planner,
                                        builder_runs=[builder], artifact_hashes=["sha256:a"],
                                        test_receipt_ids=["receipt:1"])
    assert verified["reviewer_run_id"] == "review"
    result["evidence_refs"]["test_receipt_ids"] = []
    with pytest.raises(RealWorkContractError):
        validate_reviewer_result(result, reviewer_run=reviewer, planner_run=planner,
                                 builder_runs=[builder], artifact_hashes=["sha256:a"], test_receipt_ids=["receipt:1"])
    with pytest.raises(RealWorkContractError):
        validate_reviewer_result({"success": True}, reviewer_run=reviewer, planner_run=planner,
                                 builder_runs=[builder], artifact_hashes=["sha256:a"], test_receipt_ids=["receipt:1"])


def test_reviewer_cannot_share_agent_or_model_provider_resource_with_builder():
    planner = _run("plan", "planner", "codex", "plan-model")
    builder = _run("build", "builder", "claude", "build-model")
    reviewer = _run("review", "other", "claude", "build-model")
    result = {"verdict": "FAIL", "rationale": "Evidence differs.",
              "evidence_refs": {"artifact_hashes": ["sha256:a"], "test_receipt_ids": ["receipt:1"]}}
    with pytest.raises(RealWorkContractError):
        validate_reviewer_result(result, reviewer_run=reviewer, planner_run=planner,
                                 builder_runs=[builder], artifact_hashes=["sha256:a"], test_receipt_ids=["receipt:1"])


def test_production_proof_refuses_a_mock_even_with_a_completed_run():
    class MockAdapter:
        id = "codex"
    with pytest.raises(RealWorkContractError):
        validate_production_proof({"run_ids": ["run"]}, runs=[_run("run", "a", "codex", "m")],
                                  adapter=MockAdapter())


def test_production_proof_requires_provider_session_and_reported_model():
    from core.lab_v1.providers.codex_app_server import CodexAppServerAdapter
    adapter = CodexAppServerAdapter()
    run = _run("run", "a", adapter.id, "model")
    run.provider_session_id = None
    with pytest.raises(RealWorkContractError):
        validate_production_proof({"run_ids": ["run"]}, runs=[run], adapter=adapter)


def test_production_codex_proof_rejects_injected_rpc_and_allows_unknown_reported_model():
    from core.lab_v1.providers.codex_app_server import CodexAppServerAdapter
    run = _run("run", "a", "codex_cli", "model")
    run.model_reported = None  # Codex reports this only when it reroutes.
    with pytest.raises(RealWorkContractError):
        validate_production_proof({"run_ids": ["run"]}, runs=[run],
                                  adapter=CodexAppServerAdapter(rpc_factory=lambda: None))
    proof = validate_production_proof({"run_ids": ["run"]}, runs=[run], adapter=CodexAppServerAdapter())
    assert proof["runs"][0]["model_reported"] is None
    run.model_reported = "different-model"
    with pytest.raises(RealWorkContractError):
        validate_production_proof({"run_ids": ["run"]}, runs=[run], adapter=CodexAppServerAdapter())
