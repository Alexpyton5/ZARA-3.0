from core.lab_v1.domain import RoleName, Team
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import CORE_TEAM_NAME, LabRuntime
from core.lab_v1.store import LabStore


def test_ensure_core_team_repairs_empty_existing_team_without_claiming_proof(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('core', CORE_TEAM_NAME, 'Time permanente de trabalho da ZARA.'))
    runtime = LabRuntime(store, ProviderRegistry(tmp_path / 'health.json'))

    team = runtime.ensure_core_team()
    first = store.list_agents(team.id)
    again = runtime.ensure_core_team()
    second = store.list_agents(again.id)

    assert again.id == 'core'
    assert len(first) == len(second) == 4
    assert {agent.role for agent in second} == {RoleName.CEO, RoleName.BUILDER, RoleName.REVIEWER}
    assert all('model.text' not in agent.capabilities for agent in second)
    assert store.active_binding(team.id, RoleName.CEO).agent_id == next(
        agent.id for agent in second if agent.role == RoleName.CEO)
    assert store.active_binding(team.id, RoleName.BUILDER).agent_id == next(
        agent.id for agent in second if agent.name == 'Vulcan')
    assert store.active_binding(team.id, RoleName.REVIEWER).agent_id == next(
        agent.id for agent in second if agent.role == RoleName.REVIEWER)

    ceo = next(agent for agent in second if agent.role == RoleName.CEO)
    ceo.provider_id, ceo.model = 'nvidia', 'moonshotai/kimi-k3'
    store.save_agent(ceo)
    after_fallback = runtime.ensure_core_team()
    preserved = store.list_agents(after_fallback.id)
    assert len(preserved) == 4
    assert next(agent for agent in preserved if agent.role == RoleName.CEO).id == ceo.id
    assert next(agent for agent in preserved if agent.role == RoleName.CEO).model == 'moonshotai/kimi-k3'
    reserve = next(agent for agent in preserved if agent.name == 'Vulcan Reserva')
    assert reserve.role == RoleName.BUILDER
    assert (reserve.provider_id, reserve.model) == ('nvidia', 'moonshotai/kimi-k3')
    assert 'model.text' not in reserve.capabilities
