"""Astra Fase 2 proof: a real multi-agent room inside one mission.

Room semantics under test: explicit recipient, correlation id, pending-reply
state, budget, explicit close. The room never calls a model on its own; every
model call is a MissionController dispatch. No second engine is created.
"""
import json

import pytest

from core.lab_v1.domain import AgentProfile, Session, Team, TeamMembership, Task
from core.lab_v1.mission_controller import (
    MissionController, MissionLimits, MissionStep, Receipt, Verification, ExecutionScope,
)
from core.lab_v1.runtime import MissionRoom
from core.lab_v1.store import LabStore


class Clock:
    value = 1000.0

    def __call__(self):
        return self.value


class Ports:
    """Records every dispatch context; never lies about being called."""

    def __init__(self, verdict='PASS'):
        self.executed = []
        self.verified = []
        self.verdict = verdict

    def execute(self, dispatch):
        self.executed.append(dispatch)
        return Receipt('artifact:' + dispatch.attempt_id, 'Executed: ' + dispatch.context.task_title)

    def verify(self, dispatch, receipt):
        self.verified.append(dispatch)
        return Verification(self.verdict, 'evidence:room')

    @property
    def calls(self):
        return len(self.executed)


@pytest.fixture
def world(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('team', 'Room Team'))
    for agent_id, name, role in (('researcher', 'Rita', 'RESEARCHER'),
                                 ('architect', 'Ada', 'MEMBER'),
                                 ('executor', 'Vulcan', 'BUILDER'),
                                 ('reviewer', 'Qnia', 'REVIEWER')):
        store.save_agent(AgentProfile(agent_id, name, 'fake', 'fake'))
        store.save_membership(TeamMembership('mem_' + agent_id, 'team', agent_id))
    store.save_session(Session('session', 'team', 'Ship the room'))
    store.save_task(Task('task_exec', 'session', 'Build piece', 'Build the piece',
                         'architect', assigned_agent_id='executor', acceptance='Works'))
    clock, ports = Clock(), Ports()
    controller = MissionController(store, clock=clock)
    return store, controller, clock, ports


SCOPE = ExecutionScope(("provider:fake/fake",), ("model.text", "model.invoke"),
                       authorization_state="POLICY_AUTHORIZED", authorization_ref="test-policy")


def delegate_step():
    return MissionStep('build', 'task_exec', 'DELEGATE', (),
                       'model.text', ("provider:fake/fake",))


def events(store, session_id, event_type):
    with store._connect() as conn:
        rows = conn.execute('SELECT payload FROM events WHERE session_id=? AND type=? ORDER BY seq',
                            (session_id, event_type)).fetchall()
    return [json.loads(r['payload']) for r in rows]


# ---------------------------------------------------------------------------
# Proof 1: distinct contexts, real content exchange, verifiable decision
# ---------------------------------------------------------------------------

def test_two_agents_exchange_content_and_leave_verifiable_decision(world):
    store, ctl, clock, ports = world
    ctl.plan('session', [delegate_step()], scope=SCOPE)
    ports.verdict = 'FAIL'  # keep the mission alive for the room exchange
    first_dispatch = ctl.tick('session', ports).get('steps')[0]
    assert first_dispatch['status'] == 'VERIFYING'
    assert events(store, 'session', 'mission.dispatched')

    room = MissionRoom(ctl)
    asked = room.ask('session', step_id='build', from_agent_id='executor', to_agent_id='reviewer',
                     question='Reviewer: is artifact:room acceptable given the acceptance criteria?',
                     refinement_budget=1)
    correlation = asked['correlation_id']
    assert asked['status'] == 'PENDING'
    assert room.state('session', correlation)['to_agent_id'] == 'reviewer'

    answered = room.answer('session', correlation,
                           'Contested: the artifact lacks the acceptance evidence line.',
                           decision='Reviewer holds the DELEGATE result; executor must add the evidence line.')
    assert answered['status'] == 'ANSWERED'

    question_events = events(store, 'session', 'mission.room_question')
    reply_events = events(store, 'session', 'mission.room_reply')
    decision_events = events(store, 'session', 'mission.room_decision')
    assert question_events[0]['from_agent_id'] == 'executor'
    assert question_events[0]['to_agent_id'] == 'reviewer'
    assert 'acceptance criteria' in question_events[0]['question']
    assert reply_events[0]['from_agent_id'] == 'reviewer'
    assert reply_events[0]['correlation_id'] == correlation
    assert decision_events[0]['from_agent_id'] == 'executor'
    assert decision_events[0]['to_agent_id'] == 'reviewer'
    assert 'evidence line' in decision_events[0]['decision']


def test_distinct_agents_receive_distinct_contexts(world):
    store, ctl, clock, ports = world
    store.save_task(Task('task_other', 'session', 'Research piece', 'Research alternatives',
                         'architect', assigned_agent_id='researcher', acceptance='Cited'))
    ctl.plan('session', [
        MissionStep('research', 'task_other', 'INVOKE', (), 'model.text', ("provider:fake/fake",)),
        delegate_step(),
    ], scope=SCOPE)
    ctl.tick('session', ports)  # research executed
    ctl.tick('session', ports)  # research verified; build dispatched
    ctl.tick('session', ports)  # build executed
    contexts = [d.context.render() for d in ports.executed]
    assert len(ports.executed) == 2
    assert ports.executed[0].agent_id == 'researcher'
    assert ports.executed[1].agent_id == 'executor'
    assert 'Research piece' in contexts[0] and 'Research piece' not in contexts[1]
    assert 'Build piece' in contexts[1] and 'Build piece' not in contexts[0]


# ---------------------------------------------------------------------------
# Proof 2: restart between question and reply keeps the conversation, no double turn
# ---------------------------------------------------------------------------

def test_pending_reply_survives_restart_and_cannot_be_answered_twice(world):
    store, ctl, clock, ports = world
    ctl.plan('session', [delegate_step()], scope=SCOPE)
    ports.verdict = 'FAIL'
    ctl.tick('session', ports)
    room = MissionRoom(ctl)
    correlation = room.ask('session', step_id='build', from_agent_id='executor',
                           to_agent_id='reviewer', question='Hold or pass?')['correlation_id']
    assert room.state('session', correlation)['status'] == 'PENDING'

    # Simulated process restart: a brand new controller over the same storage.
    restarted = MissionController(LabStore(store.db_path), clock=clock)
    room = MissionRoom(restarted)
    assert room.state('session', correlation)['status'] == 'PENDING'
    room.answer('session', correlation, 'Pass, with the evidence line added.',
                decision='Reviewer accepted after one refinement.')
    assert room.state('session', correlation)['status'] == 'ANSWERED'
    with pytest.raises(ValueError, match='already answered'):
        room.answer('session', correlation, 'Duplicate answer attempt.')
    assert len([p for p in events(store, 'session', 'mission.room_reply')]) == 1
    # The conversation itself was never duplicated and never re-executed the turn.
    assert ports.calls == 1
    room.close('session', correlation)
    assert room.state('session', correlation)['status'] == 'CLOSED'


# ---------------------------------------------------------------------------
# Proof 3: absence of an event never calls a model
# ---------------------------------------------------------------------------

def test_room_never_generates_spontaneous_model_calls(world):
    store, ctl, clock, ports = world
    room = MissionRoom(ctl)
    with pytest.raises(ValueError, match='Unknown room correlation'):
        room.answer('session', 'room_nobody_asked', 'Spontaneous reply.')
    with pytest.raises(ValueError, match='Unknown room correlation'):
        room.close('session', 'room_nobody_asked')
    with pytest.raises(ValueError, match='Unknown room correlation'):
        room.state('session', 'room_nobody_asked')
    assert ports.calls == 0
    assert store.list_runs('session') == []

    # No mission event asks for a room: a terminal mission has no room either.
    ctl.plan('session', [delegate_step()], scope=SCOPE)
    ctl.tick('session', ports)  # executed
    ctl.tick('session', ports)  # verified -> COMPLETED
    assert ctl.snapshot('session')['state'] == 'COMPLETED'
    with pytest.raises(ValueError, match='terminal mission'):
        room.ask('session', step_id='build', from_agent_id='executor',
                 to_agent_id='reviewer', question='Anyone there?')
    ctl.tick('session', ports)
    assert ports.calls == 1  # only the planned dispatch, nothing spontaneous
    assert room.messages('session') == []


# ---------------------------------------------------------------------------
# Proof 4: DELEGATE contestation routes back with corrections, bounded loop
# ---------------------------------------------------------------------------

def test_delegate_contestation_routes_back_to_executor_with_bounded_refinements(world):
    store, ctl, clock, ports = world
    ctl.plan('session', [delegate_step()],
             MissionLimits(max_delegations=3, max_retries=2), scope=SCOPE)
    ports.verdict = 'FAIL'
    ctl.tick('session', ports)  # executor's first attempt, verification FAIL
    room = MissionRoom(ctl)
    correlation = room.ask('session', step_id='build', from_agent_id='executor',
                           to_agent_id='reviewer', question='Verdict on the first delivery?',
                           refinement_budget=2)['correlation_id']
    result = room.contest('session', correlation,
                          ['Add the evidence line.', 'Do not claim verification you did not run.'])
    assert result == {'correlation_id': correlation, 'status': 'CONTESTED', 'routed': True,
                      'refinements': 1}
    contest_events = events(store, 'session', 'mission.room_contestation')
    assert contest_events[0]['corrections'] == ['Add the evidence line.',
                                                'Do not claim verification you did not run.']
    assert contest_events[0]['to_agent_id'] == 'executor'

    # The routed re-dispatch carries the correction list to the executor.
    doc = ctl.tick('session', ports)
    rerendered = ports.executed[-1].context.render()
    assert 'Reviewer contestation' in rerendered
    assert 'Add the evidence line.' in rerendered
    assert len(ports.executed) == 2

    # Second bounded round: reviewer contests again, budget still allows one.
    ports.verdict = 'FAIL'
    second = room.ask('session', step_id='build', from_agent_id='executor',
                      to_agent_id='reviewer', question='And the corrected delivery?',
                      refinement_budget=2)['correlation_id']
    assert room.contest('session', second, ['Only formatting left.'])['routed'] is True
    doc = ctl.tick('session', ports)
    assert len(ports.executed) == 3

    # Third contest: refinement budget exhausted -> explicit owner blocker.
    ports.verdict = 'FAIL'
    third = room.ask('session', step_id='build', from_agent_id='executor',
                     to_agent_id='reviewer', question='Final verdict?',
                     refinement_budget=2)['correlation_id']
    exhausted = room.contest('session', third, ['One more nit.'])
    assert exhausted['routed'] is False
    assert ctl.snapshot('session')['blocker'] == 'REVIEW_CONTESTATION_LIMIT'
    assert ports.calls == 3  # no model call was spent on the exhausted contestation
    with pytest.raises(ValueError, match='already answered'):
        room.contest('session', third, ['Again.'])


def test_contestation_requires_a_live_delegate_step(world):
    store, ctl, clock, ports = world
    ctl.plan('session', [delegate_step()], scope=SCOPE)
    room = MissionRoom(ctl)
    correlation = room.ask('session', step_id='build', from_agent_id='executor',
                           to_agent_id='reviewer', question='Ready?', refinement_budget=1)['correlation_id']
    # A QUESTION cannot be closed before it is answered or contested.
    with pytest.raises(ValueError, match='unanswered'):
        room.close('session', correlation)
    ctl.tick('session', ports)  # executes
    ctl.tick('session', ports)  # verifies PASS; mission completes
    with pytest.raises(ValueError, match='contested'):
        room.contest('session', correlation, ['Too late.'])
