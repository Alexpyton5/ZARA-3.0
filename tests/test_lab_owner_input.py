"""Owner steering stays in the canonical mission and fences stale work."""
import asyncio

import pytest

from core.lab_v1.domain import AgentProfile, Session, Team, TeamMembership, Task
from core.lab_v1.execution_scope import ExecutionScope
from core.lab_v1.mission_controller import MissionController, MissionStep, Receipt, Verification
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore


class Ports:
    def __init__(self):
        self.controller = None
        self.steer_during_execute = False
        self.last_dispatch = None
        self.executed = []

    def execute(self, dispatch):
        self.last_dispatch = dispatch
        self.executed.append(dispatch.step_id)
        if self.steer_during_execute:
            self.controller.submit_owner_input(dispatch.session_id, "deixe o resultado mais discreto")
        return Receipt("artifact:" + dispatch.attempt_id, "old result")

    def verify(self, dispatch, receipt):
        return Verification("PASS", "evidence:pass")


def _world(tmp_path, *, first_kind="INVOKE"):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    store.save_team(Team("team", "Team"))
    store.save_agent(AgentProfile("agent", "Worker", "fake", "fake"))
    store.save_membership(TeamMembership("membership", "team", "agent"))
    store.save_session(Session("session", "team", "Create a concise report"))
    for task_id in ("task1", "task2"):
        store.save_task(Task(task_id, "session", "Work", "Do the work", "agent",
                             assigned_agent_id="agent", acceptance="Observed result"))
    controller = MissionController(store)
    scope = ExecutionScope(("provider:fake/fake",), ("model.invoke", "sandbox.write"),
                           authorization_state="POLICY_AUTHORIZED", authorization_ref="test")
    controller.plan("session", [
        MissionStep("one", "task1", first_kind,
                    capability="sandbox.write" if first_kind == "ACTION" else "model.invoke",
                    resources=("provider:fake/fake",)),
        MissionStep("two", "task2", "INVOKE", depends_on=("one",),
                    capability="model.invoke", resources=("provider:fake/fake",)),
    ], scope=scope)
    ports = Ports()
    ports.controller = controller
    return store, controller, ports


def test_owner_input_revises_same_mission_and_reaches_next_worker(tmp_path):
    store, controller, ports = _world(tmp_path)
    controller.tick("session", ports)
    controller.tick("session", ports)  # first step is verified and remains history

    accepted = controller.submit_owner_input("session", "use no máximo três linhas")
    revised = controller.tick("session", ports)

    assert accepted["accepted"] is True
    assert accepted["classification"] == "CONSTRAINT"
    assert revised["plan_version"] == 2
    assert revised["owner_inputs"][-1]["text"] == "use no máximo três linhas"
    assert revised["steps"][0]["status"] == "DONE"
    assert "use no máximo três linhas" in ports.controller.snapshot("session")["owner_inputs"][-1]["text"]
    assert "use no máximo três linhas" in ports.last_dispatch.context.render()
    assert store.get_session("session").id == "session"


def test_owner_input_during_execution_fences_old_result(tmp_path):
    store, controller, ports = _world(tmp_path)
    ports.steer_during_execute = True

    revised = controller.tick("session", ports)

    first = revised["steps"][0]
    assert revised["plan_version"] == 2
    assert first["status"] == "PENDING"
    assert first["receipt"] is None
    assert first["superseded"][-1]["receipt"]["summary"] == "old result"
    assert store.get_task("task1").state.value == "CREATED"


def test_owner_input_never_replays_an_inflight_action(tmp_path):
    _, controller, ports = _world(tmp_path, first_kind="ACTION")
    ports.steer_during_execute = True

    received = controller.tick("session", ports)
    ports.steer_during_execute = False
    revised = controller.tick("session", ports)
    controller.tick("session", ports)

    assert received["plan_version"] == 1
    assert received["steps"][0]["status"] == "VERIFYING"
    assert revised["plan_version"] == 2
    assert revised["steps"][0]["status"] == "DONE"
    assert ports.executed.count("one") == 1
    assert "deixe o resultado mais discreto" in ports.last_dispatch.context.render()


def test_pending_owner_input_cannot_erase_crashed_dispatch_fence(tmp_path):
    _, controller, _ = _world(tmp_path)

    class CrashingPorts(Ports):
        def execute(self, dispatch):
            controller.submit_owner_input(dispatch.session_id, "mude a orientação")
            raise SystemExit("crash after dispatch")

    with pytest.raises(SystemExit):
        controller.tick("session", CrashingPorts())

    clean_ports = Ports()
    blocked = controller.tick("session", clean_ports)

    assert blocked["state"] == "BLOCKED"
    assert blocked["blocker"] == "UNCERTAIN_EFFECT"
    assert blocked["steps"][0]["status"] == "RECONCILE"
    assert clean_ports.executed == []
    assert blocked.get("owner_inputs") is None


def test_service_routes_active_mission_text_to_owner_input():
    calls = []
    controller = type("Controller", (), {
        "snapshot": lambda self, sid: {"session_id": sid, "state": "RUNNING"},
        "submit_owner_input": lambda self, sid, text: calls.append((sid, text)) or {
            "accepted": True, "session_id": sid, "status": "PENDING"},
    })()
    service = LabV1Service()
    service._autopilot = type("Autopilot", (), {"controller": controller})()

    result = asyncio.run(service.submit("session", "deixe mais discreto"))

    assert result["success"] is True
    assert result["code"] == "OWNER_INPUT_ACCEPTED"
    assert calls == [("session", "deixe mais discreto")]


def test_invalid_active_owner_input_never_falls_back_to_legacy_start():
    controller = type("Controller", (), {
        "snapshot": lambda self, sid: {"session_id": sid, "state": "QUEUED"},
        "submit_owner_input": lambda self, sid, text: (_ for _ in ()).throw(ValueError("invalid")),
    })()
    service = LabV1Service()
    service._autopilot = type("Autopilot", (), {
        "controller": controller,
        "start": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy fallback")),
    })()

    result = asyncio.run(service.submit("session", ""))

    assert result["success"] is False
    assert result["code"] == "OWNER_INPUT_INVALID"


def test_cancel_requested_rejects_owner_input_and_never_reopens_work(tmp_path):
    _, controller, _ = _world(tmp_path)
    controller.cancel("session")

    try:
        controller.submit_owner_input("session", "continue mesmo assim")
    except ValueError as exc:
        assert "cancel" in str(exc).lower()
    else:
        raise AssertionError("cancelled mission accepted new owner work")

    mission = controller.snapshot("session")
    assert mission["cancel_requested"] is True
    assert mission["plan_version"] == 1
