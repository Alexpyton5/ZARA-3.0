"""Focused contract tests for review-only routing telemetry."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.model_router import TaskType
from core.routing_telemetry import RoutingTelemetry


def test_record_persists_executor_model_outcome_and_reload(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)
    assert telemetry.record(
        TaskType.CODING,
        executor="local_runner",
        model="qwen3:4b",
        duration=1.5,
        success=True,
    )

    stored = json.loads((tmp_path / "routing" / "telemetry.json").read_text("utf-8"))
    assert stored[0]["model"] == "qwen3:4b"
    assert not (tmp_path / "routing" / "telemetry.json.tmp").exists()

    event = RoutingTelemetry(data_dir=tmp_path).get_events()[0]
    assert event["task_type"] == "coding"
    assert event["executor"] == "local_runner"
    assert event["success"] is True


def test_corrupt_file_does_not_break_startup_but_exposes_failure(tmp_path):
    telemetry_dir = tmp_path / "routing"
    telemetry_dir.mkdir()
    (telemetry_dir / "telemetry.json").write_text("not json", encoding="utf-8")

    telemetry = RoutingTelemetry(data_dir=tmp_path)

    assert telemetry.get_events() == []
    assert telemetry.last_persistence_error is not None


def test_aggregates_are_separate_for_task_executor_and_model(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)
    telemetry.record(TaskType.CODING, "worker", 2, True, model="local")
    telemetry.record(TaskType.CODING, "worker", 4, False, fallback=True, model="local")
    telemetry.record(TaskType.REASONING, "reviewer", 3, True, model="strong")

    aggregates = telemetry.get_aggregates()

    coding = aggregates["groups"]["task_type"]["coding"]
    assert coding == {
        "count": 2,
        "success_rate": 0.5,
        "fallback_rate": 0.5,
        "avg_duration": 3.0,
    }
    assert aggregates["groups"]["executor"]["worker"]["count"] == 2
    assert aggregates["groups"]["model"]["strong"]["success_rate"] == 1.0


def test_candidates_require_evidence_and_are_review_only(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)
    for index in range(5):
        telemetry.record(
            TaskType.CODING,
            "weak_worker",
            1,
            success=index == 0,
            fallback=index >= 2,
            model="small",
        )

    candidates = telemetry.routing_candidates()

    assert len(candidates) == 1
    assert candidates[0]["kind"] == "ROUTING_CANDIDATE"
    assert candidates[0]["review_required"] is True
    assert candidates[0]["auto_apply"] is False
    assert not hasattr(telemetry, "apply_candidate")


def test_candidates_do_not_fire_on_too_few_samples(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)
    telemetry.record(TaskType.CODING, "worker", 1, False, fallback=True)
    assert telemetry.routing_candidates(minimum_samples=2) == []


def test_concurrent_records_are_kept_and_json_remains_valid(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda i: telemetry.record("coding", f"worker-{i}", 0.1, True),
                range(40),
            )
        )

    assert all(results)
    assert len(telemetry.get_events(limit=100)) == 40
    assert len(json.loads(telemetry.telemetry_file.read_text("utf-8"))) == 40


def test_maximum_history_and_validation(tmp_path):
    telemetry = RoutingTelemetry(data_dir=tmp_path)
    for index in range(RoutingTelemetry.MAX_EVENTS + 5):
        telemetry.record("coding", str(index), 0, True)
    assert len(telemetry.get_events(limit=2_000)) == RoutingTelemetry.MAX_EVENTS
    assert telemetry.get_events(limit=2_000)[-1]["executor"] == "5"

    with pytest.raises(ValueError):
        telemetry.record("coding", "worker", -1, True)
    with pytest.raises(ValueError):
        telemetry.get_events(limit=-1)
