"""Acceptance tests for CODEX-NOVA-UI-FIACAO-20260930. No live/Windows calls."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from core.nova_ui_ipc import build_nova_ui_handlers


class Row(dict):
    def to_dict(self):
        return deepcopy(self)


class Store:
    def __init__(self):
        self.teams = [Row(id="team-real", name="Projeto real", archived=False)]
        self.agents = [Row(id="agent-real", name="Ana", role="ENGINEER", archived=False)]
        self.memberships = {"team-real": [Row(agent_id="agent-real", left_at=None)]}
        self.bindings = {"team-real": []}
        self.sessions = [Row(id="mission-real", team_id="team-real", objective="Corrigir busca",
                             state="RUNNING", updated_at=1000)]
        self.tasks = {"mission-real": [Row(id="task-real", title="Busca", instruction="Corrigir filtro",
                                          assigned_agent_id="agent-real", state="RUNNING", updated_at=1000)]}
        self.runs = {"mission-real": [Row(id="run-real", agent_id="agent-real", task_id="task-real", state="STARTED")]}
        self.artifacts = {"mission-real": []}
        self.missions = {"mission-real": {"state": "RUNNING", "steps": []}}
        self.autonomy = {"mission-real": {"pause_requested": False}}

    def list_teams(self, **kw): return self.teams
    def list_agents(self, **kw): return self.agents
    def list_memberships(self, tid): return self.memberships.get(tid, [])
    def list_bindings(self, tid): return self.bindings.get(tid, [])
    def list_sessions(self, **kw): return self.sessions
    def list_tasks(self, sid): return self.tasks.get(sid, [])
    def list_runs(self, sid): return self.runs.get(sid, [])
    def list_artifacts(self, sid): return self.artifacts.get(sid, [])
    def mission_snapshot(self, sid): return deepcopy(self.missions.get(sid))
    def autonomy_snapshot(self, sid): return deepcopy(self.autonomy.get(sid))


class Supervisor:
    def __init__(self, calls):
        self.calls = calls
        self.document = {"background_enabled": True, "paid_allowed": False,
                         "enabled": False, "scheduler_enabled": False}

    def policy(self): return deepcopy(self.document)

    def pause_background(self):
        self.calls.append("pause-background")
        self.document["background_enabled"] = False
        return self.policy()

    def resume_background(self):
        self.calls.append("resume-background")
        self.document["background_enabled"] = True
        return self.policy()


class Autopilot:
    def __init__(self, store, calls): self.store, self.calls = store, calls

    def pause(self, sid, reason="owner_requested"):
        self.calls.append(("pause", sid))
        self.store.autonomy[sid]["pause_requested"] = True
        return {"success": True, "state": "PAUSED", "session_id": sid}

    def resume(self, sid):
        self.calls.append(("resume", sid))
        self.store.autonomy[sid]["pause_requested"] = False
        return {"success": True, "state": "RUNNING", "session_id": sid}


class Service:
    def __init__(self, store):
        self.store, self.calls = store, []
        self.supervisor = Supervisor(self.calls)
        self.autopilot = Autopilot(store, self.calls)
        self._supervisor_task = self._scheduler_task = self._operation_consumer_task = None
        self._provider_discovery_task = None
        self.snapshot_result = {"success": True, "participation": {"agent-real": "IDLE"}}
        self.admitted = []

    def _get_runtime(self): return SimpleNamespace(store=self.store)
    def _get_supervisor(self): return self.supervisor
    def _get_autopilot(self): return self.autopilot
    async def snapshot(self): return deepcopy(self.snapshot_result)

    async def stop_background(self):
        self.calls.append("stop-background")
        for name in ("_supervisor_task", "_scheduler_task", "_operation_consumer_task"):
            setattr(self, name, None)
        return {"success": True, "state": "PAUSED"}

    async def start_background(self):
        self.calls.append("start-background")
        self._supervisor_task = SimpleNamespace(done=lambda: False)
        self._operation_consumer_task = SimpleNamespace(done=lambda: False)
        return {"success": True, "state": "RUNNING"}

    async def admit_operation_for_dispatch(self, request_id, command, payload):
        self.admitted.append((request_id, command, payload))
        return {"success": True, "accepted": True, "state": "ADMITTED",
                "operation_id": "op-real", "request_id": request_id}, True


class Legacy:
    def __init__(self):
        self.proposals = [{"id": "proposal-real", "title": "Melhorar busca", "summary": "Filtro quebrado",
                           "status": "DISCUSSION"}]
        self.lab_autonomy = SimpleNamespace(_task=None)
        self.enabled, self.running = True, True
        self.decided = []

    async def get_state(self): return {"proposals": deepcopy(self.proposals)}
    async def autonomy_status(self): return {"enabled": self.enabled, "running": self.running}
    async def autonomy_stop(self):
        self.enabled = self.running = False
        return await self.autonomy_status()

    async def autonomy_start(self):
        self.enabled = self.running = True
        return await self.autonomy_status()

    async def decide_proposal(self, pid, decision):
        self.decided.append((pid, decision))
        return {"id": pid, "status": "APPROVED" if decision == "APPROVE" else "REJECTED"}


@pytest.fixture
def host():
    responses = []
    async def send_response(request_id, response): responses.append((request_id, response))
    return SimpleNamespace(lab_v1=Service(Store()), lab=Legacy(), responses=responses,
                           send_response=send_response)


def request(host, channel, payload=None):
    handlers = build_nova_ui_handlers(host)
    asyncio.run(handlers[channel](SimpleNamespace(request_id="req-real", payload=payload)))
    return host.responses[-1][1]


def test_channels_and_real_rows(host):
    assert set(build_nova_ui_handlers(host)) == {"nova-ui-state", "nova-ui-pause", "nova-ui-resume", "nova-ui-decision"}
    state = request(host, "nova-ui-state")
    assert state["projects"][0]["id"] == "mission-real"
    assert state["projects"][0]["nome"] == "Corrigir busca"
    assert state["projects"][0]["membros"] == [{"avatar": {"id": "agent-real", "nome": "Ana", "papel": "ENGINEER"},
                                              "status": "trabalhando", "tarefaAtual": "Busca"}]
    assert state["work"][0]["id"] == "task-real"
    assert state["work"][0]["atualizadoEm"] == "1970-01-01T00:16:40Z"
    assert state["decisions"][0]["id"] == "proposal-real"
    assert not state["activity"]
    assert state["paused"] is False  # Lab is actually enabled, never globally paused.


def test_no_invented_members_or_offline_success(host):
    store = host.lab_v1.store
    store.agents.append(Row(id="outsider", name="Fora", role="MEMBER"))
    store.runs["mission-real"] = []
    host.lab_v1.snapshot_result["participation"]["agent-real"] = "OFFLINE"
    state = request(host, "nova-ui-state")
    assert state["projects"][0]["membros"] == []
    assert state["success"] is True
    assert state["warning"]
    assert any(x.get("id") == "agent-real" for x in state["unknown"])
    assert "outsider" not in repr(state)


def test_membership_and_binding_are_per_team(host):
    store = host.lab_v1.store
    store.teams.append(Row(id="other-team", name="Outro", archived=False))
    store.memberships["other-team"] = []
    store.bindings["team-real"] = [Row(agent_id="agent-real", role="REVIEWER", active=True)]
    state = request(host, "nova-ui-state")
    assert state["projects"][0]["membros"][0]["avatar"]["papel"] == "REVIEWER"
    assert state["projects"][1]["membros"] == []


def test_deliveries_use_stored_completion_and_artifact(host):
    store = host.lab_v1.store
    store.tasks["mission-real"][0].update(state="COMPLETED", result="Filtro entregue", updated_at=2000)
    store.runs["mission-real"] = []
    store.artifacts["mission-real"] = [Row(task_id="task-real", path="https://example.invalid/result")]
    state = request(host, "nova-ui-state")
    assert state["work"][0]["estado"] == "entregue"
    assert state["activity"][0]["descricao"] == "Filtro entregue"
    assert state["activity"][0]["concluidoEm"] == "1970-01-01T00:33:20Z"
    assert state["activity"][0]["entregavelUrl"] == "https://example.invalid/result"


def test_missing_owner_and_timestamp_are_not_filled(host):
    host.lab_v1.store.tasks["mission-real"][0].update(assigned_agent_id=None, updated_at=None)
    state = request(host, "nova-ui-state")
    assert state["work"] == []
    assert any(x.get("id") == "task-real" for x in state["unknown"])


def test_snapshot_failure_and_unavailable_service_stay_failures(host):
    host.lab_v1.snapshot_result = {"success": False, "error": "snapshot failed"}
    state = request(host, "nova-ui-state")
    assert state["success"] is False
    assert state["projects"] == []
    host.lab_v1 = None
    result = request(host, "nova-ui-pause")
    assert result["success"] is False
    assert result["paused"] is None
    assert result["components"]["lab"]["success"] is False


def test_pause_persists_real_control_without_weakening_policy(host):
    store = host.lab_v1.store
    store.runs["mission-real"] = []
    result = request(host, "nova-ui-pause")
    assert host.lab_v1.calls[:2] == ["pause-background", ("pause", "mission-real")]
    assert "stop-background" in host.lab_v1.calls
    assert host.lab_v1.supervisor.policy() == {"background_enabled": False, "paid_allowed": False,
                                             "enabled": False, "scheduler_enabled": False}
    assert store.autonomy["mission-real"]["pause_requested"] is True
    assert result["components"]["lab"]["paused"] is True
    assert result["components"]["autopilot"]["paused"] is True
    assert host.lab.enabled is False
    assert result["success"] is True  # Confirmed TEAM pause; explicit PC commands are separate.
    assert result["scope"] == "team"
    assert result["paused"] is True
    assert result["components"]["computer_agent"]["code"] == "COMPUTER_AGENT_CONTROL_UNAVAILABLE"


def test_inflight_provider_is_not_reported_stopped(host):
    result = request(host, "nova-ui-pause")
    assert result["success"] is False
    assert result["components"]["autopilot"]["success"] is False
    assert result["components"]["autopilot"]["code"] == "IN_FLIGHT_WORK"


def test_uncontrolled_lab_turn_cannot_be_paused_with_a_flag(host):
    host.lab_v1.store.missions = {}
    result = request(host, "nova-ui-pause")
    assert result["components"]["autopilot"]["success"] is False
    assert result["components"]["autopilot"]["code"] == "UNCONTROLLED_LAB_WORK"


def test_pause_verifies_persistence_even_if_api_says_success(host):
    host.lab_v1.autopilot.pause = lambda *a, **kw: {"success": True, "state": "PAUSED"}
    result = request(host, "nova-ui-pause")
    assert result["components"]["autopilot"]["success"] is False


def test_legacy_detached_cycle_is_not_mistaken_for_quiescence(host):
    host.lab.lab_autonomy._task = SimpleNamespace(done=lambda: False)
    result = request(host, "nova-ui-pause")
    assert result["components"]["legacy_lab"]["success"] is False
    assert result["components"]["legacy_lab"]["code"] == "LEGACY_CYCLE_STILL_RUNNING"


def test_resume_uses_actual_pauses_and_respects_other_policy(host):
    host.lab_v1.store.autonomy["mission-real"]["pause_requested"] = True
    host.lab_v1.supervisor.document["background_enabled"] = False
    result = request(host, "nova-ui-resume")
    assert ("resume", "mission-real") in host.lab_v1.calls
    assert "start-background" in host.lab_v1.calls
    assert host.lab_v1.store.autonomy["mission-real"]["pause_requested"] is False
    assert host.lab_v1.supervisor.document["paid_allowed"] is False
    assert host.lab_v1.supervisor.document["enabled"] is False
    assert result["paused"] is False


def test_resume_failure_is_not_changed_into_success(host):
    async def failed_start(): return {"success": False, "state": "BLOCKED", "error": "policy blocks"}
    host.lab_v1.start_background = failed_start
    result = request(host, "nova-ui-resume")
    assert result["success"] is False
    assert result["components"]["lab"]["success"] is False


@pytest.mark.parametrize("option,expected", [("Aprovar", "APPROVE"), ("Recusar", "REJECT")])
def test_decision_reuses_real_proposal_api(host, option, expected):
    result = request(host, "nova-ui-decision", {"id": "proposal-real", "option": option})
    assert host.lab.decided == [("proposal-real", expected)]
    assert result["success"] is True
    assert result["id"] == "proposal-real"


@pytest.mark.parametrize("payload", [{"id": "invented", "opcao": "Aprovar"},
                                     {"id": "proposal-real", "opcao": "Outra"},
                                     {"id": "proposal-real", "opcao": 0}, []])
def test_invalid_decision_never_dispatches(host, payload):
    result = request(host, "nova-ui-decision", payload)
    assert result["success"] is False
    assert host.lab.decided == []
    assert host.lab_v1.admitted == []


def test_api_failure_is_not_approved_by_adapter(host):
    async def failed_decide(*args): return {"success": False, "error": "policy denied"}
    host.lab.decide_proposal = failed_decide
    result = request(host, "nova-ui-decision", {"id": "proposal-real", "decision": "APPROVE"})
    assert result["success"] is False


def test_mission_decision_preserves_durable_ack_confirmation(host):
    host.lab_v1.store.missions["mission-real"].update(state="BLOCKED", blocker="WAITING_OWNER")
    result = request(host, "nova-ui-decision", {"id": "mission-real", "opcao": "Cancelar missão"})
    assert host.lab_v1.admitted == [("req-real", "lab.v1.cancel", {"session_id": "mission-real"})]
    assert result["accepted"] is True
    assert result["operation_id"] == "op-real"
    assert result["confirmed"] is False
    assert result["completed"] is False
    assert result["state"] == "ADMITTED"


def test_real_sqlite_store_projection_is_isolated(host, tmp_path):
    from core.lab_v1.domain import AgentProfile, RoleName, Team, TeamMembership
    from core.lab_v1.store import LabStore
    store = LabStore(tmp_path / "isolated.sqlite3")
    store.initialize()
    store.save_team(Team(id="sqlite-team", name="Time persistido"))
    store.save_agent(AgentProfile(id="sqlite-agent", name="Persistida", role=RoleName.ENGINEER,
                                  provider_id="test", model="test"))
    store.save_membership(TeamMembership(id="membership", team_id="sqlite-team", agent_id="sqlite-agent"))
    host.lab_v1.store = store
    host.lab_v1.snapshot_result["participation"] = {"sqlite-agent": "IDLE"}
    state = request(host, "nova-ui-state")
    assert state["projects"] == [{"id": "sqlite-team", "nome": "Time persistido", "membros": [
        {"avatar": {"id": "sqlite-agent", "nome": "Persistida", "papel": "ENGINEER"}, "status": "disponivel"}]}]


def test_actual_autopilot_and_supervisor_persist_pause_resume(host, tmp_path):
    from core.lab_v1.autopilot import Autopilot as RealAutopilot
    from core.lab_v1.domain import Session, SessionState, Team
    from core.lab_v1.store import LabStore
    from core.lab_v1.supervisor import AutonomySupervisor
    store = LabStore(tmp_path / "mission.sqlite3")
    store.initialize()
    store.save_team(Team(id="team", name="Persistido"))
    store.save_session(Session(id="real-sid", team_id="team", objective="Missão real", state=SessionState.RUNNING))
    runtime = SimpleNamespace(store=store)
    engine = RealAutopilot(runtime, root=tmp_path / "missions")
    supervisor = AutonomySupervisor(runtime, autopilot=engine)
    with store._connect() as conn:
        conn.execute("INSERT INTO mission_controls(session_id,document) VALUES(?,?)",
                     ("real-sid", json.dumps({"state": "RUNNING", "session_id": "real-sid", "steps": []})))
        conn.execute("INSERT INTO mission_autonomy VALUES(?,?)", ("real-sid", json.dumps({"pause_requested": False})))
    host.lab_v1.store = store
    host.lab_v1.autopilot = engine
    host.lab_v1.supervisor = supervisor
    initial = supervisor.policy()
    result = request(host, "nova-ui-pause")
    assert result["components"]["autopilot"]["paused"] is True
    assert store.autonomy_snapshot("real-sid")["pause_requested"] is True
    assert supervisor.policy()["background_enabled"] is False
    result = request(host, "nova-ui-resume")
    assert store.autonomy_snapshot("real-sid")["pause_requested"] is False
    assert supervisor.policy()["background_enabled"] is True
    assert supervisor.policy()["paid_allowed"] == initial["paid_allowed"]
    assert supervisor.policy()["authorized_models"] == initial["authorized_models"]
    assert {e.type for e in store.list_events("real-sid")} >= {"mission.paused", "mission.resumed"}


def test_pause_stops_background_even_if_store_observation_fails(host):
    host.lab_v1.store.list_sessions = lambda **kw: (_ for _ in ()).throw(RuntimeError("store unavailable"))
    result = request(host, "nova-ui-pause")
    assert "stop-background" in host.lab_v1.calls
    assert result["components"]["autopilot"]["success"] is False


def test_detached_legacy_cycle_cannot_be_resumed_into_a_duplicate(host):
    starts = []
    async def start():
        starts.append(True)
        return {"enabled": True, "running": True}
    host.lab.lab_autonomy._task = SimpleNamespace(done=lambda: False)
    host.lab.autonomy_start = start
    request(host, "nova-ui-pause")
    result = request(host, "nova-ui-resume")
    assert starts == []
    assert result["components"]["legacy_lab"]["code"] == "LEGACY_CYCLE_STILL_RUNNING"


def test_resume_rejects_running_ack_without_actual_background_task(host):
    async def pretend_start(): return {"success": True, "state": "RUNNING"}
    host.lab_v1.start_background = pretend_start
    result = request(host, "nova-ui-resume")
    assert result["components"]["lab"]["success"] is False


def test_run_does_not_make_agent_work_in_every_project(host):
    store = host.lab_v1.store
    store.teams.append(Row(id="other-team", name="Outro", archived=False))
    store.memberships["other-team"] = [Row(agent_id="agent-real", left_at=None)]
    host.lab_v1.snapshot_result["participation"]["agent-real"] = "WORKING"
    state = request(host, "nova-ui-state")
    assert state["projects"][0]["membros"][0]["status"] == "trabalhando"
    assert state["projects"][1]["membros"] == []
    assert any(x.get("project_id") == "other-team" for x in state["unknown"])


def test_activity_orders_fractional_stored_dates_correctly(host):
    store = host.lab_v1.store
    old = store.tasks["mission-real"][0]
    old.update(state="COMPLETED", updated_at=1000)
    store.tasks["mission-real"].append(Row({**old, "id": "newer", "updated_at": 1000.5}))
    state = request(host, "nova-ui-state")
    assert [row["id"] for row in state["activity"]] == ["newer", "task-real"]
