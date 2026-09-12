"""Offline controller proofs with a controlled clock and isolated V1 storage."""
import json
import sqlite3
from dataclasses import replace

import pytest

from core.lab_v1.domain import AgentProfile, Session, Team, TeamMembership, Task
from core.lab_v1.mission_controller import (
    MissionController, MissionLimits, MissionStep, Receipt, Verification, LeaseLost, ExecutionScope,
)
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore


class Clock:
    value = 1000.0

    def __call__(self):
        return self.value


class Ports:
    def __init__(self):
        self.executed = []
        self.verified = []
        self.verdict = 'PASS'

    def execute(self, dispatch):
        self.executed.append(dispatch)
        return Receipt('artifact:' + dispatch.attempt_id, 'Verified candidate')

    def verify(self, dispatch, receipt):
        self.verified.append((dispatch, receipt))
        return Verification(self.verdict, 'evidence:test-result')


@pytest.fixture
def world(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('team', 'Test Team'))
    store.save_agent(AgentProfile('agent', 'Worker', 'fake', 'fake'))
    store.save_membership(TeamMembership('member', 'team', 'agent'))
    store.save_session(Session('session', 'team', 'Fix a small module in sandbox'))
    for task_id in ('task1', 'task2'):
        store.save_task(Task(task_id, 'session', 'Small fix', 'Apply only the requested patch',
                            'agent', assigned_agent_id='agent', acceptance='Before fails; after passes'))
    clock, ports = Clock(), Ports()
    controller = MissionController(store, clock=clock)
    return store, controller, clock, ports


SCOPE = ExecutionScope(("provider:fake/fake",), ("model.invoke", "sandbox.write"),
                       authorization_state="POLICY_AUTHORIZED", authorization_ref="test-policy")


def step(id, task, kind, dependencies=()):
    return MissionStep(id, task, kind, dependencies,
                       "sandbox.write" if kind == "ACTION" else "model.invoke", ("provider:fake/fake",))


def plan(controller, limits=None):
    return controller.plan('session', [step('one', 'task1', 'INVOKE'),
                                      step('two', 'task2', 'ACTION', ('one',))], limits, scope=SCOPE)


def test_restart_between_result_and_verification_never_reexecutes(world):
    store, ctl, clock, ports = world
    plan(ctl)
    assert ctl.tick('session', ports)['state'] == 'VERIFYING'
    assert store.get_task('task1').state.value == 'RUNNING'
    ctl = MissionController(LabStore(store.db_path), clock=clock)
    assert ctl.tick('session', ports)['state'] == 'RUNNING'
    assert len(ports.executed) == 1
    ctl.tick('session', ports)
    assert ctl.tick('session', ports)['state'] == 'COMPLETED'
    ctl.tick('session', ports)
    assert len(ports.executed) == 2 and len(ports.verified) == 2
    assert store.get_session('session').state.value == 'COMPLETED'
    assert store.get_task('task2').result == 'Verified candidate'


def test_success_receipt_does_not_complete_mission(world):
    store, ctl, _, ports = world
    plan(ctl)
    ctl.tick('session', ports)
    assert store.get_session('session').state.value != 'COMPLETED'
    ports.verdict = 'FAIL'
    doc = ctl.tick('session', ports)
    assert doc['state'] == 'BLOCKED' and doc['blocker'] == 'VERIFICATION_FAIL'
    assert store.get_task('task1').state.value != 'COMPLETED'


def test_inconclusive_verification_is_explicit(world):
    _, ctl, _, ports = world
    plan(ctl)
    ctl.tick('session', ports)
    ports.verdict = 'INCONCLUSIVE'
    assert ctl.tick('session', ports)['blocker'] == 'VERIFICATION_INCONCLUSIVE'


def test_crash_after_effect_requires_reconciliation(world):
    store, ctl, clock, ports = world
    plan(ctl)
    original = ports.execute

    def crash(dispatch):
        original(dispatch)
        raise SystemExit('simulated process loss after effect')

    ports.execute = crash
    with pytest.raises(SystemExit):
        ctl.tick('session', ports)
    ctl = MissionController(LabStore(store.db_path), clock=clock)
    assert ctl.tick('session', ports)['blocker'] == 'UNCERTAIN_EFFECT'
    assert len(ports.executed) == 1
    ctl.reconcile('session', 'one', verdict='APPLIED', evidence_ref='observed:artifact',
                  receipt=Receipt('artifact:saved', 'Recovered result'))
    assert ctl.snapshot('session')['state'] == 'VERIFYING'
    ctl.tick('session', ports)
    assert len(ports.executed) == 1 and store.get_task('task1').result == 'Recovered result'


def test_safe_retry_requires_not_applied_evidence_and_counts_globally(world):
    _, ctl, _, ports = world
    plan(ctl)
    ports.execute = lambda dispatch: (_ for _ in ()).throw(OSError('timeout'))
    assert ctl.tick('session', ports)['blocker'] == 'UNCERTAIN_EFFECT'
    ctl.reconcile('session', 'one', verdict='UNKNOWN', evidence_ref='no-conclusion')
    assert ctl.snapshot('session')['state'] == 'BLOCKED'
    ctl.reconcile('session', 'one', verdict='NOT_APPLIED', evidence_ref='observed:no-effect')
    ctl.tick('session', ports)
    ctl.reconcile('session', 'one', verdict='NOT_APPLIED', evidence_ref='observed:no-effect-again')
    doc = ctl.snapshot('session')
    assert doc['blocker'] == 'RETRY_LIMIT'
    assert doc['used']['turns'] == 2 and doc['used']['retries'] == 1


def test_another_controller_cannot_dispatch_during_live_lease(world):
    store, ctl, clock, ports = world
    plan(ctl)
    other = MissionController(LabStore(store.db_path), clock=clock)
    nested = Ports()
    original = ports.execute

    def contend(dispatch):
        assert other.tick('session', nested)['steps'][0]['status'] == 'DISPATCHED'
        assert nested.executed == []
        return original(dispatch)

    ports.execute = contend
    ctl.tick('session', ports)
    assert len(ports.executed) == 1


def test_expired_lease_fences_old_worker_result(world):
    store, ctl, clock, ports = world
    plan(ctl)
    other = MissionController(LabStore(store.db_path), clock=clock)
    original = ports.execute

    def expire(dispatch):
        receipt = original(dispatch)
        clock.value += 31
        assert other.tick('session', Ports())['blocker'] == 'UNCERTAIN_EFFECT'
        return receipt

    ports.execute = expire
    doc = ctl.tick('session', ports)
    assert doc['blocker'] == 'UNCERTAIN_EFFECT'
    assert doc['steps'][0]['receipt'] is None
    assert len(ports.executed) == 1


def test_lease_renewal_is_fenced(world):
    _, ctl, clock, _ = world
    plan(ctl)
    token = ctl._claim('session')
    clock.value += 20
    ctl.renew('session', token)
    clock.value += 31
    with pytest.raises(LeaseLost):
        ctl.renew('session', token)


@pytest.mark.parametrize('limits,blocker', [
    (MissionLimits(max_turns=0), 'BUDGET_LIMIT'),
    (MissionLimits(timeout_s=1), 'TIME_LIMIT'),
])
def test_limits_block_before_execution(world, limits, blocker):
    _, ctl, clock, ports = world
    plan(ctl, limits)
    clock.value += 2
    assert ctl.tick('session', ports)['blocker'] == blocker
    assert not ports.executed


def test_delegation_and_action_limits(world):
    _, ctl, _, ports = world
    ctl.plan('session', [step('one','task1','DELEGATE')], MissionLimits(max_delegations=0), scope=SCOPE)
    assert ctl.tick('session', ports)['blocker'] == 'BUDGET_LIMIT'
    assert not ports.executed


def test_cancel_before_dispatch_and_between_steps(world):
    _, ctl, _, ports = world
    plan(ctl)
    ctl.cancel('session')
    assert ctl.tick('session', ports)['state'] == 'CANCELLED'
    assert not ports.executed


def test_cancel_inflight_preserves_receipt_and_stops_next_action(world):
    _, ctl, _, ports = world
    plan(ctl)
    original = ports.execute

    def cancel(dispatch):
        ctl.cancel('session')
        return original(dispatch)

    ports.execute = cancel
    ctl.tick('session', ports)
    assert ctl.tick('session', ports)['state'] == 'CANCELLED'
    assert ctl.snapshot('session')['steps'][0]['receipt']
    assert len(ports.executed) == 1


def test_cancel_uncertain_effect_still_needs_reconciliation(world):
    _, ctl, _, ports = world
    plan(ctl)
    ports.execute = lambda _: (_ for _ in ()).throw(OSError())
    ctl.tick('session', ports)
    ctl.cancel('session')
    assert ctl.tick('session', ports)['blocker'] == 'UNCERTAIN_EFFECT'
    ctl.reconcile('session', 'one', verdict='NOT_APPLIED', evidence_ref='observed:no-effect')
    assert ctl.snapshot('session')['state'] == 'CANCELLED'


def test_plan_revision_preserves_history_and_cannot_reset_budget(world):
    store, ctl, _, ports = world
    plan(ctl)
    assert plan(ctl)['plan_version'] == 2
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute('SELECT count(*) FROM mission_plans').fetchone()[0] == 2
    ctl.tick('session', ports)
    with pytest.raises(ValueError):
        plan(ctl)


@pytest.mark.parametrize('steps', [
    [MissionStep('one','task1','ACTION',('two',)), MissionStep('two','task2','ACTION')],
    [MissionStep('one','task1','ACTION'), MissionStep('one','task2','ACTION')],
    [MissionStep('one','unknown','ACTION')],
    [MissionStep('one','task1','SHELL')],
])
def test_invalid_plans_are_rejected(world, steps):
    _, ctl, _, _ = world
    with pytest.raises(ValueError):
        ctl.plan('session', steps, scope=SCOPE)


def test_archived_agent_blocks_without_call(world):
    store, ctl, _, ports = world
    plan(ctl)
    agent = store.get_agent('agent')
    agent.archived = True
    store.save_agent(agent)
    assert ctl.tick('session', ports)['blocker'] == 'AGENT_UNAVAILABLE'
    assert not ports.executed


def test_v1_submission_cannot_bypass_controller(world, tmp_path):
    store, ctl, _, _ = world
    plan(ctl)
    runtime = LabRuntime(store, ProviderRegistry(tmp_path / 'health.json'))
    assert runtime.submit('session', 'go')['code'] == 'MISSION_CONTROLLED'
    assert store.list_runs('session') == []
    assert runtime.snapshot('session')['session']['mission']['plan_version'] == 1


def test_additive_migration_preserves_v1_fixture_and_is_idempotent(tmp_path):
    path = tmp_path / 'v1.db'
    store = LabStore(path)
    store.initialize()
    store.save_team(Team('team', 'Legacy'))
    store.save_session(Session('session', 'team', 'Legacy objective'))
    with sqlite3.connect(path) as conn:
        before = {name: conn.execute('SELECT * FROM ' + name).fetchall()
                  for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    assert store.mission_snapshot('session') is None
    MissionController(store)
    MissionController(LabStore(path))
    with sqlite3.connect(path) as conn:
        for name, rows in before.items():
            if name != 'schema_meta':
                assert conn.execute('SELECT * FROM ' + name).fetchall() == rows
        assert conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == '1'
    assert store.get_session('session').objective == 'Legacy objective'


@pytest.mark.parametrize('phase', ['execute', 'verify'])
def test_late_results_preserve_evidence_never_complete(world, phase):
    store, ctl, clock, ports = world
    ctl.plan('session', [step('one', 'task1', 'INVOKE')], MissionLimits(timeout_s=5), scope=SCOPE)
    if phase == 'verify':
        ctl.tick('session', ports)
    original = getattr(ports, phase)

    def late(*args):
        result = original(*args)
        clock.value += 5
        return result

    setattr(ports, phase, late)
    doc = ctl.tick('session', ports)
    assert doc['state'] == 'BLOCKED'
    assert doc['blocker'] == ('LATE_EXECUTION' if phase == 'execute' else 'LATE_VERIFICATION')
    assert doc['steps'][0]['receipt']
    assert store.get_task('task1').state.value != 'COMPLETED'
    assert ctl.observations('session')
    if phase == 'execute':
        ctl.reconcile('session', 'one', verdict='APPLIED', evidence_ref='observed',
                      receipt=Receipt(**doc['steps'][0]['receipt']))
        assert ctl.tick('session', ports)['blocker'] == 'TIME_LIMIT'
        assert len(ports.executed) == 1


def test_stale_receipt_is_evidence_only(world):
    _, ctl, clock, ports = world
    plan(ctl)
    original = ports.execute

    def late(dispatch):
        clock.value += 31
        return original(dispatch)

    ports.execute = late
    doc = ctl.tick('session', ports)
    assert doc['steps'][0]['receipt'] is None
    assert json.loads(ctl.observations('session')[0]['document'])['artifact_ref']
    assert ctl.tick('session', ports)['blocker'] == 'UNCERTAIN_EFFECT'
    assert len(ports.executed) == 1


@pytest.mark.parametrize('scope,requested', [
    (SCOPE, replace(step('one', 'task1', 'INVOKE'), resources=('provider:other/model',))),
    (SCOPE, replace(step('one', 'task1', 'INVOKE'), capability='shell.unrestricted')),
    (SCOPE, replace(step('one', 'task1', 'INVOKE'), resources=())),
    (replace(SCOPE, authorization_state='DENIED'), step('one', 'task1', 'INVOKE')),
    (replace(SCOPE, risk='HIGH'), replace(step('one', 'task1', 'INVOKE'), risk='HIGH')),
    (replace(SCOPE, forbidden_capabilities=('model.invoke',)), step('one', 'task1', 'INVOKE')),
])
def test_reject_scope_before_executor_and_budget(world, scope, requested):
    _, ctl, _, ports = world
    ctl.plan('session', [requested], scope=scope)
    doc = ctl.tick('session', ports)
    assert doc['blocker'] == 'SCOPE_REJECTED'
    assert not any(doc['used'].values()) and not ports.executed


def test_canonical_scope_blocks_sibling_and_parent_escape(tmp_path):
    from core.lab_v1.execution_scope import ScopeViolation
    scope = replace(SCOPE, allowed_resources=(str(tmp_path / 'sandbox'),))
    scope.require('sandbox.write', (str(tmp_path / 'sandbox' / 'allowed.txt'),), 'LOW')
    for path in (tmp_path / 'sandbox-evil' / 'file', tmp_path / 'sandbox' / '..' / 'escape'):
        with pytest.raises(ScopeViolation):
            scope.require('sandbox.write', (str(path),), 'LOW')


def test_high_risk_requires_explicit_owner_authorization(world):
    _, ctl, _, ports = world
    scope = replace(SCOPE, risk='HIGH', authorization_state='OWNER_AUTHORIZED', authorization_ref='owner:decision1')
    ctl.plan('session', [replace(step('one', 'task1', 'INVOKE'), risk='HIGH')], scope=scope)
    assert ctl.tick('session', ports)['state'] == 'VERIFYING'


def test_atomic_v1_claim_prevents_adoption_before_session_state_changes(world, tmp_path):
    store, ctl, _, _ = world
    runtime = LabRuntime(store, ProviderRegistry(tmp_path / 'health.json'))

    def turn(session_id, text):
        assert store.get_session(session_id).state.value == 'QUEUED'
        with pytest.raises(ValueError, match='belongs to V1'):
            plan(ctl)
        other = LabRuntime(LabStore(store.db_path), ProviderRegistry(tmp_path / 'other.json'))
        assert other.submit(session_id, text)['code'] == 'BUSY'
        return {'success': True}

    runtime._submit_turn = turn
    assert runtime.submit('session', 'go')['success']
    assert store.mission_snapshot('session') is None
    # A previously used V1 session is never silently adopted even while idle.
    with pytest.raises(ValueError, match='belongs to V1'):
        plan(ctl)


def test_second_mission_rejected_until_first_safely_finishes(world):
    store, ctl, _, ports = world
    plan(ctl)
    store.save_session(Session('second', 'team', 'Another mission'))
    store.save_task(Task('task3', 'second', 'Test', 'Test', 'agent', assigned_agent_id='agent', acceptance='Verified'))
    with pytest.raises(ValueError, match='Another mission'):
        ctl.plan('second', [step('three', 'task3', 'INVOKE')], scope=SCOPE)
    ports.execute = lambda _: (_ for _ in ()).throw(OSError())
    ctl.tick('session', ports)
    ctl.cancel('session')
    with pytest.raises(ValueError, match='Another mission'):
        ctl.plan('second', [step('three', 'task3', 'INVOKE')], scope=SCOPE)
    ctl.reconcile('session', 'one', verdict='NOT_APPLIED', evidence_ref='no-effect')
    assert ctl.plan('second', [step('three', 'task3', 'INVOKE')], scope=SCOPE)['state'] == 'QUEUED'
