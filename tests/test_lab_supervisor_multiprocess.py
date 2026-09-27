"""Cross-process proof for the supervisor gate used by the Lab scheduler."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from core.lab_v1.domain import CapabilityGap, Team
from core.lab_v1.mission_controller import MissionController
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor


REPOSITORY = str(Path(__file__).resolve().parents[1])
T0 = 1_000_000.0


CHILD = r'''
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, {repository!r})

from core.lab_v1.domain import Session, new_id
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import ImprovementScheduler
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor

root = Path(sys.argv[1])
store = LabStore(root / "lab.db")
store.initialize()
runtime = LabRuntime(store, ProviderRegistry(root / ("health-" + str(os.getpid()) + ".json")))
supervisor = AutonomySupervisor(runtime)
scheduler = ImprovementScheduler(runtime, supervisor, clock=lambda: {now!r})


class Engine:
    def __init__(self):
        self.store = store
        self.autopilot = None

    def observe_local(self):
        return [{{"source_path": "core/actions/os_ops.py", "source_sha256": "source-sha"}}]

    def _capability_gap_evidence(self):
        return [{{"id": gap.id, "required": gap.required, "detail": json.loads(gap.detail)}}
                for gap in store.list_capability_gaps()]

    @staticmethod
    def _runtime_gap_sources(inventory, gaps):
        return inventory, gaps

    @staticmethod
    def _observation_id(kind, payload):
        return "same-real-gap"

    @staticmethod
    def _inspection_batches(inventory):
        return []

    def _already_observed(self, observation_id):
        with store._connect() as conn:
            return conn.execute("SELECT session_id FROM lab_evolution WHERE repair_id=?",
                                (observation_id,)).fetchone()

    def observe_and_plan(self, *, inventory=None):
        # Widen the pre-fix race: both OS processes used to enter here because
        # each one owned a different threading.Lock.
        time.sleep(0.5)
        sid = new_id("session")
        store.save_session(Session(sid, "team", objective="Repair factual capability gap"))
        with store._connect() as conn:
            conn.execute("INSERT INTO mission_controls(session_id,document) VALUES(?,?)", (
                sid, json.dumps({{"session_id": sid, "state": "QUEUED"}})))
            document = {{"session_id": sid, "repair_id": "same-real-gap"}}
            conn.execute("INSERT INTO lab_evolution VALUES(?,?,?)", (
                sid, "repair-" + str(os.getpid()), json.dumps(document)))
        return {{"success": True, "state": "QUEUED", "session_id": sid}}

    def snapshot(self, sid):
        return {{"session_id": sid, "repair_id": "same-real-gap"}}


supervisor.ensure_team = lambda: None
scheduler._engine = lambda policy: Engine()
(root / ("ready-" + str(os.getpid()))).write_text("ready", encoding="utf-8")
while not (root / "go").exists():
    time.sleep(0.01)
result = scheduler.cycle(now={now!r})
print(json.dumps(result), flush=True)
'''


def test_two_real_processes_create_at_most_one_gap_mission_and_spend_budget_once(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "core/actions/os_ops.py"
    source.parent.mkdir(parents=True)
    source.write_text("# factual executor\n", encoding="utf-8")

    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    MissionController(store)
    store.save_team(Team("team", "Multiprocess proof"))
    store.save_capability_gap(CapabilityGap(
        "gap:real", None, "runtime.action.os_brightness_absolute",
        detail=json.dumps({"source_path": "core/actions/os_ops.py"})))
    supervisor = AutonomySupervisor(SimpleNamespace(store=store))
    supervisor._save(
        enabled=True,
        background_enabled=True,
        scheduler_enabled=True,
        workspace=str(workspace),
        max_new_evolution_missions_per_day=5,
        daily_date=None,
        daily_missions=0,
    )
    with store._connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS lab_evolution(
            session_id TEXT PRIMARY KEY REFERENCES sessions(id),
            repair_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL)""")

    script = tmp_path / "scheduler_child.py"
    script.write_text(CHILD.format(repository=REPOSITORY, now=T0), encoding="utf-8")
    processes = [subprocess.Popen(
        [sys.executable, str(script), str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for _ in range(2)]
    deadline = time.monotonic() + 20
    while len(list(tmp_path.glob("ready-*"))) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(list(tmp_path.glob("ready-*"))) == 2
    (tmp_path / "go").write_text("go", encoding="utf-8")

    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        results.append(json.loads(stdout.strip().splitlines()[-1]))

    assert sorted(item["state"] for item in results) == ["BUSY", "DISPATCHED"], results
    assert len(store.list_sessions()) == 1
    assert supervisor.policy()["daily_missions"] == 1
