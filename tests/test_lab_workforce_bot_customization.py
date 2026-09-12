"""Owner-selectable bot provider/model ("bots customizaveis", 2026-09-12).

Alex wants to pick, per Lab bot, which provider/model it runs on -- his
Anthropic plan (claude_cli), his OpenAI plan (codex_cli), or his free NVIDIA
NIM key (nvidia/Nemotron) -- and to have the Lab fall back to whatever is
still authorized and available when a paid plan runs out of quota.

Everything here exercises the REAL decision pipeline (WorkforcePolicy +
ProviderRegistry), exactly like tests/test_lab_policy_facade.py. Only the
HTTP transport is fake: `FakeAdapter` never makes a network call, so these
tests are deterministic and free. `registry.list_models()` returns real
`ModelDescriptor.to_dict()` rows, and `registry.record_result()` mutates the
same on-disk health file the real Lab reads, so the fallback exercised here
is the identical mechanism `default_registry()` and `WorkforcePolicy.
choose_for_role()` use in production -- no second failover system.

NVIDIA/Nemotron real-call evidence (2026-09-12, outside this test file, not
repeatable in CI because it needs Alex's live key): a direct call through
`core.lab_v1.providers.nvidia.NvidiaApiAdapter` with the real key from
`config/api_keys.json` ran `GET /v1/models` (82 real ids returned, including
both ids authorized below) and then a real chat completion against each of
`nvidia/nemotron-3-super-120b-a12b` and `nvidia/nemotron-3-ultra-550b-a55b`;
both echoed the exact requested text and reported their own id back as
`model_reported`. That is why exactly those two ids -- and only those two --
are OWNER_REPORTED_FREE and authorized in `WorkforcePolicy.default_document()`.
"""
from __future__ import annotations

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.workforce_policy import ResourceClass, WorkforcePolicy, human_message


class FakeAdapter(ProviderAdapter):
    """Deterministic stand-in for a real provider: no network, ever."""

    def __init__(self, provider_id: str, *, availability=Availability.AVAILABLE, models=()):
        self.id = self.label = provider_id
        self._availability = availability
        self._models = tuple(models)

    @property
    def declared_models(self):
        return tuple(
            ModelDescriptor(provider_id=self.id, model_id=model_id, display_name=model_id)
            for model_id in self._models
        )

    def probe(self) -> ProviderInfo:
        return ProviderInfo(self.id, self.label, 'fake', self._availability,
                            authenticated=True, quota_available=True)

    def complete(self, **kwargs):
        raise AssertionError('decision-layer tests must never invoke a real model')


def registry_with(tmp_path, *adapters):
    registry = ProviderRegistry(tmp_path / 'health.json')
    for adapter in adapters:
        registry.register(adapter)
    return registry


def agent(agent_id, name, provider_id, model, role):
    return AgentProfile(agent_id, name, provider_id, model, role=role)


NVIDIA_PROVEN = 'nvidia/nemotron-3-super-120b-a12b'


# ---------------------------------------------------------------------
# 1. No configuration -> current behaviour preserved
# ---------------------------------------------------------------------

def test_no_override_configured_behaviour_is_unchanged(tmp_path):
    policy = WorkforcePolicy({})
    a = agent('agent:builder', 'Builder', 'codex_cli', 'gpt-5.6-luna', RoleName.BUILDER)
    assert policy.bot_override(a.id) is None
    choice = policy.effective_resource(a)
    assert (choice.provider_id, choice.model_id) == ('codex_cli', 'gpt-5.6-luna')

    registry = registry_with(tmp_path, FakeAdapter('codex_cli', models=['gpt-5.6-luna']))
    provider = registry.list_providers()[0]
    decision = policy.authorize(a, provider, model_available=True)
    assert decision.allowed and decision.resource_class is ResourceClass.PLAN_INCLUDED


# ---------------------------------------------------------------------
# 2. Owner configures a bot to a specific provider/model -> selection respects it
# ---------------------------------------------------------------------

def test_owner_override_is_respected_by_selection(tmp_path):
    registry = registry_with(
        tmp_path,
        FakeAdapter('codex_cli', models=['gpt-5.6-luna']),
        FakeAdapter('nvidia', models=[NVIDIA_PROVEN]),
    )
    policy = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'codex_cli', 'gpt-5.6-luna', RoleName.BUILDER)

    decision, new_document = policy.with_bot_override(
        agent=builder, provider_id='nvidia', model_id=NVIDIA_PROVEN, registry=registry,
    )
    assert decision.allowed and decision.code == 'AUTHORIZED'
    assert new_document is not None
    assert new_document['agent_model_overrides'][builder.id] == {
        'provider_id': 'nvidia', 'model_id': NVIDIA_PROVEN,
    }
    # original document/instance is untouched -- caller decides when to persist
    assert policy.bot_override(builder.id) is None

    reconfigured = WorkforcePolicy(new_document)
    choice = reconfigured.effective_resource(builder)
    assert (choice.provider_id, choice.model_id) == ('nvidia', NVIDIA_PROVEN)
    provider = next(p for p in registry.list_providers() if p.id == 'nvidia')
    final = reconfigured.authorize(
        agent(builder.id, builder.name, choice.provider_id, choice.model_id, builder.role),
        provider, model_available=True,
    )
    assert final.allowed and final.resource_class is ResourceClass.OWNER_REPORTED_FREE


# ---------------------------------------------------------------------
# 3. Owner configures a nonexistent/unauthorized model -> clear, non-silent refusal
# ---------------------------------------------------------------------

def test_unknown_model_is_refused_clearly(tmp_path):
    registry = registry_with(tmp_path, FakeAdapter('nvidia', models=[NVIDIA_PROVEN]))
    policy = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'nvidia', NVIDIA_PROVEN, RoleName.BUILDER)

    decision, new_document = policy.with_bot_override(
        agent=builder, provider_id='nvidia', model_id='nvidia/modelo-que-nao-existe', registry=registry,
    )
    assert not decision.allowed
    assert decision.code == 'MODEL_NOT_AUTHORIZED'
    assert new_document is None
    message = human_message(decision)
    assert message and 'Traceback' not in message and 'Exception' not in message
    assert message == 'Esse modelo ainda nao esta na lista de modelos liberados do Lab.'


def test_catalog_presence_alone_does_not_authorize_a_model(tmp_path):
    """A model can be real and discovered and still refused: only the curated
    `authorized_models` allow-list grants use, never the catalog by itself."""
    registry = registry_with(
        tmp_path, FakeAdapter('nvidia', models=[NVIDIA_PROVEN, 'nvidia/llama-3.1-nemotron-70b-instruct']),
    )
    policy = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'nvidia', NVIDIA_PROVEN, RoleName.BUILDER)
    decision = policy.validate_bot_configuration(
        agent=builder, provider_id='nvidia', model_id='nvidia/llama-3.1-nemotron-70b-instruct', registry=registry,
    )
    assert not decision.allowed and decision.code == 'MODEL_NOT_AUTHORIZED'


# ---------------------------------------------------------------------
# 4. A provider out of quota -> fallback to another authorized resource
# ---------------------------------------------------------------------

def test_quota_exhausted_provider_fails_over_to_another_authorized_resource(tmp_path):
    registry = registry_with(
        tmp_path,
        FakeAdapter('codex_cli', models=['gpt-5.6-luna']),
        FakeAdapter('nvidia', models=[NVIDIA_PROVEN]),
    )
    registry.record_result(
        'codex_cli', 'gpt-5.6-luna',
        ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='sem cota'),
    )
    policy = WorkforcePolicy({})
    providers = {p.id: p for p in registry.list_providers()}
    assert providers['codex_cli'].availability is Availability.QUOTA_EXHAUSTED

    codex_builder = agent('agent:codex', 'Codex Builder', 'codex_cli', 'gpt-5.6-luna', RoleName.BUILDER)
    nvidia_builder = agent('agent:nvidia', 'Nemotron Builder', 'nvidia', NVIDIA_PROVEN, RoleName.BUILDER)
    decisions = [
        policy.authorize(codex_builder, providers.get('codex_cli'), model_available=True),
        policy.authorize(nvidia_builder, providers.get('nvidia'), model_available=True),
    ]
    assert decisions[0].allowed is False and decisions[0].code == 'RESOURCE_UNAVAILABLE'
    assert decisions[1].allowed is True

    chosen = policy.choose_for_role(decisions, 'BUILDER')
    assert chosen is not None and chosen.provider_id == 'nvidia' and chosen.model_id == NVIDIA_PROVEN
    assert policy.choose_fallback(decisions) is chosen


# ---------------------------------------------------------------------
# 5. No resource available at all -> honest failure, never a fake success
# ---------------------------------------------------------------------

def test_no_authorized_resource_available_yields_honest_failure(tmp_path):
    registry = registry_with(
        tmp_path,
        FakeAdapter('codex_cli', models=['gpt-5.6-luna']),
        FakeAdapter('nvidia', models=[NVIDIA_PROVEN]),
    )
    registry.record_result('codex_cli', 'gpt-5.6-luna',
                           ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='sem cota'))
    registry.record_result('nvidia', NVIDIA_PROVEN,
                           ProviderResult(False, availability=Availability.AUTH_REQUIRED, error='sem chave'))
    policy = WorkforcePolicy({})
    providers = {p.id: p for p in registry.list_providers()}
    codex_builder = agent('agent:codex', 'Codex Builder', 'codex_cli', 'gpt-5.6-luna', RoleName.BUILDER)
    nvidia_builder = agent('agent:nvidia', 'Nemotron Builder', 'nvidia', NVIDIA_PROVEN, RoleName.BUILDER)
    decisions = [
        policy.authorize(codex_builder, providers.get('codex_cli'), model_available=True),
        policy.authorize(nvidia_builder, providers.get('nvidia'), model_available=True),
    ]
    assert all(not decision.allowed for decision in decisions)
    assert {decision.code for decision in decisions} == {'RESOURCE_UNAVAILABLE'}
    assert policy.choose_fallback(decisions) is None
    assert policy.choose_for_role(decisions, 'BUILDER') is None
    for decision in decisions:
        assert human_message(decision) == (
            'Esse modelo nao esta respondendo agora (fora do ar ou sem cota). Escolha outro ou tente mais tarde.'
        )


# ---------------------------------------------------------------------
# 6. Reviewer independence preserved even with custom configuration
# ---------------------------------------------------------------------

def test_reviewer_independence_blocks_a_matching_manual_override(tmp_path):
    registry = registry_with(
        tmp_path, FakeAdapter('claude_cli', models=['opus', 'sonnet']), FakeAdapter('nvidia', models=[NVIDIA_PROVEN]),
    )
    policy = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'claude_cli', 'opus', RoleName.BUILDER)
    reviewer = agent('agent:reviewer', 'Reviewer', 'claude_cli', 'sonnet', RoleName.REVIEWER)
    team = [builder, reviewer]

    # Reconfiguring the reviewer onto the builder's exact pair is refused.
    decision, new_document = policy.with_bot_override(
        agent=reviewer, provider_id='claude_cli', model_id='opus', registry=registry, team_agents=team,
    )
    assert not decision.allowed and decision.code == 'REVIEWER_NOT_INDEPENDENT'
    assert new_document is None
    assert 'independente' in human_message(decision) or 'diferente' in human_message(decision)

    # The same rule blocks it from the other direction: reconfiguring the
    # builder onto the reviewer's exact pair.
    decision2, doc2 = policy.with_bot_override(
        agent=builder, provider_id='claude_cli', model_id='sonnet', registry=registry, team_agents=team,
    )
    assert not decision2.allowed and decision2.code == 'REVIEWER_NOT_INDEPENDENT'
    assert doc2 is None

    # A genuinely distinct pair for the reviewer is still allowed.
    decision3, doc3 = policy.with_bot_override(
        agent=reviewer, provider_id='nvidia', model_id=NVIDIA_PROVEN, registry=registry, team_agents=team,
    )
    assert decision3.allowed and decision3.code == 'AUTHORIZED'
    assert doc3 is not None


def test_reviewer_independence_ignores_archived_teammates(tmp_path):
    """An archived agent no longer occupies a role, so it cannot block a pick."""
    registry = registry_with(tmp_path, FakeAdapter('claude_cli', models=['opus', 'sonnet']))
    policy = WorkforcePolicy({})
    archived_builder = agent('agent:old-builder', 'Old Builder', 'claude_cli', 'opus', RoleName.BUILDER)
    archived_builder.archived = True
    reviewer = agent('agent:reviewer', 'Reviewer', 'claude_cli', 'sonnet', RoleName.REVIEWER)

    decision = policy.validate_bot_configuration(
        agent=reviewer, provider_id='claude_cli', model_id='opus', registry=registry,
        team_agents=[archived_builder, reviewer],
    )
    assert decision.allowed


# ---------------------------------------------------------------------
# 7. Listing bots and listing models: coherent data, honest paid/free labels
# ---------------------------------------------------------------------

def test_describe_bots_and_describe_models_are_coherent_and_honestly_labelled(tmp_path):
    registry = registry_with(
        tmp_path,
        FakeAdapter('claude_cli', models=['opus', 'sonnet', 'haiku']),
        FakeAdapter('nvidia', models=[NVIDIA_PROVEN, 'nvidia/llama-3.1-nemotron-70b-instruct']),
    )
    policy = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'claude_cli', 'opus', RoleName.BUILDER)
    reviewer = agent('agent:reviewer', 'Reviewer', 'nvidia', NVIDIA_PROVEN, RoleName.REVIEWER)

    bots = policy.describe_bots([builder, reviewer], registry=registry)
    by_id = {row['agent_id']: row for row in bots}
    assert by_id[builder.id]['provider_id'] == 'claude_cli' and by_id[builder.id]['model_id'] == 'opus'
    assert by_id[builder.id]['cost_label'] == 'Incluso no plano mensal do Alex'
    assert by_id[builder.id]['custom_override'] is False
    assert by_id[reviewer.id]['cost_label'] == 'Gratuito (informado pelo dono)'
    assert by_id[reviewer.id]['provider_availability'] == Availability.AVAILABLE.value
    # The plan-included worker is never described with "gratuito" wording,
    # and the free worker is never described as "incluso no plano" -- the two
    # cost stories must not blur together.
    assert 'ratuito' not in by_id[builder.id]['cost_label']
    assert 'plano' not in by_id[reviewer.id]['cost_label']

    models = policy.describe_models(registry)
    rows = {(row['provider_id'], row['model_id']): row for row in models}
    assert rows[('claude_cli', 'opus')]['authorized'] is True
    assert rows[('claude_cli', 'opus')]['cost_label'] == 'Incluso no plano mensal do Alex'
    assert rows[('nvidia', NVIDIA_PROVEN)]['authorized'] is True
    assert rows[('nvidia', NVIDIA_PROVEN)]['cost_label'] == 'Gratuito (informado pelo dono)'
    # Discovered-but-not-yet-curated model: real, listed, but not authorized,
    # and its cost is honestly unknown rather than assumed free.
    unauthorized_key = ('nvidia', 'nvidia/llama-3.1-nemotron-70b-instruct')
    assert rows[unauthorized_key]['authorized'] is False
    assert rows[unauthorized_key]['cost_label'] == 'Custo desconhecido'


def test_describe_bots_reflects_a_custom_override():
    policy_before = WorkforcePolicy({})
    builder = agent('agent:builder', 'Builder', 'codex_cli', 'gpt-5.6-luna', RoleName.BUILDER)
    overridden_document = {
        **WorkforcePolicy.default_document(),
        'agent_model_overrides': {builder.id: {'provider_id': 'nvidia', 'model_id': NVIDIA_PROVEN}},
    }
    policy_after = WorkforcePolicy(overridden_document)

    before_row = policy_before.describe_bots([builder])[0]
    after_row = policy_after.describe_bots([builder])[0]
    assert before_row['provider_id'] == 'codex_cli' and before_row['custom_override'] is False
    assert after_row['provider_id'] == 'nvidia' and after_row['model_id'] == NVIDIA_PROVEN
    assert after_row['custom_override'] is True
