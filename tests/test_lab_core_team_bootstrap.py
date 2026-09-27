from core.lab_v1.domain import AgentProfile, Lifecycle, RoleName, TeamMembership
from core.lab_v1.providers.registry import default_registry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore


def _runtime(tmp_path):
    return LabRuntime(LabStore(tmp_path / "lab.db"), default_registry())


def test_new_core_team_workers_are_admissible_for_text_work(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()

    agents = runtime.store.list_agents(team_id=team.id)

    assert len(agents) == 5
    assert all("model.text" in agent.capabilities for agent in agents)


def test_existing_core_team_is_migrated_without_touching_other_agents(tmp_path):
    runtime = _runtime(tmp_path)
    team = runtime.ensure_core_team()
    core = runtime.store.list_agents(team_id=team.id)[0]
    core.capabilities = []
    runtime.store.save_agent(core)
    extra = AgentProfile(
        id="agent_custom", name="Custom", provider_id="codex_cli", model="gpt-5.6-luna",
        role=RoleName.MEMBER, lifecycle=Lifecycle.PERMANENT,
    )
    runtime.store.save_agent(extra)
    runtime.store.save_membership(TeamMembership(
        id="member_custom", team_id=team.id, agent_id=extra.id,
    ))

    runtime.ensure_core_team()

    migrated = runtime.store.get_agent(core.id)
    untouched = runtime.store.get_agent(extra.id)
    assert "model.text" in migrated.capabilities
    assert untouched.capabilities == []
