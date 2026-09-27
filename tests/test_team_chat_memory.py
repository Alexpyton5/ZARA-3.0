from pathlib import Path

import pytest

from core.lab_v1.team_chat_memory import TeamChatMemory
from core.obsidian_memory import ObsidianMemoryManager


def test_team_chat_writes_structured_jsonl_to_obsidian(tmp_path: Path):
    result = TeamChatMemory(ObsidianMemoryManager(tmp_path)).append(
        mission_id="m-1", role="RESEARCHER", state="OBSERVED",
        summary="Fonte oficial observada.", evidence_refs=["sha256:abc"],
        next_action="Enviar ao arquiteto.",
    )
    assert result["success"] is True
    content = Path(result["path"]).read_text(encoding="utf-8")
    assert '"role": "RESEARCHER"' in content
    assert '"state": "OBSERVED"' in content


def test_team_chat_rejects_secret_shaped_content(tmp_path: Path):
    with pytest.raises(ValueError, match="potencialmente sensível"):
        TeamChatMemory(ObsidianMemoryManager(tmp_path)).append(
            mission_id="m-1", role="CEO", state="APPROVED",
            summary="api_key: do-not-write",
        )
