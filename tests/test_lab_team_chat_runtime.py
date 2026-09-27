from pathlib import Path

from core.lab_v1.domain import AgentProfile, MessageKind, RoleName, Session, Team, TeamMembership
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.team_chat_memory import TeamChatMemory
from core.obsidian_memory import ObsidianMemoryManager


def test_real_agent_baton_is_projected_once_to_the_shared_vault(tmp_path: Path):
    store = LabStore(tmp_path / "lab.db")
    vault = tmp_path / "vault"
    vault.mkdir()
    journal = TeamChatMemory(ObsidianMemoryManager(vault))
    runtime = LabRuntime(store, ProviderRegistry(tmp_path / "health.json"), team_chat=journal)
    team = Team("team", "ZARA Core")
    store.save_team(team)
    ceo = AgentProfile("ceo", "Artemis", "test", "test", role=RoleName.CEO)
    store.save_agent(ceo)
    store.save_membership(TeamMembership("membership", team.id, ceo.id))
    session = Session("session", team.id, "Uma missão real")
    store.save_session(session)

    message = runtime._add_message(
        session, kind=MessageKind.AGENT, author=ceo.name,
        content="Delegação validada com evidência.", author_agent_id=ceo.id,
        run_id="run-real",
    )
    runtime._project_team_chat_message(session, message)  # restart/replay of the same canonical row

    journal_path = next((vault / "Zara-Memoria" / "Chat-Lab").glob("*.md"))
    content = journal_path.read_text(encoding="utf-8")
    assert content.count('"record_id": "' + message.id + '"') == 1
    assert '"role": "CEO"' in content
    assert '"evidence_refs": ["message:' + message.id in content
