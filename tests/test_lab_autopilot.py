import json
import shutil
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, Team, TeamMembership)
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
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


class BootstrapClaudeAdapter(ProviderAdapter):
    id = 'claude_cli'
    label = 'Claude fixture'
    controlled_text_only = True
    declared_models = tuple(ModelDescriptor('claude_cli', model, model.title())
                            for model in ('opus', 'sonnet', 'haiku'))

    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure

    def probe(self):
        return ProviderInfo(self.id, self.label, 'fixture', Availability.AVAILABLE)

    def complete_with_options(self, **kwargs):
        return self.complete(**kwargs)

    def complete(self, **kwargs):
        model = kwargs['model']
        self.calls.append(model)
        if self.failure:
            return ProviderResult(False, availability=self.failure, error=self.failure.value)
        return ProviderResult(True, text='A test passing is evidence only for that test.',
                              availability=Availability.AVAILABLE, model_reported=model)


class NvidiaBootstrapAdapter(ProviderAdapter):
    id = 'nvidia'
    label = 'NVIDIA fixture'
    controlled_text_only = True
    declared_models = tuple(ModelDescriptor('nvidia', model, model)
                            for model in ('moonshotai/kimi-k3', 'z-ai/glm-5.3',
                                          'nvidia/nemotron-3-super-120b-a12b',
                                          'nvidia/nemotron-3-ultra-550b-a55b'))

    def __init__(self):
        self.calls = []

    def probe(self):
        return ProviderInfo(self.id, self.label, 'fixture', Availability.AVAILABLE,
                            models=[item.model_id for item in self.declared_models])

    def complete_with_options(self, **kwargs):
        return self.complete(**kwargs)

    def complete(self, **kwargs):
        model = kwargs['model']
        self.calls.append(model)
        return ProviderResult(True, text='Uma verificação precisa confirma apenas o escopo observado.',
                              availability=Availability.AVAILABLE, model_reported=model)


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


def _core_autopilot(tmp_path, adapter, policy=None, additional=()):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(adapter)
    for extra in additional:
        registry.register(extra)
    runtime = LabRuntime(store, registry)
    return Autopilot(runtime, root=tmp_path / 'missions', policy=policy or
                     WorkforcePolicy(WorkforcePolicy.default_document()))


def test_first_core_team_selection_certifies_two_distinct_workers_and_reuses_proof(tmp_path):
    adapter = BootstrapClaudeAdapter()
    autopilot = _core_autopilot(tmp_path, adapter)

    team, planner, builder = autopilot._team()

    assert team.name == 'ZARA Core'
    assert planner.role == RoleName.CEO and builder.role == RoleName.BUILDER
    assert (planner.provider_id, planner.model) != (builder.provider_id, builder.model)
    assert adapter.calls == ['opus', 'sonnet', 'haiku']
    assert len(autopilot.store.list_agents(team.id)) == 4
    assert all('model.text' in agent.capabilities for agent in autopilot.store.list_agents(team.id)
               if agent.name != 'Vulcan Reserva')
    assert 'model.text' not in next(agent for agent in autopilot.store.list_agents(team.id)
                                   if agent.name == 'Vulcan Reserva').capabilities

    restart_adapter = BootstrapClaudeAdapter()
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(restart_adapter)
    restarted = Autopilot(LabRuntime(autopilot.store, registry), root=tmp_path / 'missions',
                          policy=WorkforcePolicy(WorkforcePolicy.default_document()))
    _, restarted_planner, restarted_builder = restarted._team()
    assert (restarted_planner.id, restarted_builder.id) == (planner.id, builder.id)
    assert restart_adapter.calls == []


def test_first_core_team_does_not_mark_workers_callable_when_certification_fails(tmp_path):
    adapter = BootstrapClaudeAdapter(failure=Availability.AUTH_REQUIRED)
    autopilot = _core_autopilot(tmp_path, adapter)

    with pytest.raises(ValueError, match='WAITING_RESOURCE.*AUTH_REQUIRED'):
        autopilot._team()

    profiles = autopilot.store.list_agents()
    assert len(profiles) == 4
    assert all('model.text' not in agent.capabilities for agent in profiles)
    assert adapter.calls == ['opus']


def test_first_core_team_respects_unknown_cost_before_model_call(tmp_path):
    document = WorkforcePolicy.default_document()
    document['resource_classes']['claude_cli/*'] = 'UNKNOWN_COST'
    adapter = BootstrapClaudeAdapter()
    autopilot = _core_autopilot(tmp_path, adapter, WorkforcePolicy(document))

    with pytest.raises(ValueError, match='WAITING_RESOURCE.*UNKNOWN_COST'):
        autopilot._team()

    assert adapter.calls == []
    assert all('model.text' not in agent.capabilities for agent in autopilot.store.list_agents())


def test_first_core_team_uses_distinct_owner_authorized_nvidia_fallbacks_after_claude_auth_failure(tmp_path):
    claude = BootstrapClaudeAdapter(failure=Availability.AUTH_REQUIRED)
    nvidia = NvidiaBootstrapAdapter()
    autopilot = _core_autopilot(tmp_path, claude, additional=(nvidia,))
    core = autopilot.runtime.ensure_core_team()
    original = {agent.name: agent.id for agent in autopilot.store.list_agents(core.id)}

    team, planner, builder = autopilot._team()

    assert team.name == 'ZARA Core'
    assert planner.id == original['Artemis']
    assert builder.id == original['Vulcan']
    assert (planner.provider_id, planner.model) == ('nvidia', 'moonshotai/kimi-k3')
    assert (builder.provider_id, builder.model) == ('nvidia', 'z-ai/glm-5.3')
    assert (planner.provider_id, planner.model) != (builder.provider_id, builder.model)
    assert len(autopilot.store.list_agents(team.id)) == 4
    assert all('model.text' in agent.capabilities for agent in (planner, builder))
    reviewer = next(agent for agent in autopilot.store.list_agents(team.id)
                    if agent.role == RoleName.REVIEWER)
    assert (reviewer.provider_id, reviewer.model) == (
        'nvidia', 'nvidia/nemotron-3-super-120b-a12b')
    assert 'model.text' in reviewer.capabilities
    reserve = next(agent for agent in autopilot.store.list_agents(team.id)
                   if agent.name == 'Vulcan Reserva')
    assert reserve.id == original['Vulcan Reserva'] and reserve.role == RoleName.BUILDER
    assert (reserve.provider_id, reserve.model) == ('nvidia', 'moonshotai/kimi-k3')
    assert 'model.text' in reserve.capabilities
    assert nvidia.calls == ['moonshotai/kimi-k3', 'z-ai/glm-5.3', 'moonshotai/kimi-k3',
                            'nvidia/nemotron-3-super-120b-a12b']


def test_core_reviewer_uses_certified_ultra_when_super_is_temporarily_overloaded(tmp_path):
    class OverloadedSuper(NvidiaBootstrapAdapter):
        def complete(self, **kwargs):
            if kwargs['model'] == 'nvidia/nemotron-3-super-120b-a12b':
                self.calls.append(kwargs['model'])
                return ProviderResult(False, availability=Availability.PROVIDER_ERROR,
                                      error='Service temporarily overloaded')
            return super().complete(**kwargs)

    nvidia = OverloadedSuper()
    autopilot = _core_autopilot(tmp_path, BootstrapClaudeAdapter(failure=Availability.AUTH_REQUIRED),
                                additional=(nvidia,))
    team, _, _ = autopilot._team()
    reviewer = next(agent for agent in autopilot.store.list_agents(team.id)
                    if agent.role == RoleName.REVIEWER)
    assert (reviewer.provider_id, reviewer.model) == ('nvidia', 'nvidia/nemotron-3-ultra-550b-a55b')
    assert 'model.text' in reviewer.capabilities
    assert nvidia.calls[-2:] == ['nvidia/nemotron-3-super-120b-a12b',
                                 'nvidia/nemotron-3-ultra-550b-a55b']


def test_core_glm_failure_hands_same_mission_to_certified_kimi_builder(tmp_path):
    claude = BootstrapClaudeAdapter(failure=Availability.AUTH_REQUIRED)
    nvidia = NvidiaBootstrapAdapter()
    autopilot = _core_autopilot(tmp_path, claude, additional=(nvidia,))
    autopilot.executor_factory = Files
    team, planner, primary = autopilot._team()
    reserve = next(agent for agent in autopilot.store.list_agents(team.id)
                   if agent.name == 'Vulcan Reserva')
    assert primary.model == 'z-ai/glm-5.3'
    assert reserve.id != planner.id and reserve.id != primary.id

    plan = {'mission': 'Document', 'plan_version': 1, 'tasks': [
        {'id': 'document', 'title': 'Document', 'instruction': 'Create the requested short document',
         'role': 'BUILDER', 'capability': 'artifact.text', 'path': 'result.md',
         'risk': 'LOW', 'repair_budget': 1, 'depends_on': [],
         'acceptance': {'method': 'constraints', 'min_chars': 10, 'max_chars': 100,
                        'required_sections': []}}]}
    mission_calls = []

    def mission_complete(**kwargs):
        model, system = kwargs['model'], kwargs['system']
        mission_calls.append(model)
        if system.startswith('Return JSON only:'):
            text = json.dumps(plan)
        elif system.startswith('Implement only') and model == 'z-ai/glm-5.3':
            return ProviderResult(False, availability=Availability.PROVIDER_ERROR,
                                  error='invalid provider response')
        elif system.startswith('Implement only') and model == 'moonshotai/kimi-k3':
            text = 'ZARA_AUTOPILOT_OK'
        else:
            raise AssertionError((model, system[:50]))
        return ProviderResult(True, text=text, availability=Availability.AVAILABLE,
                              model_reported=model)

    nvidia.complete = mission_complete
    sid = autopilot.start('Create a short document')['session_id']
    result = autopilot.run(sid)

    assert result['state'] == 'COMPLETED'
    assert result['session_id'] == sid and len(autopilot.store.list_sessions()) == 1
    assert result['autonomy']['owner_touches'] == 1
    assert result['autonomy']['recovery_automatic'] is True
    assert mission_calls == ['moonshotai/kimi-k3', 'z-ai/glm-5.3', 'moonshotai/kimi-k3']
    assert autopilot.store.get_task(sid + ':document:draft').assigned_agent_id == reserve.id
    handoffs = [item for item in autopilot.store.list_handoffs(sid)
                if item.reason.startswith('PROVIDER_')]
    assert len(handoffs) == 1
    assert (handoffs[0].from_agent_id, handoffs[0].to_agent_id) == (primary.id, reserve.id)
    assert Path(result['autonomy']['target']).read_text() == 'ZARA_AUTOPILOT_OK'
    with autopilot.store._connect() as conn:
        proof_rows = conn.execute('SELECT document FROM model_certification_runs').fetchall()
    certified = {json.loads(row[0]).get('agent_id') for row in proof_rows
                 if json.loads(row[0]).get('state') == 'COMPLETED'
                 and json.loads(row[0]).get('result', {}).get('ok')}
    for run in autopilot.store.list_runs(sid):
        agent = autopilot.store.get_agent(run.agent_id)
        assert agent.id in certified
        assert autopilot._decision(agent, retry=True, team_id=team.id).allowed
        assert autopilot.policy.resource_class(agent.provider_id, agent.model).value == 'OWNER_REPORTED_FREE'
    assert claude.calls == ['opus']


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
    assert not engine.store.list_capability_gaps(sid)
    assert engine.runtime.submit(sid, 'Cannot bypass')['code'] == 'MISSION_CONTROLLED'
    assert len([m for m in engine.store.list_messages(sid) if m.kind.value == 'ZARA']) == 1
    engine.run(sid)
    assert len(engine.store.list_runs(sid)) == 2
    assert len([m for m in engine.store.list_messages(sid) if m.kind.value == 'ZARA']) == 1


def test_spontaneous_observation_is_attributed_to_zara_and_owner_intent_to_alex(engine, monkeypatch):
    monkeypatch.setattr('core.lab_v1.source_mission.source_requested', lambda *_: False)
    owner_sid = engine.start('Owner intent')['session_id']
    assert engine.store.list_messages(owner_sid)[0].author == 'Alex'
    engine.controller.cancel(owner_sid)
    engine.run(owner_sid)

    observed_sid = engine.start('Observed defect', mission_kind='SELF_IMPROVEMENT',
        evidence={'observation_kind': 'BEHAVIORAL_COUNTEREXAMPLE'})['session_id']
    observed = engine.store.list_messages(observed_sid)[0]
    assert observed.kind.value == 'USER' and observed.author == 'ZARA'
    engine.controller.cancel(observed_sid)
    engine.run(observed_sid)

    owner_review = engine.start('Owner requested review', mission_kind='SELF_IMPROVEMENT')['session_id']
    assert engine.store.list_messages(owner_review)[0].author == 'Alex'


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


def test_restart_after_plan_checkpoint_retains_same_mission(engine):
    from core.lab_v1.autopilot import _AutopilotPorts
    sid = engine.start('Document')['session_id']
    engine.controller.tick(sid, _AutopilotPorts(engine, sid, engine.metrics(sid)))
    resumed = Autopilot(LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
                        root=engine.root, executor_factory=Files, policy=engine.policy)
    assert resumed.run(sid)['state'] == 'COMPLETED'
    assert len(resumed.store.list_runs(sid)) == 2


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
