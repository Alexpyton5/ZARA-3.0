from core.lab_v1.domain import AgentProfile, Availability, ProviderResult, RoleName, TeamMembership
from core.lab_v1.router import TaskRouter
from test_lab_fleet_certification import fleet, Fake
import pytest


def test_catalog_is_unproven_and_provider_quota_wins(fleet):
    runtime, _, fake = fleet
    registry = runtime.registry
    assert registry.model_status('fake', 'model')['availability'] == 'DISCOVERED_UNPROVEN'
    registry.record_result('fake', 'model', fake.answer)
    assert registry.model_status('fake', 'model')['availability'] == 'AVAILABLE'
    registry.record_result('fake', 'other', ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED))
    assert registry.model_status('fake', 'model')['availability'] == 'QUOTA_EXHAUSTED'
    registry.record_result('fake', 'model', fake.answer)
    assert registry.model_status('fake', 'model')['availability'] == 'AVAILABLE'
    fake.state = Availability.DISABLED_BY_OWNER_POLICY
    registry.invalidate_probe_cache('fake')
    assert registry.model_status('fake', 'model')['availability'] == 'DISABLED_BY_OWNER_POLICY'


def test_profile_role_effort_preference_and_fallback(fleet):
    runtime, _, fake = fleet
    runtime.registry.record_result('fake', 'model', fake.answer)
    for name, role in [('Lead', RoleName.CEO), ('Worker', RoleName.MEMBER)]:
        runtime.store.save_agent(AgentProfile(name, name, 'fake', 'model', role=role, capabilities=['model.text'], effort='low'))
        runtime.store.save_membership(TeamMembership('member-'+name, 'team', name))
    router = TaskRouter(runtime)
    selected = router.select('team', 'analysis', complexity='low')
    assert selected.agent_id == 'Worker' and selected.options.effort == 'low'
    assert router.select('team', 'planning').agent_id == 'Lead'
    assert router.select('team', 'planning', exclude=('Lead',)).reason == 'compatible_role_fallback'
    with pytest.raises(ValueError, match='WAITING_NAMED_AGENT'):
        router.select('team', 'planning', preferred_name='Unavailable')
    with pytest.raises(ValueError, match='NO_PROVEN'):
        router.select('team', 'research', free_only=True)
