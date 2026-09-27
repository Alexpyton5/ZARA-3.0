from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock

import pytest

import core.actions.os_ops  # noqa: F401 - registers clipboard actions
from core.action_registry import execute_action, get_registry
from core.ipc_handlers import IPCHandler


@pytest.fixture
def clipboard(monkeypatch):
    state = {"value": "ANTES"}
    fake = types.SimpleNamespace(
        paste=lambda: state["value"],
        copy=lambda value: state.__setitem__("value", value),
    )
    monkeypatch.setitem(sys.modules, "pyperclip", fake)
    get_registry().medium_risk_open = False
    monkeypatch.setattr(get_registry(), "pc_control_allowed", True)
    return state


@pytest.mark.asyncio
async def test_voice_write_requires_natural_confirmation_then_readback(clipboard):
    handler = IPCHandler(AsyncMock())
    get_registry().pc_control_allowed = True
    preview = await handler._try_pc_intent(
        "Zara, coloque ‘reunião amanhã às 10’ na área de transferência"
    )
    assert preview == "Posso copiar ‘reunião amanhã às 10’?"
    assert clipboard["value"] == "ANTES"

    reply = await handler._try_pc_intent("Zara, sim")
    assert reply == "Copiado e confirmado."
    assert clipboard["value"] == "reunião amanhã às 10"

    preview = await handler._try_pc_intent("Zara, coloque ZARA_Mantem_Maiusculas na area de transferencia")
    assert "ZARA_Mantem_Maiusculas" in preview
    assert await handler._try_pc_intent("sim") == "Copiado e confirmado."
    assert clipboard["value"] == "ZARA_Mantem_Maiusculas"


@pytest.mark.asyncio
async def test_medium_gate_still_blocks_unconfirmed_write(clipboard):
    result = await execute_action("os_clipboard", text="NÃO DEVE COPIAR")
    assert result.success is False
    assert "MEDIUM" in result.error
    assert clipboard["value"] == "ANTES"


@pytest.mark.asyncio
async def test_cancel_clear_and_sensitive_read_are_honest(clipboard):
    handler = IPCHandler(AsyncMock())
    assert await handler._try_pc_intent("Zara, limpe a área de transferência") == "Posso limpar a área de transferência?"
    assert await handler._try_pc_intent("não") == "Cancelado. Não alterei a área de transferência."
    assert clipboard["value"] == "ANTES"

    clipboard["value"] = "senha: SEGREDO_123"
    reply = await handler._try_pc_intent("Zara, o que está na área de transferência?")
    assert "conteúdo sensível" in reply
    assert "SEGREDO_123" not in reply


@pytest.mark.asyncio
async def test_copy_this_without_text_context_does_not_guess(clipboard):
    handler = IPCHandler(AsyncMock())
    assert await handler._try_pc_intent("Zara, copie isso") == "Qual texto devo colocar na área de transferência?"
    assert clipboard["value"] == "ANTES"
