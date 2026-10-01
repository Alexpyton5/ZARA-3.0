"""F4 acceptance gates; no actual build, pytest subprocess, or hardware."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from core.nova_ui_ipc import _project
from tools import build_current as current
from tools import build_source_candidate as candidate
from tools import zara_validate as validator


def receipt(sha):
    return {"mode": "full", "status": "passed", "source_changed": False,
            "source_identity_before": sha, "source_identity_after": sha,
            "result": {"returncode": 0, "failed": 0, "failed_tests": [],
                       "passed": 2, "marker_expr": "not live"}}


def test_matching_full_receipt_permits_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(current, "ROOT", tmp_path)
    current.write_json(tmp_path / ".zara-tests/latest.json", receipt("same"))
    assert current._require_full_validation({"sha256": "same"})["status"] == "passed"


@pytest.mark.parametrize("change", [
    {"mode": "incremental"}, {"status": "failed"}, {"source_changed": True},
    {"source_identity_before": "old"}, {"source_identity_after": "old"},
    {"result": {"returncode": 1, "failed": 1, "passed": 2}},
    {"result": {"returncode": 0, "failed": 0, "passed": 0}},
])
@pytest.mark.parametrize("reuse", [False, True])
def test_failed_or_stale_gate_blocks_before_any_build_effect(tmp_path, monkeypatch, change, reuse):
    monkeypatch.setattr(current, "ROOT", tmp_path)
    value = receipt("same")
    value.update(change)
    current.write_json(tmp_path / ".zara-tests/latest.json", value)
    monkeypatch.setattr(current, "source_identity", lambda: {"sha256": "same"})
    def forbidden(*args, **kwargs):
        pytest.fail("build effect before validated source")
    for name in ("emit_stage", "build_preflight", "toolchain", "run"):
        monkeypatch.setattr(current, name, forbidden)
    with pytest.raises(ValueError):
        current.build_package("test", reuse_sidecar=reuse, clean_incomplete=True)


@pytest.mark.parametrize("payload", [None, "{broken", "[]"])
def test_missing_or_malformed_receipt_is_closed(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(current, "ROOT", tmp_path)
    if payload is not None:
        path = tmp_path / ".zara-tests/latest.json"
        path.parent.mkdir()
        path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        current._require_full_validation({"sha256": "same"})


@pytest.mark.parametrize("path", ["tests/test_example.py", "requirements.txt", "tools/zara_validate.py", "pytest.ini"])
def test_gate_hash_covers_test_validator_and_configuration_content(tmp_path, monkeypatch, path):
    monkeypatch.setattr(current, "ROOT", tmp_path)
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("first", encoding="utf-8")
    first = current.source_identity()["sha256"]
    target.write_text("other", encoding="utf-8")
    assert current.source_identity()["sha256"] != first


@pytest.mark.parametrize("changed", [False, True])
def test_validator_records_both_hashes_and_rejects_mid_run_mutation(tmp_path, monkeypatch, changed):
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    for name, relative in (("RUNS_DIR", ".zara-tests/runs"), ("BASELINE_PATH", ".zara-tests/baseline.json"),
                           ("LATEST_PATH", ".zara-tests/latest.json"), ("HISTORY_PATH", ".zara-tests/history.json")):
        monkeypatch.setattr(validator, name, tmp_path / relative)
    values = iter(["first", "other" if changed else "first"])
    monkeypatch.setattr(validator, "_source_snapshot", lambda: {"sha256": next(values)})
    monkeypatch.setattr(validator, "_current_commit", lambda: "fake")
    monkeypatch.setattr(validator, "_changed_files", lambda: [])
    monkeypatch.setattr(validator, "_run_pytest", lambda **kwargs: {
        "passed": 2, "failed": 0, "skipped": 0, "failed_tests": [], "summary_line": "2 passed",
        "targets": ["tests"], "duration_seconds": 0, "returncode": 0, "marker_expr": "not live"})
    monkeypatch.setattr(sys, "argv", ["zara_validate", "--full"])
    assert validator.main() == (1 if changed else 0)
    record = json.loads(validator.LATEST_PATH.read_text(encoding="utf-8"))
    assert record["source_identity_before"] == "first"
    assert record["source_identity_after"] == ("other" if changed else "first")
    assert record["status"] == ("failed" if changed else "passed")


def test_staged_projection_contains_validator_tests_and_config(tmp_path):
    workspace, staged = tmp_path / "work", tmp_path / "stage"
    for name in ("tools/zara_validate.py", "tools/build_current.py", "tests/test_local.py",
                 "tests/conftest.py", "pyproject.toml", "requirements.txt", "pytest.ini"):
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    candidate._copy_projection(workspace, staged)
    for name in ("tools/zara_validate.py", "tests/test_local.py", "tests/conftest.py",
                 "pyproject.toml", "requirements.txt", "pytest.ini"):
        assert (staged / name).read_text(encoding="utf-8") == name
    assert not (staged / ".venv").exists()


def test_staged_full_uses_external_python_explicit_environment(tmp_path, monkeypatch):
    python = tmp_path / "external/python.exe"
    python.parent.mkdir()
    python.write_bytes(b"fake")
    staged = tmp_path / "stage"
    staged.mkdir()
    calls = []
    monkeypatch.setattr(candidate, "_run", lambda cmd, **kw: calls.append((cmd, kw)))
    candidate._validate_staged(python, staged, {"ALLOW_LIVE_TESTS": "1", "PYTEST_ADDOPTS": "-k partial"}, tmp_path / "evidence")
    command, call = calls[0]
    assert command == [str(python.resolve()), "tools/zara_validate.py", "--full"]
    assert call["cwd"] == staged
    assert call["env"]["ZARA_VALIDATE_PYTHON"] == str(python.resolve())
    assert call["env"]["PYTHONPATH"] == str(staged.resolve())
    assert "ALLOW_LIVE_TESTS" not in call["env"] and "PYTEST_ADDOPTS" not in call["env"]


def facts_for_sessions():
    session = {"id": "A", "team_id": "crew", "objective": "Projeto A", "state": "RUNNING",
               "mission": {"state": "RUNNING", "steps": []}, "autonomy": {"pause_requested": False},
               "tasks": [{"id": "task-A", "title": "Tarefa A", "assigned_agent_id": "agent",
                          "state": "RUNNING", "updated_at": 1000}],
               "runs": [{"agent_id": "agent", "task_id": "task-A", "state": "STARTED"}], "artifacts": []}
    other = deepcopy(session)
    other.update(id="B", objective="Projeto B", runs=[], autonomy={"pause_requested": True})
    other["tasks"][0].update(id="task-B", title="Tarefa B")
    return {"teams": [{"id": "crew", "name": "Crew"}],
            "agents": [{"id": "agent", "name": "Ana", "role": "ENGINEER"}],
            "bindings": {"crew": []}, "memberships": {"crew": [{"agent_id": "agent", "left_at": None}]},
            "sessions": [session, other]}


def test_office_same_crew_working_and_paused_sessions_are_independent():
    projects, *_ = _project({"participation": {"agent": "WORKING"}}, facts_for_sessions())
    by_id = {row["id"]: row for row in projects}
    a, b = by_id["A"]["membros"][0], by_id["B"]["membros"][0]
    assert a["status"] == "trabalhando" and a["tarefaAtual"] == "Tarefa A"
    assert b["status"] == "pausado" and "tarefaAtual" not in b


def test_office_missing_session_evidence_does_not_inherit_global_working():
    facts = facts_for_sessions()
    facts["sessions"][1].update(tasks=[], runs=[], autonomy=None)
    projects, _, _, unknown = _project({"participation": {"agent": "WORKING"}}, facts)
    by_id = {row["id"]: row for row in projects}
    assert by_id["A"]["membros"][0]["status"] == "trabalhando"
    assert by_id["B"]["membros"] == []
    assert any(row.get("project_id") == "B" and row.get("id") == "agent" for row in unknown)


def test_office_two_running_sessions_have_their_own_current_task():
    facts = facts_for_sessions()
    facts["sessions"][1].update(runs=[{"agent_id": "agent", "task_id": "task-B", "state": "STARTED"}],
                                autonomy={"pause_requested": False})
    projects, *_ = _project({"participation": {"agent": "WORKING"}}, facts)
    assert {p["id"]: p["membros"][0]["tarefaAtual"] for p in projects} == {"A": "Tarefa A", "B": "Tarefa B"}


def test_staged_full_failure_prevents_build(tmp_path, monkeypatch):
    workspace, sandbox = tmp_path / "workspace", tmp_path / "sandbox"
    source = sandbox / "source"
    source.mkdir(parents=True)
    (source / 'main.py').write_text("print('candidate')", encoding='utf-8')
    python = workspace / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fake")
    cli = workspace / "frontend/node_modules/electron-builder/cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(candidate, "_require_review", lambda value: None)
    monkeypatch.setattr(candidate, "_require_build_space", lambda value: None)
    monkeypatch.setattr(candidate, "_bind_review", lambda *args: None)
    monkeypatch.setattr(candidate, "_dependency_junction", lambda *args: None)
    monkeypatch.setattr(candidate, "_git", lambda *args: "fake")
    calls = []
    def fail_full(command, **kwargs):
        calls.append(command)
        assert command[1:] == ["tools/zara_validate.py", "--full"]
        assert kwargs["cwd"] == sandbox / "desktop-workspace"
        raise candidate.CandidateBuildError("CANDIDATE_FULL_VALIDATION_FAILED")
    monkeypatch.setattr(candidate, "_run", fail_full)
    monkeypatch.setattr(candidate, "_source_identity", lambda *args: pytest.fail("build after failed full"))
    with pytest.raises(candidate.CandidateBuildError, match="FULL_VALIDATION_FAILED"):
        candidate.build_candidate(workspace=workspace, sandbox=sandbox, source_root=source,
                                  allowed_paths=['main.py'], review_evidence={})
    assert len(calls) == 1
    assert not (sandbox / "desktop-workspace/.venv").exists()
