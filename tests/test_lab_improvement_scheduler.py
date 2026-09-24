"""The 24/7 improvement scheduler, proved on real stores and a real restart.

Two worlds are exercised here, both entirely inside `tmp_path`:

* an **idle** Lab (`idle_scheduler`) whose workspace holds no source at all, so
  "there is nothing worth doing" is a fact and not a stub — this is what proves
  backoff, persistence and restart survival without ever reaching a provider;
* the **capability-gap** Lab (the `loop` fixture reused verbatim from
  `tests/test_lab_capability_gap_loop.py`), where a real ZARA turn failed, a
  real `CapabilityGap` was persisted, and the scheduler must turn it into a
  real Mission through the canonical `EvolutionEngine.observe_and_plan` flow.

Nothing in this file touches the owner's workspace, CURRENT build, Lab database
or the real autonomy policy. Tests set an explicit persisted pause or opt-in;
the production fallback stays False when no owner policy exists.
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import (
    SCHEDULER_BASE_INTERVAL_SECONDS,
    SCHEDULER_DEDUP_WINDOW_SECONDS,
    SCHEDULER_ENABLED,
    SCHEDULER_ENV_FLAG,
    SCHEDULER_MAX_INTERVAL_SECONDS,
    ImprovementScheduler,
    LabV1Service,
    scheduler_enabled,
)
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor
from tests.test_lab_capability_gap_loop import (  # noqa: F401  (loop is a fixture)
    EXECUTOR_PATH,
    loop,
    observe_the_failed_action,
)

REPOSITORY = str(Path(__file__).resolve().parents[1])
BASE = SCHEDULER_BASE_INTERVAL_SECONDS
T0 = 1_000_000.0


def idle_scheduler(root: Path, *, opted_in: bool = True, cap: int = 1) -> ImprovementScheduler:
    """A whole Lab over root/lab.db whose workspace provably has no work in it.

    Autonomy itself is left disabled so `AutonomySupervisor.tick` stands down
    immediately: this file is about the scheduler, not about the supervisor.
    """
    workspace = root / "empty-workspace"
    workspace.mkdir(exist_ok=True)
    store = LabStore(root / "lab.db")
    store.initialize()
    runtime = LabRuntime(store, ProviderRegistry(root / "health.json"))
    supervisor = AutonomySupervisor(runtime)
    supervisor._save(enabled=False, background_enabled=True, workspace=str(workspace),
                     scheduler_enabled=opted_in, max_new_evolution_missions_per_day=cap)
    return ImprovementScheduler(runtime, supervisor)


def gap_scheduler(loop, *, cap: int = 1) -> ImprovementScheduler:  # noqa: F811
    supervisor = AutonomySupervisor(loop["runtime"], autopilot=loop["autopilot"])
    supervisor._save(enabled=True, background_enabled=True, workspace=str(loop["workspace"]),
                     scheduler_enabled=True, max_new_evolution_missions_per_day=cap)
    return ImprovementScheduler(loop["runtime"], supervisor)


# ---------------------------------------------------------------------------
# 1. An explicit persisted pause wins and nothing runs by itself.
# ---------------------------------------------------------------------------
def test_explicit_pause_refuses_to_look_for_work(tmp_path, monkeypatch):
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    assert SCHEDULER_ENABLED is False           # the in-source default that ships
    scheduler = idle_scheduler(tmp_path, opted_in=False)
    assert scheduler_enabled(scheduler._policy()) is False
    assert scheduler.enabled() is False

    result = scheduler.cycle()

    assert result == {"state": "DISABLED", "dispatched": False, "enabled": False}
    # Nothing was scheduled, nothing was counted, nothing was created.
    persisted = scheduler.state()
    assert persisted["state"] == "NEVER_RAN" and persisted["cycles"] == 0
    assert persisted["next_run_at"] == 0.0
    assert scheduler.store.list_sessions() == []


def test_with_the_switch_off_background_work_cannot_bring_the_scheduler_up(tmp_path, monkeypatch):
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    scheduler = idle_scheduler(tmp_path, opted_in=False)
    service = LabV1Service()
    service._supervisor = scheduler.supervisor
    service._scheduler = scheduler
    service._background_interval = 0.05

    async def exercise():
        started = await service.start_scheduler()
        background = await service.start_background()
        await asyncio.sleep(0.25)
        return started, background, await service.stop_background()

    started, background, stopped = asyncio.run(exercise())

    assert started == {"success": True, "state": "DISABLED"}
    assert background["state"] == "RUNNING"      # the supervisor loop, not the scheduler
    assert service._scheduler_task is None       # no scheduler task was ever created
    assert stopped["state"] == "PAUSED"
    assert scheduler.state()["cycles"] == 0
    assert scheduler.store.list_sessions() == []


def test_the_owner_opt_in_is_persisted_and_reversible(tmp_path, monkeypatch):
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    scheduler = idle_scheduler(tmp_path, opted_in=False)
    service = LabV1Service()
    service._supervisor = scheduler.supervisor
    service._scheduler = scheduler
    service._scheduler_poll_seconds = 0.05

    async def exercise():
        before = await service.start_scheduler()
        turned_on = await service.configure_scheduler(True)
        running = service._scheduler_task is not None and not service._scheduler_task.done()
        on_disk = scheduler.supervisor.policy()["scheduler_enabled"]
        turned_off = await service.configure_scheduler(False)
        return before, turned_on, running, on_disk, turned_off

    before, turned_on, running, on_disk, turned_off = asyncio.run(exercise())

    assert before == {"success": True, "state": "DISABLED"}
    assert turned_on == {"success": True, "enabled": True} and running is True
    assert on_disk is True                       # persisted in lab_autonomy_policy
    assert turned_off == {"success": True, "enabled": False}
    assert service._scheduler_task is None
    assert scheduler.supervisor.policy()["scheduler_enabled"] is False


# ---------------------------------------------------------------------------
# 2. Backoff and cadence.
# ---------------------------------------------------------------------------
def test_backoff_grows_when_there_is_nothing_worth_doing(tmp_path, monkeypatch):
    monkeypatch.setenv(SCHEDULER_ENV_FLAG, "1")
    scheduler = idle_scheduler(tmp_path)

    first = scheduler.cycle(now=T0)
    early = scheduler.cycle(now=T0 + 1)
    second = scheduler.cycle(now=first["next_run_at"])
    third = scheduler.cycle(now=second["next_run_at"])

    assert first["state"] == "NO_WORK" and first["interval_seconds"] == BASE * 2
    # Asking again before it is due costs one SQLite read and nothing else.
    assert early["state"] == "WAITING" and early["dispatched"] is False
    assert early["seconds_remaining"] == pytest.approx(BASE * 2 - 1)
    assert second["interval_seconds"] == BASE * 4
    assert third["interval_seconds"] == BASE * 8
    assert scheduler.state()["consecutive_idle_cycles"] == 3
    assert scheduler.state()["cycles"] == 3       # the WAITING probe is not a cycle
    assert scheduler.store.list_sessions() == []


def test_backoff_stops_at_the_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv(SCHEDULER_ENV_FLAG, "1")
    scheduler = idle_scheduler(tmp_path)
    now, intervals = T0, []

    for _ in range(10):
        result = scheduler.cycle(now=now)
        intervals.append(result["interval_seconds"])
        now = result["next_run_at"]

    assert intervals[:5] == [BASE * 2, BASE * 4, BASE * 8, BASE * 16, SCHEDULER_MAX_INTERVAL_SECONDS]
    assert set(intervals[4:]) == {SCHEDULER_MAX_INTERVAL_SECONDS}


# ---------------------------------------------------------------------------
# 3. Restart survival, by a real child process.
# ---------------------------------------------------------------------------
CHILD = '''
import json, os, sys
sys.path.insert(0, {repository!r})
os.environ["ZARA_LAB_SCHEDULER_ENABLED"] = "1"
from pathlib import Path
from tests.test_lab_improvement_scheduler import idle_scheduler

root = Path(sys.argv[1])
scheduler = idle_scheduler(root)
result = scheduler.cycle(now=float(sys.argv[2]))
(root / "first.json").write_text(json.dumps(result))
os._exit(9)
'''


def test_the_schedule_survives_a_real_process_restart(tmp_path, monkeypatch):
    monkeypatch.setenv(SCHEDULER_ENV_FLAG, "1")
    script = tmp_path / "child_scheduler.py"
    script.write_text(CHILD.format(repository=REPOSITORY), encoding="utf-8")
    done = subprocess.run([sys.executable, str(script), str(tmp_path), str(T0)],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 9, (done.returncode, done.stdout[-3000:], done.stderr[-3000:])
    first = json.loads((tmp_path / "first.json").read_text())
    assert first["state"] == "NO_WORK" and first["interval_seconds"] == BASE * 2

    # A brand new process, new store, new supervisor, same database: the restart.
    scheduler = idle_scheduler(tmp_path)
    resumed = scheduler.state()

    assert resumed["next_run_at"] == first["next_run_at"]
    assert resumed["interval_seconds"] == BASE * 2
    assert resumed["consecutive_idle_cycles"] == 1 and resumed["cycles"] == 1
    # It resumes the grown interval instead of restarting at the base cadence.
    assert scheduler.cycle(now=T0 + 1)["state"] == "WAITING"
    assert scheduler.cycle(now=first["next_run_at"])["interval_seconds"] == BASE * 4


# ---------------------------------------------------------------------------
# 4. Real work: a real gap becomes a real Mission through the canonical flow.
# ---------------------------------------------------------------------------
def test_a_real_capability_gap_creates_a_real_mission(loop, monkeypatch):  # noqa: F811
    # No environment override here: this proves route 3, the persisted opt-in.
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop)

    result = scheduler.cycle(now=T0)

    assert result["state"] == "DISPATCHED" and result["dispatched"] is True
    assert result["kind"] == "CAPABILITY_GAP" and result["key"].startswith("gap:")
    sid = result["session_id"]
    # A real mission in the real controller, created by the canonical flow.
    assert loop["autopilot"].controller.snapshot(sid)["state"] == "QUEUED"
    metrics = loop["autopilot"].metrics(sid)
    assert metrics["mission_kind"] == "SELF_IMPROVEMENT"
    assert metrics["evidence"]["observation_kind"] == "RUNTIME_CAPABILITY_FAILURE"
    assert metrics["source_work"]["source_paths"] == [EXECUTOR_PATH]
    # A productive cycle snaps the cadence back to the base and spends budget once.
    assert result["interval_seconds"] == BASE
    assert scheduler.state()["consecutive_idle_cycles"] == 0
    assert scheduler.state()["dispatched"] == 1
    assert scheduler.supervisor.policy()["daily_missions"] == 1
    assert scheduler.supervisor.policy()["active_session"] == sid


def test_a_live_mission_outranks_speculative_improvement_work(loop, monkeypatch):  # noqa: F811
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop, cap=5)
    first = scheduler.cycle(now=T0)
    sessions_before = [row.id for row in loop["store"].list_sessions()]

    busy = scheduler.cycle(now=first["next_run_at"])

    assert busy["state"] == "BUSY_HIGHER_PRIORITY" and busy["dispatched"] is False
    assert busy["detail"]["active_sessions"] == [first["session_id"]]
    # Standing down for a live mission is not an unproductive cycle: no backoff.
    assert busy["interval_seconds"] == BASE
    assert busy["consecutive_idle_cycles"] == 0
    assert [row.id for row in loop["store"].list_sessions()] == sessions_before
    assert scheduler.supervisor.policy()["daily_missions"] == 1


def test_the_daily_budget_is_the_supervisors_and_is_never_exceeded(loop, monkeypatch):  # noqa: F811
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop, cap=1)
    first = scheduler.cycle(now=T0)
    loop["autopilot"].controller.cancel(first["session_id"])   # the machine is idle again

    blocked = scheduler.cycle(now=first["next_run_at"])

    assert blocked["state"] == "BUDGET_EXHAUSTED" and blocked["dispatched"] is False
    assert blocked["detail"]["cap"] == 1 and blocked["detail"]["remaining"] == 0
    assert blocked["interval_seconds"] == BASE * 2       # exhausted budget backs off
    assert len(loop["store"].list_sessions()) == 1
    assert scheduler.supervisor.policy()["daily_missions"] == 1


def test_the_same_capability_gap_never_produces_a_second_mission(loop, monkeypatch):  # noqa: F811
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop, cap=5)
    first = scheduler.cycle(now=T0)
    loop["autopilot"].controller.cancel(first["session_id"])

    second = scheduler.cycle(now=first["next_run_at"])

    assert first["kind"] == "CAPABILITY_GAP"
    # Budget and idleness both allow more work, so the scheduler moves on to the
    # next *different* candidate instead of re-running the one already handled.
    assert second["state"] == "DISPATCHED"
    assert second["kind"] == "SOURCE_INSPECTION"
    assert second["key"] != first["key"]
    assert first["key"] in scheduler.state()["recent_work"]
    with loop["store"]._connect() as conn:
        documents = [json.loads(row[0]) for row in
                     conn.execute("SELECT document FROM lab_evolution")]
    runtime_missions = [doc for doc in documents
                        if doc["observation"].get("kind") == "RUNTIME_CAPABILITY_FAILURE"]
    assert len(runtime_missions) == 1
    assert len(loop["store"].list_sessions()) == 2


def test_a_candidate_dispatched_inside_the_window_is_skipped(loop, monkeypatch):  # noqa: F811
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop, cap=5)
    candidates, _ = scheduler._candidates(scheduler._policy())
    keys = [item["key"] for item in candidates]
    # Priority: the real gap is offered before exploratory source inspection.
    assert [item["kind"] for item in candidates] == ["CAPABILITY_GAP", "SOURCE_INSPECTION"]
    scheduler._save(recent_work={key: {"at": T0, "session_id": "earlier", "kind": "K"}
                                 for key in keys})

    skipped = scheduler.cycle(now=T0 + 60)

    assert skipped["state"] == "DEDUP_ALL_KNOWN" and skipped["dispatched"] is False
    assert sorted(skipped["detail"]["skipped"]) == sorted(keys)
    assert loop["store"].list_sessions() == []
    # VALUE > ACTIVITY: deciding there was nothing to do cost zero model calls.
    assert loop["adapter"].prompts == []
    # Outside the dedup window the same candidate becomes eligible again.
    later = scheduler.cycle(now=T0 + SCHEDULER_DEDUP_WINDOW_SECONDS + 1)
    assert later["state"] == "DISPATCHED" and later["key"] == keys[0]
    # Measured, and stronger than the requirement: not even the dispatch talks
    # to a model. `Autopilot.start` only queues the mission; the planner is
    # reached later, when the supervisor tick actually runs it.
    assert loop["adapter"].prompts == []


def test_an_unproductive_cycle_never_reaches_a_provider(tmp_path, monkeypatch, loop):  # noqa: F811
    """Every stand-down branch, measured: no prompt is ever sent."""
    monkeypatch.delenv(SCHEDULER_ENV_FLAG, raising=False)
    observe_the_failed_action(loop)
    scheduler = gap_scheduler(loop, cap=0)          # budget closed

    exhausted = scheduler.cycle(now=T0)
    waiting = scheduler.cycle(now=T0 + 1)

    assert exhausted["state"] == "BUDGET_EXHAUSTED" and waiting["state"] == "WAITING"
    assert loop["adapter"].prompts == []
    assert loop["store"].list_sessions() == []

    # The idle Lab, on its own database: a NO_WORK cycle runs against a registry
    # with no provider registered at all, so any attempt to reach one would
    # raise and the cycle would report FAILED instead.
    monkeypatch.setenv(SCHEDULER_ENV_FLAG, "1")
    idle_root = tmp_path / "idle-lab"
    idle_root.mkdir()
    assert idle_scheduler(idle_root).cycle(now=T0)["state"] == "NO_WORK"


# ---------------------------------------------------------------------------
# 5. The driver is a timer, never a spin loop.
# ---------------------------------------------------------------------------
def test_the_scheduler_loop_ticks_on_a_timer_and_does_not_busy_poll(tmp_path, monkeypatch):
    monkeypatch.setenv(SCHEDULER_ENV_FLAG, "1")
    scheduler = idle_scheduler(tmp_path)
    service = LabV1Service()
    service._supervisor = scheduler.supervisor
    service._scheduler = scheduler
    service._scheduler_poll_seconds = 0.05
    cycles, sleeps = [], []
    real_sleep = asyncio.sleep

    def observed_cycle(**kwargs):
        cycles.append(time.monotonic())
        return {"state": "NO_WORK", "dispatched": False}

    async def observed_sleep(delay, *args, **kwargs):
        sleeps.append(delay)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(scheduler, "cycle", observed_cycle)
    monkeypatch.setattr(asyncio, "sleep", observed_sleep)

    async def exercise():
        assert (await service.start_scheduler())["state"] == "RUNNING"
        await real_sleep(0.35)
        return await service.stop_scheduler()

    stopped = asyncio.run(exercise())

    assert stopped["state"] == "PAUSED"
    assert 2 <= len(cycles) <= 12, cycles          # a timer, not a spin loop
    assert sleeps and all(delay >= 0.05 for delay in sleeps)
    gaps = [b - a for a, b in zip(cycles, cycles[1:], strict=False)]
    assert all(gap >= 0.04 for gap in gaps), gaps
    assert service._scheduler_error is None
