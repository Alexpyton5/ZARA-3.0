from pathlib import Path

from core.lab_v1.service import LabV1Service


def test_unknown_research_operation_is_rejected_without_side_effect(tmp_path: Path):
    service = LabV1Service()
    service._research_skill_pipeline = None
    result = __import__('asyncio').run(service.research_skill_pipeline('delete_everything', {}))
    assert result['success'] is False
    assert 'desconhecida' in result['error']


def test_team_chat_rejects_invalid_role_and_state(tmp_path: Path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    from core.lab_v1.team_chat_memory import TeamChatMemory
    from core.obsidian_memory import ObsidianMemoryManager
    service = LabV1Service()
    service._team_chat_memory = TeamChatMemory(ObsidianMemoryManager(vault))
    result = __import__('asyncio').run(service.append_team_chat({
        'mission_id': 'm-1', 'role': 'UNKNOWN', 'state': 'OBSERVED', 'summary': 'não deve salvar'
    }))
    assert result['success'] is False
    assert result['state'] == 'REJECTED'
    assert not list(vault.rglob('*.md'))
