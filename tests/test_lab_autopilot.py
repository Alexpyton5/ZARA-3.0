import json
import shutil
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, Team, TeamMembership)
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.claude_cli import ClaudeCliAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.router import TaskRouter
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


class TextAdapter(ProviderAdapter):
    """Unit-only deterministic adapter; it is not runtime/provider evidence."""
    controlled_text_only = True
    def __init__(self, name):
        self.id = self.label = name
        self.calls = []
        self.failure = False
        self.invalid = False
        self.fenced = False

    def probe(self):
        return ProviderInfo(self.id, self.label, 'test', Availability.AVAILABLE, models=['test'])

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            return ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='quota')
        text = json.dumps({'mission': 'Document', 'plan_version': 1, 'tasks': [
            {'id': 'document', 'title': 'Document', 'instruction': 'Create the requested short document',
             'role': 'BUILDER', 'capability': 'artifact.text', 'path': 'result.md',
             'risk': 'LOW', 'repair_budget': 1, 'depends_on': [],
             'acceptance': {'method': 'constraints', 'min_chars': 10, 'max_chars': 100,
                            'required_sections': []}}]})
        if 'Implement only' in kwargs.get('system', ''):
            text = 'ZARA_AUTOPILOT_OK'
        if self.invalid:
            text = 'invalid plan'
        if self.fenced:
            text = '```json\n' + text + '\n```'
        return ProviderResult(True, text=text, availability=Availability.AVAILABLE, model_reported=kwargs['model'],
                              input_tokens=10, output_tokens=20, duration_ms=1, provider_session_id='fake-request')


class Files:
    def __init__(self, sandbox):
        self.sandbox = sandbox

    def execute(self, request, deadline):
        Path(request.path).write_bytes(request.content.encode('utf-8'))
        return {'success': True, 'data': {'executor': 'test'}}


@pytest.fixture
def engine(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    for name in ('primary', 'fallback'):
        registry.register(TextAdapter(name))
        registry.record_result(name, 'test', ProviderResult(True, availability=Availability.AVAILABLE))
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Auto Test'))
    for name, provider, role in (('lead', 'primary', RoleName.CEO), ('worker', 'fallback', RoleName.BUILDER),
                                 ('spare', 'fallback', RoleName.CEO)):
        store.save_agent(AgentProfile(name, name, provider, 'test', role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership('member:' + name, 'team', name))
    policy = WorkforcePolicy({'mission_entry_enabled': True, 'background_enabled': True,
        'authorized_providers': ['primary', 'fallback'],
        'resource_classes': {'primary/*': 'OWNER_REPORTED_FREE', 'fallback/*': 'OWNER_REPORTED_FREE'},
        'authorized_models': ['primary/*', 'fallback/*'],
        'authorized_roles': ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER']})
    return Autopilot(runtime, root=tmp_path / 'missions', executor_factory=Files, policy=policy)


@pytest.mark.skipif(shutil.which('claude') is None,
                    reason='claude CLI absent: provider availability cannot be asserted honestly here')
def test_workforce_selects_a_real_claude_cli_agent_after_owner_reauthorization(tmp_path):
    """The four gates that used to refuse `claude_cli`, checked together.

    Uses the real ClaudeCliAdapter and the real default policy, but never calls
    `complete()` — `probe()` is a local `which` lookup and spends nothing. What
    is asserted is only that the selection layer now admits the provider:
    the paid proof that it *answers* is the acceptance Run, not a test.
    """
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(ClaudeCliAdapter())
    # Gate 1: registered unwrapped, not behind OwnerDisabledAdapter.
    assert type(registry.get('claude_cli')) is ClaudeCliAdapter
    # Gate 2: text-only, which autopilot/router/fleet all require.
    assert registry.get('claude_cli').controlled_text_only is True

    registry.record_result('claude_cli', 'sonnet',
                           ProviderResult(True, availability=Availability.AVAILABLE))
    registry.record_result('claude_cli', 'opus',
                           ProviderResult(True, availability=Availability.AVAILABLE))
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Claude Reauth'))
    for name, model, role in (('artemis', 'opus', RoleName.CEO), ('vulcan', 'sonnet', RoleName.BUILDER)):
        # Gate 4: the AgentInstance carries model.text.
        store.save_agent(AgentProfile(name, name, 'claude_cli', model, role=role,
                                      capabilities=['model.text']))
        store.save_membership(TeamMembership('member:' + name, 'team', name))

    # Gate 3: the default document (no overrides) authorizes them.
    autopilot = Autopilot(runtime, root=tmp_path / 'missions', executor_factory=Files,
                          policy=WorkforcePolicy(WorkforcePolicy.default_document()))
    chosen = autopilot.candidates('team')
    assert {a.id for a in chosen} == {'artemis', 'vulcan'}
    assert all(autopilot._decision(a, team_id='team').code == 'AUTHORIZED' for a in chosen)
    assert all(autopilot._decision(a, team_id='team').resource_class.value == 'PLAN_INCLUDED'
               for a in chosen)

    # Role decides the occupant; the model is profile data, not the routing key.
    for task_type, expected in (('implementation', ('vulcan', 'sonnet')), ('planning', ('artemis', 'opus'))):
        selection = TaskRouter(runtime).select('team', task_type)
        assert (selection.agent_id, selection.model) == expected
        assert selection.provider_id == 'claude_cli'


def test_worker_selection_probes_only_resources_assigned_to_that_team(tmp_path):
    class UnexpectedAdapter(TextAdapter):
        def probe(self):
            raise AssertionError('unrelated provider must not be probed for worker selection')

    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(TextAdapter('chosen'))
    registry.register(UnexpectedAdapter('unrelated'))
    registry.record_result('chosen', 'test', ProviderResult(True, availability=Availability.AVAILABLE))
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Focused selection'))
    worker = AgentProfile('worker', 'Worker', 'chosen', 'test', RoleName.BUILDER,
                          capabilities=['model.text'])
    store.save_agent(worker)
    store.save_membership(TeamMembership('membership', 'team', worker.id))
    policy = WorkforcePolicy({
        'authorized_providers': ['chosen'], 'authorized_models': ['chosen/*'],
        'authorized_roles': ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER'],
        'resource_classes': {'chosen/*': 'OWNER_REPORTED_FREE'},
    })
    autopilot = Autopilot(runtime, root=tmp_path / 'missions', executor_factory=Files, policy=policy)

    assert autopilot.candidates('team') == [worker]
    assert autopilot._decision(worker, team_id='team').allowed


def test_one_intent_routes_delegates_executes_verifies_and_reports(engine):
    started = engine.start('Create a document with ZARA_AUTOPILOT_OK')
    sid = started['session_id']
    result = engine.run(sid)
    assert result['state'] == 'COMPLETED'
    metrics = result['autonomy']
    assert metrics['owner_touches'] == 1
    assert all(metrics[k] for k in ('agent_selection_automatic', 'task_creation_automatic',
                                    'delegation_automatic', 'context_transfer_automatic',
                                    'verification_automatic', 'final_report_automatic'))
    assert Path(metrics['target']).read_text() == 'ZARA_AUTOPILOT_OK'
    runs = engine.store.list_runs(sid)
    assert len(runs) == 2 and len({r.agent_id for r in runs}) == 2
    assert all(r.model_reported == 'test' for r in runs)
    assert all(r.cost_usd is None and r.cost_basis.value == 'UNKNOWN' for r in runs)
    artifacts = engine.store.list_artifacts(sid)
    responses = {a.id: a for a in artifacts if a.kind == 'MODEL_TEXT'}
    bindings = [json.loads(a.body) for a in artifacts if a.kind == 'MODEL_RESPONSE_BINDING']
    assert len(bindings) == len(responses) == len(runs)
    for binding in bindings:
        response = responses[binding['artifact_id']]
        bound_run = engine.store.get_run(binding['run_id'])
        assert binding['session_id'] == sid == bound_run.session_id
        assert binding['task_id'] == response.task_id == bound_run.task_id
        assert binding['attempt_id'] == response.id.removeprefix('response:')
        assert binding['artifact_sha256'] == __import__('hashlib').sha256(
            response.body.encode('utf-8')).hexdigest()
    assert not engine.store.list_capability_gaps(sid)
    assert engine.runtime.submit(sid, 'Cannot bypass')['code'] == 'MISSION_CONTROLLED'
    assert len([m for m in engine.store.list_messages(sid) if m.kind.value == 'ZARA']) == 1
    engine.run(sid)
    assert len(engine.store.list_runs(sid)) == 2
    assert len([m for m in engine.store.list_messages(sid) if m.kind.value == 'ZARA']) == 1


def test_quota_failover_retains_session_and_uses_bounded_handoff(engine):
    engine.runtime.registry.get('primary').failure = True
    sid = engine.start('Create document')['session_id']
    result = engine.run(sid)
    assert result['state'] == 'COMPLETED'
    assert result['autonomy']['recovery_automatic'] is True
    runs = engine.store.list_runs(sid)
    assert len(runs) == 3 and runs[0].state.value == 'FAILED'
    assert len([h for h in engine.store.list_handoffs(sid) if h.reason.startswith('PROVIDER_')]) == 1
    assert result['mission']['used']['retries'] == 1
    assert result['autonomy']['owner_touches'] == 1


def test_invalid_lead_result_stops_without_worker_or_file(engine):
    engine.runtime.registry.get('primary').invalid = True
    sid = engine.start('Document')['session_id']
    result = engine.run(sid)
    assert result['state'] == 'BLOCKED_NEEDS_OWNER'
    assert result['mission']['blocker'] == 'REPAIR_LIMIT'
    assert len(engine.store.list_runs(sid)) == 2
    assert not (Path(result['autonomy']['sandbox']) / 'result.md').exists()
    with engine.store._connect() as conn:
        assert conn.execute('SELECT count(*) FROM autonomy_gaps').fetchone()[0] >= 1


def test_busy_request_and_cancel_do_not_call_models(engine):
    sid = engine.start('First')['session_id']
    busy = engine.start('Second')
    assert busy['code'] == 'MISSION_BUSY'
    assert busy['error'] == 'Outra missão solicitada por você ainda está em andamento.'
    engine.controller.cancel(sid)
    assert engine.run(sid)['state'] == 'CANCELLED'
    assert not engine.store.list_runs(sid)


def test_stale_provider_block_is_superseded_for_next_owner_mission(engine):
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['state'] = 'BLOCKED'
        doc['liveness_state'] = 'BLOCKED'
        doc['blocker'] = 'PROVIDER_PROVIDER_NOT_AUTHORIZED'
        doc['reason'] = doc['blocker']
        doc['steps'][0]['status'] = 'PROVIDER_FAILED'
        conn.execute("UPDATE tasks SET state='RUNNING' WHERE id=?", (doc['steps'][0]['task_id'],))
        engine.controller._save(conn, doc, 'test.provider_blocked')
        conn.execute('UPDATE mission_controls SET lease_token=NULL, lease_until=0, lease_owner=NULL WHERE session_id=?', (sid,))

    owner = engine.start('Second')
    assert owner['success'] is True and owner['state'] == 'QUEUED'
    assert engine.controller.snapshot(sid)['state'] == 'CANCELLED'
    assert engine.store.get_task(sid + ':plan').state.value == 'FAILED'
    with engine.store._connect() as conn:
        event = conn.execute("SELECT type FROM events WHERE session_id=? AND type='mission.superseded_stale_provider_block'", (sid,)).fetchone()
    assert event is not None


def test_provider_quota_wait_with_expired_lease_still_blocks_next_mission(engine):
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['state'] = 'WAITING_RESOURCE'
        doc['liveness_state'] = 'WAITING_RESOURCE'
        doc['blocker'] = 'PROVIDER_QUOTA_EXHAUSTED'
        doc['reason'] = doc['blocker']
        doc['steps'][0]['status'] = 'PROVIDER_FAILED'
        engine.controller._save(conn, doc, 'test.provider_quota_wait')
        conn.execute('UPDATE mission_controls SET lease_token=NULL, lease_until=0, lease_owner=NULL WHERE session_id=?', (sid,))

    busy = engine.start('Second')
    assert busy['success'] is False and busy['code'] == 'MISSION_BUSY'
    assert engine.controller.snapshot(sid)['state'] == 'WAITING_RESOURCE'


def test_quota_wait_count_limit_is_persisted_terminal_and_does_not_block_owner(engine):
    """A finite quota budget must end without another provider call or owner lockout."""
    from core.lab_v1.autopilot import _AutopilotPorts

    clock = [1_000.0]
    engine.controller.clock = lambda: clock[0]
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['limits'].update(max_quota_waits=2, max_quota_wait_s=7_200)
        engine.controller._save(conn, doc, 'test.quota_wait_limit')

    engine.runtime.registry.get('primary').failure = True
    ports = _AutopilotPorts(engine, sid, engine.metrics(sid))
    first = engine.controller.tick(sid, ports)
    failed = first['steps'][0]
    assert first['state'] == 'WAITING_RESOURCE'
    assert failed['quota_waits'] == 1
    assert failed['quota_wait_started_at'] == 1_000.0
    assert failed['quota_wait_deadline'] == 8_200.0

    clock[0] = failed['retry_at']
    assert engine.controller.resume_due_resource(sid) is True
    limited = engine.controller.tick(sid, ports)
    assert limited['state'] == 'FAILED'
    assert limited['liveness_state'] == 'FAILED'
    assert limited['blocker'] == 'QUOTA_WAIT_LIMIT'
    assert limited['steps'][0]['quota_waits'] == 2

    calls_before = len(engine.runtime.registry.get('primary').calls)
    clock[0] += 99_999
    assert engine.controller.resume_due_resource(sid) is False
    assert engine.controller.tick(sid, ports)['state'] == 'FAILED'
    assert len(engine.runtime.registry.get('primary').calls) == calls_before
    assert engine.start('Second')['success'] is True


def test_quota_wait_time_limit_terminates_before_retry_call(engine):
    """The persisted quota deadline stops a due retry before it reaches a provider."""
    from core.lab_v1.autopilot import _AutopilotPorts

    clock = [2_000.0]
    engine.controller.clock = lambda: clock[0]
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['limits'].update(max_quota_waits=9, max_quota_wait_s=60)
        engine.controller._save(conn, doc, 'test.quota_wait_time_limit')

    engine.runtime.registry.get('primary').failure = True
    ports = _AutopilotPorts(engine, sid, engine.metrics(sid))
    waiting = engine.controller.tick(sid, ports)
    clock[0] = waiting['steps'][0]['retry_at']
    calls_before = len(engine.runtime.registry.get('primary').calls)

    assert engine.controller.resume_due_resource(sid) is False
    limited = engine.controller.snapshot(sid)
    assert limited['state'] == 'FAILED'
    assert limited['blocker'] == 'QUOTA_WAIT_LIMIT'
    assert engine.controller.tick(sid, ports)['state'] == 'FAILED'
    assert len(engine.runtime.registry.get('primary').calls) == calls_before


def test_provider_refusal_with_active_lease_still_blocks_next_mission(engine):
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['state'] = 'BLOCKED'
        doc['liveness_state'] = 'BLOCKED'
        doc['blocker'] = 'PROVIDER_PROVIDER_NOT_AUTHORIZED'
        doc['reason'] = doc['blocker']
        doc['steps'][0]['status'] = 'PROVIDER_FAILED'
        engine.controller._save(conn, doc, 'test.provider_blocked_with_lease')
        conn.execute('UPDATE mission_controls SET lease_token=?,lease_until=?,lease_owner=? WHERE session_id=?',
                     ('active', engine.controller.clock() + 60, 'worker', sid))

    busy = engine.start('Second')
    assert busy['success'] is False and busy['code'] == 'MISSION_BUSY'
    assert engine.controller.snapshot(sid)['state'] == 'BLOCKED'


def test_provider_refusal_preflight_does_not_mutate_before_atomic_plan(engine, monkeypatch):
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['state'] = 'BLOCKED'
        doc['liveness_state'] = 'BLOCKED'
        doc['blocker'] = 'PROVIDER_PROVIDER_NOT_AUTHORIZED'
        doc['reason'] = doc['blocker']
        doc['steps'][0]['status'] = 'PROVIDER_FAILED'
        conn.execute("UPDATE tasks SET state='RUNNING' WHERE id=?", (doc['steps'][0]['task_id'],))
        engine.controller._save(conn, doc, 'test.provider_blocked')
        conn.execute('UPDATE mission_controls SET lease_token=NULL, lease_until=0, lease_owner=NULL WHERE session_id=?', (sid,))

    def reject_plan(*args, **kwargs):
        raise ValueError('plan rejected')

    monkeypatch.setattr(engine.controller, 'plan', reject_plan)
    with pytest.raises(ValueError, match='plan rejected'):
        engine.start('Second')

    assert engine.controller.snapshot(sid)['state'] == 'BLOCKED'
    assert engine.store.get_task(sid + ':plan').state.value == 'RUNNING'


def test_uncertain_block_still_blocks_next_owner_mission(engine):
    sid = engine.start('First')['session_id']
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        doc['state'] = 'BLOCKED'
        doc['liveness_state'] = 'BLOCKED'
        doc['blocker'] = 'UNCERTAIN_EFFECT'
        doc['reason'] = doc['blocker']
        doc['steps'][0]['status'] = 'RECONCILE'
        engine.controller._save(conn, doc, 'test.uncertain_blocked')
        conn.execute('UPDATE mission_controls SET lease_token=NULL, lease_until=0, lease_owner=NULL WHERE session_id=?', (sid,))

    busy = engine.start('Second')
    assert busy['success'] is False and busy['code'] == 'MISSION_BUSY'


def test_owner_submission_retires_failed_daily_review_and_starts_immediately(engine):
    engine.runtime.registry.get('primary').invalid = True
    daily = engine.start('Internal review')['session_id']
    blocked = engine.run(daily)
    assert blocked['state'] == 'BLOCKED_NEEDS_OWNER'
    engine._metrics(daily, mission_kind='DAILY_OPPORTUNITY_REVIEW')
    calls_before = sum(len(engine.runtime.registry.get(name).calls) for name in ('primary', 'fallback'))
    owner = engine.start('Owner mission')
    assert owner['success'] is True and owner['state'] == 'QUEUED'
    assert engine.controller.snapshot(daily)['state'] == 'FAILED'
    assert engine.metrics(daily)['owner_priority_applied'] is True
    assert sum(len(engine.runtime.registry.get(name).calls) for name in ('primary', 'fallback')) == calls_before


def test_failed_daily_review_is_terminal_and_cannot_block_next_day(engine):
    engine.runtime.registry.get('primary').invalid = True
    daily = engine.start('Internal review', mission_kind='DAILY_OPPORTUNITY_REVIEW')['session_id']
    result = engine.run(daily)
    assert result['state'] == 'FAILED'
    assert result['mission']['blocker'].startswith('INTERNAL_REVIEW_FAILED:')


def test_restart_after_artifact_before_receipt_recovers_continuity_without_replay(engine):
    from core.lab_v1.agent_continuity import AgentContinuity
    from core.lab_v1.autopilot import _AutopilotPorts

    sid = engine.start('Document')['session_id']
    ports = _AutopilotPorts(engine, sid, engine.metrics(sid))
    execute = ports.execute

    def crash_after_artifact(dispatch):
        execute(dispatch)
        raise SystemExit('crash after durable artifact')

    ports.execute = crash_after_artifact
    with pytest.raises(SystemExit, match='crash after durable artifact'):
        engine.controller.tick(sid, ports)

    assert AgentContinuity(engine.store).load_checkpoint(sid, 'lead') is None
    calls_before_restart = len(engine.runtime.registry.get('primary').calls)
    resumed = Autopilot(LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
                        root=engine.root, executor_factory=Files, policy=engine.policy)
    assert resumed.run(sid)['state'] == 'COMPLETED'
    assert len(resumed.store.list_runs(sid)) == 2
    assert len(engine.runtime.registry.get('primary').calls) == calls_before_restart
    checkpoint = AgentContinuity(resumed.store).load_checkpoint(sid, 'lead')
    assert checkpoint.cursor == 'plan'
    assert checkpoint.state['artifact_ref'].startswith('response:')


@pytest.mark.parametrize('binding_defect', ['missing', 'digest_mismatch'])
def test_interrupted_model_response_without_complete_binding_stays_explicitly_unknown(
        engine, binding_defect):
    sid = engine.start('Document')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        step = next(item for item in doc['steps'] if item['id'] == 'plan')
        step.update(status='RECONCILE', receipt=None, verification=None)
        doc['state'], doc['blocker'] = 'BLOCKED', 'UNCERTAIN_EFFECT'
        conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0 WHERE session_id=?', (sid,))
        engine.controller._save(conn, doc, 'test.interrupted_unbound_model_response')
    binding_id = 'MODEL_RESPONSE_BINDING:' + step['attempt_id']
    with engine.store._connect() as conn:
        if binding_defect == 'missing':
            conn.execute('DELETE FROM artifacts WHERE id=?', (binding_id,))
        else:
            binding = json.loads(conn.execute(
                'SELECT body FROM artifacts WHERE id=?', (binding_id,)).fetchone()[0])
            binding['artifact_sha256'] = '0' * 64
            conn.execute('UPDATE artifacts SET body=? WHERE id=?', (json.dumps(binding), binding_id))

    calls_before_recovery = len(engine.runtime.registry.get('primary').calls)
    engine._recover_interrupted(sid)

    recovered = next(item for item in engine.controller.snapshot(sid)['steps'] if item['id'] == 'plan')
    assert recovered['status'] == 'RECONCILE'
    assert recovered['reconciliation']['verdict'] == 'UNKNOWN'
    assert 'RESPONSE_RUN_BINDING_' in recovered['reconciliation']['evidence_ref']
    assert len(engine.runtime.registry.get('primary').calls) == calls_before_recovery


def test_restart_injects_existing_agent_continuity_and_advances_after_durable_artifact(engine):
    from core.lab_v1.agent_continuity import AgentContinuity

    sid = engine.start('Document')['session_id']
    continuity = AgentContinuity(engine.store)
    previous = continuity.save_checkpoint(
        sid,
        'lead',
        cursor='owner-intake',
        summary='Owner intent was admitted and the bounded plan is still pending.',
        state={'phase': 'planning'},
    )

    resumed = Autopilot(
        LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
        root=engine.root,
        executor_factory=Files,
        policy=engine.policy,
    )
    result = resumed.run(sid)

    assert result['state'] == 'COMPLETED'
    first_prompt = engine.runtime.registry.get('primary').calls[0]['prompt']
    assert previous.summary in first_prompt
    current = AgentContinuity(resumed.store).load_checkpoint(sid, 'lead')
    assert current.revision == previous.revision + 1
    assert current.cursor == 'plan'
    assert current.state['artifact_ref'].startswith('response:')


def test_autopilot_injects_only_promoted_relevant_lesson_with_evidence(engine):
    from core.lab_v1.domain import EventType, LabEvent, Session, Team

    def mark_lesson(session_id, suffix, statement, *, promote=True):
        evidence = engine.store.append_event(LabEvent(
            f'evidence:{suffix}', 0, EventType.TASK_COMPLETED,
            session_id, f'task:{suffix}', {'result': 'observed'}))
        marker = engine.store.append_event(LabEvent(
            f'lesson:{suffix}', 0, EventType.LESSON_MARKED_VERIFIED,
            session_id, None, {
                'lesson': statement,
                'evidence_event_id': evidence.id,
            }))
        if promote:
            engine.store.promote_lesson(marker.id)
        return evidence

    previous_sid = 'previous-document-mission'
    engine.store.save_session(Session(previous_sid, 'team', 'Earlier document mission'))
    evidence = mark_lesson(
        previous_sid, 'document-planning',
        'Document planning must keep acceptance criteria bounded.')
    mark_lesson(
        previous_sid, 'irrelevant-colors',
        'Dashboard colors should use balanced visual spacing.')
    mark_lesson(
        previous_sid, 'unpromoted-document',
        'Document planning should include an unpromoted private draft.',
        promote=False)
    engine.store.save_team(Team('foreign-team', 'Foreign'))
    foreign_sid = 'foreign-document-mission'
    engine.store.save_session(Session(foreign_sid, 'foreign-team', 'Foreign document'))
    mark_lesson(
        foreign_sid, 'foreign-document',
        'Document planning from another team must stay isolated.')

    sid = engine.start('Document')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'

    first_prompt = engine.runtime.registry.get('primary').calls[0]['prompt']
    assert 'Document planning must keep acceptance criteria bounded.' in first_prompt
    assert f'[evidencia: event:{evidence.id}]' in first_prompt
    assert 'Dashboard colors should use balanced visual spacing.' not in first_prompt
    assert 'unpromoted private draft' not in first_prompt
    assert 'another team must stay isolated' not in first_prompt
    worker_prompt = engine.runtime.registry.get('fallback').calls[0]['prompt']
    assert 'Document planning must keep acceptance criteria bounded.' in worker_prompt


def test_concurrent_restart_sync_of_same_receipt_is_idempotent(engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    from core.lab_v1.agent_continuity import AgentContinuity

    sid = engine.start('Document')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'
    with engine.store._connect() as conn:
        conn.execute("DELETE FROM agent_continuity WHERE session_id=? AND agent_id='lead'", (sid,))

    first = Autopilot(
        LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
        root=engine.root, executor_factory=Files, policy=engine.policy)
    second = Autopilot(
        LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
        root=engine.root, executor_factory=Files, policy=engine.policy)
    original_load = AgentContinuity.load_checkpoint
    barrier = threading.Barrier(2)
    counter_lock = threading.Lock()
    calls = 0

    def racing_load(self, session_id, agent_id):
        nonlocal calls
        checkpoint = original_load(self, session_id, agent_id)
        with counter_lock:
            calls += 1
            should_wait = calls <= 2
        if should_wait:
            barrier.wait(timeout=5)
        return checkpoint

    monkeypatch.setattr(AgentContinuity, 'load_checkpoint', racing_load)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(item._sync_agent_continuity, sid) for item in (first, second)]
        for future in futures:
            future.result(timeout=5)

    checkpoint = original_load(AgentContinuity(engine.store), sid, 'lead')
    assert checkpoint.revision == 1
    assert checkpoint.state['artifact_ref'].startswith('response:')


def test_completed_mission_replay_does_not_repeat_provider_or_checkpoint(engine):
    from core.lab_v1.agent_continuity import AgentContinuity

    sid = engine.start('Document')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'
    continuity = AgentContinuity(engine.store)
    revisions = {
        agent_id: continuity.load_checkpoint(sid, agent_id).revision
        for agent_id in ('lead', 'worker')
    }
    calls = {
        provider_id: len(engine.runtime.registry.get(provider_id).calls)
        for provider_id in ('primary', 'fallback')
    }

    restarted = Autopilot(
        LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
        root=engine.root,
        executor_factory=Files,
        policy=engine.policy,
    )
    assert restarted.run(sid)['state'] == 'COMPLETED'

    assert {
        agent_id: continuity.load_checkpoint(sid, agent_id).revision
        for agent_id in ('lead', 'worker')
    } == revisions
    assert {
        provider_id: len(engine.runtime.registry.get(provider_id).calls)
        for provider_id in ('primary', 'fallback')
    } == calls


def test_fenced_provider_json_uses_existing_defensive_parser(engine):
    engine.runtime.registry.get('primary').fenced = True
    sid = engine.start('Document')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'
    assert len(engine.store.list_runs(sid)) == 2


def test_verifier_repair_reuses_receipt_without_extra_provider_call(engine):
    from core.lab_v1.autopilot import _AutopilotPorts
    from core.lab_v1.mission_controller import Verification
    sid = engine.start('Document')['session_id']
    ports = _AutopilotPorts(engine, sid, engine.metrics(sid))
    engine.controller.tick(sid, ports)
    ports.verify = lambda *_: Verification('FAIL', 'old-verifier')
    assert engine.controller.tick(sid, ports)['state'] == 'BLOCKED'
    before = engine.controller.snapshot(sid)
    engine.controller.recheck_verification(sid, reason='Corrected JSON fence handling')
    assert engine.controller.snapshot(sid)['used'] == before['used']
    assert engine.controller.snapshot(sid)['deadline'] == before['deadline']
    assert engine.run(sid)['state'] == 'COMPLETED'
    assert len(engine.store.list_runs(sid)) == 2


@pytest.mark.asyncio
async def test_service_entry_is_persisted_before_execution(engine):
    svc = LabV1Service()
    svc._autopilot = engine
    svc._supervisor = type('Supervisor', (), {'policy': lambda self: engine.policy.document,
        'tick': lambda self: {'state': 'MONITORING'}})()
    result = await svc.start_autopilot('Document')
    assert result['state'] == 'QUEUED'
    assert engine.store.list_sessions()
    await svc.stop_background()


@pytest.mark.asyncio
async def test_ipc_ack_precedes_work_and_does_not_block_other_commands():
    import asyncio
    from unittest.mock import AsyncMock
    from core.ipc_handlers import IPCHandler, IPCMessage
    release = asyncio.Event()
    svc = LabV1Service()
    svc.start_autopilot = AsyncMock(return_value={'success': True, 'session_id': 'persisted', 'state': 'QUEUED'})
    async def work(sid):
        await release.wait()
        return {'success': True}
    svc.run_autopilot = work
    handler = IPCHandler(AsyncMock())
    handler.lab_v1 = svc
    await handler.handle_message(IPCMessage(type='lab-v1-autopilot', request_id='start', payload={'intent': 'Document'}))
    assert handler.send.call_args.args[0].response['state'] == 'QUEUED'
    assert handler._lab_v1_background_tasks
    release.set()
    await asyncio.gather(*handler._lab_v1_background_tasks)


@pytest.mark.asyncio
async def test_packaged_entry_canary_queues_and_cancels_without_provider_worker(monkeypatch):
    from unittest.mock import AsyncMock
    from core.ipc_handlers import IPCHandler, IPCMessage
    monkeypatch.setenv('ZARA_LAB_ENTRY_CANARY', '1')
    svc = LabV1Service()
    svc.start_autopilot = AsyncMock(return_value={
        'success': True, 'session_id': 'persisted', 'state': 'QUEUED'})
    svc.run_autopilot = AsyncMock()
    handler = IPCHandler(AsyncMock())
    handler._smoke_test = True
    handler.lab_v1 = svc
    await handler.handle_lab_v1_autopilot(IPCMessage(
        type='lab-v1-autopilot', request_id='entry', payload={'intent': 'Document'}))
    assert handler.send.call_args.args[0].response['state'] == 'QUEUED'
    assert not handler._lab_v1_background_tasks
    svc.run_autopilot.assert_not_called()


@pytest.mark.asyncio
async def test_smoke_mode_cannot_start_autopilot(monkeypatch):
    from unittest.mock import AsyncMock
    from core.ipc_handlers import IPCHandler, IPCMessage
    monkeypatch.setenv('ZARA_SMOKE_TEST', '1')
    handler = IPCHandler(AsyncMock())
    handler.handle_lab_v1_autopilot = AsyncMock()
    await handler.handle_message(IPCMessage(type='lab-v1-autopilot', request_id='blocked', payload={'intent': 'Document'}))
    assert handler.send.call_args.args[0].error.startswith('SMOKE_READ_ONLY')
    handler.handle_lab_v1_autopilot.assert_not_called()
