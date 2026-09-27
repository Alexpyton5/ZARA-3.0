import pytest

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult, RoleName, Team
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
    answer = ProviderResult(True, text='Observed tests are required.', availability=Availability.AVAILABLE,
                            model_reported='model')

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


class FakeNvidia(Fake):
    id = 'nvidia'
    label = 'NVIDIA fixture'
    declared_models = (ModelDescriptor('nvidia', 'nvidia/test-a', 'Test A'),)
    state = Availability.UNKNOWN
    answer = ProviderResult(True, text='Observed tests are required.', availability=Availability.AVAILABLE,
                            model_reported='nvidia/test-a', provider_session_id='request-1')


@pytest.fixture
def nvidia_fleet(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    adapter = FakeNvidia()
    registry.register(adapter)
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Test'))
    return runtime, FleetCertification(runtime), adapter


def test_nvidia_unknown_first_call_can_certify_only_matching_reported_model(nvidia_fleet):
    runtime, cert, adapter = nvidia_fleet
    doc = runtime.certify_model(key='first', provider_id='nvidia', model='nvidia/test-a')
    assert doc['state'] == 'COMPLETED'
    assert doc['result']['model_reported'] == 'nvidia/test-a'
    assert doc['result']['provider_session_id'] == 'request-1'
    assert cert.register_proven_agent('first', team_id='team', name='Worker', role=RoleName.MEMBER).model == 'nvidia/test-a'
    repeated = runtime.certify_model(key='first', provider_id='nvidia', model='nvidia/test-a')
    assert repeated['agent_id'] == runtime.store.list_agents()[0].id
    assert repeated['result'] == doc['result']
    assert adapter.calls == 1


@pytest.mark.parametrize(('reported', 'expected_error'), [
    (None, 'MODEL_IDENTITY_MISSING'),
    ('nvidia/test-b', 'MODEL_IDENTITY_MISMATCH'),
])
def test_nvidia_wrong_or_missing_identity_cannot_certify_or_admit(nvidia_fleet, reported, expected_error):
    runtime, cert, adapter = nvidia_fleet
    adapter.answer = ProviderResult(True, text='Some answer', availability=Availability.AVAILABLE,
                                    model_reported=reported, provider_session_id='request-2')

    doc = runtime.certify_model(key='identity-check', provider_id='nvidia', model='nvidia/test-a')

    assert doc['state'] == 'FAILED'
    assert doc['result']['ok'] is False
    assert doc['result']['error'] == expected_error
    assert doc['result']['model_reported'] == reported
    assert doc['result']['provider_session_id'] == 'request-2'
    assert runtime.registry.health_snapshot()['model:nvidia:nvidia/test-a']['availability'] != Availability.AVAILABLE.value
    with pytest.raises(ValueError, match='NO_CALLABLE_PROOF'):
        cert.register_proven_agent('identity-check', team_id='team', name='Worker', role=RoleName.MEMBER)
    assert runtime.certify_model(key='identity-check', provider_id='nvidia', model='nvidia/test-a') == doc
    assert adapter.calls == 1
