"""ZARA LAB REAL V1 — thin async-friendly facade for the IPC layer.

Every public method here returns a plain JSON-safe dict and never raises.
IPC handlers call this directly off the stdin dispatch loop; one uncaught
exception here would take that whole loop down. Errors come back as
`{"success": False, "error": "<mensagem curta em portugues>"}` — a shape a
caller can forward straight to the UI without translating anything.

Why `asyncio.to_thread` around `LabRuntime.submit()`
------------------------------------------------------
`submit()` shells out to a real CLI subprocess (see
`core/lab_v1/providers/claude_cli.py`) that can legitimately run for tens of
seconds. `core/ipc_handlers.py`'s `handle_lab_send` already documents the
failure mode this exists to prevent: a blocking worker turn on ZARA's own
IPC thread starves unrelated commands like `lab-state` and `system-metrics`
for the entire duration of someone else's model call. Every method that can
touch the store or a provider goes through a thread for the same reason,
even the cheap ones — consistency here is what keeps a future edit from
reintroducing the bug by "optimizing" one call site back onto the main
thread.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from pathlib import Path
from typing import Any

from core.lab_v1.domain import (
    AgentProfile,
    EventType,
    LabEvent,
    Lifecycle,
    RoleName,
    Session,
    TeamMembership,
    new_id,
    now,
)
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.providers.registry import default_registry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore

__all__ = ["LabV1Service", "ImprovementScheduler", "scheduler_enabled",
           "SCHEDULER_ENABLED", "SCHEDULER_ENV_FLAG"]

#: Reconciliation outcome a boot may never step over silently: the promotion
#: could not be driven to a single coherent state by the machine alone.
UNRESOLVED_PROMOTION_STATES = frozenset({"RECONCILIATION_NEEDS_OWNER"})

#: Durable record of what each boot found and did. One row per promotion
#: journal, plus the `@last_boot` summary row.
BOOT_RECONCILIATION_TABLE = "lab_boot_reconciliation"
LAST_BOOT_ROW = "@last_boot"

# =====================================================================
# 24/7 improvement scheduler — MASTER SWITCH
# =====================================================================
#
# The code fallback stays False. The persisted policy is authoritative: new
# Lab policies enable the scheduler following Alex's explicit 2026-09-23
# request, while an explicit saved False always keeps it paused across restart.
# The environment flag remains a test/development override only when no saved
# policy value exists.
#
# Policy resolution order in `scheduler_enabled()`:
#
#   1. explicit persisted True/False;
#   2. environment variable, only for a policy without that field;
#   3. the source fallback below.
#
# A saved pause cannot be overridden by an environment flag or source default.
SCHEDULER_ENABLED = False
SCHEDULER_ENV_FLAG = "ZARA_LAB_SCHEDULER_ENABLED"
SCHEDULER_POLICY_FLAG = "scheduler_enabled"

#: One row (id=1) holding the whole durable schedule, on the Lab's SQLite DB.
SCHEDULER_TABLE = "lab_improvement_schedule"

#: Normal cadence when the last cycle found work, and the ceiling backoff may
#: reach when it keeps finding none.
SCHEDULER_BASE_INTERVAL_SECONDS = 900.0
SCHEDULER_MAX_INTERVAL_SECONDS = 21600.0
SCHEDULER_BACKOFF_MULTIPLIER = 2.0

#: How long a dispatched piece of work keeps blocking an identical candidate.
SCHEDULER_DEDUP_WINDOW_SECONDS = 86400.0

#: Floor for the background task's sleep. There is no code path that sleeps 0.
SCHEDULER_POLL_SECONDS = 30.0

#: A mission in one of these states no longer occupies the machine.
TERMINAL_MISSION_STATES = frozenset({"COMPLETED", "CANCELLED", "FAILED"})


def scheduler_enabled(policy: dict | None = None) -> bool:
    """The single authority on whether the improvement scheduler may run."""
    import os

    saved = (policy or {}).get(SCHEDULER_POLICY_FLAG)
    if type(saved) is bool:
        return saved
    if os.environ.get(SCHEDULER_ENV_FLAG) == "1":
        return True
    return SCHEDULER_ENABLED


class ImprovementScheduler:
    """Periodically asks a local, provider-free question: is there work worth doing?

    This is a *policy* layer, not another engine. Every candidate it can pick
    already exists: `EvolutionEngine.observe_and_plan` is the only way it
    creates a Mission, `AutonomySupervisor`'s persisted daily counter is the
    only budget it spends, and the Mission it creates is carried forward by the
    supervisor tick that already runs — the scheduler never runs a mission
    itself.

    The nine properties it is responsible for:

    * **off by default** — see `scheduler_enabled` above;
    * **persistent** — the whole schedule is one JSON row in `LabStore`, so a
      restart resumes the same interval and the same dedup window instead of
      starting over at the base cadence;
    * **idle-aware** — any non-terminal mission in `mission_controls` outranks
      speculative improvement work, so the cycle stands down;
    * **backoff** — an unproductive cycle multiplies the interval up to the
      ceiling; a productive one snaps it back to the base;
    * **budgeted** — `max_new_evolution_missions_per_day` / `daily_missions`
      from the autonomy policy, the same counter `AutonomySupervisor.tick`
      spends. There is no second budget;
    * **deduplicated** — a candidate key that was dispatched inside the dedup
      window is skipped, on top of the structural dedup already inside
      `EvolutionEngine._already_observed`;
    * **prioritised** — a real capability gap always outranks exploratory
      source inspection;
    * **not a spin loop** — the driver sleeps until `next_run_at`, never less
      than `SCHEDULER_POLL_SECONDS`;
    * **cheap when idle** — deciding "is there work?" reads SQLite and hashes
      local source. It never calls a provider to find out. A provider is only
      reached after a real candidate has already been chosen.
    """

    def __init__(self, runtime, supervisor, *, clock=time.time):
        self.runtime = runtime
        self.store = runtime.store
        self.supervisor = supervisor
        self.clock = clock
        with self.store._connect() as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {SCHEDULER_TABLE}("
                         "id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL)")

    # -- durable schedule -------------------------------------------------
    @staticmethod
    def default_state() -> dict[str, Any]:
        return {
            "state": "NEVER_RAN",
            "next_run_at": 0.0,
            "interval_seconds": SCHEDULER_BASE_INTERVAL_SECONDS,
            "base_interval_seconds": SCHEDULER_BASE_INTERVAL_SECONDS,
            "max_interval_seconds": SCHEDULER_MAX_INTERVAL_SECONDS,
            "backoff_multiplier": SCHEDULER_BACKOFF_MULTIPLIER,
            "dedup_window_seconds": SCHEDULER_DEDUP_WINDOW_SECONDS,
            "consecutive_idle_cycles": 0,
            "cycles": 0,
            "dispatched": 0,
            "recent_work": {},
            "last_cycle": None,
            "last_dispatch_at": None,
            "last_dispatch_key": None,
        }

    def state(self) -> dict[str, Any]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT document FROM {SCHEDULER_TABLE} WHERE id=1").fetchone()
        stored = json.loads(row[0]) if row else {}
        return self.default_state() | stored

    def _save(self, **changes) -> dict[str, Any]:
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                f"SELECT document FROM {SCHEDULER_TABLE} WHERE id=1").fetchone()
            value = self.default_state() | (json.loads(row[0]) if row else {})
            value.update(changes)
            conn.execute(f"INSERT INTO {SCHEDULER_TABLE} VALUES(1,?) "
                         "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                         (json.dumps(value, ensure_ascii=False, default=str),))
        return value

    def _policy(self) -> dict[str, Any]:
        try:
            return self.supervisor.policy()
        except Exception:
            return {}

    def enabled(self) -> bool:
        return scheduler_enabled(self._policy())

    def seconds_until_next(self, *, now: float | None = None) -> float:
        now = self.clock() if now is None else now
        return max(0.0, float(self.state().get("next_run_at") or 0.0) - now)

    def snapshot(self) -> dict[str, Any]:
        state = self.state()
        state["enabled"] = self.enabled()
        state["source_default"] = SCHEDULER_ENABLED
        state["env_flag"] = SCHEDULER_ENV_FLAG
        return state

    # -- one cycle --------------------------------------------------------
    def cycle(self, *, now: float | None = None) -> dict[str, Any]:
        """Run one decision without racing the supervisor's mission tick."""
        lock = getattr(self.supervisor, "lock", None)
        acquired = False
        if lock is not None:
            acquired = lock.acquire(blocking=False)
            if not acquired:
                return {"state": "BUSY", "dispatched": False}
        try:
            return self._cycle_once(now=now)
        finally:
            if acquired:
                lock.release()

    def _cycle_once(self, *, now: float | None = None) -> dict[str, Any]:
        """Run at most one scheduling decision. Never raises, never blocks long."""
        now = self.clock() if now is None else now
        try:
            policy = self._policy()
            if not scheduler_enabled(policy):
                # Nothing is read, nothing is written, no work is looked for.
                return {"state": "DISABLED", "dispatched": False, "enabled": False}
            state = self.state()
            due_at = float(state.get("next_run_at") or 0.0)
            if now < due_at:
                return {"state": "WAITING", "dispatched": False,
                        "seconds_remaining": due_at - now, "next_run_at": due_at}
            active = self._active_missions()
            if active:
                # Idle detection: a live mission outranks speculative work. This
                # is not an unproductive cycle, so the interval is not backed off.
                return self._stand_down(state, now, "BUSY_HIGHER_PRIORITY",
                                        backoff=False, detail={"active_sessions": active})
            budget = self._budget(policy, now)
            if budget["remaining"] <= 0:
                return self._stand_down(state, now, "BUDGET_EXHAUSTED",
                                        backoff=True, detail=budget)
            candidates, inventory = self._candidates(policy)
            if not candidates:
                return self._stand_down(state, now, "NO_WORK", backoff=True,
                                        detail={"candidates": 0})
            fresh = [item for item in candidates
                     if not self._recently_dispatched(state, item["key"], now)]
            if not fresh:
                return self._stand_down(
                    state, now, "DEDUP_ALL_KNOWN", backoff=True,
                    detail={"skipped": [item["key"] for item in candidates]})
            return self._dispatch(state, now, fresh[0], budget, policy, inventory)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            try:
                self._save(state="FAILED", last_cycle={"at": now, "outcome": "FAILED",
                                                       "detail": detail},
                           next_run_at=now + SCHEDULER_BASE_INTERVAL_SECONDS)
            except Exception:
                pass
            return {"state": "FAILED", "dispatched": False, "error": detail}

    # -- decisions --------------------------------------------------------
    def _active_missions(self) -> list[str]:
        """Session ids of every mission that has not reached a terminal state.

        `mission_controls` is created by `MissionController`, not by
        `LabStore.initialize`, so a Lab that has never run a mission has no
        such table. Absent table means no mission, never an exception.
        """
        with self.store._connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                "AND name='mission_controls'").fetchone():
                return []
            rows = conn.execute("SELECT document FROM mission_controls").fetchall()
        active = []
        for row in rows:
            mission = json.loads(row[0])
            if mission.get("state") not in TERMINAL_MISSION_STATES:
                active.append(mission.get("session_id"))
        return active

    def _budget(self, policy: dict, now: float) -> dict[str, Any]:
        """The supervisor's own daily counter, read the way the supervisor reads it."""
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        cap = int(policy.get("max_new_evolution_missions_per_day") or 0)
        used = int(policy.get("daily_missions") or 0) if policy.get("daily_date") == day else 0
        return {"day": day, "cap": cap, "used": used, "remaining": cap - used}

    def _engine(self, policy: dict):
        """A provider-free EvolutionEngine. No model is reached by construction."""
        from core.lab_v1.evolution import EvolutionEngine
        from core.lab_v1.workforce_policy import WorkforcePolicy
        return EvolutionEngine(self.runtime, policy.get("workspace"),
                               policy=WorkforcePolicy(policy),
                               autopilot=getattr(self.supervisor, "autopilot", None))

    def _candidates(self, policy: dict) -> tuple[list[dict[str, Any]], list]:
        """Local, deterministic answer to "is there work?" — priority ordered.

        Both probes mirror exactly what `EvolutionEngine.observe_and_plan` would
        select, using the engine's own identity helpers so the keys line up with
        the missions it actually creates. If they ever drift, the dispatch below
        degrades to `NO_WORK` (the planner returns no session) — it can never
        drift into creating a duplicate mission, because `_already_observed`
        inside the engine remains the authority.
        """
        engine = self._engine(policy)
        inventory = engine.observe_local()
        gaps = engine._capability_gap_evidence()
        candidates: list[dict[str, Any]] = []

        # Priority 1 — a real capability gap observed by the runtime.
        runtime_sources, runtime_gaps = engine._runtime_gap_sources(inventory, gaps)
        if runtime_sources:
            runtime_id = engine._observation_id(
                "RUNTIME_CAPABILITY_FAILURE",
                {"sources": runtime_sources, "gaps": runtime_gaps})
            if not engine._already_observed(runtime_id):
                candidates.append({
                    "kind": "CAPABILITY_GAP", "priority": 1, "key": "gap:" + runtime_id,
                    "paths": [item["source_path"] for item in runtime_sources],
                    "gap_ids": [item["id"] for item in runtime_gaps]})

        # Priority 2 — exploratory inspection of source nobody has looked at.
        inspection_gaps = [gap for gap in gaps
                           if not str(gap["required"]).startswith("runtime.action.")]
        for batch in engine._inspection_batches(inventory):
            inspection_id = engine._observation_id(
                "SOURCE_INSPECTION", {"sources": batch, "capability_gaps": inspection_gaps})
            if engine._already_observed(inspection_id):
                continue
            candidates.append({
                "kind": "SOURCE_INSPECTION", "priority": 2,
                "key": "inspection:" + inspection_id,
                "paths": [item["source_path"] for item in batch]})
            break

        candidates.sort(key=lambda item: item["priority"])
        return candidates, inventory

    def _recently_dispatched(self, state: dict, key: str, now: float) -> bool:
        record = (state.get("recent_work") or {}).get(key)
        if not record:
            return False
        window = float(state.get("dedup_window_seconds") or SCHEDULER_DEDUP_WINDOW_SECONDS)
        return (now - float(record.get("at") or 0.0)) < window

    def _prune(self, recent: dict, now: float, window: float) -> dict:
        return {key: value for key, value in recent.items()
                if (now - float(value.get("at") or 0.0)) < window}

    # -- outcomes ---------------------------------------------------------
    def _stand_down(self, state: dict, now: float, outcome: str, *,
                    backoff: bool, detail: Any) -> dict[str, Any]:
        base = float(state.get("base_interval_seconds") or SCHEDULER_BASE_INTERVAL_SECONDS)
        ceiling = float(state.get("max_interval_seconds") or SCHEDULER_MAX_INTERVAL_SECONDS)
        factor = float(state.get("backoff_multiplier") or SCHEDULER_BACKOFF_MULTIPLIER)
        current = float(state.get("interval_seconds") or base)
        if backoff:
            interval = min(ceiling, max(base, current) * factor)
            idle = int(state.get("consecutive_idle_cycles") or 0) + 1
        else:
            interval = base
            idle = int(state.get("consecutive_idle_cycles") or 0)
        saved = self._save(
            state=outcome, interval_seconds=interval, next_run_at=now + interval,
            consecutive_idle_cycles=idle, cycles=int(state.get("cycles") or 0) + 1,
            last_cycle={"at": now, "outcome": outcome, "detail": detail})
        return {"state": outcome, "dispatched": False, "interval_seconds": interval,
                "next_run_at": saved["next_run_at"],
                "consecutive_idle_cycles": idle, "detail": detail}

    def _dispatch(self, state: dict, now: float, candidate: dict, budget: dict,
                  policy: dict, inventory) -> dict[str, Any]:
        """Create one real Mission through the canonical flow, then stand back.

        The scheduler does not run the mission. `AutonomySupervisor.tick` finds
        the pending mission on its own cadence and carries it, exactly as it
        does for a mission an owner started.
        """
        self.supervisor.ensure_team()
        engine = self._engine(policy)
        engine.autopilot = getattr(self.supervisor, "autopilot", None) or engine.autopilot
        planned = engine.observe_and_plan(inventory=inventory)
        session_id = planned.get("session_id")
        if not session_id:
            return self._stand_down(state, now, "NO_WORK", backoff=True,
                                    detail={"planner_state": planned.get("state"),
                                            "candidate": candidate["key"]})
        observed = engine.snapshot(session_id) or {}
        base = float(state.get("base_interval_seconds") or SCHEDULER_BASE_INTERVAL_SECONDS)
        window = float(state.get("dedup_window_seconds") or SCHEDULER_DEDUP_WINDOW_SECONDS)
        record = {"at": now, "session_id": session_id, "kind": candidate["kind"]}
        recent = self._prune(dict(state.get("recent_work") or {}), now, window)
        recent[candidate["key"]] = record
        # Also key by what the engine actually observed: if it picked a branch
        # other than the one probed, that branch is the thing not to repeat.
        if observed.get("repair_id"):
            recent["observation:" + str(observed["repair_id"])] = record
        self.supervisor._save(daily_date=budget["day"], daily_missions=budget["used"] + 1,
                              active_session=session_id)
        saved = self._save(
            state="DISPATCHED", interval_seconds=base, next_run_at=now + base,
            consecutive_idle_cycles=0, cycles=int(state.get("cycles") or 0) + 1,
            dispatched=int(state.get("dispatched") or 0) + 1, recent_work=recent,
            last_dispatch_at=now, last_dispatch_key=candidate["key"],
            last_cycle={"at": now, "outcome": "DISPATCHED",
                        "detail": {"key": candidate["key"], "kind": candidate["kind"],
                                   "session_id": session_id,
                                   "paths": candidate.get("paths", [])}})
        return {"state": "DISPATCHED", "dispatched": True, "session_id": session_id,
                "kind": candidate["kind"], "key": candidate["key"],
                "interval_seconds": base, "next_run_at": saved["next_run_at"],
                "budget": {**budget, "used": budget["used"] + 1}}


class LabV1Service:
    """Lazily builds and caches store/registry/adapter/runtime, once."""

    def __init__(self) -> None:
        self._store: LabStore | None = None
        self._runtime: LabRuntime | None = None
        self._autopilot = None
        self._golden = None
        self._supervisor = None
        self._supervisor_task = None
        self._manus = None
        self.on_release_ready = None
        self._ipc_loop: asyncio.AbstractEventLoop | None = None
        self._release_event_error: str | None = None
        self._background_interval = 2.0
        self._background_error: str | None = None
        self._boot_reconciliation: dict[str, Any] | None = None
        self._scheduler = None
        self._scheduler_task = None
        self._scheduler_error: str | None = None
        self._scheduler_poll_seconds = SCHEDULER_POLL_SECONDS

    def _get_supervisor(self):
        if self._supervisor is None:
            from core.lab_v1.supervisor import AutonomySupervisor
            self._supervisor = AutonomySupervisor(self._get_runtime(), autopilot=self._autopilot)
        return self._supervisor

    async def start_background(self):
        try:
            self._ipc_loop = asyncio.get_running_loop()
            policy = self._get_supervisor().policy()
            from core.lab_v1.workforce_policy import WorkforcePolicy
            workforce = WorkforcePolicy(policy)
            if not workforce.background_enabled:
                return {'success': True, 'state': 'PAUSED'}
            if self._supervisor_task and not self._supervisor_task.done():
                return {'success': True, 'state': 'RUNNING'}
            if hasattr(self._get_supervisor(), 'set_autopilot'):
                # The supervisor creates its Autopilot lazily. Bind the desktop
                # event before its first tick can complete a source promotion.
                await asyncio.to_thread(self._get_autopilot)
            self._background_error = None
            self._supervisor_task = asyncio.create_task(self._background_loop())
            # Integrated, but gated: with the master switch off this returns
            # DISABLED and creates no task, so background work can never bring
            # the scheduler up as a side effect.
            await self.start_scheduler()
            return {'success': True, 'state': 'RUNNING'}
        except Exception:
            return {'success': False, 'state': 'BLOCKED', 'error': 'Supervisor do Lab indisponivel.'}

    async def _background_loop(self):
        try:
            while True:
                try:
                    await asyncio.to_thread(self._get_supervisor().tick)
                    self._background_error = None
                except Exception as exc:
                    self._background_error = f'{type(exc).__name__}: {exc}'
                    supervisor = self._get_supervisor()
                    if hasattr(supervisor, 'record_background_error'):
                        await asyncio.to_thread(supervisor.record_background_error, self._background_error)
                policy = self._get_supervisor().policy()
                interval = max(0.01, float(getattr(self, '_background_interval', policy.get('cadence_seconds', 2))))
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._background_error = f'{type(exc).__name__}: {exc}'
            supervisor = self._get_supervisor()
            if hasattr(supervisor, 'record_background_error'):
                await asyncio.to_thread(supervisor.record_background_error, self._background_error)

    async def stop_background(self):
        task, self._supervisor_task = self._supervisor_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.stop_scheduler()
        return {'success': True, 'state': 'PAUSED'}

    # -- 24/7 improvement scheduler --------------------------------------
    def _get_scheduler(self) -> ImprovementScheduler:
        if self._scheduler is None:
            self._scheduler = ImprovementScheduler(self._get_runtime(), self._get_supervisor())
        return self._scheduler

    async def scheduler_state(self):
        try:
            return {'success': True,
                    'scheduler': await asyncio.to_thread(self._get_scheduler().snapshot),
                    'error': self._scheduler_error,
                    'task_state': ('RUNNING' if self._scheduler_task is not None
                                   and not self._scheduler_task.done() else 'STOPPED')}
        except Exception:
            return {'success': False, 'error': 'Agendador de melhorias indisponivel.'}

    async def configure_scheduler(self, enabled: bool):
        """Owner opt-in, persisted. This is the knob Alex flips after review."""
        if type(enabled) is not bool:
            return {'success': False, 'error': 'enabled precisa ser booleano.'}
        try:
            await asyncio.to_thread(
                lambda: self._get_supervisor()._save(**{SCHEDULER_POLICY_FLAG: enabled}))
            if enabled:
                await self.start_scheduler()
            else:
                await self.stop_scheduler()
            return {'success': True, 'enabled': scheduler_enabled(self._get_supervisor().policy())}
        except Exception:
            return {'success': False, 'error': 'Nao foi possivel configurar o agendador.'}

    async def start_scheduler(self):
        try:
            if not scheduler_enabled(self._get_supervisor().policy()):
                return {'success': True, 'state': 'DISABLED'}
            if self._scheduler_task is not None and not self._scheduler_task.done():
                return {'success': True, 'state': 'RUNNING'}
            self._scheduler_error = None
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            return {'success': True, 'state': 'RUNNING'}
        except Exception:
            return {'success': False, 'state': 'BLOCKED',
                    'error': 'Agendador de melhorias indisponivel.'}

    async def stop_scheduler(self):
        task, self._scheduler_task = self._scheduler_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return {'success': True, 'state': 'PAUSED'}

    async def _scheduler_loop(self):
        """Timer, never a spin: sleep until the persisted `next_run_at`."""
        try:
            while True:
                try:
                    await asyncio.to_thread(self._get_scheduler().cycle)
                    self._scheduler_error = None
                except Exception as exc:
                    self._scheduler_error = f'{type(exc).__name__}: {exc}'
                floor = max(0.01, float(self._scheduler_poll_seconds))
                try:
                    remaining = await asyncio.to_thread(self._get_scheduler().seconds_until_next)
                except Exception:
                    remaining = floor
                await asyncio.sleep(max(floor, min(float(remaining), SCHEDULER_MAX_INTERVAL_SECONDS)))
        except asyncio.CancelledError:
            raise

    @staticmethod
    def workforce_refusal():
        return {'success': False, 'code': 'WORKFORCE_POLICY_REQUIRED', 'state': 'BLOCKED',
                'error': 'A equipe automatica aguarda uma politica de modelos e limites. Nenhuma missao foi iniciada.'}

    async def front_snapshot(self):
        from core.lab_v1.front_brain import FrontBrain
        return await asyncio.to_thread(lambda: FrontBrain(self._get_runtime()).snapshot())

    async def select_front_brain(self, model):
        from core.lab_v1.front_brain import FrontBrain
        return await asyncio.to_thread(lambda: FrontBrain(self._get_runtime()).select(model))

    async def front_reply(self, text, *, requested_model=None, history=None, context='',
                          result_is_current=None):
        from core.lab_v1.front_brain import FrontBrain
        return await asyncio.to_thread(lambda: FrontBrain(self._get_runtime()).reply(
            text, requested_model=requested_model, history=history, context=context,
            result_is_current=result_is_current))

    async def discard_front_run(self, run_id):
        """Keep the factual Run receipt while removing its interrupted chat turn."""
        from core.lab_v1.front_brain import _SESSION
        return await asyncio.to_thread(
            self._get_runtime().store.delete_messages_for_run, _SESSION, str(run_id)
        )

    async def configure_autonomy(self, enabled):
        try:
            policy = await asyncio.to_thread(self._get_supervisor().configure, enabled=enabled)
            if enabled is False:
                await self.stop_scheduler()
            await self.start_background()
            return {'success': True, 'policy': policy}
        except Exception:
            return {'success': False, 'error': 'Workspace de manutencao indisponivel; nenhuma atualizacao foi iniciada.'}

    async def capture_feedback(self, text, *, channel='conversation'):
        try:
            from core.lab_v1.feedback_inbox import FeedbackInbox
            result = await asyncio.to_thread(
                FeedbackInbox(self._get_runtime().store).record, text, channel=channel)
            return {'success': True, 'captured': result is not None}
        except Exception:
            return {'success': False, 'captured': False}

    async def capture_runtime_failure(self, action_id, *, source_path, stage, status,
                                      reason, channel, run_id=None, dedup_key=None):
        """Persist a factual executor/postcondition failure for architect review.

        `dedup_key` exists because the default identity of a gap is the hash of
        the whole evidence blob — which carries `reason`, `channel` and
        `run_id`. For an executor failure that is fine: each failure is its own
        fact. For "ZARA did not recognise this phrase" it is not: the same
        phrase said twice would land on two different `gap_id`s (different
        run_id, different channel) and the store would grow one row per
        utterance, with `EvolutionEngine` seeing each row as new evidence.
        A caller that already knows the stable identity of the gap (the
        normalised phrase) passes it here, and the store upserts a single row.
        """
        accepted = {'EXECUTOR_FAILED', 'CAPABILITY_MISSING', 'POSTCONDITION_FAILED'}
        if (status not in accepted or not str(action_id).strip()
                or not str(stage).strip() or not str(reason).strip()
                or not str(channel).strip()):
            return {'success': False, 'captured': False,
                    'error': 'Factual capability failure evidence is incomplete.'}
        try:
            evidence = {
                'observation_kind': 'RUNTIME_CAPABILITY_FAILURE',
                'action_id': str(action_id), 'source_path': str(source_path or ''),
                'stage': str(stage), 'status': status,
                'reason': str(reason), 'channel': str(channel),
                'run_id': str(run_id) if run_id is not None else None,
            }
            identity = (str(dedup_key) if dedup_key is not None and str(dedup_key).strip()
                        else json.dumps(evidence, ensure_ascii=False, sort_keys=True))
            gap_id = 'runtime-gap:' + hashlib.sha256(identity.encode('utf-8')).hexdigest()
            from core.lab_v1.domain import CapabilityGap
            gap = CapabilityGap(gap_id, None, 'runtime.action.' + str(action_id),
                                detail=json.dumps(evidence, ensure_ascii=False, sort_keys=True))
            await asyncio.to_thread(self._get_runtime().store.save_capability_gap, gap)
            return {'success': True, 'captured': True, 'gap_id': gap_id}
        except Exception:
            return {'success': False, 'captured': False,
                    'error': 'Falha factual de capacidade não foi registrada.'}

    def _get_autopilot(self):
        supervisor = self._get_supervisor()
        if self._autopilot is None:
            self._autopilot = getattr(supervisor, 'autopilot', None)
            if self._autopilot is None:
                from core.lab_v1.autopilot import Autopilot
                from core.lab_v1.workforce_policy import WorkforcePolicy
                self._autopilot = Autopilot(self._get_runtime(), policy=WorkforcePolicy(supervisor.policy()))
        if hasattr(supervisor, 'set_autopilot') and getattr(supervisor, 'autopilot', None) is None:
            supervisor.set_autopilot(self._autopilot)
        self._autopilot.on_release_ready = self._queue_release_ready
        return self._autopilot

    def _queue_release_ready(self, payload: dict[str, Any]) -> bool:
        """Deliver the verified release event on the IPC loop from a worker."""
        callback, loop = self.on_release_ready, self._ipc_loop
        if not callable(callback) or loop is None or loop.is_closed():
            return False
        try:
            result = callback(payload)
            if inspect.isawaitable(result):
                future = asyncio.run_coroutine_threadsafe(result, loop)

                def finished(done):
                    try:
                        done.result()
                    except Exception as exc:
                        self._release_event_error = f'{type(exc).__name__}: {exc}'

                future.add_done_callback(finished)
            return True
        except Exception as exc:
            self._release_event_error = f'{type(exc).__name__}: {exc}'
            return False

    async def start_autopilot(self, intent: str, session_id: str | None = None):
        self._ipc_loop = asyncio.get_running_loop()
        try:
            blocked = await asyncio.to_thread(self._promotion_block)
            if blocked is not None:
                return blocked
            from core.lab_v1.workforce_policy import WorkforcePolicy
            if not WorkforcePolicy(self._get_supervisor().policy()).mission_entry_enabled:
                return self.workforce_refusal()
            result = await asyncio.to_thread(self._get_autopilot().start, intent, session_id=session_id)
            import os
            entry_canary = (os.environ.get('ZARA_SMOKE_TEST') == '1'
                            and os.environ.get('ZARA_LAB_ENTRY_CANARY') == '1')
            if result.get('success') and not entry_canary:
                await self.start_background()
            return result
        except ValueError as exc:
            return {'success': False, 'state': 'WAITING_RESOURCE', 'code': str(exc), 'error': str(exc)}
        except Exception:
            return {'success': False, 'state': 'BLOCKED_NEEDS_OWNER', 'error': 'Nao foi possivel iniciar a missao.'}

    async def run_autopilot(self, session_id: str):
        self._ipc_loop = asyncio.get_running_loop()
        try:
            return await asyncio.to_thread(self._get_autopilot().run, session_id)
        except Exception:
            return {'success': False, 'state': 'BLOCKED_NEEDS_OWNER', 'error': 'Falha ao continuar a missao.'}

    async def resume_source_autopilot(self, session_id: str):
        """Resume a failed source mission in place; never creates another session."""
        self._ipc_loop = asyncio.get_running_loop()
        try:
            return await asyncio.to_thread(self._get_autopilot().resume_failed_source, session_id)
        except Exception:
            return {'success': False, 'state': 'BLOCKED_NEEDS_OWNER', 'error': 'Falha ao retomar a missao.'}

    async def cancel_autopilot(self, session_id: str):
        try:
            controller = self._get_autopilot().controller
            await asyncio.to_thread(controller.cancel, session_id)
            return {'success': True, 'mission': controller.snapshot(session_id)}
        except Exception:
            return {'success': False, 'error': 'Missao nao encontrada.'}

    def _get_golden(self):
        if self._golden is None:
            from core.lab_v1.golden_path import GoldenPath
            self._golden = GoldenPath(self._get_runtime())
        return self._golden

    @staticmethod
    def is_self_improvement_intent(intent):
        import re
        return bool(re.search(r'\b(?:audit[ae]|melhor[ae]|corrij[ae])\b', intent, re.I)
                    and re.search(r'\b(?:zara|pr[óo]pria|classificador)\b', intent, re.I))

    def _get_runtime(self) -> LabRuntime:
        if self._runtime is None:
            store = LabStore()
            store.initialize()
            # Boot gate: an interrupted promotion owns the runtime until it is
            # reconciled. Nothing below this line may run on top of a
            # half-promoted source/package/pointer state.
            self._boot_reconciliation = self._reconcile_interrupted_promotions(store)
            registry = default_registry()
            memory_adapter = LabMemoryAdapter(store)
            self._store = store
            self._runtime = LabRuntime(store, registry, memory_adapter)
        return self._runtime

    # -- boot reconciliation ---------------------------------------------
    def _reconcile_interrupted_promotions(self, store) -> dict[str, Any]:
        """Drive any interrupted source promotion to one coherent state, at boot.

        This is only the missing *caller*: the mechanism is the canonical one in
        `core/lab_v1/release.py` (`reconcile_promotions` → `SourcePromotion.reconcile`),
        which decides from disk evidence, never from what the journal claims, and
        never replays an effect it cannot prove. Idempotent by construction — a
        journal already in a terminal state reports `ALREADY_TERMINAL` and nothing
        is touched, so restarting the service repeatedly cannot duplicate an effect.

        Every outcome is persisted, including the ones that failed: a boot is
        never allowed to look clean by forgetting that a promotion could not be
        reconciled.
        """
        report: dict[str, Any] = {"checked_at": time.time(), "state": "CLEAN",
                                  "pending_before": [], "records": [],
                                  "queue_records": [], "unresolved": []}
        try:
            self._ensure_boot_table(store)
            from core.lab_v1.release import (
                SOURCE_WORKFLOW, ReleaseQueue, _build_module_for_workspace,
                pending_promotions, reconcile_promotions,
            )
            from core.lab_v1.supervisor import _default_workspace
            build = _build_module_for_workspace(_default_workspace())
            report["pending_before"] = pending_promotions(build=build)
            if report["pending_before"]:
                report["records"] = reconcile_promotions(build=build)
            # A crash can leave the journal committed while the SQLite release
            # row still says ACTIVATING/MONITORING/COMMIT_PENDING. Reconcile that
            # row from the journal before allowing the next mission to start.
            queue = ReleaseQueue(store, build=build)
            with store._connect() as conn:
                rows = conn.execute('SELECT session_id, document FROM lab_releases').fetchall()
            for sid, raw in rows:
                doc = json.loads(raw)
                if (doc.get('workflow') == SOURCE_WORKFLOW
                        and doc.get('state') in {'ACTIVATING', 'MONITORING', 'COMMIT_PENDING'}):
                    resolved = queue.reconcile_interrupted(sid)
                    report['queue_records'].append({'session_id': sid,
                                                    'state': resolved.get('state'),
                                                    'journal': resolved.get('rollback_journal'),
                                                    'needs_owner': resolved.get('needs_owner', False)})
        except Exception as exc:
            # Reconciliation itself broke. That is the loudest possible state:
            # persist it and let the Lab refuse mission entry.
            report["state"] = "NEEDS_OWNER"
            report["error"] = f"{type(exc).__name__}: {exc}"
            report["unresolved"] = [{"journal": "BOOT_RECONCILIATION_FAILED",
                                     "state": report["error"]}]
            try:
                self._persist_summary(store, report)
            except Exception:
                pass
            return report
        try:
            self._persist_records(store, report["records"])
            report["unresolved"] = (self._unresolved_promotions(store)
                                     + self._unresolved_release_queue(store))
            report["state"] = ("NEEDS_OWNER" if report["unresolved"]
                               else "RECONCILED" if report["records"] or report["queue_records"]
                               else "CLEAN")
            self._persist_summary(store, report)
        except Exception as exc:
            report["state"] = "NEEDS_OWNER"
            report["error"] = f"{type(exc).__name__}: {exc}"
        return report

    @staticmethod
    def _ensure_boot_table(store) -> None:
        with store._connect() as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {BOOT_RECONCILIATION_TABLE}("
                         "journal TEXT PRIMARY KEY, document TEXT NOT NULL)")

    @staticmethod
    def _persist_records(store, records) -> None:
        """Write one receipt per journal. A later `NONE` never overwrites a real one."""
        with store._connect() as conn:
            for record in records:
                document = json.dumps(record, ensure_ascii=False, default=str)
                journal = str(record.get("journal"))
                verb = "IGNORE" if record.get("action") == "NONE" else "REPLACE"
                conn.execute(f"INSERT OR {verb} INTO {BOOT_RECONCILIATION_TABLE} VALUES(?,?)",
                             (journal, document))

    @staticmethod
    def _persist_summary(store, report) -> None:
        LabV1Service._ensure_boot_table(store)
        with store._connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO {BOOT_RECONCILIATION_TABLE} VALUES(?,?)",
                         (LAST_BOOT_ROW, json.dumps(report, ensure_ascii=False, default=str)))

    @staticmethod
    def _unresolved_promotions(store) -> list[dict[str, Any]]:
        """Failures recorded by any past boot, re-checked against the journal on disk.

        A recorded failure stops counting only when the journal itself stops
        declaring it — never because a later boot forgot about it.
        """
        LabV1Service._ensure_boot_table(store)
        with store._connect() as conn:
            rows = conn.execute(
                f"SELECT journal, document FROM {BOOT_RECONCILIATION_TABLE}").fetchall()
        unresolved = []
        for journal, document in rows:
            if str(journal).startswith("@"):
                continue
            try:
                record = json.loads(document)
            except ValueError:
                continue
            if record.get("to_state") not in UNRESOLVED_PROMOTION_STATES:
                continue
            try:
                state = json.loads(Path(journal).read_text(encoding="utf-8")).get("state")
            except (OSError, ValueError):
                state = "JOURNAL_UNREADABLE"
            if state in UNRESOLVED_PROMOTION_STATES or state == "JOURNAL_UNREADABLE":
                unresolved.append({"journal": journal, "state": state,
                                   "reason": record.get("reason")})
        return unresolved

    @staticmethod
    def _unresolved_release_queue(store) -> list[dict[str, Any]]:
        from core.lab_v1.release import SOURCE_WORKFLOW

        with store._connect() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_releases'").fetchone()
            rows = conn.execute('SELECT session_id, document FROM lab_releases').fetchall() if exists else []
        unresolved = []
        for sid, raw in rows:
            try:
                doc = json.loads(raw)
            except ValueError:
                unresolved.append({'session_id': sid, 'state': 'QUEUE_UNREADABLE'})
                continue
            if (doc.get('workflow') == SOURCE_WORKFLOW
                    and (doc.get('state') in {'ACTIVATING', 'MONITORING', 'COMMIT_PENDING'}
                         or (doc.get('state') == 'BLOCKED' and doc.get('needs_owner')))):
                unresolved.append({'session_id': sid, 'state': doc.get('state'),
                                   'journal': doc.get('rollback_journal')})
        return unresolved

    def boot_reconciliation(self) -> dict[str, Any]:
        """What the boot gate found, with the unresolved list re-read from disk."""
        report = dict(self._boot_reconciliation or {"state": "NOT_RUN"})
        try:
            if self._store is not None:
                report["unresolved"] = (self._unresolved_promotions(self._store)
                                        + self._unresolved_release_queue(self._store))
                if report["unresolved"]:
                    report["state"] = "NEEDS_OWNER"
        except Exception as exc:
            report["state"] = "NEEDS_OWNER"
            report["error"] = f"{type(exc).__name__}: {exc}"
        return report

    def _promotion_block(self) -> dict[str, Any] | None:
        """Refuse mission entry while an interrupted promotion still needs the owner."""
        try:
            self._get_runtime()
        except Exception:
            return None
        report = self.boot_reconciliation()
        if not report.get("unresolved"):
            return None
        return {"success": False, "code": "PROMOTION_RECONCILIATION_NEEDS_OWNER",
                "state": "BLOCKED_NEEDS_OWNER", "boot_reconciliation": report,
                "error": "Uma promocao interrompida nao pode ser reconciliada; "
                         "nenhuma missao inicia ate o dono resolver."}

    async def snapshot(self, session_id: str | None = None, team_id: str | None = None) -> dict[str, Any]:
        try:
            runtime = self._get_runtime()
            data = await asyncio.to_thread(runtime.snapshot, session_id, team_id)
            from core.lab_v1.manus import ManusWorkCell
            if self._manus is None:
                self._manus = ManusWorkCell(runtime.store)
            data['workcells'] = [self._manus.status()]
            supervisor_policy = self._get_supervisor().policy()
            task = self._supervisor_task
            supervisor_policy['background_task_state'] = (
                'RUNNING' if task is not None and not task.done()
                else 'FAILED' if self._background_error
                else 'STOPPED')
            supervisor_policy['background_error'] = self._background_error or (
                supervisor_policy.get('error_detail') if supervisor_policy.get('last_state') == 'FAILED' else None)
            data['autonomy_policy'] = supervisor_policy
            from core.lab_v1.scout import TechnologyScout
            data['improvement_opportunities'] = TechnologyScout(runtime.store).snapshot()['opportunities']
            from core.lab_v1.release import ReleaseQueue
            data['release'] = ReleaseQueue(runtime.store).snapshot()
            data['boot_reconciliation'] = await asyncio.to_thread(self.boot_reconciliation)
            try:
                data['improvement_scheduler'] = await asyncio.to_thread(
                    self._get_scheduler().snapshot)
            except Exception as exc:
                data['improvement_scheduler'] = {'state': 'UNAVAILABLE', 'enabled': False,
                                                 'error': f'{type(exc).__name__}: {exc}'}
            data.setdefault("success", True)
            return data
        except Exception as exc:
            return {"success": False, "error": f"Falha ao ler o estado do Lab: {exc}"}

    async def create_session(
        self,
        objective: str,
        *,
        acceptance_criteria: list[str] | None = None,
        max_delegations: int = 4,
        max_cost_usd: float | None = None,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            runtime = self._get_runtime()
            assert self._store is not None

            def _create() -> Session:
                team = self._store.get_team(team_id) if team_id else runtime.ensure_core_team()
                if team is None or team.archived:
                    raise ValueError("Time nao encontrado ou arquivado.")
                session = Session(
                    id=new_id("session"), team_id=team.id, objective=objective,
                    acceptance_criteria=list(acceptance_criteria or []),
                    max_delegations=max_delegations, max_cost_usd=max_cost_usd,
                )
                self._store.save_session(session)
                return session

            session = await asyncio.to_thread(_create)
            return {"success": True, "session": session.to_dict()}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao criar sessao no Lab: {exc}"}

    async def submit(self, session_id: str, text: str) -> dict[str, Any]:
        # A controlled mission accepts only its original owner objective. Further
        # worker transitions belong to MissionController, never to chat messages.
        try:
            mission = self._get_autopilot().controller.snapshot(session_id)
            if mission:
                return {'success': False, 'code': 'MISSION_CONTROLLED', 'state': mission['state'],
                        'error': 'A missao continua automaticamente pelo Mission Controller.'}
        except Exception:
            pass
        session = await asyncio.to_thread(self._get_runtime().store.get_session, session_id)
        if session is None:
            return {'success': False, 'code': 'SESSION_NOT_FOUND', 'state': 'BLOCKED', 'error': 'Missao nao encontrada.'}
        if getattr(session.state, 'value', session.state) != 'QUEUED':
            return {'success': False, 'code': 'SESSION_NOT_QUEUED', 'state': str(getattr(session.state, 'value', session.state)),
                    'error': 'Somente uma sessao inicial na fila pode entrar no Mission Controller.'}
        return await self.start_autopilot(text, session_id=session_id)

    async def create_agent(
        self,
        *,
        name: str,
        provider_id: str,
        model: str,
        role: str = "MEMBER",
        team_id: str | None = None,
        lifecycle: str = "PERMANENT",
        instructions: str = "",
        fallback_agent_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            self._get_runtime()
            assert self._store is not None

            role_enum = RoleName(role)
            lifecycle_enum = Lifecycle(lifecycle)
            adapter = self._runtime.registry.get(provider_id)
            if adapter is None or model not in {m.model_id for m in adapter.declared_models}:
                raise ValueError('Escolha um modelo real do catalogo do provedor.')

            def _create() -> AgentProfile:
                agent = AgentProfile(
                    id=new_id("agent"), name=name, provider_id=provider_id, model=model,
                    role=role_enum, instructions=instructions, lifecycle=lifecycle_enum,
                    fallback_agent_id=fallback_agent_id,
                    capabilities=['model.text'] if adapter.controlled_text_only else [],
                )
                self._store.save_agent(agent)
                self._store.append_event(
                    LabEvent(
                        id=new_id("evt"), seq=0, type=EventType.AGENT_CREATED, session_id=None,
                        entity_id=agent.id, payload={"name": agent.name, "role": agent.role.value},
                        occurred_at=now(),
                    )
                )
                if team_id:
                    self._store.save_membership(
                        TeamMembership(id=new_id("mem"), team_id=team_id, agent_id=agent.id)
                    )
                return agent

            agent = await asyncio.to_thread(_create)
            return {"success": True, "agent": agent.to_dict()}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao criar agente: {exc}"}

    async def archive_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            self._get_runtime()
            assert self._store is not None

            def _archive() -> AgentProfile | None:
                agent = self._store.get_agent(agent_id)
                if agent is None:
                    return None
                # Archive, never hard-delete: past Messages/Runs/Tasks still
                # reference this agent_id, and deleting the row would orphan
                # that history.
                agent.archived = True
                self._store.save_agent(agent)
                self._store.append_event(
                    LabEvent(
                        id=new_id("evt"), seq=0, type=EventType.AGENT_ARCHIVED, session_id=None,
                        entity_id=agent.id, payload={}, occurred_at=now(),
                    )
                )
                return agent

            agent = await asyncio.to_thread(_archive)
            if agent is None:
                return {"success": False, "error": f"Agente '{agent_id}' nao encontrado."}
            return {"success": True, "agent": agent.to_dict()}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao arquivar agente: {exc}"}

    async def rebind_role(self, team_id: str, role: str, agent_id: str, reason: str) -> dict[str, Any]:
        try:
            runtime = self._get_runtime()
            role_enum = RoleName(role)
            handoff = await asyncio.to_thread(
                runtime.rebind_role, team_id, role_enum, agent_id, reason=reason,
            )
            return {"success": True, "handoff": handoff.to_dict()}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao trocar o titular do papel: {exc}"}

    async def providers(self) -> dict[str, Any]:
        try:
            runtime = self._get_runtime()
            infos = await asyncio.to_thread(runtime.registry.list_providers)
            return {"success": True, "providers": [p.to_dict() for p in infos]}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao consultar provedores: {exc}"}
