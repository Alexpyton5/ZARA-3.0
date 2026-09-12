"""Offline proof only: no provider, model or executor calls."""
import json
from dataclasses import replace

import pytest

from core.lab_v1.domain import AgentProfile, Run, RunState, Session, Task, Team, TeamMembership
from core.lab_v1.execution_scope import ExecutionScope
from core.lab_v1.mission_controller import MissionController, MissionLimits, MissionStep, TextProviderFailure
from core.lab_v1.store import LabStore


@pytest.fixture
def held(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('team', 'Offline test'))
    store.save_agent(AgentProfile('ceo', 'CEO', 'fake', 'model', effort='high'))
    store.save_membership(TeamMembership('member', 'team', 'ceo'))
    store.save_session(Session('mission', 'team', 'Original objective'))
    store.save_task(Task('plan', 'mission', 'Plan', 'Plan safely', 'ceo', assigned_agent_id='ceo', acceptance='Real plan'))
    clock = [1000.0]
    ctl = MissionController(store, clock=lambda: clock[0])
    scope = ExecutionScope(('provider:fake/model',), ('model.text',), authorization_state='POLICY_AUTHORIZED', authorization_ref='test')
    ctl.plan('mission', [MissionStep('plan', 'plan', 'INVOKE', (), 'model.text', ('provider:fake/model',))], MissionLimits(timeout_s=100), scope=scope)

    class Quota:
        def execute(self, dispatch):
            raise TextProviderFailure('QUOTA_EXHAUSTED')

    ctl.tick('mission', Quota())
    clock[0] = 9000.0
    proof = Run('proof', 'mission', 'ceo', 'fake', 'model', state=RunState.COMPLETED,
                effort='high', provider_session_id='real-route-id-in-fixture', started_at=8998, ended_at=8999)
    store.save_run(proof)
    return store, ctl, clock, proof


def test_resume_same_agent_after_quota_wait_preserves_budget_and_objective(held):
    store, ctl, clock, _ = held
    before = ctl.snapshot('mission')
    assert ctl.resume_after_quota('mission', proof_run_id='proof')
    after = ctl.snapshot('mission')
    assert after['state'] == 'QUEUED' and after['blocker'] is None
    assert after['deadline'] == before['deadline'] + clock[0] - before['updated_at']
    assert after['used'] == {**before['used'], 'retries': before['used']['retries'] + 1}
    assert after['steps'][0]['status'] == 'PENDING'
    assert store.get_session('mission').objective == 'Original objective'
    assert store.get_task('plan').assigned_agent_id == 'ceo'
    assert store.get_task('plan').state.value == 'CREATED'
    assert not ctl.resume_after_quota('mission', proof_run_id='proof')
    assert MissionController(LabStore(store.db_path), clock=lambda: clock[0]).snapshot('mission') == after


@pytest.mark.parametrize('change', [
    {'model': 'other'}, {'agent_id': 'other'}, {'effort': 'low'},
    {'state': RunState.FAILED}, {'provider_session_id': None},
    {'started_at': 998, 'ended_at': 999}, {'started_at': 8000, 'ended_at': 8001},
])
def test_rejects_invalid_or_stale_proof_without_changing_checkpoint(held, change):
    store, ctl, _, proof = held
    # Existing FK agent needed only for the deliberately mismatched proof.
    store.save_agent(AgentProfile('other', 'Other', 'fake', 'model'))
    store.save_run(replace(proof, **change))
    before = ctl.snapshot('mission')
    assert not ctl.resume_after_quota('mission', proof_run_id='proof')
    assert ctl.snapshot('mission') == before


@pytest.mark.parametrize('block', ['lease', 'cancel', 'budget', 'uncertain'])
def test_resume_fails_closed_on_unsafe_state(held, block):
    store, ctl, _, _ = held
    doc = ctl.snapshot('mission')
    with store._connect() as conn:
        if block == 'lease':
            conn.execute("UPDATE mission_controls SET lease_token='other',lease_until=9999")
        elif block == 'cancel':
            doc['cancel_requested'] = True
        elif block == 'budget':
            doc['used']['retries'] = doc['limits']['max_retries']
        else:
            doc['steps'][0]['status'] = 'RECONCILE'
        conn.execute('UPDATE mission_controls SET document=?', (json.dumps(doc),))
    assert not ctl.resume_after_quota('mission', proof_run_id='proof')
