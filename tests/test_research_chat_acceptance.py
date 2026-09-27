from pathlib import Path

from core.lab_v1.research_skill_autopilot import AutonomousResearchSkillPipeline
from core.lab_v1.team_chat_memory import TeamChatMemory
from core.obsidian_memory import ObsidianMemoryManager


def test_full_research_chat_approval_and_rollback(tmp_path: Path):
    pipeline = AutonomousResearchSkillPipeline(tmp_path / "skills", fetcher=lambda _url: b"official release: safe improvement")
    vault = tmp_path / "vault"
    vault.mkdir()
    chat = TeamChatMemory(ObsidianMemoryManager(vault))
    research = pipeline.research("safe improvement", ["https://example.test/release"])
    chat.append(mission_id=research["research_id"], role="RESEARCHER", state="OBSERVED", summary="Evidência coletada.", evidence_refs=[research["findings"][0]["sha256"]], next_action="Arquiteto analisa.")
    candidate = pipeline.create_candidate(skill_id="safe-improvement", version="1.0.0", description="Melhoria segura", permissions=[], research=research)
    chat.append(mission_id=research["research_id"], role="ARCHITECT", state="PLANNED", summary="Candidato aprovado para testes.")
    pipeline.record_test(candidate["skill_id"], candidate["version"], "acceptance", passed=True, summary="Teste controlado passou.")
    activated = pipeline.activate(candidate["skill_id"], candidate["version"], owner_approved=True)
    assert activated["state"] == "ACTIVE"
    pipeline.create_candidate(skill_id="safe-improvement", version="1.1.0", description="Nova versão segura", permissions=[], research=research)
    pipeline.record_test("safe-improvement", "1.1.0", "acceptance", passed=True, summary="Teste passou.")
    pipeline.activate("safe-improvement", "1.1.0", owner_approved=True)
    rolled = pipeline.rollback("safe-improvement", to_version="1.0.0")
    assert rolled["to_version"] == "1.0.0"
    chat.append(mission_id=research["research_id"], role="CEO", state="ROLLED_BACK", summary="Rollback validado.", next_action="Manter versão estável.")
    assert list((vault / "Zara-Memoria" / "Chat-Lab").glob("*.md"))
