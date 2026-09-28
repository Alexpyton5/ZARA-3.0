from __future__ import annotations

import asyncio

import pytest

from core.supercerebro_auto_off import SupercerebroAutoOff


@pytest.mark.asyncio
async def test_windows_lock_trips_off_immediately():
    reasons: list[str] = []
    monitor = SupercerebroAutoOff(
        lambda reason: _record(reasons, reason),
        is_locked=lambda: True,
        idle_seconds=lambda: 0,
    )

    assert await monitor.check_once() is True
    assert reasons == ["windows-locked"]


@pytest.mark.asyncio
async def test_idle_trips_at_ten_minutes_but_not_before():
    reasons: list[str] = []
    idle = [599.9]
    monitor = SupercerebroAutoOff(
        lambda reason: _record(reasons, reason),
        is_locked=lambda: False,
        idle_seconds=lambda: idle[0],
    )

    assert await monitor.check_once() is False
    assert reasons == []
    idle[0] = 600
    assert await monitor.check_once() is True
    assert reasons == ["idle-timeout"]


@pytest.mark.asyncio
async def test_monitor_uncertainty_fails_closed():
    reasons: list[str] = []

    def unavailable() -> bool:
        raise OSError("desktop state unavailable")

    monitor = SupercerebroAutoOff(
        lambda reason: _record(reasons, reason),
        is_locked=unavailable,
        idle_seconds=lambda: 0,
    )

    assert await monitor.check_once() is True
    assert reasons == ["monitor-unavailable"]


@pytest.mark.asyncio
async def test_running_monitor_polls_until_lock_and_then_stops():
    reasons: list[str] = []
    monitor = SupercerebroAutoOff(
        lambda reason: _record(reasons, reason),
        is_locked=lambda: True,
        idle_seconds=lambda: 0,
        poll_interval_seconds=0.001,
    )
    monitor.start()
    await asyncio.wait_for(_wait_for_reason(reasons), timeout=0.2)

    assert reasons == ["windows-locked"]
    assert monitor.running is False


@pytest.mark.asyncio
async def test_stop_cancels_monitor_without_auto_disabling():
    reasons: list[str] = []
    monitor = SupercerebroAutoOff(
        lambda reason: _record(reasons, reason),
        is_locked=lambda: False,
        idle_seconds=lambda: 0,
        poll_interval_seconds=0.001,
    )
    monitor.start()
    monitor.stop()
    await asyncio.sleep(0.01)

    assert reasons == []
    assert monitor.running is False


async def _record(reasons: list[str], reason: str) -> None:
    reasons.append(reason)


async def _wait_for_reason(reasons: list[str]) -> None:
    while not reasons:
        await asyncio.sleep(0)
