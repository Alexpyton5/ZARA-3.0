from core.lab_v1.service import LabV1Service


def _health(**overrides):
    values = {
        "supervisor_state": "RUNNING",
        "supervisor_error": None,
        "operation_consumer": {"state": "RUNNING", "error": None},
        "publication": {"state": "CLEAR", "pending": False, "count": 0},
        "scheduler_state": "WAITING",
        "scheduler_error": None,
        "memory": {"status": "available", "degraded": False},
        "research_scheduler": "READY",
    }
    values.update(overrides)
    return LabV1Service._resident_health(**values)


def test_resident_health_keeps_each_failure_domain_distinct():
    health = _health(
        supervisor_state="FAILED",
        supervisor_error="tick failed",
        operation_consumer={"state": "FAILED", "error": "dispatch failed"},
        publication={"state": "PENDING", "pending": True, "count": 2},
        scheduler_state="WAITING",
        scheduler_error="scheduler loop failed",
        memory={"status": "degraded", "degraded": True},
    )

    assert health["state"] == "DEGRADED"
    assert health["supervisor"] == "FAILED"
    assert health["supervisor_error"] == "tick failed"
    assert health["operation_consumer"] == "FAILED"
    assert health["operation_consumer_error"] == "dispatch failed"
    assert health["pending_publication"] == "PENDING"
    assert health["publication_pending"] is True
    assert health["scheduler_error"] == "scheduler loop failed"
    assert health["memory_degraded"] is True
    assert health["degraded_memory"] is True
    assert health["issues"] == [
        "SUPERVISOR_ERROR",
        "OPERATION_CONSUMER_ERROR",
        "PENDING_PUBLICATION",
        "SCHEDULER_ERROR",
        "MEMORY_DEGRADED",
    ]


def test_resident_health_does_not_call_paused_components_failures():
    health = _health(
        supervisor_state="STOPPED",
        operation_consumer={"state": "STOPPED", "error": None},
        scheduler_state="DISABLED",
        research_scheduler="DISABLED_BY_POLICY",
    )

    assert health["state"] == "OK"
    assert health["resident"] is False
    assert health["supervisor"] == "STOPPED"
    assert health["operation_consumer"] == "STOPPED"
    assert health["pending_publication"] == "CLEAR"
    assert health["scheduler_error"] is None
    assert health["memory_degraded"] is False
    assert health["issues"] == []
