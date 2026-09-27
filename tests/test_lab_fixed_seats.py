"""The eleven Lab seats invite real members; vacant seats never speak."""

import logging

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleBinding, RoleName, Team, TeamMembership
from core.lab_v1.domain import Session
from core.lab_v1.fixed_seats import FIXED_SEATS, InvitationDenied, invited_agents, run_invited_turn, seat_snapshot
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


def _team_with_eleven_seats(tmp_path):
    store = LabStore(tmp_path / 'lab-v1.db')
    store.initialize()
    store.save_team(Team('lab-team', 'ZARA Lab'))
    for role in FIXED_SEATS:
        agent = AgentProfile(
            id=f'agent-{role.value}', name=role.value, provider_id='fake',
            model='free-model', role=role, capabilities=['model.text'],
        )
        store.save_agent(agent)
        store.save_membership(TeamMembership(
            id=f'member-{role.value}', team_id='lab-team', agent_id=agent.id,
        ))
        store.save_role_binding(RoleBinding(
            id=f'binding-{role.value}', team_id='lab-team', role=role, agent_id=agent.id,
        ))
    return store


def test_eleven_fixed_seats_have_distinct_names():
    assert [role.value for role in FIXED_SEATS] == [
        'CEO', 'ARCHITECT', 'UI_DESIGNER', 'ENGINEER', 'SCRIBE',
        'REVIEWER', 'CRITIC', 'SECRETARY', 'TESTER', 'RESEARCHER', 'PACKAGER',
    ]


def test_only_two_invited_members_receive_a_turn(tmp_path, caplog):
    store = _team_with_eleven_seats(tmp_path)
    called = []
    caplog.set_level(logging.INFO)

    def fake_speak(agent):
        called.append(agent.id)
        logging.info('fake Lab turn: %s', agent.id)

    turn = run_invited_turn(
        store, 'lab-team', [RoleName.ARCHITECT, RoleName.TESTER],
        authorize=lambda agent: True, speak=fake_speak,
    )
    assert called == ['agent-ARCHITECT', 'agent-TESTER']
    assert turn['spoken_agent_ids'] == called
    assert len(turn['silent_agent_ids']) == 9
    assert not set(turn['silent_agent_ids']) & set(called)
    assert len(caplog.records) == 2
    assert len(store.list_agents(team_id='lab-team')) == 11


def test_vacant_or_unauthorized_seat_cannot_be_invited(tmp_path):
    store = _team_with_eleven_seats(tmp_path)
    with pytest.raises(InvitationDenied):
        invited_agents(store, 'lab-team', [RoleName.MEMBER], authorize=lambda agent: True)
    with pytest.raises(InvitationDenied):
        invited_agents(store, 'lab-team', [RoleName.CEO], authorize=lambda agent: False)
    store.close_role_binding('binding-RESEARCHER', 1.0)
    with pytest.raises(InvitationDenied):
        invited_agents(store, 'lab-team', [RoleName.RESEARCHER], authorize=lambda agent: True)


def test_binding_identity_and_membership_are_rechecked(tmp_path):
    store = _team_with_eleven_seats(tmp_path)
    assert len(seat_snapshot(store, 'lab-team')) == 11
    store.save_agent(AgentProfile('impostor', 'Impostor', 'fake', 'free-model',
                                  role=RoleName.MEMBER, capabilities=['model.text']))
    store.save_membership(TeamMembership('impostor-membership', 'lab-team', 'impostor'))
    store.save_role_binding(RoleBinding('impostor-binding', 'lab-team', RoleName.CEO, 'impostor'))
    with pytest.raises(InvitationDenied):
        invited_agents(store, 'lab-team', [RoleName.CEO], authorize=lambda agent: True)


def test_astra_is_denied_by_default_even_if_ceo_invites():
    policy = WorkforcePolicy({'authorized_models': [
        *WorkforcePolicy.default_document()['authorized_models'],
        'codex_cli/gpt-6-astra',
    ]})
    astra = AgentProfile('astra', 'Astra', 'codex_cli', 'gpt-6-astra', role=RoleName.CEO)
    provider = ProviderInfo('codex_cli', 'Codex', 'test', Availability.AVAILABLE,
                            authenticated=True)
    decision = policy.authorize(astra, provider, model_available=True)
    assert not decision.allowed and decision.code == 'ASTRA_DISABLED'


def test_all_eleven_roles_have_configurable_model_order():
    policy = WorkforcePolicy(WorkforcePolicy.default_document())
    for role in FIXED_SEATS:
        order = policy.document['role_model_preference'][role.value]
        assert order and len(order) >= 2
        assert policy.preference_rank(order[0], role.value) < policy.preference_rank(order[-1], role.value)


def test_configured_fallback_keeps_same_invited_agent_identity(tmp_path):
    class FakeProvider(ProviderAdapter):
        controlled_text_only = True

        def __init__(self, provider_id, availability):
            self.id = self.label = provider_id
            self.availability = availability

        def probe(self):
            return ProviderInfo(self.id, self.label, 'fake', self.availability)

        def complete(self, **kwargs):
            raise AssertionError('selection must not invoke a provider')

    store = _team_with_eleven_seats(tmp_path)
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(FakeProvider('fake', Availability.OFFLINE))
    registry.register(FakeProvider('fallback', Availability.AVAILABLE))
    registry.record_result('fallback', 'free-model', ProviderResult(True, availability=Availability.AVAILABLE))
    policy = WorkforcePolicy({
        'authorized_providers': ['fake', 'fallback'],
        'authorized_models': ['fake/free-model', 'fallback/free-model'],
        'resource_classes': {'fake/*': 'OWNER_REPORTED_FREE', 'fallback/*': 'OWNER_REPORTED_FREE'},
        'seat_resource_fallbacks': {
            'ARCHITECT': [{'provider_id': 'fallback', 'model_id': 'free-model'}],
        },
    })
    engine = Autopilot(LabRuntime(store, registry), root=tmp_path / 'missions', policy=policy)
    selected = engine.candidates('lab-team', RoleName.ARCHITECT)
    assert [agent.id for agent in selected] == ['agent-ARCHITECT']
    decision = engine._decision(selected[0], team_id='lab-team')
    assert decision.allowed and decision.provider_id == 'fallback'
    assert engine._resource_for(selected[0], 'lab-team') == 'provider:fallback/free-model'


@pytest.mark.asyncio
async def test_room_invokes_only_bound_invited_seat_and_blocks_astra(tmp_path):
    class FakeCodex(ProviderAdapter):
        id = label = 'codex_cli'

        def __init__(self):
            self.calls = []

        def probe(self):
            return ProviderInfo(self.id, self.label, 'fake', Availability.AVAILABLE)

        def complete(self, **kwargs):
            self.calls.append(kwargs)
            return ProviderResult(True, text='Resposta simulada', availability=Availability.AVAILABLE,
                                  model_reported=kwargs['model'])

    store = _team_with_eleven_seats(tmp_path)
    store.save_session(Session('test-room', 'lab-team', 'Conversa de teste'))
    for agent in store.list_agents(team_id='lab-team'):
        agent.provider_id, agent.model = 'codex_cli', 'gpt-5.6-sol'
        store.save_agent(agent)
    adapter = FakeCodex()
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(adapter)
    service = LabV1Service()
    service._store = store
    service._runtime = LabRuntime(store, registry)

    answer = await service.room_message('test-room', '@ARCHITECT olá')
    assert answer['success'] and answer['agent_id'] == 'agent-ARCHITECT'
    assert len(adapter.calls) == 1

    store.close_role_binding('binding-CRITIC', 1.0)
    denied = await service.room_message('test-room', '@CRITIC olá')
    assert not denied['success'] and len(adapter.calls) == 1

    ceo = store.get_agent('agent-CEO')
    ceo.model = 'gpt-6-astra'
    store.save_agent(ceo)
    denied_astra = await service.room_message('test-room', '@CEO olá')
    assert not denied_astra['success'] and len(adapter.calls) == 1
