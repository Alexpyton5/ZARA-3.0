import hashlib
import json
from dataclasses import replace

import pytest

from core.lab_v1.domain import AgentProfile, Session, Task, Team, TeamMembership
from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation
from core.lab_v1.hermes_executor import ActionRequest, HermesActionPorts
from core.lab_v1.mission_controller import MissionController, MissionStep
from core.lab_v1.store import LabStore


class FakeFiles:
    def __init__(self):
        self.calls = []
        self.lie = False

    def execute(self, request, deadline):
        from pathlib import Path
        self.calls.append(request)
        if not self.lie:
            path = Path(request.arguments['path'])
            if request.capability == 'files.write':
                path.write_bytes(request.arguments['content'].encode('utf-8'))
            else:
                path.unlink()
        return {'success': True, 'data': {'executor': 'fake'}}


@pytest.fixture
def action_world(tmp_path):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('team', 'Test'))
    store.save_agent(AgentProfile('agent', 'Worker', 'fake', 'fake'))
    store.save_membership(TeamMembership('member', 'team', 'agent'))
    store.save_session(Session('mission', 'team', 'Create and verify a sandbox file'))
    for name in ('write', 'rollback'):
        store.save_task(Task(name, 'mission', name, name, 'agent', assigned_agent_id='agent', acceptance='Exact result'))
    scope = ExecutionScope((str(sandbox),), ('files.write', 'files.delete'),
                           authorization_state='POLICY_AUTHORIZED', authorization_ref='sandbox-policy')
    ctl, executor = MissionController(store), FakeFiles()
    ports = HermesActionPorts(store, executor)
    path = str(sandbox / 'proof.txt')
    request = ActionRequest('action', 'mission', 'write', 'agent', 'Write proof', 'files.write',
                            {'path': path, 'content': 'ZARA_HERMES_OK'}, scope, 'LOW',
                            scope.authorization_state, 'Exact bytes', 'SHA256 equality', 'Delete created file')
    return store, ctl, ports, executor, request


def start(world, request=None, rollback=False):
    store, ctl, ports, executor, original = world
    request = request or original
    ports.prepare(request)
    steps = [MissionStep('write', 'write', 'ACTION', capability='files.write', resources=(request.arguments['path'],))]
    if rollback:
        digest = hashlib.sha256(request.arguments['content'].encode()).hexdigest()
        ports.prepare(replace(request, action_id='rollback', task_id='rollback', capability='files.delete',
                              arguments={'path': request.arguments['path'], 'before_sha256': digest},
                              expected_result='File absent'))
        steps.append(MissionStep('rollback', 'rollback', 'ACTION', ('write',), 'files.delete', (request.arguments['path'],)))
    ctl.plan('mission', steps, scope=request.execution_scope)


def test_receipt_then_independent_verify_and_owned_rollback(action_world):
    store, ctl, ports, executor, request = action_world
    start(action_world, rollback=True)
    assert ctl.tick('mission', ports)['state'] == 'VERIFYING'
    assert store.get_task('write').state.value != 'COMPLETED'
    assert ctl.tick('mission', ports)['state'] == 'RUNNING'
    ctl.tick('mission', ports)
    assert ctl.tick('mission', ports)['state'] == 'COMPLETED'
    assert len(executor.calls) == 2
    assert store.get_task('rollback').state.value == 'COMPLETED'
    with store._connect() as conn:
        results = [json.loads(r[0]) for r in conn.execute('SELECT document FROM mission_action_results')]
    assert all(r['verification_status'] == 'PASS' for r in results)


def test_executor_success_without_effect_fails_verification(action_world):
    _, ctl, ports, executor, _ = action_world
    executor.lie = True
    start(action_world)
    ctl.tick('mission', ports)
    assert ctl.tick('mission', ports)['blocker'] == 'VERIFICATION_FAIL'


def test_restart_verifies_without_replaying_file_write(action_world):
    store, ctl, ports, executor, _ = action_world
    start(action_world)
    ctl.tick('mission', ports)
    ctl = MissionController(LabStore(store.db_path))
    ports = HermesActionPorts(ctl.store, executor)
    assert ctl.tick('mission', ports)['state'] == 'COMPLETED'
    assert len(executor.calls) == 1


@pytest.mark.parametrize('mutation', ['author', 'scope', 'resource', 'arguments'])
def test_mutated_request_cannot_reach_tool(action_world, mutation):
    store, ctl, ports, executor, request = action_world
    start(action_world)
    with store._connect() as conn:
        data = json.loads(conn.execute('SELECT document FROM mission_action_requests').fetchone()[0])
        if mutation == 'author':
            data['requested_by'] = 'another-agent'
        elif mutation == 'scope':
            data['execution_scope']['authorization_ref'] = 'forged'
        elif mutation == 'resource':
            data['arguments']['path'] += '.outside'
        else:
            data['arguments']['command'] = 'echo forbidden'
        conn.execute('UPDATE mission_action_requests SET document=?', (json.dumps(data),))
    assert ctl.tick('mission', ports)['state'] == 'BLOCKED'
    assert not executor.calls


def test_changed_file_rejected_before_tool(action_world):
    from pathlib import Path
    _, ctl, ports, executor, request = action_world
    start(action_world)
    Path(request.arguments['path']).write_text('Unrelated contents')
    assert ctl.tick('mission', ports)['state'] == 'BLOCKED'
    assert not executor.calls
