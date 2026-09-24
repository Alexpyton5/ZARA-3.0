import pytest

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, Team, TeamMembership
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.fleet import FleetCertification


class Fake(ProviderAdapter):
    id = 'fake'
    label = 'Offline fixture'
    controlled_text_only = True
    declared_models = (ModelDescriptor('fake', 'model', 'Model', supports_effort=True, effort_levels=('low',)),)
    calls = 0
    state = Availability.AVAILABLE
    answer = ProviderResult(True, text='Observed tests are required.', availability=Availability.AVAILABLE)

    def probe(self):
        return ProviderInfo(self.id, self.label, 'fixture', self.state)

    def complete_with_options(self, **kwargs):
        return self.complete(**kwargs)

    def complete(self, **kwargs):
        self.calls += 1
        return self.answer


@pytest.fixture
def fleet(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    adapter = Fake()
    registry.register(adapter)
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Test'))
    return runtime, FleetCertification(runtime), adapter


def invoke(runtime):
    return runtime.certify_model(key='test-run', provider_id='fake', model='model', effort='low')


def test_profile_requires_real_result_and_restart_does_not_retry(fleet):
    runtime, cert, fake = fleet
    with pytest.raises(ValueError, match='NO_CALLABLE_PROOF'):
        cert.register_proven_agent('missing', team_id='team', name='Worker', role=RoleName.MEMBER)
    doc = invoke(runtime)
    assert doc['state'] == 'COMPLETED' and runtime.store.list_agents() == []
    assert invoke(runtime) == doc and fake.calls == 1
    agent = cert.register_proven_agent('test-run', team_id='team', name='Worker', role=RoleName.MEMBER)
    assert agent.model == 'model' and agent.effort == 'low'
    assert FleetCertification(runtime).register_proven_agent('test-run', team_id='team', name='Worker', role=RoleName.MEMBER).id == agent.id


def test_successful_proof_promotes_existing_non_callable_profile(fleet):
    runtime, cert, fake = fleet
    placeholder = AgentProfile('placeholder', 'Worker', 'fake', 'model', role=RoleName.MEMBER)
    runtime.store.save_agent(placeholder)
    runtime.store.save_membership(TeamMembership('member:placeholder', 'team', placeholder.id))

    invoke(runtime)
    proven = cert.register_proven_agent(
        'test-run', team_id='team', name='Worker', role=RoleName.MEMBER)

    assert proven.id == placeholder.id
    assert proven.capabilities == ['model.text']
    assert len(runtime.store.list_agents(team_id='team')) == 1
    assert fake.calls == 1


def test_successful_fallback_proof_retargets_the_existing_core_role_profile(fleet):
    runtime, cert, fake = fleet
    placeholder = AgentProfile('artemis', 'Artemis', 'claude_cli', 'opus', role=RoleName.CEO)
    runtime.store.save_agent(placeholder)
    runtime.store.save_membership(TeamMembership('member:artemis', 'team', placeholder.id))

    invoke(runtime)
    proven = cert.register_proven_agent(
        'test-run', team_id='team', name='Artemis', role=RoleName.CEO,
        placeholder_id=placeholder.id)

    assert proven.id == placeholder.id
    assert (proven.provider_id, proven.model) == ('fake', 'model')
    assert proven.capabilities == ['model.text']
    assert len(runtime.store.list_agents(team_id='team')) == 1
    assert fake.calls == 1


@pytest.mark.parametrize('state', [Availability.AUTH_REQUIRED, Availability.DISABLED_BY_OWNER_POLICY, Availability.OFFLINE])
def test_owner_and_auth_blocks_never_call(fleet, state):
    runtime, _, fake = fleet
    fake.state = state
    assert invoke(runtime)['state'] == 'FAILED' and fake.calls == 0


def test_quota_never_creates_agent_or_retries(fleet):
    runtime, cert, fake = fleet
    fake.answer = ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='QUOTA_EXHAUSTED')
    assert invoke(runtime)['result']['availability'] == Availability.QUOTA_EXHAUSTED
    assert invoke(runtime)['state'] == 'FAILED' and fake.calls == 1
    with pytest.raises(ValueError):
        cert.register_proven_agent('test-run', team_id='team', name='Worker', role=RoleName.MEMBER)


def test_invalid_effort_makes_no_call(fleet):
    runtime, _, fake = fleet
    with pytest.raises(ValueError, match='UNSUPPORTED_EFFORT'):
        runtime.certify_model(key='test-run', provider_id='fake', model='model', effort='ultra')
    assert fake.calls == 0
