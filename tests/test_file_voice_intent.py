from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from core.action_registry import ActionResult
from core.file_voice_intent import detect_file_intent
from core.ipc_handlers import IPCHandler


@pytest.mark.parametrize(
    ("phrase", "action", "mutating"),
    [
        ("liste os arquivos em Downloads", "files_list", False),
        ("abra o último arquivo que baixei", "files_open_latest", False),
        ("procure ZARA nos arquivos em Documentos", "files_search", False),
        ("resuma o arquivo nota.txt em Downloads", "files_text_summary", False),
        ("crie o arquivo nota.txt em Downloads com o conteúdo Olá", "files_write", True),
        ("adicione nova linha ao arquivo nota.txt em Downloads", "files_write", True),
        ("sobrescreva o arquivo nota.txt em Downloads com novo", "files_write", True),
        ("renomeie o arquivo nota.txt para final.txt em Downloads", "files_rename", True),
        ("copie o arquivo final.txt de Downloads para Documentos", "files_copy", True),
        ("mova o arquivo final.txt de Downloads para Documentos", "files_move", True),
        ("organize Downloads sem apagar nada", "files_organize_by_extension", True),
    ],
)
def test_closed_file_intents(phrase, action, mutating):
    result = detect_file_intent(phrase)

    assert result is not None
    assert result.action == action
    assert result.mutating is mutating


@pytest.mark.parametrize(
    "phrase",
    [
        "delete tudo em Downloads",
        r"resuma o arquivo ..\secrets.txt em Downloads",
        "execute powershell em Downloads",
    ],
)
def test_file_intents_reject_delete_traversal_and_arbitrary_commands(phrase):
    assert detect_file_intent(phrase) is None


@pytest.mark.asyncio
async def test_latest_download_routes_known_downloads_path(tmp_path, monkeypatch):
    execute = AsyncMock(return_value=ActionResult(
        success=True,
        output="Abri o último download seguro: nota.pdf.",
        data={"name": "nota.pdf", "hwnd": 321, "status": "OPEN_CONFIRMED"},
    ))
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    monkeypatch.setattr("core.actions.os_ops._resolve_safe_folder", lambda folder: tmp_path)
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_file_intent("Zara, abra o último arquivo que baixei")

    assert reply == "Abri o último download seguro: nota.pdf."
    execute.assert_awaited_once_with("files_open_latest", path=str(tmp_path))
    assert handler._operational_context["action_type"] == "window"
    assert handler._operational_context["hwnd"] == 321


@pytest.mark.asyncio
async def test_explicit_file_mutation_routes_confirmed_known_path(tmp_path, monkeypatch):
    execute = AsyncMock(return_value=ActionResult(success=True, output="Written"))
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    monkeypatch.setattr("core.actions.os_ops._resolve_safe_folder", lambda folder: tmp_path)
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_file_intent(
        "crie o arquivo nota.txt em Downloads com o conteúdo Olá"
    )

    assert reply == "Written"
    execute.assert_awaited_once_with(
        "files_write",
        path=str(tmp_path / "nota.txt"),
        content="Olá",
        confirm=True,
    )


def test_text_and_voice_share_file_executor():
    assert "_try_file_intent" in inspect.getsource(IPCHandler.handle_send_message)
    assert "_try_file_intent" in inspect.getsource(IPCHandler._process_voice_message)
