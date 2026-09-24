import asyncio
from types import SimpleNamespace
import threading

from core.lab_v1.service import ImprovementScheduler, LabV1Service, scheduler_enabled
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor


class _IdleScheduler:
    def __init__(self):
        self.cycles = 0

    def cycle(self):
        self.cycles += 1
        return {"state": "NO_WORK", "dispatched": False}

    def seconds_until_next(self):
        return 3600


class _CountingSupervisor:
    def __init__(self):
        self.lock = threading.Lock()
        self.ticks = 0

    def policy(self):
        return {
            "enabled": True,
            "background_enabled": True,
            "scheduler_enabled": True,
            "cadence_seconds": 3600,
        }

    def tick(self):
        self.ticks += 1
        return {"state": "MONITORING"}


def test_first_run_enables_autonomy_but_a_saved_pause_survives_restart(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    runtime = SimpleNamespace(store=store)

    first_boot = AutonomySupervisor(runtime)
    assert first_boot.policy()["scheduler_enabled"] is True
    assert scheduler_enabled(first_boot.policy()) is True

    first_boot._save(scheduler_enabled=False)
    next_boot = AutonomySupervisor(runtime)
    assert next_boot.policy()["scheduler_enabled"] is False
    assert scheduler_enabled(next_boot.policy()) is False


def test_autonomy_toggle_persists_and_starts_or_pauses_both_loops(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    runtime = SimpleNamespace(store=store)
    supervisor = AutonomySupervisor(runtime)
    supervisor._save(workspace=str(tmp_path), enabled=False, scheduler_enabled=False)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "build_current.py").touch()

    service = LabV1Service()
    service._runtime = runtime
    service._store = store
    service._supervisor = supervisor
    service._scheduler = _IdleScheduler()
    service._background_interval = 3600
    service._scheduler_poll_seconds = 3600

    async def exercise():
        try:
            enabled = await service.configure_autonomy(True)
            await asyncio.sleep(0.02)
            active = (service._supervisor_task is not None
                      and not service._supervisor_task.done()
                      and service._scheduler_task is not None
                      and not service._scheduler_task.done())
            paused = await service.configure_autonomy(False)
            paused_cleanly = service._scheduler_task is None
            policy = supervisor.policy()
            return enabled, active, paused, paused_cleanly, policy
        finally:
            await service.stop_background()

    enabled, active, paused, paused_cleanly, policy = asyncio.run(exercise())

    assert enabled["success"] is True
    assert active is True
    assert paused["success"] is True
    assert paused_cleanly is True
    assert policy["enabled"] is False
    assert policy["scheduler_enabled"] is False


def test_app_startup_is_idempotent_for_supervisor_and_scheduler_tasks():
    service = LabV1Service()
    supervisor = _CountingSupervisor()
    scheduler = _IdleScheduler()
    service._supervisor = supervisor
    service._scheduler = scheduler
    service._background_interval = 3600
    service._scheduler_poll_seconds = 3600

    async def exercise():
        try:
            first, second = await asyncio.gather(
                service.start_background(), service.start_background())
            await asyncio.sleep(0.05)
            supervisor_task = service._supervisor_task
            scheduler_task = service._scheduler_task
            third = await service.start_background()
            return first, second, third, supervisor_task, scheduler_task
        finally:
            await service.stop_background()

    first, second, third, supervisor_task, scheduler_task = asyncio.run(exercise())

    assert first["state"] == second["state"] == third["state"] == "RUNNING"
    assert supervisor_task is not None and scheduler_task is not None
    assert supervisor.ticks == 1
    assert scheduler.cycles == 1


def test_scheduler_defers_while_supervisor_holds_the_mission_lock(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    supervisor = AutonomySupervisor(SimpleNamespace(store=store))
    supervisor._save(scheduler_enabled=True)
    scheduler = ImprovementScheduler(SimpleNamespace(store=store), supervisor)

    supervisor.lock.acquire()
    try:
        result = scheduler.cycle()
    finally:
        supervisor.lock.release()

    assert result == {"state": "BUSY", "dispatched": False}
    assert scheduler.state()["cycles"] == 0
