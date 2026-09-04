from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_compound_local_commands_are_preflighted_and_run_in_order():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock(
        side_effect=(
            "Brilho definido para 40% e confirmado.",
            "Luz noturna ativada e confirmada.",
            "Downloads aberto e verificado.",
        )
    )

    reply = await handler._try_compound_pc_intent(
        "Zara, brilho em 40%, ative a luz noturna, abra Downloads"
    )

    assert reply == (
        "Resultado por etapa: 1) Brilho definido para 40% e confirmado. "
        "2) Luz noturna ativada e confirmada. 3) Downloads aberto e verificado."
    )
    assert [call.args[0] for call in handler._try_pc_intent.await_args_list] == [
        "brilho em 40%",
        "ative a luz noturna",
        "abra Downloads",
    ]


@pytest.mark.asyncio
async def test_compound_request_executes_nothing_when_one_step_is_unknown():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock()

    reply = await handler._try_compound_pc_intent(
        "Zara, brilho em 40%, faça uma coisa desconhecida, abra Downloads"
    )

    assert "não é suportada" in reply
    handler._try_pc_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_comma_text_is_not_treated_as_compound_pc_control():
    handler = IPCHandler(AsyncMock())

    assert await handler._try_compound_pc_intent("Olá, como você está?") is None


def test_text_and_voice_entrypoints_share_compound_executor():
    text_source = inspect.getsource(IPCHandler.handle_send_message)
    voice_source = inspect.getsource(IPCHandler._process_voice_message)

    assert "_try_compound_pc_intent" in text_source
    assert "_try_compound_pc_intent" in voice_source
