from datetime import datetime

from core.actions.system import (
    system_info_action,
    system_metrics_action,
    system_processes_action,
    system_time_action,
)


def test_local_time_comes_from_timezone_aware_system_clock():
    before = datetime.now().astimezone()
    result = system_time_action()
    after = datetime.now().astimezone()

    observed = datetime.fromisoformat(result.data["local_iso"])
    assert result.success is True
    assert result.data["verified"] is True
    assert observed.tzinfo is not None
    assert before <= observed <= after
    assert result.output == f"Agora são {observed:%H:%M}."


def test_system_information_contains_real_operational_fields():
    result = system_info_action()
    assert result.success is True
    assert result.data["uptime_seconds"] >= 0
    assert isinstance(result.data["network"]["adapters"], list)
    assert result.data["disk"]["total"] > 0
    assert result.data["battery"] is None or 0 <= result.data["battery"]["percent"] <= 100


def test_metrics_and_processes_have_readback():
    metrics = system_metrics_action(interval=0)
    processes = system_processes_action(limit=3)
    assert metrics.success is True and metrics.data["memory"]["total"] > 0
    assert processes.success is True and processes.data["count"] <= 3
