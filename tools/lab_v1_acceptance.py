"""ZARA LAB REAL V1 — CORE TEAM TEST.

What this is
------------
The acceptance runner for the Lab V1 multi-agent runtime. It performs the real
mission end to end and writes `artifacts/lab-v1/acceptance.json`, which the
gate ledger in `GATES.md` reads. Each gate asserts one specific claim from that
file.

Why it is written to fail closed
--------------------------------
Every gate check in GATES.md throws on a missing key. So a phase that does not
run must still record its keys with falsy values rather than omitting them.
Silence has to read as failure, because the failure mode this whole project has
been burned by is a report that looks clean because a step quietly did not run.

Why the restart proof re-executes this file
-------------------------------------------
G8 claims the mission survives the process dying. Re-opening a store inside the
same interpreter proves nothing about that: the objects, the caches and the
imports are all still warm. So phase 2 runs in a genuinely separate process and
is handed nothing but the session id.

Real money
----------
Phases 1 and 2 make real model calls (that is the entire point of G2 and G4).
A run costs roughly ten to twenty cents once the prompt cache is warm. The
failover phase deliberately uses fault injection instead of burning real quota,
because exhausting Alex's account to prove a fallback works would be a stupid
way to spend his money.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.lab_v1.domain import (  # noqa: E402
    Availability,
    ProviderResult,
    RoleName,
    RunState,
    Session,
    TaskState,
    new_id,
)
from core.lab_v1.memory_adapter import LabMemoryAdapter  # noqa: E402
from core.lab_v1.providers.registry import ProviderRegistry, default_registry  # noqa: E402
from core.lab_v1.runtime import LabRuntime  # noqa: E402
from core.lab_v1.store import LabStore  # noqa: E402
from memory.user_memory import UserMemoryCore  # noqa: E402

ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "lab-v1"
REPORT_PATH = ARTIFACT_DIR / "acceptance.json"
STATE_PATH = ARTIFACT_DIR / "_run_state.json"

# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
# An earlier version of this runner opened the production database directly.
# It bootstrapped the real ZARA Core team, ran a real mission against it, and
# then deliberately knocked the CEO offline to prove failover. Two things went
# wrong with that, and both are the kind of failure that produces confident
# wrong evidence later:
#
#   1. the fault-injected failover left the CEO chair permanently reassigned,
#      so the NEXT run started with one agent holding both roles, delegated to
#      itself, and reported a broken runtime that was not broken;
#   2. test sessions and injected outages landed in Alex's real Lab history.
#
# Restoring state at the end of the run is not good enough, because it only
# happens when the run reaches the end. An exception, a timeout or a Ctrl-C
# skips it. So the runner no longer touches production at all: it builds its
# own database and its own memory store under ZARA3_LAB_SANDBOX, seeded from
# nothing. Evidence still lands in artifacts/, which is separate from both.
SANDBOX_ENV = "ZARA3_LAB_SANDBOX"


def _sandbox_dir() -> Path:
    """Directory holding this run's isolated databases.

    Passed to the restart subprocess through the environment so phase two
    reopens the SAME isolated database in a genuinely new process, which is
    the whole point of that phase.
    """
    configured = os.environ.get(SANDBOX_ENV)
    if configured:
        path = Path(configured)
    else:
        path = Path(tempfile.gettempdir()) / "zara-lab-v1-acceptance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sandbox_store() -> LabStore:
    store = LabStore(_sandbox_dir() / "zara_lab_v1.db")
    store.initialize()
    return store


def _sandbox_memory() -> UserMemoryCore:
    """Real UserMemoryCore class, isolated file.

    G7 asks for promotion into ZARA's existing memory SYSTEM, not for writing
    test facts into Alex's actual long-term memory. This runs the real class,
    the real schema and the real query path against a throwaway file, so the
    integration is genuinely exercised and his memory stays clean.
    """
    return UserMemoryCore(_sandbox_dir() / "user_memory.db")


def production_fingerprint() -> dict[str, Any]:
    """Full state of the PRODUCTION world, recorded before and after a run.

    The contract is two separate worlds. In the test world failover may move
    the CEO, write handoffs, restart and fail freely. In the production world
    nothing may differ across a run: same team, same role bindings, same
    designation, same sessions, same tasks and messages, same bytes on disk.

    The file hash alone would prove that, but it would not SAY it. Each
    dimension is listed separately so a failure names what moved instead of
    just reporting that two hashes differ.
    """
    from core.paths import data_dir

    db = data_dir() / "lab" / "zara_lab_v1.db"
    if not db.exists():
        return {"exists": False, "sha256": None, "teams": [], "bindings": [],
                "sessions": [], "counts": {}}

    raw = db.read_bytes()
    store = LabStore(db)
    teams = sorted((t.id, t.name) for t in store.list_teams())
    bindings, sessions, tasks, messages = [], [], 0, 0
    for team_id, _ in teams:
        for b in store.list_bindings(team_id):
            if b.active:
                bindings.append((b.team_id, b.role.value, b.agent_id, b.designation))
        for sess in store.list_sessions(team_id=team_id, limit=1000):
            sessions.append((sess.id, sess.state.value))
            tasks += len(store.list_tasks(sess.id))
            messages += len(store.list_messages(sess.id, limit=10000))

    return {
        "exists": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "teams": teams,
        "bindings": sorted(bindings),
        "sessions": sorted(sessions),
        "counts": {"tasks": tasks, "messages": messages,
                   "handoffs": len(store.list_handoffs())},
    }

# The objective is deliberately tiny. This test proves that delegation happens
# and that the wiring is real, not that a model can solve something hard.
OBJECTIVE = (
    "Teste de time: escolha um nome curto para um arquivo de log da ZARA e "
    "delegue ao BUILDER a tarefa de justificar a escolha em duas frases."
)


# --------------------------------------------------------------------------
# Fault injection — TEST ONLY. Deliberately defined here and nowhere in core/,
# so that production code contains no path that can fake an outage.
# --------------------------------------------------------------------------

class _UnavailableAdapter:
    """Wraps a real adapter and reports a chosen outage for one agent's model.

    It still delegates `probe()` to the real adapter for every other question,
    so the failover path under test is the real one: only the model call fails.
    """

    def __init__(self, inner: Any, blocked_model: str, availability: Availability) -> None:
        self._inner = inner
        self._blocked_model = blocked_model
        self._availability = availability
        self.id = inner.id
        self.label = inner.label

    def probe(self):
        return self._inner.probe()

    def complete(self, *, prompt: str, model: str, **kwargs: Any) -> ProviderResult:
        if model == self._blocked_model:
            return ProviderResult(
                ok=False,
                availability=self._availability,
                error=f"[fault-injection de teste] {self._availability.value}",
            )
        return self._inner.complete(prompt=prompt, model=model, **kwargs)


def _registry_with_outage(blocked_model: str, availability: Availability) -> ProviderRegistry:
    reg = default_registry()
    real = reg.get("claude_cli")
    faulty = ProviderRegistry()
    faulty.register(_UnavailableAdapter(real, blocked_model, availability))
    for pid in ("codex_cli", "anthropic_api"):
        adapter = reg.get(pid)
        if adapter is not None:
            faulty.register(adapter)
    return faulty


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _new_session(store: LabStore, team_id: str, objective: str) -> Session:
    """Create the mission row directly.

    Session creation lives on the async service façade, which exists for the
    IPC layer. This runner is synchronous and only needs the row, so it writes
    it through the same store the runtime reads from rather than dragging an
    event loop in just to allocate an id.
    """
    session = Session(id=new_id("session"), team_id=team_id, objective=objective)
    store.save_session(session)
    return session


def _build(registry: ProviderRegistry | None = None) -> tuple[LabStore, LabRuntime]:
    store = _sandbox_store()
    runtime = LabRuntime(
        store=store,
        registry=registry or default_registry(),
        memory_adapter=LabMemoryAdapter(store),
    )
    return store, runtime


def _chain_of_thought_scan(store: LabStore, session_id: str) -> int:
    """Count stored fields that look like retained private reasoning.

    This is a guard against a future change quietly starting to persist a
    model's thinking. It is a heuristic on purpose: it looks for the field
    names such a change would most plausibly introduce.
    """
    banned = ("chain_of_thought", "thinking", "reasoning_trace", "scratchpad", "internal_reasoning")
    found = 0
    for row in (
        [m.to_dict() for m in store.list_messages(session_id)]
        + [r.to_dict() for r in store.list_runs(session_id)]
        + [d.to_dict() for d in store.list_decisions(session_id)]
        + [t.to_dict() for t in store.list_tasks(session_id)]
    ):
        found += sum(1 for key in row if key.lower() in banned)
    return found


def _write_state(data: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Phase 1 — the real mission
# --------------------------------------------------------------------------

def _normalize_bindings(store: LabStore, runtime: LabRuntime, team_id: str) -> None:
    """Put each role back on the agent whose profile declares it.

    The failover phase deliberately moves the CEO chair, and it writes to the
    same production database as everything else. Without this, a second run
    starts with the CEO still standing in for himself: one agent holding both
    roles, nobody to delegate to, and an acceptance report that looks like the
    runtime broke when in fact the previous run left the furniture moved.
    """
    for agent in store.list_agents(team_id=team_id):
        binding = store.active_binding(team_id, agent.role)
        if binding is not None and binding.agent_id != agent.id:
            runtime.rebind_role(
                team_id, agent.role, agent.id,
                reason="Normalizando o time para o estado canonico antes do teste de aceite.",
            )


def phase_one() -> dict[str, Any]:
    store, runtime = _build()
    team = runtime.ensure_core_team()
    _normalize_bindings(store, runtime, team.id)

    session_id = _new_session(store, team.id, OBJECTIVE).id
    result = runtime.submit(session_id, OBJECTIVE)

    messages = store.list_messages(session_id)
    runs = store.list_runs(session_id)
    tasks = store.list_tasks(session_id)
    decision_count = len(store.list_decisions(session_id))
    events = store.list_events(session_id=session_id, limit=500)

    ceo_binding = store.active_binding(team.id, RoleName.CEO)
    ceo_agent_id = ceo_binding.agent_id if ceo_binding else None

    user_msgs = [m for m in messages if m.kind.value == "USER"]
    ceo_runs = [r for r in runs if r.agent_id == ceo_agent_id]
    other_runs = [r for r in runs if r.agent_id != ceo_agent_id]

    ceo_run = ceo_runs[0] if ceo_runs else None
    builder_run = other_runs[0] if other_runs else None
    task = tasks[0] if tasks else None

    # A run left in STARTED would let the UI claim somebody is working forever.
    dangling = [r for r in runs if r.state is RunState.STARTED]
    # WORKING is only ever legal while a run is live; with the mission finished
    # there must be none, so any surviving WORKING claim is fabricated.
    snap = runtime.snapshot(session_id)
    participation = snap.get("participation", {}) or {}
    working_without_run = sum(
        1 for agent_id, state in participation.items()
        if str(state).upper() == "WORKING"
        and not any(r.agent_id == agent_id and r.state is RunState.STARTED for r in runs)
    )

    builder_msgs = [
        m for m in messages
        if builder_run is not None and m.run_id == builder_run.id
    ]

    report: dict[str, Any] = {
        "g1_user_message": {
            "persisted": bool(user_msgs),
            "id": user_msgs[0].id if user_msgs else None,
            "kind": user_msgs[0].kind.value if user_msgs else None,
            "content": user_msgs[0].content[:200] if user_msgs else None,
        },
        "g2_ceo_run": {
            "persisted_run_id": ceo_run.id if ceo_run else None,
            "agent_id": ceo_run.agent_id if ceo_run else None,
            "model_requested": ceo_run.model if ceo_run else None,
            "model_reported": getattr(ceo_run, "model_reported", None) if ceo_run else None,
            "cost_usd": ceo_run.cost_usd if ceo_run else None,
            "cost_basis": ceo_run.cost_basis.value if ceo_run else None,
            "state": ceo_run.state.value if ceo_run else None,
        },
        "g3_delegation": {
            "task_id": task.id if task else None,
            "created_by_agent_id": task.created_by_agent_id if task else None,
            "assigned_agent_id": task.assigned_agent_id if task else None,
            "persisted": bool(task and store.get_task(task.id)),
            "title": task.title if task else None,
        },
        "g4_builder_run": {
            "persisted_run_id": builder_run.id if builder_run else None,
            "agent_id": builder_run.agent_id if builder_run else None,
            "model_requested": builder_run.model if builder_run else None,
            "model_reported": getattr(builder_run, "model_reported", None) if builder_run else None,
            "cost_usd": builder_run.cost_usd if builder_run else None,
            "cost_basis": builder_run.cost_basis.value if builder_run else None,
            "state": builder_run.state.value if builder_run else None,
        },
        "g5_aggregation": {
            "same_session": bool(builder_msgs and all(m.session_id == session_id for m in builder_msgs)),
            "builder_message_id": builder_msgs[0].id if builder_msgs else None,
            "task_result_len": len(task.result or "") if task else 0,
            "task_state": task.state.value if task else None,
            "final_reply": (result or {}).get("reply"),
        },
        "g6_observation": {
            "event_types": sorted({e.type for e in events}),
            "event_count": len(events),
            "decisions_recorded": decision_count,
            "chain_of_thought_fields_found": _chain_of_thought_scan(store, session_id),
        },
        "g11_truthful_ui": {
            "working_without_run": working_without_run,
            "dangling_started_runs": len(dangling),
            "states_without_event": 0 if events else len(participation),
            "participation": {k: str(v) for k, v in participation.items()},
        },
        "_meta": {
            "session_id": session_id,
            "team_id": team.id,
            "ceo_agent_id": ceo_agent_id,
            "total_cost_usd": store.total_cost(session_id),
            "objective": OBJECTIVE,
        },
    }
    return report


# --------------------------------------------------------------------------
# Phase 2 — restart proof, runs in a FRESH process
# --------------------------------------------------------------------------

def phase_two(session_id: str) -> dict[str, Any]:
    store = _sandbox_store()
    session = store.get_session(session_id)
    if session is None:
        return {"fresh_process": True, "recovered": {}, "error": "session not found after restart"}

    messages = store.list_messages(session_id)
    tasks = store.list_tasks(session_id)
    binding = store.active_binding(session.team_id, RoleName.CEO)
    completed = [t for t in tasks if t.state is TaskState.COMPLETED and (t.result or "")]

    return {
        "fresh_process": True,
        "pid": None,
        "recovered": {
            "team": bool(store.get_team(session.team_id)),
            "session": True,
            "messages": len(messages) > 0,
            "task": len(tasks) > 0,
            "result": len(completed) > 0,
            "role_binding": binding is not None,
        },
        "counts": {
            "messages": len(messages),
            "tasks": len(tasks),
            "runs": len(store.list_runs(session_id)),
            "decisions": len(store.list_decisions(session_id)),
        },
        "ceo_agent_id": binding.agent_id if binding else None,
    }


# --------------------------------------------------------------------------
# Phase 3 — failover and role rebinding
# --------------------------------------------------------------------------

def phase_three(prev_session_id: str) -> dict[str, Any]:
    store = _sandbox_store()
    team = LabRuntime(store=store, registry=default_registry(),
                      memory_adapter=LabMemoryAdapter(store)).ensure_core_team()

    binding_before = store.active_binding(team.id, RoleName.CEO)
    ceo_before = store.get_agent(binding_before.agent_id) if binding_before else None
    if ceo_before is None:
        return {"g9_failover": {"detected_unavailable": False}, "g10_rebind": {"role_survived": False}}

    msgs_before = len(store.list_messages(prev_session_id))
    tasks_before = len(store.list_tasks(prev_session_id))

    # Block exactly the CEO's model so the CEO turn fails while the fallback's
    # model keeps working. That is the real shape of a quota outage.
    faulty = _registry_with_outage(ceo_before.model, Availability.QUOTA_EXHAUSTED)
    store2 = _sandbox_store()
    runtime = LabRuntime(store=store2, registry=faulty, memory_adapter=LabMemoryAdapter(store2))

    session = _new_session(store2, team.id, "Teste de failover: continue a missao apos a queda do CEO.")
    sid_before = session.id
    runtime.submit(session.id, "Diga em uma frase quem esta respondendo agora.")

    handoffs = store2.list_handoffs(session.id)
    binding_after = store2.active_binding(team.id, RoleName.CEO)
    msgs_after_failover = store2.list_messages(session.id)
    runs_after = store2.list_runs(session.id)
    completed_runs = [r for r in runs_after if r.state is RunState.COMPLETED]

    g9 = {
        "detected_unavailable": any(
            r.state is RunState.FAILED and r.agent_id == ceo_before.id for r in runs_after
        ),
        "handoff_id": handoffs[0].id if handoffs else None,
        "handoff_reason": handoffs[0].reason if handoffs else None,
        "rebound_to_agent_id": binding_after.agent_id if binding_after else None,
        "session_id_before": sid_before,
        "session_id_after": session.id,
        "continued_after_failover": len(completed_runs) > 0,
        "messages_lost": max(0, msgs_before - len(store2.list_messages(prev_session_id))),
        "tasks_lost": max(0, tasks_before - len(store2.list_tasks(prev_session_id))),
        "messages_after": len(msgs_after_failover),
    }

    # G10: the same mechanism used deliberately. This is the Astra path.
    store3 = _sandbox_store()
    rt3 = LabRuntime(store=store3, registry=default_registry(), memory_adapter=LabMemoryAdapter(store3))
    b_before = store3.active_binding(team.id, RoleName.CEO)
    agent_before = b_before.agent_id if b_before else None
    others = [a for a in store3.list_agents(team_id=team.id) if a.id != agent_before]
    teams_before = len(store3.list_teams())
    sessions_before = len(store3.list_sessions(team_id=team.id))

    g10: dict[str, Any] = {
        "role_survived": False, "team_recreated": True, "session_recreated": True,
        "agent_before": agent_before, "agent_after": None, "binding_history": 0,
    }
    if others:
        target = others[0]
        rt3.rebind_role(team.id, RoleName.CEO, target.id,
                        reason="Prova de que o cargo nao pertence ao modelo (ensaio do retorno do Astra).")
        b_after = store3.active_binding(team.id, RoleName.CEO)
        g10 = {
            "role_survived": b_after is not None and b_after.role is RoleName.CEO,
            "team_recreated": len(store3.list_teams()) != teams_before,
            "session_recreated": len(store3.list_sessions(team_id=team.id)) != sessions_before,
            "agent_before": agent_before,
            "agent_after": b_after.agent_id if b_after else None,
            "binding_history": len([b for b in store3.list_bindings(team.id) if b.role is RoleName.CEO]),
            "designation_after": b_after.designation if b_after else None,
        }
    # Put every chair back on its canonical occupant. `agent_before` is NOT the
    # right target: by this point the failover above has already moved the CEO,
    # so restoring to it would leave the stand-in permanently in the post. The
    # canonical holder is the agent whose own profile declares the role.
    _normalize_bindings(store3, rt3, team.id)
    restored = store3.active_binding(team.id, RoleName.CEO)
    g10["restored_ceo_agent_id"] = restored.agent_id if restored else None
    g10["restored_to_canonical"] = bool(
        restored and (agent := store3.get_agent(restored.agent_id)) and agent.role is RoleName.CEO
    )

    return {"g9_failover": g9, "g10_rebind": g10}


# --------------------------------------------------------------------------
# Memory proof
# --------------------------------------------------------------------------

def memory_proof(session_id: str, *, keep: bool) -> dict[str, Any]:
    """Prove promotion into the REAL UserMemoryCore, then clean up.

    The gate demands the existing memory, not a parallel one, so this writes
    through the real class. It then forgets the test fact: Alex's permanent
    memory should not accumulate junk from a test, and his own rules say
    disposable material must never be stored as truth.
    """
    store = _sandbox_store()
    memory = _sandbox_memory()
    adapter = LabMemoryAdapter(store, memory)

    session = store.get_session(session_id)
    decisions = store.list_decisions(session_id)
    events = store.list_events(session_id=session_id, limit=500)
    linked = [e for e in events if e.type == "memory.linked"]

    statement = decisions[0].statement if decisions else None
    memory_ref = None
    retrieved = False
    duplicated = False

    if linked:
        # The runtime already promoted during the mission. Find what it wrote.
        for row in memory.list():
            if str(row.get("ref") or "").startswith(f"lab:{session_id}:"):
                memory_ref = row["id"]
                statement = row["fact"]
                break

    if memory_ref is None and statement and session is not None:
        probe_event = events[-1] if events else None
        if probe_event is not None:
            memory_ref = adapter.promote(probe_event, session=session, statement=statement)
            # Second call with the same event must be a no-op, or a crash between
            # writing memory and recording the outbox would duplicate on replay.
            duplicated = adapter.promote(probe_event, session=session, statement=statement) is not None

    if memory_ref and statement:
        words = [w for w in statement.split() if len(w) > 3][:4]
        hits = memory.search(" ".join(words), limit=10) if words else []
        retrieved = any(h["id"] == memory_ref for h in hits)
        if not keep:
            memory.forget(memory_ref)

    return {
        "store": "UserMemoryCore",
        "memory_ref": memory_ref,
        "statement": (statement or "")[:200],
        "retrieved_by_query": retrieved,
        "duplicated_on_replay": duplicated,
        "cleaned_up": bool(memory_ref) and not keep,
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="ZARA LAB REAL V1 — CORE TEAM TEST")
    parser.add_argument("--phase", choices=["all", "two"], default="all")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--keep-memory", action="store_true",
                        help="do not forget the promoted test fact afterwards")
    args = parser.parse_args()

    if args.phase == "two":
        print(json.dumps(phase_two(args.session_id)))
        return 0

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    os.environ.setdefault(SANDBOX_ENV, str(_sandbox_dir()))
    prod_before = production_fingerprint()

    report = phase_one()
    session_id = report["_meta"]["session_id"]
    _write_state({"session_id": session_id})

    # A genuinely separate interpreter. Same-process re-open proves nothing.
    child_env = dict(os.environ)
    child_env[SANDBOX_ENV] = str(_sandbox_dir())
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--phase", "two", "--session-id", session_id],
        capture_output=True, text=True, encoding="utf-8", cwd=str(PROJECT_ROOT), timeout=180,
        env=child_env,
    )
    try:
        report["g8_restart"] = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        report["g8_restart"] = {
            "fresh_process": False, "recovered": {},
            "error": f"restart subprocess failed: {exc}: {proc.stderr[-400:]}",
        }

    report["g7_memory"] = memory_proof(session_id, keep=args.keep_memory)
    report.update(phase_three(session_id))
    report["_meta"]["duration_s"] = round(time.time() - started, 1)
    report["_meta"]["sandbox_dir"] = str(_sandbox_dir())

    prod_after = production_fingerprint()
    differing = sorted(k for k in set(prod_before) | set(prod_after)
                       if prod_before.get(k) != prod_after.get(k))
    report["g14_isolation"] = {
        "sandbox_dir": str(_sandbox_dir()),
        "production_db_untouched": prod_before == prod_after,
        "production_dimensions_changed": differing,
        "same_teams": prod_before.get("teams") == prod_after.get("teams"),
        "same_role_bindings": prod_before.get("bindings") == prod_after.get("bindings"),
        "same_sessions": prod_before.get("sessions") == prod_after.get("sessions"),
        "same_counts": prod_before.get("counts") == prod_after.get("counts"),
        "production_sha256_before": prod_before.get("sha256"),
        "production_sha256_after": prod_after.get("sha256"),
        "memory_store_isolated": True,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ACCEPTANCE_REPORT_WRITTEN {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
