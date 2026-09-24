import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import core.lab_v1.evolution as evolution_module

from core.lab_v1.domain import CapabilityGap, Session, Team
from core.lab_v1.evolution import EvolutionEngine, LEGACY_WORKFLOW, WORKFLOW
from core.lab_v1.store import LabStore


class StubAutopilot:
    def __init__(self, store):
        self.store = store
        self.starts = []
        self.runs = []

    def start(self, objective, **kwargs):
        self.starts.append((objective, kwargs))
        sid = "dynamic" if len(self.starts) == 1 else f"dynamic-{len(self.starts)}"
        if self.store.get_session(sid) is None:
            self.store.save_session(Session(sid, "team", objective=objective))
        return {"success": True, "session_id": sid, "state": "QUEUED"}

    def run(self, sid):
        self.runs.append(sid)
        return {"success": True, "session_id": sid, "state": "COMPLETED"}


@pytest.fixture
def engine(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "core/lab_v1/feedback_inbox.py"
    source.parent.mkdir(parents=True)
    source.write_text("def looks_like_product_criticism(text):\n    return True\n", encoding="utf-8")
    for name in ("alpha.py", "beta.py", "gamma.py"):
        (source.parent / name).write_text("VALUE = 1\n", encoding="utf-8")
    nested = workspace / "memory/nested.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("VALUE = 1\n", encoding="utf-8")
    (source.parent / "hermes_adapter.py").write_text("VALUE = 1\n", encoding="utf-8")
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team("team", "Internal"))
    runtime = SimpleNamespace(store=store)
    autopilot = StubAutopilot(store)
    result = EvolutionEngine(runtime, workspace, autopilot=autopilot)
    result.test_autopilot = autopilot
    return result


def test_observer_dispatches_dynamic_source_improvement_with_factual_evidence(engine):
    result = engine.observe_and_plan()
    assert result["session_id"] == "dynamic" and result["workflow"] == WORKFLOW
    objective, kwargs = engine.test_autopilot.starts[0]
    assert "core/lab_v1/feedback_inbox.py" in objective
    assert kwargs["mission_kind"] == "SELF_IMPROVEMENT"
    evidence = kwargs["evidence"]
    assert evidence["source_path"] == "core/lab_v1/feedback_inbox.py"
    assert evidence["behavioral_counterexample"]["expected"] is False
    assert evidence["behavioral_counterexample"]["observed"] is True
    expected_sha = hashlib.sha256(Path(engine.snapshot("dynamic")["source"]).read_bytes()).hexdigest()
    assert evidence["source_sha256"] == expected_sha
    assert len(evidence["source_inventory"]) == 5
    assert all("hermes" not in item["source_path"] for item in evidence["source_inventory"])
    assert engine.snapshot("dynamic")["production_activation"] == "OWNER_APPROVAL_REQUIRED"


def test_handled_counterexample_falls_back_to_rotating_source_inspection(engine):
    assert engine.observe_and_plan()["session_id"] == "dynamic"
    second = engine.observe_and_plan()
    assert second["session_id"] == "dynamic-2"
    objective, kwargs = engine.test_autopilot.starts[1]
    assert kwargs["evidence"]["observation_kind"] == "SOURCE_INSPECTION"
    assert len(kwargs["evidence"]["sources"]) == 3
    assert "não presuma defeito" in objective.casefold()


def test_fixed_behavior_still_allows_honest_source_inspection(engine):
    source = engine.workspace / "core/lab_v1/feedback_inbox.py"
    source.write_text("def looks_like_product_criticism(text):\n    return False\n", encoding="utf-8")
    result = engine.observe_and_plan()
    assert result["state"] == "QUEUED"
    evidence = engine.test_autopilot.starts[0][1]["evidence"]
    assert evidence["observation_kind"] == "SOURCE_INSPECTION"
    assert "behavioral_counterexample" not in evidence


def test_frozen_backend_skips_python_cli_probe_and_still_dispatches_source_inspection(
        monkeypatch, engine):
    monkeypatch.setattr(evolution_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        evolution_module.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("frozen backend must not be invoked as python -c"),
    )

    result = engine.observe_and_plan()

    assert result["state"] == "QUEUED"
    evidence = engine.test_autopilot.starts[0][1]["evidence"]
    assert evidence["observation_kind"] == "SOURCE_INSPECTION"


def test_frozen_backend_detects_counterexample_only_when_package_matches_checkout(monkeypatch, engine):
    import sys
    source = engine.workspace / 'core/lab_v1/feedback_inbox.py'
    package = engine.workspace / 'frontend' / 'release-candidate-test'
    unpacked = package / 'win-unpacked'
    exe = unpacked / 'ZARA 3.0.exe'
    backend = unpacked / 'resources' / 'backend' / 'zara-backend.exe'
    exe.parent.mkdir(parents=True)
    backend.parent.mkdir(parents=True)
    exe.write_bytes(b'frontend')
    backend.write_bytes(b'backend')
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {'sha256': 'source-set', 'files': [
        {'path': 'core/lab_v1/feedback_inbox.py', 'sha256': source_sha}]}
    (package / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    info = {'BUILD_ID': 'release-candidate-test', 'EXE_PATH': str(exe),
            'SOURCE_SHA256': manifest['sha256'],
            'BACKEND_SHA256': hashlib.sha256(backend.read_bytes()).hexdigest().upper()}
    (unpacked / 'BUILD_INFO.json').write_text(json.dumps(info))
    (engine.workspace / 'ZARA_ACTIVE_BUILD.json').write_text(json.dumps(info))
    monkeypatch.setattr(evolution_module.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(backend))

    result = engine.observe_and_plan()

    assert result['state'] == 'QUEUED'
    evidence = engine.test_autopilot.starts[0][1]['evidence']
    assert evidence['observation_kind'] == 'BEHAVIORAL_COUNTEREXAMPLE'
    assert evidence['behavioral_counterexample']['observer'] == 'PACKAGED_CLASSIFIER_MATCHING_CHECKOUT'


def test_unchanged_batches_are_not_re_read_until_a_source_changes(engine):
    source = engine.workspace / "core/lab_v1/feedback_inbox.py"
    source.write_text("def looks_like_product_criticism(text):\n    return False\n", encoding="utf-8")
    assert engine.observe_and_plan()["state"] == "QUEUED"
    assert engine.observe_and_plan()["state"] == "QUEUED"
    assert engine.observe_and_plan()["state"] == "NO_CHANGED_SOURCE_BATCH"
    assert len(engine.test_autopilot.starts) == 2
    (engine.workspace / "core/lab_v1/alpha.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert engine.observe_and_plan()["state"] == "QUEUED"
    assert len(engine.test_autopilot.starts) == 3


def test_local_observer_persists_hashes_without_starting_a_mission(engine):
    inventory = engine.observe_local()
    assert len(inventory) == 5
    assert engine.test_autopilot.starts == []
    state = engine.observer_snapshot()
    assert state["inventory_count"] == 5
    assert len(state["inventory_sha256"]) == 64
    assert all(len(item["source_sha256"]) == 64 for item in state["sources"])


def test_new_capability_gap_is_new_architect_evidence_even_when_source_is_unchanged(engine):
    source = engine.workspace / "core/lab_v1/feedback_inbox.py"
    source.write_text("def looks_like_product_criticism(text):\n    return False\n", encoding="utf-8")
    while engine.observe_and_plan().get("session_id"):
        pass
    engine.store.save_capability_gap(CapabilityGap("gap:runtime", None, "windows.open_missing"))
    result = engine.observe_and_plan()
    assert result["state"] == "QUEUED"
    evidence = engine.test_autopilot.starts[-1][1]["evidence"]
    assert evidence["observation_kind"] == "SOURCE_INSPECTION"
    gap = evidence["capability_gaps"][0]
    assert gap["id"] == "gap:runtime" and gap["required"] == "windows.open_missing"
    assert gap["available"] is False


def test_factual_runtime_gap_dispatches_its_actual_executor_source(engine):
    source = engine.workspace / "core/lab_v1/feedback_inbox.py"
    source.write_text("def looks_like_product_criticism(text):\n    return False\n", encoding="utf-8")
    detail = json.dumps({"observation_kind": "RUNTIME_CAPABILITY_FAILURE",
                         "source_path": "core/lab_v1/alpha.py",
                         "action_id": "alpha", "status": "EXECUTOR_FAILED"})
    engine.store.save_capability_gap(CapabilityGap(
        "runtime-gap:alpha", None, "runtime.action.alpha", detail=detail))
    result = engine.observe_and_plan()
    assert result["state"] == "QUEUED"
    evidence = engine.test_autopilot.starts[0][1]["evidence"]
    assert evidence["observation_kind"] == "RUNTIME_CAPABILITY_FAILURE"
    assert evidence["sources"][0]["source_path"] == "core/lab_v1/alpha.py"


def test_dynamic_run_uses_existing_autopilot(engine):
    engine.observe_and_plan()
    result = engine.run("dynamic")
    assert result["state"] == "COMPLETED"
    assert engine.test_autopilot.runs == ["dynamic"]


def test_legacy_catalog_mission_is_retired_without_execution(engine):
    engine.store.save_session(Session("legacy", "team", objective="Old repair"))
    legacy = {"session_id": "legacy", "repair_id": "catalog", "workflow": LEGACY_WORKFLOW,
              "state": "CANDIDATE_VERIFIED", "build_state": "PACKAGE_PENDING"}
    with engine.store._connect() as conn:
        conn.execute("INSERT INTO lab_evolution VALUES(?,?,?)",
                     ("legacy", "catalog", json.dumps(legacy)))
    result = engine.run("legacy")
    assert result["state"] == "LEGACY_RETIRED"
    assert result["build_state"] == "NOT_SCHEDULED"
    assert engine.test_autopilot.runs == []


def test_capability_gaps_remain_factual_proposals(engine):
    engine.store.save_capability_gap(CapabilityGap("gap:unknown", None, "unknown.future.capability"))
    engine.observe_and_plan()
    proposal = next(p for p in engine.proposals() if p["gap_id"] == "gap:unknown")
    assert proposal["state"] == "PROPOSAL_ONLY_UNSUPPORTED"
