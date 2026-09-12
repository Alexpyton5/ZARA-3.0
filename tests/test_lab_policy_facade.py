import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, RoleName
from core.lab_v1.service import LabV1Service
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.domain import ProviderResult
from core.lab_v1.workforce_policy import ResourceClass, WorkforcePolicy


def agent(model, role=RoleName.BUILDER, provider='codex_cli'):
    return AgentProfile('agent:' + model, model, provider, model, role=role,
                        capabilities=['model.text'])


def info(provider='codex_cli'):
    return ProviderInfo(provider, provider, 'test', Availability.AVAILABLE,
                        authenticated=True, quota_available=True)


def test_default_policy_authorizes_only_plan_included_codex_and_claude_workers():
    policy = WorkforcePolicy({})
    for model in ('gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra'):
        decision = policy.authorize(agent(model), info(), model_available=True)
        assert decision.allowed
        assert decision.resource_class is ResourceClass.PLAN_INCLUDED
    # Alex re-authorized claude_cli on 2026-09-10: it reuses the already
    # authenticated Claude Code CLI session, so it is PLAN_INCLUDED like Codex.
    # `haiku` joined opus/sonnet on 2026-09-10 (TASK 2) after a real call proved
    # the provider answers as canonicalModel `claude-haiku-4-5`.
    for model in ('opus', 'sonnet', 'haiku'):
        decision = policy.authorize(agent(model, provider='claude_cli'), info('claude_cli'),
                                    model_available=True)
        assert decision.allowed
        assert decision.resource_class is ResourceClass.PLAN_INCLUDED
    astra = policy.authorize(agent('gpt-6-astra'), info(), model_available=True)
    unknown = policy.authorize(agent('future-model'), info(), model_available=True)
    external = policy.authorize(agent('free-model', provider='nvidia'), info('nvidia'), model_available=True)
    # An authorized provider still does not authorize its whole catalog: `fable`
    # is a real Claude CLI alias but is not a declared Lab model, so it stays refused.
    fable = policy.authorize(agent('fable', provider='claude_cli'), info('claude_cli'), model_available=True)
    assert not fable.allowed and fable.code == 'MODEL_NOT_AUTHORIZED'
    assert not unknown.allowed and unknown.code == 'MODEL_NOT_AUTHORIZED'
    assert not external.allowed and external.code == 'PROVIDER_NOT_AUTHORIZED'
    assert not astra.allowed and astra.code == 'MODEL_NOT_AUTHORIZED'


def test_a_revoked_provider_is_revoked_by_document_not_by_hardcoded_identity():
    """The old `claude_cli -> OWNER_DISABLED` branch was an identity check in
    code, which is why reverting it took a code change instead of a policy edit.
    Revocation must be expressible purely in the document."""
    policy = WorkforcePolicy({'authorized_providers': ['codex_cli'],
                              'authorized_models': ['codex_cli/*']})
    decision = policy.authorize(agent('opus', provider='claude_cli'), info('claude_cli'),
                                model_available=True)
    assert not decision.allowed and decision.code == 'PROVIDER_NOT_AUTHORIZED'


def test_paid_and_unknown_resources_never_become_silent_fallbacks():
    policy = WorkforcePolicy({
        'authorized_providers': ['paid', 'unknown'],
        'authorized_models': ['paid/*', 'unknown/*'],
        'resource_classes': {'paid/*': 'PAID', 'unknown/*': 'UNKNOWN_COST'},
    })
    decisions = [
        policy.authorize(agent('m', provider='paid'), info('paid'), model_available=True),
        policy.authorize(agent('m', provider='unknown'), info('unknown'), model_available=True),
    ]
    assert [item.code for item in decisions] == ['PAID_NOT_AUTHORIZED', 'UNKNOWN_COST']
    assert policy.choose_fallback(decisions) is None


def test_role_selection_uses_economical_authorized_worker():
    policy = WorkforcePolicy({})
    decisions = [policy.authorize(agent(model), info(), model_available=True)
                 for model in ('gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-luna')]
    assert policy.choose_for_role(decisions, 'BUILDER').model_id == 'gpt-5.6-luna'
    assert policy.preference_rank('gpt-5.6-luna', 'BUILDER') < policy.preference_rank('gpt-6-astra', 'BUILDER')


def test_service_and_supervisor_share_one_autopilot_instance():
    service = LabV1Service()
    shared = SimpleNamespace(start=Mock(return_value={
        'success': True, 'session_id': 'mission', 'state': 'QUEUED'}))
    supervisor = SimpleNamespace(
        policy=lambda: WorkforcePolicy.default_document(), autopilot=None,
        set_autopilot=lambda value: setattr(supervisor, 'autopilot', value),
        tick=Mock(return_value={'state': 'MONITORING'}))
    service._runtime = SimpleNamespace(store=SimpleNamespace())
    service._supervisor = supervisor
    service._autopilot = shared
    service._get_autopilot()
    assert supervisor.autopilot is shared


def test_background_task_failure_is_visible_and_loop_survives():
    service = LabV1Service()
    ticks = Mock(side_effect=[RuntimeError('boom'), {'state': 'MONITORING'}])
    recorded = []
    service._supervisor = SimpleNamespace(
        policy=lambda: {'background_enabled': True, 'cadence_seconds': 0.01},
        tick=ticks, record_background_error=lambda detail: recorded.append(detail))
    service._background_interval = 0.01

    async def exercise():
        assert (await service.start_background())['state'] == 'RUNNING'
        await asyncio.sleep(0.04)
        await service.stop_background()

    asyncio.run(exercise())
    assert ticks.call_count >= 2
    assert recorded and recorded[0].startswith('RuntimeError: boom')


def test_stale_quota_denial_becomes_retryable_without_becoming_success_evidence(tmp_path):
    class Adapter(ProviderAdapter):
        id = label = 'codex_cli'; controlled_text_only = True
        def probe(self): return info()
        def complete(self, **kwargs): raise AssertionError('listing must not invoke model')
    registry = ProviderRegistry(tmp_path / 'health.json'); registry.register(Adapter())
    registry.record_result('codex_cli', 'gpt-5.6-sol', ProviderResult(
        False, availability=Availability.QUOTA_EXHAUSTED, error='quota'), observed_at=1)
    current = registry.list_providers()[0]
    assert current.availability is Availability.AVAILABLE
    assert 'revalida o recurso' in current.detail
