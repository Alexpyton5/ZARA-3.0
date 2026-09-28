import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, RoleName
from core.lab_v1.workforce_policy import ResourceClass, WorkforcePolicy


def _policy(**updates):
    document = {
        'mission_entry_enabled': True,
        'paid_allowed': False,
        'resource_classes': {
            'codex_cli/gpt-5.6-luna': 'PLAN_INCLUDED',
            'codex_cli/gpt-5.6-sol': 'PLAN_INCLUDED',
            'codex_cli/gpt-5.6-terra': 'PLAN_INCLUDED',
            'codex_cli/gpt-6-astra': 'UNKNOWN_COST',
            'nvidia/*': 'OWNER_REPORTED_FREE',
        },
        'authorized_models': ['codex_cli/gpt-5.6-luna', 'codex_cli/gpt-5.6-sol',
                              'codex_cli/gpt-5.6-terra', 'nvidia/*'],
        'authorized_roles': ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER'],
        'max_repair_attempts': 1,
    }
    document.update(updates)
    return WorkforcePolicy(document)


def _agent(provider, model, role=RoleName.BUILDER):
    return AgentProfile('agent', 'Worker', provider, model, role=role, capabilities=['model.text'])


def test_workforce_policy_distinguishes_resource_and_identity_layers():
    policy = _policy()
    info = ProviderInfo('codex_cli', 'Codex', 'test', Availability.AVAILABLE,
                        models=['gpt-5.6-sol'], authenticated=True, quota_available=True)
    allowed = policy.authorize(_agent('codex_cli', 'gpt-5.6-sol'), info, model_available=True)
    assert allowed.allowed and allowed.resource_class is ResourceClass.PLAN_INCLUDED
    assert allowed.provider_id == 'codex_cli' and allowed.model_id == 'gpt-5.6-sol'
    assert allowed.agent_id == 'agent' and allowed.role == 'BUILDER'

    for resource_class in ('PAID', 'UNKNOWN_COST', 'UNAVAILABLE'):
        denied = _policy(resource_classes={'codex_cli/gpt-5.6-sol': resource_class}).authorize(
            _agent('codex_cli', 'gpt-5.6-sol'), info, model_available=True)
        assert not denied.allowed
        assert denied.code in {'PAID_NOT_AUTHORIZED', 'UNKNOWN_COST', 'RESOURCE_UNAVAILABLE'}
    print('LAB_LEVEL4_POLICY_OK')


def test_workforce_policy_rejects_unhealthy_unlisted_role_and_silent_paid_fallback():
    info = ProviderInfo('codex_cli', 'Codex', 'test', Availability.QUOTA_EXHAUSTED,
                        models=['gpt-5.6-sol'], authenticated=True, quota_available=False)
    denied = _policy().authorize(_agent('codex_cli', 'gpt-5.6-sol'), info, model_available=False)
    assert not denied.allowed and denied.code == 'RESOURCE_UNAVAILABLE'
    denied = _policy(authorized_roles=['REVIEWER']).authorize(
        _agent('codex_cli', 'gpt-5.6-sol'), ProviderInfo('codex_cli', 'Codex', 'test', Availability.AVAILABLE),
        model_available=True)
    assert not denied.allowed and denied.code == 'ROLE_NOT_AUTHORIZED'
    assert _policy().choose_fallback([denied]) is None
    print('LAB_LEVEL4_POLICY_OK')


@pytest.mark.asyncio
async def test_background_continues_persisted_mission_without_ui_message(monkeypatch):
    from core.lab_v1.service import LabV1Service
    service = LabV1Service()
    calls = []
    loop = asyncio.get_running_loop()
    twice = asyncio.Event()

    def tick():
        calls.append('tick')
        if len(calls) >= 2:
            loop.call_soon_threadsafe(twice.set)

    service._supervisor = SimpleNamespace(
        policy=lambda: {'mission_entry_enabled': True, 'background_enabled': True, 'cadence_seconds': 1},
        tick=tick)
    monkeypatch.setattr(service, '_background_interval', 0.01, raising=False)
    result = await service.start_background()
    assert result['success'] is True
    await asyncio.wait_for(twice.wait(), timeout=1.0)
    await service.stop_background()
    assert len(calls) >= 2
    print('LAB_LEVEL4_BACKGROUND_OK')


def test_restart_does_not_replay_uncertain_effect(tmp_path):
    from core.lab_v1.domain import AgentProfile, Session, Task, Team, TeamMembership
    from core.lab_v1.execution_scope import ExecutionScope
    from core.lab_v1.mission_controller import MissionController, MissionStep
    from core.lab_v1.store import LabStore
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    store.save_team(Team('team', 'Team'))
    store.save_agent(_agent('fake', 'fake'))
    store.save_membership(TeamMembership('membership', 'team', 'agent'))
    store.save_session(Session('session', 'team', 'objective'))
    store.save_task(Task('task', 'session', 'write', 'write once', 'agent', assigned_agent_id='agent', acceptance='receipt'))
    controller = MissionController(store)
    controller.plan('session', [MissionStep('write', 'task', 'ACTION', capability='files.write', resources=(str(tmp_path),))],
                    scope=ExecutionScope((str(tmp_path),), ('files.write',), authorization_state='POLICY_AUTHORIZED'))
    with store._connect() as conn:
        doc = json.loads(conn.execute('SELECT document FROM mission_controls WHERE session_id=?', ('session',)).fetchone()[0])
        doc['steps'][0]['status'] = 'RECONCILE'
        doc['state'] = 'BLOCKED'; doc['blocker'] = 'UNCERTAIN_EFFECT'
        conn.execute('UPDATE mission_controls SET document=?,lease_token=NULL,lease_until=0 WHERE session_id=?',
                     (json.dumps(doc), 'session'))
    restarted = MissionController(LabStore(tmp_path / 'lab.db'))
    class Ports:
        def execute(self, _): raise AssertionError('uncertain action replayed')
        def verify(self, *_): raise AssertionError('uncertain action verified without reconciliation')
    state = restarted.tick('session', Ports())
    assert state['state'] == 'BLOCKED' and state['blocker'] == 'UNCERTAIN_EFFECT'
    print('LAB_LEVEL4_RESTART_OK')
