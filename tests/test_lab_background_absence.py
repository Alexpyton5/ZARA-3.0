"""Safe work continues with the owner absent: no Lab window, no chat, no 'continue'.

The mission is created and interrupted by a real child process that is killed.
The owner then never touches anything again: only the existing local supervisor
(``AutonomySupervisor.tick``) and the service background loop run, and they must
carry the mission to COMPLETED on their own, on a timer — never busy polling.

Everything lives in tmp_path; no production workspace or package is touched.
"""
import asyncio
import time

import pytest

from core.lab_v1.supervisor import AutonomySupervisor
from tests.test_lab_restart_resume import build_engine, crash_a_real_lab_process


def supervisor_for(engine, workspace):
    supervisor = AutonomySupervisor(engine.runtime, autopilot=engine)
    supervisor._save(enabled=True, background_enabled=True, workspace=str(workspace),
                     cadence_seconds=60)
    return supervisor


@pytest.fixture
def abandoned(tmp_path, monkeypatch):
    """A real mission, interrupted by a process kill, with nobody watching."""
    crashed = crash_a_real_lab_process(tmp_path, 'AFTER_DURABLE_RECEIPT')
    engine = build_engine(tmp_path, monkeypatch)
    return {'engine': engine, 'sid': crashed['session']['session_id'], 'root': tmp_path,
            'supervisor': supervisor_for(engine, tmp_path / 'workspace')}


def test_supervisor_alone_finishes_the_abandoned_mission(abandoned):
    engine, sid, supervisor = abandoned['engine'], abandoned['sid'], abandoned['supervisor']
    assert engine.controller.snapshot(sid)['state'] == 'RUNNING'
    owner_touches = engine.metrics(sid)['owner_touches']

    # No UI, no chat, no engine.run() from the test: only the timer's tick.
    result = supervisor.tick()

    assert result['state'] == 'COMPLETED'
    assert engine.controller.snapshot(sid)['state'] == 'COMPLETED'
    assert supervisor.policy()['active_session'] == sid
    assert supervisor.policy()['last_state'] == 'COMPLETED'
    # The owner was not consulted, and no new session was invented.
    assert engine.metrics(sid)['owner_touches'] == owner_touches
    assert [row.id for row in engine.store.list_sessions()] == [sid]
    work = engine.metrics(sid)['source_work']
    assert work['candidate_build']['status'] == 'PACKAGED_RUNTIME_CANDIDATE'
    # Autonomous work stops at the gate: nothing was promoted without the owner.
    assert work['promotion_gate']['desktop_promoted'] is False


def test_a_finished_mission_is_never_re_run_and_new_work_stays_budgeted(abandoned):
    engine, sid, supervisor = abandoned['engine'], abandoned['sid'], abandoned['supervisor']
    assert supervisor.tick()['state'] == 'COMPLETED'
    finished = engine.controller.snapshot(sid)

    supervisor.tick()
    supervisor.tick()

    # The completed mission is untouched by every later tick.
    assert engine.controller.snapshot(sid) == finished
    # Any new autonomous work is a distinct session, capped by the daily budget.
    sessions = [row.id for row in engine.store.list_sessions()]
    assert sid in sessions and len(sessions) <= 2
    assert supervisor.policy()['daily_missions'] <= supervisor.policy()['max_new_evolution_missions_per_day']


def test_background_loop_ticks_on_a_timer_and_does_not_busy_poll(abandoned, monkeypatch):
    from core.lab_v1.service import LabV1Service

    service = LabV1Service()
    service._supervisor = abandoned['supervisor']
    service._background_interval = 0.05
    started_at = []
    sleeps = []
    real_sleep = asyncio.sleep

    def observed_tick():
        started_at.append(time.monotonic())
        return {'state': 'MONITORING'}

    async def observed_sleep(delay, *args, **kwargs):
        sleeps.append(delay)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(abandoned['supervisor'], 'tick', observed_tick)
    monkeypatch.setattr(asyncio, 'sleep', observed_sleep)

    async def exercise():
        assert (await service.start_background())['state'] == 'RUNNING'
        await real_sleep(0.35)
        return await service.stop_background()

    stopped = asyncio.run(exercise())

    assert stopped['state'] == 'PAUSED'
    assert 2 <= len(started_at) <= 12, started_at  # a timer, not a spin loop
    assert sleeps and all(delay >= 0.05 for delay in sleeps)
    gaps = [b - a for a, b in zip(started_at, started_at[1:], strict=False)]
    assert all(gap >= 0.04 for gap in gaps), gaps
    assert service._background_error is None
