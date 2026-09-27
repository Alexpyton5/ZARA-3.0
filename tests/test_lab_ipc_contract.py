from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lab_research_and_chat_channels_exist_in_all_ipc_layers():
    preload = (ROOT / "frontend/src/preload.ts").read_text(encoding="utf-8")
    main = (ROOT / "frontend/src/main.ts").read_text(encoding="utf-8")
    types = (ROOT / "frontend/src/renderer/types/global.d.ts").read_text(encoding="utf-8")
    backend = (ROOT / "core/ipc_handlers.py").read_text(encoding="utf-8")

    assert "ipcRenderer.invoke('lab-v1-research-skill'" in preload
    assert "ipcMain.handle('lab-v1-research-skill'" in main
    assert "'lab-v1-research-skill': self.handle_lab_v1_research_skill" in backend
    assert "async def handle_lab_v1_research_skill" in backend
    assert "researchSkill?:" in types

    assert "ipcRenderer.invoke('lab-v1-team-chat'" in preload
    assert "ipcMain.handle('lab-v1-team-chat'" in main
    assert "'lab-v1-team-chat': self.handle_lab_v1_team_chat" in backend
    assert "async def handle_lab_v1_team_chat" in backend
    assert "teamChat?:" in types
