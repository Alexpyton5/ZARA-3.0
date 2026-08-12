from unittest.mock import AsyncMock, Mock

import pytest

from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "folder"),
    [
        ("abra Downloads", "downloads"),
        ("vá para Downloads", "downloads"),
        ("mostre Downloads", "downloads"),
        ("abre meus Documentos", "documents"),
        ("mostre Documents", "documents"),
        ("mostre a Área de Trabalho", "desktop"),
        ("vá para Desktop", "desktop"),
        ("abra minhas Imagens", "pictures"),
        ("mostre Pictures", "pictures"),
        ("abra a pasta da ZARA", "zara_root"),
        ("vá para ZARA folder", "zara_root"),
    ],
)
def test_folder_aliases_map_to_closed_allowlist(phrase, folder):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_open"
    assert result.param == folder


@pytest.mark.parametrize(
    "phrase",
    [
        "abra Downloads/../Windows",
        r"abra \\servidor\share",
        "abra https://example.com",
        "abra Downloads && powershell",
        "abra C:/Windows/System32",
        "abra %USERPROFILE%",
        "abra pasta secreta",
    ],
)
def test_freeform_paths_never_map_to_folder_action(phrase):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.action != "os_open"


def test_os_open_rejects_non_allowlisted_path_before_dispatch(monkeypatch):
    startfile = Mock()
    monkeypatch.setattr(os_ops.os, "startfile", startfile)

    result = os_ops.os_open_action(r"..\Windows")

    assert result.success is False
    assert result.data["allowlisted"] is False
    startfile.assert_not_called()


def test_os_open_rejects_missing_known_folder(monkeypatch):
    monkeypatch.setattr(os_ops, "_resolve_safe_folder", lambda folder: None)

    result = os_ops.os_open_action("downloads")

    assert result.success is False
    assert result.data == {"folder": "downloads", "allowlisted": True, "exists": False}


def test_os_open_canonical_path_dispatch_and_verification(monkeypatch, tmp_path):
    canonical = tmp_path.resolve()
    explorer_states = iter(({10}, {10}))
    startfile = Mock()
    monkeypatch.setattr(os_ops, "_resolve_safe_folder", lambda folder: canonical)
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: next(explorer_states))
    monkeypatch.setattr(os_ops.os, "startfile", startfile)
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)

    result = os_ops.os_open_action("downloads")

    assert result.success is True
    assert result.data["path"] == str(canonical)
    assert result.data["verification"] == "EXPLORER_PROCESS_PRESENT"
    startfile.assert_called_once_with(str(canonical))


@pytest.mark.asyncio
async def test_local_folder_dispatch_works_without_superbrain(monkeypatch):
    execute = AsyncMock(
        return_value=type(
            "Result", (),
            {"success": True, "error": "", "output": "Downloads aberto e verificado."},
        )()
    )
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("abra Downloads")

    assert reply == "Downloads aberto e verificado."
    execute.assert_awaited_once_with("os_open", folder="downloads")


@pytest.mark.asyncio
async def test_ipc_routes_only_canonical_folder_id(monkeypatch):
    calls = []

    async def fake_execute_action(action, **params):
        calls.append((action, params))
        return type("Result", (), {"success": True, "error": "", "output": "Solicitação enviada."})()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)

    reply = await handler._try_pc_intent("abra a pasta da ZARA")

    assert calls == [("os_open", {"folder": "zara_root"})]
    assert reply == "Solicitação enviada."
