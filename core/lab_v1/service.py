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
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from core.lab_v1.domain import (
    AgentProfile,
    EventType,
    LabEvent,
    Lifecycle,
    MessageKind,
    RoleName,
    Session,
    TeamMembership,
    new_id,
    now,
)
from core.lab_v1.autopilot import WorkspaceNotConfigured
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.operation_ledger import IdempotencyConflict, OperationLedger
from core.lab_v1.providers.registry import default_registry
from core.lab_v1.research_skill_autopilot import AutonomousResearchSkillPipeline
from core.lab_v1.team_chat_memory import TeamChatMemory
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
# `SCHEDULER_ENABLED` is the installation default.  Alex authorized the Lab
# to be resident by default, but the persisted policy remains the authority:
# `configure_scheduler(False)` must survive a restart and turn it back off.
#
# Precedence in `scheduler_enabled()` is therefore deliberately explicit:
#
#   1. a persisted boolean `scheduler_enabled` in `lab_autonomy_policy`;
#   2. `ZARA_LAB_SCHEDULER_ENABLED=1` for isolated sandbox tests;
#   3. this installation default for a Lab database that predates the setting.
#
# This gives a new or migrated installation a working default without making
# the owner opt-out ineffective.
# Owner-approved priority: let the bounded Lab improvement loop run while ZARA
# is open. This does not grant shell access or bypass workforce policy; every
# candidate still passes the supervisor budget, deduplication, mission scope,
# artifact verification and provider capability gates below.
SCHEDULER_ENABLED = True
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
RESEARCH_INTERVAL_SECONDS = 21600.0
RESEARCH_SOURCES = (
    "https://github.com/openai/codex/releases.atom",
    "https://github.com/NousResearch/hermes-agent/releases.atom",
)

#: A mission in one of these states no longer occupies the machine.
TERMINAL_MISSION_STATES = frozenset({"COMPLETED", "CANCELLED", "FAILED"})


def scheduler_enabled(policy: dict | None = None) -> bool:
    """The single authority on whether the improvement scheduler may run."""
    import os

    configured = (policy or {}).get(SCHEDULER_POLICY_FLAG)
    if type(configured) is bool:
        return configured
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

    * **installed by default and owner-configurable** — see `scheduler_enabled` above;
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
        policy = self._policy()
        configured = policy.get(SCHEDULER_POLICY_FLAG)
        state["enabled"] = scheduler_enabled(policy)
        state["configured_enabled"] = configured if type(configured) is bool else None
        state["activation_source"] = (
            "PERSISTED_POLICY" if type(configured) is bool else
            "PROCESS_OVERRIDE" if __import__("os").environ.get(SCHEDULER_ENV_FLAG) == "1" else
            "INSTALLATION_DEFAULT"
        )
        state["source_default"] = SCHEDULER_ENABLED
        state["env_flag"] = SCHEDULER_ENV_FLAG
        return state

    # -- one cycle --------------------------------------------------------
    def cycle(self, *, now: float | None = None) -> dict[str, Any]:
        """Run one decision under the supervisor's single mission gate."""
        gate = self.supervisor.lock
        if not gate.acquire(blocking=False):
            return {"state": "BUSY", "dispatched": False}
        try:
            return self._cycle_locked(now=now)
        finally:
            gate.release()

    def _cycle_locked(self, *, now: float | None = None) -> dict[str, Any]:
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
        except WorkspaceNotConfigured as exc:
            detail = str(exc)
            try:
                self._save(state="WORKSPACE_NOT_CONFIGURED",
                           last_cycle={"at": now, "outcome": "WORKSPACE_NOT_CONFIGURED",
                                       "detail": detail},
                           next_run_at=now + SCHEDULER_BASE_INTERVAL_SECONDS)
            except Exception:
                pass
            return {"state": "WORKSPACE_NOT_CONFIGURED", "dispatched": False,
                    "error": detail}
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
        self._shared_brain = None
        self._autopilot = None
        self._golden = None
        self._supervisor = None
        self._supervisor_task = None
        self._provider_discovery_task = None
        self._provider_discovery_error = None
        self._manus = None
        self.on_release_ready = None
        self._background_interval = 2.0
        self._background_error: str | None = None
        self._boot_reconciliation: dict[str, Any] | None = None
        self._scheduler = None
        self._scheduler_task = None
        self._scheduler_error: str | None = None
        self._scheduler_poll_seconds = SCHEDULER_POLL_SECONDS
        self._operation_ledger: OperationLedger | None = None
        self._operation_reconciled = False
        self._operation_consumer_task: asyncio.Task | None = None
        self._operation_consumer_queue: asyncio.Queue[str] | None = None
        self._operation_consumer_idle: asyncio.Event | None = None
        self._operation_consumer_loop: asyncio.AbstractEventLoop | None = None
        self._operation_consumer_error: str | None = None
        self._operation_consumer_results: list[dict[str, Any]] = []
        self._proposal_feed = None
        self._agent_inventory_cache = None
        self._agent_profiles = None
        self._research_skill_pipeline = None
        self._team_chat_memory = None
        self._research_last_run = 0.0
        self._research_last_result: dict[str, Any] | None = None

    def _get_research_skill_pipeline(self) -> AutonomousResearchSkillPipeline:
        if self._research_skill_pipeline is None:
            self._research_skill_pipeline = AutonomousResearchSkillPipeline()
        return self._research_skill_pipeline

    def _get_team_chat_memory(self) -> TeamChatMemory:
        if self._team_chat_memory is None:
            self._team_chat_memory = TeamChatMemory()
        return self._team_chat_memory

    async def append_team_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(self._get_team_chat_memory().append, **payload)
            return result
        except Exception as exc:
            return {"success": False, "state": "REJECTED", "error": str(exc)}

    async def research_skill_pipeline(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run one bounded research/skill gate without executing discovered code."""
        try:
            pipeline = self._get_research_skill_pipeline()
            if operation == "snapshot":
                return {"success": True, **await asyncio.to_thread(pipeline.snapshot)}
            if operation == "research":
                result = await asyncio.to_thread(pipeline.research, payload.get("topic"), payload.get("sources", []))
                return {"success": True, "result": result}
            if operation == "candidate":
                result = await asyncio.to_thread(
                    pipeline.create_candidate,
                    skill_id=payload.get("skill_id"), version=payload.get("version"),
                    description=payload.get("description"), permissions=payload.get("permissions", []),
                    research=payload.get("research") or {},
                )
                return {"success": True, "result": result}
            if operation == "test":
                result = await asyncio.to_thread(
                    pipeline.record_test, payload.get("skill_id"), payload.get("version"),
                    payload.get("test_id"), passed=payload.get("passed") is True,
                    summary=payload.get("summary"),
                )
                return {"success": True, "result": result}
            if operation == "activate":
                result = await asyncio.to_thread(
                    pipeline.activate, payload.get("skill_id"), payload.get("version"),
                    owner_approved=payload.get("owner_approved") is True,
                )
                return {"success": True, "result": result}
            if operation == "rollback":
                result = await asyncio.to_thread(
                    pipeline.rollback, payload.get("skill_id"), to_version=payload.get("to_version"),
                )
                return {"success": True, "result": result}
            return {"success": False, "error": "Operação de pesquisa/skill desconhecida"}
        except Exception as exc:
            return {"success": False, "error": str(exc), "code": type(exc).__name__}

    async def _run_scheduled_research(self) -> dict[str, Any]:
        """Collect bounded official release evidence; never creates/activates code."""
        now = time.time()
        if now - self._research_last_run < RESEARCH_INTERVAL_SECONDS:
            return {"state": "WAITING", "next_in": RESEARCH_INTERVAL_SECONDS - (now - self._research_last_run)}
        try:
            result = await asyncio.to_thread(
                self._get_research_skill_pipeline().research,
                "ZARA Lab official release research",
                RESEARCH_SOURCES,
            )
            self._research_last_run = now
            self._research_last_result = {"state": "OBSERVED", "research_id": result.get("research_id"), "findings": len(result.get("findings", [])), "failures": len(result.get("failures", [])), "at": now}
            return self._research_last_result
        except Exception as exc:
            self._research_last_run = now
            self._research_last_result = {"state": "FAILED", "error": type(exc).__name__, "at": now}
            return self._research_last_result

    def _get_operation_ledger(self) -> OperationLedger:
        if self._operation_ledger is None:
            store = self._store or LabStore()
            self._operation_ledger = OperationLedger(store.db_path)
        if not self._operation_reconciled:
            self._operation_ledger.reconcile_interrupted()
            self._operation_reconciled = True
        return self._operation_ledger

    async def admit_operation(
        self, request_id: str, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist a command admission only; dispatch is a separate contract."""
        result, _dispatch_required = await self.admit_operation_for_dispatch(
            request_id, command, payload
        )
        if result.get("accepted"):
            await self.authorize_operation_dispatch(result["operation_id"])
            self.wake_operation_consumer(result["operation_id"])
        return result

    async def admit_operation_for_dispatch(
        self, request_id: str, command: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Return the stable ACK plus whether this call created the outbox item."""
        try:
            ledger = await asyncio.to_thread(self._get_operation_ledger)
            ack = await asyncio.to_thread(
                ledger.admit,
                request_id,
                command,
                payload,
                dispatch_authorized=False,
            )
            return {
                "success": True,
                "accepted": ack.accepted,
                "state": "ADMITTED",
                "request_id": ack.request_id,
                "operation_id": ack.operation_id,
                "command": ack.command,
                "payload_sha256": ack.payload_sha256,
                "accepted_at": ack.accepted_at,
            }, ack.newly_admitted
        except IdempotencyConflict:
            return {
                "success": False,
                "accepted": False,
                "state": "REJECTED",
                "code": "IDEMPOTENCY_CONFLICT",
                "request_id": str(request_id),
                "error": "O request_id já foi usado com outro comando ou conteúdo.",
            }, False

        except ValueError as exc:
            return {
                "success": False,
                "accepted": False,
                "state": "REJECTED",
                "code": "INVALID_OPERATION",
                "request_id": str(request_id),
                "error": str(exc),
            }, False
        except Exception:
            return {
                "success": False,
                "accepted": False,
                "state": "REJECTED",
                "code": "OPERATION_ADMISSION_FAILED",
                "request_id": str(request_id),
                "error": "Não foi possível registrar a operação do Lab.",
            }, False

    async def authorize_operation_dispatch(self, operation_id: str) -> bool:
        """Persist the post-ACK release before any consumer is awakened."""
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        return await asyncio.to_thread(ledger.authorize_dispatch, operation_id)

    @staticmethod
    def _operation_status_dict(status) -> dict[str, Any]:
        return {
            "success": status.state == "COMPLETED",
            "operation_id": status.operation_id,
            "request_id": status.request_id,
            "command": status.command,
            "state": status.state,
            "result": status.result,
            "finished_at": status.finished_at,
        }

    async def dispatch_operation(self, operation_id: str) -> dict[str, Any]:
        """Claim and dispatch one durable operation through existing contracts."""
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        operation = await asyncio.to_thread(ledger.claim, operation_id)
        if operation is None:
            status = await asyncio.to_thread(ledger.operation_status, operation_id)
            if status is None:
                return {
                    "success": False,
                    "operation_id": operation_id,
                    "state": "FAILED",
                    "result": {"success": False, "code": "OPERATION_NOT_FOUND"},
                }
            if status.state in {"COMPLETED", "FAILED", "INTERRUPTED"}:
                await self._publish_operation_terminal_event(status)
            return self._operation_status_dict(status)

        try:
            payload = json.loads(operation.payload_json)
            if operation.command == "lab.v1.submit":
                objective = str(payload.get("objective") or "").strip()
                if not objective:
                    raise ValueError("Objective is required")
                session_id = payload.get("session_id")
                if session_id is not None and not isinstance(session_id, str):
                    raise ValueError("Session id must be text")
                result = await self.start_autopilot(objective, session_id=session_id)
            elif operation.command == "lab.v1.message":
                session_id = str(payload.get("session_id") or "").strip()
                content = str(payload.get("content") or "").strip()
                if not session_id or not content:
                    raise ValueError("Session id and content are required")
                result = await self.submit(session_id, content)
            elif operation.command == "lab.v1.room":
                session_id = str(payload.get("session_id") or "").strip()
                content = str(payload.get("content") or "").strip()
                if not session_id or not content:
                    raise ValueError("Session id and content are required")
                result = await self.room_message(session_id, content)
            elif operation.command == "lab.v1.cancel":
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    raise ValueError("Session id is required")
                result = await self.cancel_autopilot(session_id)
            elif operation.command == "lab.v1.resume":
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    raise ValueError("Session id is required")
                result = await self.resume_source_autopilot(session_id)
            else:
                raise ValueError("Unsupported Lab operation command")
            terminal = "COMPLETED" if bool(result.get("success")) else "FAILED"
        except asyncio.CancelledError:
            await asyncio.shield(asyncio.to_thread(
                ledger.finish,
                operation_id,
                "INTERRUPTED",
                {
                    "success": False,
                    "code": "CONSUMER_SHUTDOWN_OUTCOME_UNKNOWN",
                    "error": "The operation consumer stopped during dispatch.",
                },
            ))
            raise
        except Exception as exc:
            terminal = "FAILED"
            result = {
                "success": False,
                "code": "OPERATION_DISPATCH_FAILED",
                "error": str(exc),
            }
        status = await asyncio.to_thread(ledger.finish, operation_id, terminal, result)
        await self._publish_operation_terminal_event(status)
        return self._operation_status_dict(status)

    @staticmethod
    def _operation_session_id(operation, status) -> str | None:
        try:
            payload = json.loads(operation.payload_json)
        except (TypeError, ValueError):
            payload = {}
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        if not session_id and isinstance(status.result, dict):
            session_id = status.result.get("session_id")
            mission = status.result.get("mission")
            if not session_id and isinstance(mission, dict):
                session_id = mission.get("id") or mission.get("session_id")
        return str(session_id).strip() if session_id else None

    async def _get_operation_event_store(self, ledger: OperationLedger) -> LabStore:
        store = self._store
        if store is None:
            store = LabStore(ledger.db_path)
            await asyncio.to_thread(store.initialize)
            self._store = store
        return store

    async def _publish_operation_terminal_event(self, status) -> bool:
        """Mirror one terminal result into the durable Lab event stream."""
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        await self._get_operation_event_store(ledger)
        claimed = await asyncio.to_thread(
            ledger.claim_event_publications, status.operation_id
        )
        if not claimed:
            return False
        return await self._write_claimed_operation_terminal_event(ledger, claimed[0])

    async def _write_claimed_operation_terminal_event(
        self, ledger: OperationLedger, status
    ) -> bool:
        operation = await asyncio.to_thread(ledger.get_operation, status.operation_id)
        if operation is None:
            raise ValueError("Terminal operation has no admission record")
        try:
            return await asyncio.to_thread(
                ledger.publish_result_event,
                status.operation_id,
                session_id=self._operation_session_id(operation, status),
                payload=self._operation_status_dict(status),
                occurred_at=status.finished_at or now(),
            )
        except BaseException:
            await asyncio.shield(asyncio.to_thread(
                ledger.release_event_publication, status.operation_id
            ))
            raise

    async def publish_pending_operation_terminal_events(self) -> int:
        """Resume any terminal event publication interrupted by an earlier process."""
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        await self._get_operation_event_store(ledger)
        published = 0
        while True:
            # Claim one at a time so a single malformed/colliding event cannot
            # strand the rest of a batch behind a live publisher PID.
            statuses = await asyncio.to_thread(
                ledger.claim_event_publications, None, 1
            )
            if not statuses:
                return published
            for status in statuses:
                if await self._write_claimed_operation_terminal_event(ledger, status):
                    published += 1

    async def dispatch_pending_operations(self) -> list[dict[str, Any]]:
        """Drain durable work left before a prior process could schedule it."""
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        results = []
        while True:
            operation_ids = await asyncio.to_thread(ledger.pending_operation_ids)
            if not operation_ids:
                break
            progressed = False
            for operation_id in operation_ids:
                try:
                    item = await self.dispatch_operation(operation_id)
                    results.append(item)
                    if item.get("state") != "ADMITTED":
                        progressed = True
                except Exception as exc:
                    status = await asyncio.to_thread(
                        ledger.operation_status, operation_id
                    )
                    results.append({
                        "success": False,
                        "operation_id": operation_id,
                        "state": status.state if status is not None else "FAILED",
                        "result": {
                            "success": False,
                            "code": "OPERATION_CONSUMER_FAILED",
                            "error": str(exc),
                        },
                    })
            if not progressed:
                break
        return results

    async def claim_operation_result_publications(self) -> list[dict[str, Any]]:
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        statuses = await asyncio.to_thread(
            ledger.claim_result_publications
        )
        return [self._operation_status_dict(status) for status in statuses]

    async def mark_operation_result_published(self, operation_id: str) -> None:
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        await asyncio.to_thread(
            ledger.mark_result_published, operation_id
        )

    async def release_operation_result_publication(self, operation_id: str) -> None:
        ledger = await asyncio.to_thread(self._get_operation_ledger)
        await asyncio.to_thread(
            ledger.release_result_publication, operation_id
        )

    def _get_supervisor(self):
        if self._supervisor is None:
            from core.lab_v1.supervisor import AutonomySupervisor
            self._supervisor = AutonomySupervisor(self._get_runtime(), autopilot=self._autopilot)
        return self._supervisor

    async def _start_operation_consumer(
        self, *, wait_for_recovery: bool = True
    ) -> None:
        task = self._operation_consumer_task
        if task is not None and not task.done():
            return
        self._operation_consumer_loop = asyncio.get_running_loop()
        self._operation_consumer_queue = asyncio.Queue()
        self._operation_consumer_idle = asyncio.Event()
        self._operation_consumer_task = asyncio.create_task(
            self._operation_consumer_loop_main(),
            name="zara-lab-v1-operation-consumer",
        )
        # Direct service callers can require recovery before continuing. IPC
        # startup must let the durable sweep run in the background, otherwise
        # one slow prior operation holds every later request behind it.
        if wait_for_recovery:
            await self.wait_for_operation_idle()

    def wake_operation_consumer(self, operation_id: str) -> None:
        """Release one durable operation to the live consumer by exact id."""
        loop = self._operation_consumer_loop
        queue = self._operation_consumer_queue
        if loop is None or queue is None or loop.is_closed():
            return

        def signal() -> None:
            idle = self._operation_consumer_idle
            if idle is not None:
                idle.clear()
            queue.put_nowait(operation_id)

        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            signal()
        else:
            loop.call_soon_threadsafe(signal)

    async def wait_for_operation_idle(self) -> None:
        idle = self._operation_consumer_idle
        if idle is not None:
            await idle.wait()

    def operation_consumer_status(self) -> dict[str, Any]:
        if self._operation_consumer_error:
            state = "FAILED"
        elif (self._operation_consumer_task is not None
              and not self._operation_consumer_task.done()):
            state = "RUNNING"
        else:
            state = "STOPPED"
        return {
            "state": state,
            "error": self._operation_consumer_error,
            "results": list(self._operation_consumer_results),
        }

    def _record_operation_consumer_results(
        self, results: list[dict[str, Any]]
    ) -> None:
        self._operation_consumer_results = results
        failed = next(
            (item for item in results
             if item.get("success") is False
             or item.get("state") in {"FAILED", "INTERRUPTED"}),
            None,
        )
        self._operation_consumer_error = (
            "OPERATION_FAILED" if failed is not None else None
        )

    async def _operation_consumer_loop_main(self) -> None:
        try:
            queue = self._operation_consumer_queue
            idle = self._operation_consumer_idle
            if queue is None or idle is None:
                return

            # One boot-only sweep recovers operations from the previous process.
            idle.clear()
            try:
                self._record_operation_consumer_results(
                    await self.dispatch_pending_operations()
                )
                await self.publish_pending_operation_terminal_events()
            except Exception as exc:
                self._operation_consumer_error = f"{type(exc).__name__}: {exc}"
            finally:
                idle.set()

            while True:
                operation_id = await queue.get()
                idle.clear()
                try:
                    self._record_operation_consumer_results([
                        await self.dispatch_operation(operation_id)
                    ])
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._operation_consumer_error = f"{type(exc).__name__}: {exc}"
                finally:
                    queue.task_done()
                    if queue.empty():
                        idle.set()
        except asyncio.CancelledError:
            raise

    async def _stop_operation_consumer(self) -> None:
        task, self._operation_consumer_task = self._operation_consumer_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._operation_consumer_queue = None
        self._operation_consumer_idle = None
        self._operation_consumer_loop = None

    async def start_background(self, *, wait_for_operation_recovery: bool = True):
        try:
            # Entry-only packaged canaries prove renderer/preload admission
            # and cancellation.  Do not start the durable operation consumer
            # here: it would race the harness and invoke a real provider
            # before the owner-entry assertion is captured.
            import os
            if os.environ.get('ZARA_SMOKE_TEST') == '1' and os.environ.get('ZARA_LAB_ENTRY_CANARY') == '1':
                return {'success': True, 'state': 'PAUSED'}
            # Durable commands are independent of the autonomous-work switch.
            # Start/recover their consumer before touching providers or team
            # bootstrap.  A paused Lab must still drain an operation admitted
            # before boot, and that path must not require a provider runtime.
            await self._start_operation_consumer(
                wait_for_recovery=wait_for_operation_recovery
            )
            policy = self._get_supervisor().policy()
            from core.lab_v1.workforce_policy import WorkforcePolicy
            workforce = WorkforcePolicy(policy)
            if not workforce.background_enabled:
                return {'success': True, 'state': 'PAUSED'}
            # Bootstrap the visible permanent workforce only when resident
            # autonomy is active.  Interactive surfaces bootstrap the same
            # idempotent team through their own runtime entry points.
            runtime = self._get_runtime()
            if hasattr(runtime, 'ensure_core_team'):
                await asyncio.to_thread(runtime.ensure_core_team)
            if self._supervisor_task and not self._supervisor_task.done():
                # A restart/wake must also repair a scheduler that was stopped
                # independently.  start_scheduler is idempotent, so this can
                # never create a second timer.
                if hasattr(self._get_supervisor(), "lock"):
                    await self.start_scheduler()
                return {'success': True, 'state': 'RUNNING'}
            self._background_error = None
            self._supervisor_task = asyncio.create_task(self._background_loop())
            # Integrated, but gated: with the master switch off this returns
            # DISABLED and creates no task, so background work can never bring
            # the scheduler up as a side effect.
            # Test doubles may implement only the supervisor heartbeat.  The
            # durable improvement scheduler requires the real supervisor's
            # cross-process mission lock; do not manufacture a second runtime
            # around a partial test/service adapter.
            if hasattr(self._get_supervisor(), "lock"):
                await self.start_scheduler()
            return {'success': True, 'state': 'RUNNING'}
        except Exception:
            return {'success': False, 'state': 'BLOCKED', 'error': 'Supervisor do Lab indisponivel.'}

    def _start_provider_discovery(self):
        """Start account/model discovery only after a Lab surface needs it."""
        runtime = self._get_runtime()
        registry = getattr(runtime, 'registry', None)
        if registry is None:
            return None
        codex = registry.get('codex_cli')
        if codex is None or codex.probe().availability.can_work:
            return None
        if self._provider_discovery_task is not None and not self._provider_discovery_task.done():
            return self._provider_discovery_task

        async def _discover_codex_models():
            try:
                await asyncio.to_thread(registry.discover_models, 'codex_cli')
                registry.invalidate_probe_cache('codex_cli')
                self._provider_discovery_error = None
            except Exception as exc:
                self._provider_discovery_error = type(exc).__name__

        self._provider_discovery_task = asyncio.create_task(
            _discover_codex_models(), name='zara-lab-codex-discovery'
        )
        return self._provider_discovery_task

    async def _background_loop(self):
        try:
            while True:
                try:
                    tick = self._get_supervisor().tick
                    # Test doubles are already event-loop safe; avoiding a
                    # thread hop keeps the heartbeat observable at sub-100ms
                    # cadences while real supervisors remain isolated off-loop.
                    if type(tick).__module__.startswith("unittest.mock"):
                        tick()
                    else:
                        await asyncio.to_thread(tick)
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
        await self._stop_operation_consumer()
        discovery, self._provider_discovery_task = self._provider_discovery_task, None
        if discovery is not None and not discovery.done():
            discovery.cancel()
            try:
                await discovery
            except asyncio.CancelledError:
                pass
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
                    # Resolve the scheduler inside the worker as well.  Its
                    # first construction opens the Lab store and memory; doing
                    # that while evaluating the argument here would freeze the
                    # event loop before ``to_thread`` even starts.
                    await asyncio.to_thread(lambda: self._get_scheduler().cycle())
                    await self._run_scheduled_research()
                    self._scheduler_error = None
                except Exception as exc:
                    self._scheduler_error = f'{type(exc).__name__}: {exc}'
                floor = max(0.01, float(self._scheduler_poll_seconds))
                try:
                    remaining = await asyncio.to_thread(
                        lambda: self._get_scheduler().seconds_until_next())
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
        discovery = self._start_provider_discovery()
        if discovery is not None:
            try:
                await asyncio.wait_for(asyncio.shield(discovery), timeout=35)
            except (asyncio.TimeoutError, Exception):
                pass
        return await asyncio.to_thread(lambda: FrontBrain(self._get_runtime()).snapshot())

    async def select_front_brain(self, model):
        from core.lab_v1.front_brain import FrontBrain
        return await asyncio.to_thread(lambda: FrontBrain(self._get_runtime()).select(model))

    async def front_reply(self, text, *, requested_model=None, history=None, context='',
                          result_is_current=None):
        from core.lab_v1.front_brain import FrontBrain
        discovery = self._start_provider_discovery()
        if discovery is not None:
            try:
                await asyncio.wait_for(asyncio.shield(discovery), timeout=35)
            except (asyncio.TimeoutError, Exception):
                pass
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
            await self.start_background()
            return {'success': True, 'policy': policy}
        except Exception:
            return {'success': False, 'error': 'Workspace de manutencao indisponivel; nenhuma atualizacao foi iniciada.'}

    async def activate_autopilot(self):
        """Persist the owner-requested continuous Lab mode and start it now."""
        try:
            await asyncio.to_thread(self._get_supervisor()._save,
                                    background_enabled=True,
                                    **{SCHEDULER_POLICY_FLAG: True})
            background = await self.start_background()
            scheduler = await self.scheduler_state()
            return {'success': bool(background.get('success')),
                    'background': background, 'scheduler': scheduler,
                    'mode': 'CONTINUOUS_WHILE_ZARA_OPEN'}
        except Exception as exc:
            return {'success': False, 'mode': 'CONTINUOUS_WHILE_ZARA_OPEN',
                    'error': str(exc)}

    async def capture_feedback(self, text, *, channel='conversation'):
        try:
            from core.lab_v1.feedback_inbox import FeedbackInbox
            result = await asyncio.to_thread(
                FeedbackInbox(self._get_runtime().store).record, text, channel=channel)
            return {'success': True, 'captured': result is not None}
        except Exception:
            return {'success': False, 'captured': False}

    def _get_proposal_feed(self):
        """Return the durable Lab proposal feed on the existing Lab database.

        The feed is an additive surface: it does not replace evolution tables,
        mission controls, or the legacy Lab. Keeping its schema behind the
        dedicated store lets the proposal UI arrive before any activation path
        is trusted, and makes every state transition explicit and auditable.
        """
        if self._proposal_feed is None:
            from core.lab_v1.proposal_feed import ProposalFeedStore
            self._proposal_feed = ProposalFeedStore(self._get_runtime().store.db_path)
        return self._proposal_feed

    async def proposal_feed_list(self, state=None, limit=100):
        try:
            return {'success': True, 'proposals': await asyncio.to_thread(
                self._get_proposal_feed().list_proposals, state, limit=limit)}
        except Exception as exc:
            return {'success': False, 'proposals': [], 'error': str(exc)}

    async def proposal_feed_register(self, proposal):
        try:
            item = await asyncio.to_thread(
                self._get_proposal_feed().register_proposal, proposal)
            return {'success': True, 'proposal': item}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    async def proposal_feed_update(self, proposal_id, state):
        try:
            item = await asyncio.to_thread(
                self._get_proposal_feed().update_state, proposal_id, state)
            if item is None:
                return {'success': False, 'error': 'Proposta não encontrada.'}
            return {'success': True, 'proposal': item}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    async def agent_inventory(self, *, refresh=False):
        """Return the read-only inventory of local agent manifests.

        Discovery is intentionally separate from workforce activation: this
        endpoint inventories TOML metadata only and never starts a provider or
        changes the effective workforce policy.
        """
        try:
            if self._agent_inventory_cache is None or refresh:
                from core.lab_v1.agent_inventory_adapter import load_agent_inventory
                agents_dir = Path(__file__).resolve().parents[2] / '.codex' / 'agents'
                self._agent_inventory_cache = await asyncio.to_thread(
                    load_agent_inventory, agents_dir)
            return {
                'success': True,
                'count': len(self._agent_inventory_cache),
                'agents': list(self._agent_inventory_cache),
                'activated': False,
            }
        except Exception as exc:
            return {'success': False, 'count': 0, 'agents': [], 'activated': False,
                    'error': str(exc)}

    def _get_agent_profiles(self):
        if self._agent_profiles is None:
            from core.lab_v1.agent_profiles import AgentProfileStore
            from core.paths import data_dir
            self._agent_profiles = AgentProfileStore(data_dir() / 'lab' / 'agent_profiles')
        return self._agent_profiles

    async def agent_profiles(self):
        """List versioned soul/model/permission profiles without activating them."""
        try:
            return {'success': True, 'profiles': await asyncio.to_thread(self._get_agent_profiles().list)}
        except Exception as exc:
            return {'success': False, 'profiles': [], 'error': str(exc)}

    async def agent_profile(self, agent_id: str):
        try:
            return {'success': True, 'profile': await asyncio.to_thread(self._get_agent_profiles().get, agent_id)}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    async def update_agent_profile(self, *, agent_id: str, soul: str | None = None,
                                   provider_id: str | None = None, model: str | None = None,
                                   permissions: list[str] | None = None):
        """Persist owner-editable profile data; next mission reads the version."""
        try:
            await asyncio.to_thread(
                self._get_agent_profiles().validate_update,
                soul=soul, provider_id=provider_id, model=model, permissions=permissions,
            )
            # Provider/model remain governed by the canonical workforce policy.
            # The owner-facing profile must never claim a model change that the
            # actual runner rejected or will silently ignore.
            if provider_id is not None or model is not None:
                current = await asyncio.to_thread(self._get_agent_profiles().get, agent_id)
                effective_provider = provider_id or current.get('provider_id')
                effective_model = model or current.get('model')
                if effective_provider and effective_model:
                    configured = await self.configure_agent(
                        agent_id=agent_id,
                        provider_id=str(effective_provider), model=str(effective_model),
                    )
                    if not configured.get('success'):
                        return configured
            profile = await asyncio.to_thread(
                self._get_agent_profiles().update, agent_id,
                soul=soul, provider_id=provider_id, model=model,
                permissions=permissions)
            # LabRuntime already uses AgentProfile.instructions in CEO,
            # builder and reviewer prompts. Mirror the versioned soul there so
            # customization affects missions as well as informal room chat.
            runtime = self._get_runtime()
            agent = runtime.store.get_agent(agent_id)
            if agent is not None:
                permission_capabilities = [
                    f"permission:{item}" for item in (profile.get('permissions') or [])
                ]
                capabilities = [
                    item for item in agent.capabilities
                    if item != 'profile.permissions.configured' and not item.startswith('permission:')
                ] + ['profile.permissions.configured', *permission_capabilities]
                updated_agent = replace(
                    agent,
                    instructions=str(profile.get('soul') or ''),
                    capabilities=capabilities,
                )
                await asyncio.to_thread(runtime.store.save_agent, updated_agent)
            return {'success': True, 'profile': profile}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    async def rollback_agent_profile(self, *, agent_id: str, version: int):
        try:
            history = await asyncio.to_thread(self._get_agent_profiles().history, agent_id)
            target = next((item for item in history if int(item.get('version', -1)) == int(version)), None)
            if target is None:
                return {'success': False, 'error': 'versão não encontrada'}
            if target.get('provider_id') and target.get('model'):
                configured = await self.configure_agent(
                    agent_id=agent_id,
                    provider_id=str(target['provider_id']), model=str(target['model']),
                )
                if not configured.get('success'):
                    return configured
            profile = await asyncio.to_thread(self._get_agent_profiles().rollback, agent_id, version)
            runtime = self._get_runtime()
            agent = runtime.store.get_agent(agent_id)
            if agent is not None:
                permission_capabilities = [
                    f"permission:{item}" for item in (profile.get('permissions') or [])
                ]
                capabilities = [
                    item for item in agent.capabilities
                    if item != 'profile.permissions.configured' and not item.startswith('permission:')
                ] + ['profile.permissions.configured', *permission_capabilities]
                await asyncio.to_thread(runtime.store.save_agent, replace(
                    agent,
                    instructions=str(profile.get('soul') or ''),
                    capabilities=capabilities,
                ))
            return {'success': True, 'profile': profile}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

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
        return self._autopilot

    async def start_autopilot(self, intent: str, session_id: str | None = None):
        try:
            blocked = await asyncio.to_thread(self._promotion_block)
            if blocked is not None:
                return blocked
            from core.lab_v1.workforce_policy import WorkforcePolicy
            if not WorkforcePolicy(self._get_supervisor().policy()).mission_entry_enabled:
                return self.workforce_refusal()
            autopilot = self._get_autopilot()
            runtime = getattr(autopilot, 'runtime', None)
            if runtime is not None and hasattr(runtime, 'ensure_core_team'):
                await asyncio.to_thread(runtime.ensure_core_team)
            result = await asyncio.to_thread(autopilot.start, intent, session_id=session_id)
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
        try:
            return await asyncio.to_thread(self._get_autopilot().run, session_id)
        except Exception:
            return {'success': False, 'state': 'BLOCKED_NEEDS_OWNER', 'error': 'Falha ao continuar a missao.'}

    async def resume_source_autopilot(self, session_id: str):
        """Resume a failed source mission in place; never creates another session."""
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

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        try:
            if not self._store or not self._store.get_session(session_id):
                return {'success': False, 'error': 'Conversa não encontrada.'}
            mission = self._get_autopilot().controller.snapshot(session_id)
            if mission and mission.get('state') not in ('COMPLETED', 'FAILED', 'CANCELLED'):
                return {'success': False, 'error': 'Conclua ou cancele a missão antes de excluir.'}
            await asyncio.to_thread(self._store.hide_session, session_id)
            return {'success': True, 'session_id': session_id}
        except Exception as exc:
            return {'success': False, 'error': f'Não foi possível excluir: {exc}'}

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
            memory_adapter = self._build_memory_adapter(store)
            self._store = store
            self._runtime = LabRuntime(store, registry, memory_adapter)
        return self._runtime

    def _build_memory_adapter(self, store) -> LabMemoryAdapter:
        """Adapter wired to the one shared second brain and Obsidian.

        The brain composes the same canonical domains ZARA consults, so a
        verified mission fact is queryable from both paths. Any composition
        failure degrades to the plain adapter — the Lab must still run.
        """
        try:
            from core.obsidian_memory import ObsidianMemoryManager
            from memory.project_memory import ProjectMemory
            from memory.second_brain_composition import (
                build_shared_second_brain,
                default_obsidian_index_db,
            )
            from memory.user_memory import UserMemoryCore

            obsidian = ObsidianMemoryManager()
            user_memory = UserMemoryCore()
            self._shared_brain = build_shared_second_brain(
                user_memory=user_memory,
                lab_store=store,
                project_memory=ProjectMemory(),
                obsidian=obsidian,
                obsidian_index_db=default_obsidian_index_db(),
            )
            return LabMemoryAdapter(
                store, user_memory, obsidian, second_brain=self._shared_brain
            )
        except Exception:
            self._shared_brain = None
            return LabMemoryAdapter(store)

    def get_shared_brain(self):
        """The shared second brain composed with the canonical Lab store."""
        self._get_runtime()
        return self._shared_brain

    def shared_lab_store(self):
        """Read-only Lab store for shared-memory composition; never mutates."""
        try:
            return self._get_runtime().store
        except Exception:
            return None

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
                                  "pending_before": [], "records": [], "unresolved": []}
        try:
            self._ensure_boot_table(store)
            from core.lab_v1.release import pending_promotions, reconcile_promotions
            report["pending_before"] = pending_promotions()
            if report["pending_before"]:
                report["records"] = reconcile_promotions()
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
            report["unresolved"] = self._unresolved_promotions(store)
            report["state"] = ("NEEDS_OWNER" if report["unresolved"]
                               else "RECONCILED" if report["records"] else "CLEAN")
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

    def boot_reconciliation(self) -> dict[str, Any]:
        """What the boot gate found, with the unresolved list re-read from disk."""
        report = dict(self._boot_reconciliation or {"state": "NOT_RUN"})
        try:
            if self._store is not None:
                report["unresolved"] = self._unresolved_promotions(self._store)
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

    def _pending_publication_status(self, release: Any = None) -> dict[str, Any]:
        """Read publication queues without claiming or publishing any item."""
        operation_results = 0
        operation_events = 0
        try:
            ledger = self._get_operation_ledger()
            with ledger._connect() as conn:
                operation_results = int(conn.execute(
                    "SELECT COUNT(*) FROM lab_operation_results "
                    "WHERE publication_state != 'PUBLISHED'"
                ).fetchone()[0])
                operation_events = int(conn.execute(
                    "SELECT COUNT(*) FROM lab_operation_event_outbox "
                    "WHERE state != 'PUBLISHED'"
                ).fetchone()[0])
        except Exception as exc:
            return {
                "state": "ERROR",
                "pending": None,
                "count": None,
                "operation_results": operation_results,
                "operation_events": operation_events,
                "release": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

        release_state = release.get("state") if isinstance(release, dict) else None
        release_pending = bool(
            release_state
            and release_state not in {"ACTIVE", "ROLLED_BACK", "BLOCKED"}
        )
        count = operation_results + operation_events + int(release_pending)
        return {
            "state": "PENDING" if count else "CLEAR",
            "pending": bool(count),
            "count": count,
            "operation_results": operation_results,
            "operation_events": operation_events,
            "release": release_pending,
            "release_state": release_state,
        }

    @staticmethod
    def _resident_health(
        *,
        supervisor_state: str | None,
        supervisor_error: str | None,
        operation_consumer: dict[str, Any],
        publication: dict[str, Any],
        scheduler_state: str | None,
        scheduler_error: str | None,
        memory: dict[str, Any],
        research_scheduler: str,
    ) -> dict[str, Any]:
        """Build a resident-health view while preserving each failure domain."""
        consumer_state = operation_consumer.get("state") or "STOPPED"
        consumer_error = operation_consumer.get("error")
        publication_pending = publication.get("pending")
        publication_error = publication.get("error")
        memory_state = memory.get("status") or "unavailable"
        memory_degraded = bool(memory.get("degraded")) or memory_state in {
            "degraded", "unavailable"
        }

        issues: list[str] = []
        if supervisor_error or supervisor_state == "FAILED":
            issues.append("SUPERVISOR_ERROR")
        if consumer_error or consumer_state == "FAILED":
            issues.append("OPERATION_CONSUMER_ERROR")
        if publication_error:
            issues.append("PUBLICATION_STATUS_ERROR")
        elif publication_pending is True:
            issues.append("PENDING_PUBLICATION")
        if scheduler_error or scheduler_state in {"FAILED", "UNAVAILABLE", "ERROR"}:
            issues.append("SCHEDULER_ERROR")
        if memory_degraded:
            issues.append("MEMORY_DEGRADED")

        publication_state = publication.get("state") or (
            "PENDING" if publication_pending else "CLEAR"
        )
        return {
            "state": "DEGRADED" if issues else "OK",
            "resident": supervisor_state == "RUNNING",
            "supervisor": supervisor_state,
            "supervisor_error": supervisor_error,
            "operation_consumer": consumer_state,
            "operation_consumer_error": consumer_error,
            "pending_publication": publication_state,
            "publication_pending": publication_pending,
            "publication": publication,
            "improvement_scheduler": scheduler_state,
            "scheduler_error": scheduler_error,
            "research_scheduler": research_scheduler,
            "central_memory": memory_state,
            "memory_degraded": memory_degraded,
            "degraded_memory": memory_degraded,
            "issues": issues,
        }

    async def snapshot(self, session_id: str | None = None, team_id: str | None = None) -> dict[str, Any]:
        try:
            runtime = self._get_runtime()
            self._start_provider_discovery()
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
            # The renderer must see the same memory-health fact used by the
            # Lab runtime.  This is a read-only, bounded status snapshot; the
            # vault remains canonical and the SQLite index remains derived.
            try:
                brain = self.get_shared_brain()
                getter = getattr(brain, 'get_central_memory_status', None)
                data['central_memory'] = (
                    getter() if callable(getter) else
                    {'status': 'unavailable', 'available': False,
                     'note_count': 0, 'degraded': True}
                )
            except Exception as exc:
                data['central_memory'] = {
                    'status': 'degraded', 'available': False,
                    'note_count': 0, 'degraded': True,
                    'error': type(exc).__name__,
                }
            try:
                data['improvement_scheduler'] = await asyncio.to_thread(
                    self._get_scheduler().snapshot)
            except Exception as exc:
                data['improvement_scheduler'] = {'state': 'UNAVAILABLE', 'enabled': False,
                                                 'error': f'{type(exc).__name__}: {exc}'}
            data['research_scheduler'] = {
                'enabled': scheduler_enabled(self._get_supervisor().policy()),
                'interval_seconds': RESEARCH_INTERVAL_SECONDS,
                'last_run': self._research_last_result,
                'pipeline': self._get_research_skill_pipeline().snapshot(),
            }
            supervisor_state = data['autonomy_policy'].get('background_task_state')
            scheduler_state = data['improvement_scheduler'].get('state')
            scheduler_error = self._scheduler_error or data['improvement_scheduler'].get('error')
            if not scheduler_error and scheduler_state in {'FAILED', 'UNAVAILABLE', 'ERROR'}:
                scheduler_error = scheduler_state
            operation_consumer = self.operation_consumer_status()
            publication = await asyncio.to_thread(
                self._pending_publication_status, data.get('release')
            )
            data['resident_health'] = self._resident_health(
                supervisor_state=supervisor_state,
                supervisor_error=data['autonomy_policy'].get('background_error'),
                operation_consumer=operation_consumer,
                publication=publication,
                scheduler_state=scheduler_state,
                scheduler_error=scheduler_error,
                memory=data['central_memory'],
                research_scheduler=(
                    'READY' if data['research_scheduler']['enabled']
                    else 'DISABLED_BY_POLICY'
                ),
            )
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
        # Active owner messages revise the same controlled mission. They never
        # trigger a second worker path through the legacy runtime.
        controller = None
        mission = None
        try:
            controller = self._get_autopilot().controller
            mission = controller.snapshot(session_id)
        except Exception:
            pass
        if mission:
            if (mission['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED')
                    and hasattr(controller, 'submit_owner_input')):
                try:
                    accepted = await asyncio.to_thread(controller.submit_owner_input, session_id, text)
                    return {'success': True, 'code': 'OWNER_INPUT_ACCEPTED', 'state': mission['state'], **accepted}
                except ValueError as exc:
                    return {'success': False, 'code': 'OWNER_INPUT_INVALID', 'state': mission['state'],
                            'error': str(exc)}
                except Exception:
                    return {'success': False, 'code': 'OWNER_INPUT_FAILED', 'state': mission['state'],
                            'error': 'Nao foi possivel registrar a orientacao na missao.'}
            return {'success': False, 'code': 'MISSION_CONTROLLED', 'state': mission['state'],
                    'error': 'A missao continua automaticamente pelo Mission Controller.'}
        session = await asyncio.to_thread(self._get_runtime().store.get_session, session_id)
        if session is None:
            return {'success': False, 'code': 'SESSION_NOT_FOUND', 'state': 'BLOCKED', 'error': 'Missao nao encontrada.'}
        if getattr(session.state, 'value', session.state) != 'QUEUED':
            return {'success': False, 'code': 'SESSION_NOT_QUEUED', 'state': str(getattr(session.state, 'value', session.state)),
                    'error': 'Somente uma sessao inicial na fila pode entrar no Mission Controller.'}
        return await self.start_autopilot(text, session_id=session_id)

    async def room_message(self, session_id: str, content: str) -> dict[str, Any]:
        """Persist a natural Lab chat turn and route one optional @mention.

        Plain chat goes to the active CEO/regent. An explicit mention resolves
        to exactly one active team member. Both paths create a real Run and the
        returned provenance comes from that persisted Run; greetings never
        become code missions.
        """
        text = str(content or "").strip()
        sid = str(session_id or "").strip()
        if not sid or not text or len(text) > 12000:
            return {"success": False, "code": "ROOM_MESSAGE_INVALID",
                    "error": "A mensagem precisa ter entre 1 e 12000 caracteres."}

        # The composer is one natural-language surface. It must not trap Alex
        # in a chatbot-only path when he explicitly asks the team to work.
        try:
            mission = self._get_autopilot().controller.snapshot(sid)
        except Exception:
            mission = None
        if mission and mission.get('state') not in ('COMPLETED', 'FAILED', 'CANCELLED'):
            return await self.submit(sid, text)
        if self.is_lab_work_request(text):
            return await self.start_autopilot(text, session_id=sid)

        discovery = self._start_provider_discovery()
        if discovery is not None:
            try:
                await asyncio.wait_for(asyncio.shield(discovery), timeout=35)
            except (asyncio.TimeoutError, Exception):
                pass

        def _turn() -> dict[str, Any]:
            from core.lab_v1 import mentions

            runtime = self._get_runtime()
            store = runtime.store
            session = store.get_session(sid)
            if session is None:
                team = runtime.ensure_core_team()
                session = Session(
                    id=sid, team_id=team.id,
                    objective=(text[:120] or "Conversa com a equipe"),
                )
                store.save_session(session)
            team = store.get_team(session.team_id)
            if team is None or team.archived:
                raise ValueError("A equipe desta conversa não está disponível.")

            mentioned = mentions.resolve_mentions(store, team.id, text)
            if len(mentioned) > 1:
                raise mentions.MentionResolutionError(
                    "Envie a mensagem para um participante por vez."
                )
            if mentioned:
                recipient_id = mentioned[0]
            else:
                binding = store.active_binding(team.id, RoleName.CEO)
                if binding is None:
                    raise ValueError("A equipe não possui um líder ativo.")
                recipient_id = binding.agent_id
            agent = store.get_agent(recipient_id)
            if agent is None or agent.archived:
                raise ValueError("O participante escolhido não está disponível.")

            user_message = runtime._add_message(
                session, kind=MessageKind.USER, author="Alex", content=text,
                to_agent_id=agent.id, to_role=agent.role.value,
            )
            recent = store.list_messages(session.id, limit=20)
            history = "\n".join(
                f"{item.author}: {item.content}" for item in recent[-20:-1]
            )[-12000:]
            prompt = (
                ("Conversa recente:\n" + history + "\n\n") if history else ""
            ) + f"Alex: {text}"
            system = (
                f"Você é {agent.name}, participante {agent.role.value} do ZARA Lab. "
                "Converse em português natural, curto e útil. Não devolva JSON. "
                "Não afirme que executou, testou ou alterou código sem evidência no turno."
            )
            profile = self._get_agent_profiles().get(agent.id)
            soul = str(profile.get('soul') or '').strip()
            permissions = [
                str(item).strip() for item in (profile.get('permissions') or [])
                if str(item).strip()
            ]
            if soul:
                system += f"\n\nIdentidade e missão configuradas pelo owner:\n{soul[:24000]}"
            if permissions:
                system += (
                    "\n\nPermissões declaradas para este agente: "
                    + ", ".join(permissions[:32])
                    + ". Não ultrapasse essas permissões."
                )
            run, provider_result = runtime._run_agent(
                session, agent, prompt, system, timeout_s=120,
            )
            if not provider_result.ok or not str(provider_result.text or "").strip():
                return {
                    "success": False, "code": "ROOM_AGENT_UNAVAILABLE",
                    "error": "O participante não conseguiu responder agora.",
                    "session_id": session.id, "run_id": run.id,
                    "provider": run.provider_id, "model_requested": run.model,
                    "model_reported": run.model_reported,
                }
            answer = str(provider_result.text).strip()
            mismatch = bool(run.model_reported and run.model_reported != run.model)
            if mismatch:
                return {
                    "success": False, "code": "MODEL_MISMATCH",
                    "error": "O provedor retornou outro modelo; a resposta foi rejeitada.",
                    "session_id": session.id, "run_id": run.id,
                    "agent_id": agent.id, "agent_name": agent.name,
                    "provider": run.provider_id, "model_requested": run.model,
                    "model_reported": run.model_reported,
                    "provenance_status": "MISMATCH_REJECTED",
                }
            agent_message = runtime._add_message(
                session, kind=MessageKind.AGENT, author=agent.name,
                content=answer, author_agent_id=agent.id, run_id=run.id,
                reply_to=user_message.id, correlation_id=user_message.correlation_id,
            )
            return {
                "success": True,
                "code": "ROOM_REPLY",
                "session_id": session.id, "response": answer,
                "message_id": agent_message.id, "run_id": run.id,
                "agent_id": agent.id, "agent_name": agent.name,
                "provider": run.provider_id, "model_requested": run.model,
                "model_reported": run.model_reported,
                "provenance_status": "MATCHED" if run.model_reported else "UNREPORTED",
            }

        try:
            return await asyncio.to_thread(_turn)
        except Exception as exc:
            return {"success": False, "code": "ROOM_MESSAGE_FAILED", "error": str(exc)}

    @staticmethod
    def is_lab_work_request(text: str) -> bool:
        """Separate conversational turns from explicit requests for real work."""
        import re
        value = str(text or '').strip()
        action = re.search(
            r'\b(?:convoque|acione|chame|execute|trabalhe|investigue|pesquise|implemente|'
            r'corrija|conserte|melhore|otimize|reforce|crie|faça|faca|resolva|teste|revise)\b',
            value, re.I,
        )
        target = re.search(
            r'\b(?:time|equipe|agentes?|bots?|zara|lab|c[oó]digo|voz|mem[oó]ria|interface|'
            r'backend|frontend|windows|navegador|chrome|modelos?|open\s*code)\b',
            value, re.I,
        )
        return bool(action and target)

    async def evidence_handoff(
        self, session_id: str | None = None, packet_id: str | None = None,
        *, packet_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Read the persisted Builder -> Reviewer packet after any restart."""
        try:
            handoff = await asyncio.to_thread(
                self._get_runtime().store.get_evidence_handoff,
                session_id, packet_id, packet_sha256=packet_sha256,
            )
            if handoff is None:
                return {"success": False, "code": "EVIDENCE_HANDOFF_NOT_FOUND",
                        "state": "NOT_FOUND", "error": "Pacote de evidencias nao encontrado."}
            return {"success": True, "state": "RECOVERED", "handoff": handoff}
        except Exception as exc:
            return {"success": False, "code": "EVIDENCE_HANDOFF_READ_FAILED",
                    "state": "BLOCKED", "error": f"Falha ao ler pacote de evidencias: {exc}"}

    async def list_evidence_handoffs(self, session_id: str | None = None) -> dict[str, Any]:
        """List durable evidence packets without depending on live Autopilot state."""
        try:
            handoffs = await asyncio.to_thread(
                self._get_runtime().store.list_evidence_handoffs, session_id,
            )
            return {"success": True, "state": "RECOVERED", "handoffs": handoffs}
        except Exception as exc:
            return {"success": False, "code": "EVIDENCE_HANDOFF_LIST_FAILED",
                    "state": "BLOCKED", "error": f"Falha ao listar pacotes de evidencias: {exc}"}

    # IPC/UI-friendly aliases; all paths remain read-only and store-backed.
    get_evidence_handoff = evidence_handoff
    get_review_evidence_packet = evidence_handoff

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

    async def configure_agent(self, *, agent_id: str, provider_id: str, model: str) -> dict[str, Any]:
        """Change one existing participant after the same policy/catalog checks."""
        try:
            runtime = self._get_runtime(); assert self._store is not None
            agent = self._store.get_agent(agent_id)
            if agent is None: raise ValueError('Participante não encontrado.')
            adapter = runtime.registry.get(provider_id)
            if adapter is None or model not in {m.model_id for m in adapter.declared_models}:
                raise ValueError('Escolha um modelo real do catálogo do provedor.')
            supervisor = self._get_supervisor()
            policy = __import__('core.lab_v1.workforce_policy', fromlist=['WorkforcePolicy']).WorkforcePolicy(
                supervisor.policy()
            )
            # The policy override is the single authority used later by worker
            # selection.  Updating only AgentProfile used to make the card show
            # Alex's new choice while effective_resource() silently kept an old
            # override (often an unavailable provider).
            decision, updated_policy = policy.with_bot_override(
                agent=agent, provider_id=provider_id, model_id=model,
                registry=runtime.registry, team_agents=self._store.list_agents(),
            )
            if not decision.allowed or updated_policy is None:
                raise ValueError(policy.human_message(decision))
            updated = replace(agent, provider_id=provider_id, model=model,
                              capabilities=['model.text'] if adapter.controlled_text_only else [])
            await asyncio.to_thread(self._store.save_agent, updated)
            await asyncio.to_thread(
                supervisor._save,
                agent_model_overrides=updated_policy['agent_model_overrides'],
            )
            return {'success': True, 'agent': updated.to_dict(), 'model': model,
                    'provider_id': provider_id, 'effective_resource': {
                        'provider_id': provider_id, 'model_id': model,
                    }}
        except Exception as exc:
            return {'success': False, 'error': f'Não foi possível configurar o participante: {exc}'}

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
            self._start_provider_discovery()
            infos = await asyncio.to_thread(runtime.registry.list_providers)
            return {"success": True, "providers": [p.to_dict() for p in infos]}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao consultar provedores: {exc}"}
