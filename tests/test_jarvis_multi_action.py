from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_jarvis_plan_runs_existing_primitives_and_preserves_partial_failure():
    handler = IPCHandler(AsyncMock())
    handler.supercerebro_active = True
    handler._try_pc_intent = AsyncMock(
        side_effect=(
            "Brilho definido para 45% e confirmado.",
            "Luz noturna ativada e confirmada.",
            "Pasta da ZARA aberta.",
            "Não consegui executar essa ação. MEDIA_COMMAND_SENT_NOT_PROVEN",
        )
    )
    handler._try_operational_memory_intent = AsyncMock(return_value="Falta fechar a FRONT-08.")
    handler._try_reminder_intent = AsyncMock(
        return_value="Certo. Vou te lembrar de revisar daqui a 2 minutos. (id REM-1)"
    )

    reply = await handler._try_jarvis_multi_action(
        "Zara, deixa o computador confortável, abre o projeto, coloca uma música, "
        "vê o que ficou pendente e me lembra de revisar daqui a 2 minutos."
    )

    assert reply is not None
    assert "Plano Jarvis concluído: 4/5" in reply
    assert "[FALHOU] Música" in reply
    assert "MEDIA_COMMAND_SENT_NOT_PROVEN" in reply
    assert "[OK] Pendências" in reply
    assert "[OK] Lembrete" in reply
    assert [call.args[0] for call in handler._try_pc_intent.await_args_list] == [
        "brilho em 45%",
        "ative a luz noturna",
        "abra a pasta da zara",
        "continue a música",
    ]
    handler._try_reminder_intent.assert_awaited_once_with(
        "me lembra de revisar daqui a 2 minutos"
    )


@pytest.mark.asyncio
async def test_jarvis_plan_requires_superbrain_before_any_primitive_runs():
    handler = IPCHandler(AsyncMock())
    handler.supercerebro_active = False
    handler._try_pc_intent = AsyncMock()

    reply = await handler._try_jarvis_multi_action(
        "Zara, deixa o computador confortável, abre o projeto e vê o que ficou pendente."
    )

    assert reply == "Para executar um pedido com várias etapas, ative o Supercérebro."
    handler._try_pc_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_jarvis_plan_keeps_missing_reminder_time_as_pending():
    handler = IPCHandler(AsyncMock())
    handler.supercerebro_active = True
    handler._try_pc_intent = AsyncMock(return_value="Confirmado.")
    handler._try_operational_memory_intent = AsyncMock(return_value="Uma pendência.")
    handler._try_reminder_intent = AsyncMock(return_value="Que horas?")

    reply = await handler._try_jarvis_multi_action(
        "Zara, abre o projeto, coloca uma música, vê o que ficou pendente e me lembra de revisar."
    )

    assert reply is not None
    assert "[PENDENTE] Lembrete: Que horas?" in reply
    assert "3/4" in reply


@pytest.mark.asyncio
async def test_practical_jarvis_plan_completes_five_runtime_proven_domains():
    handler = IPCHandler(AsyncMock())
    handler.supercerebro_active = True
    handler._try_pc_intent = AsyncMock(
        side_effect=(
            "Pasta da ZARA aberta e confirmada.",
            "Downloads aberto e verificado.",
            "CPU 12%, memória 58%, bateria 100%.",
        )
    )
    handler._try_operational_memory_intent = AsyncMock(return_value="Falta revisar o LAB.")
    handler._try_reminder_intent = AsyncMock(
        return_value="Certo. Vou te lembrar de revisar daqui a 2 minutos. (id REM-2)"
    )

    reply = await handler._try_jarvis_multi_action(
        "Zara, abra o projeto, abra Downloads, veja o status do computador, "
        "veja o que ficou pendente e me lembre de revisar daqui a 2 minutos."
    )

    assert reply is not None
    assert "Plano Jarvis concluído: 5/5" in reply
    assert "[OK] Projeto" in reply
    assert "[OK] Downloads" in reply
    assert "[OK] Estado do PC" in reply
    assert "[OK] Pendências" in reply
    assert "[OK] Lembrete" in reply
    assert [call.args[0] for call in handler._try_pc_intent.await_args_list] == [
        "abra a pasta da zara",
        "abra Downloads",
        "como está o computador",
    ]


@pytest.mark.asyncio
async def test_ordinary_conversation_is_not_a_jarvis_plan():
    handler = IPCHandler(AsyncMock())
    assert await handler._try_jarvis_multi_action("Olá, como você está hoje?") is None


def test_text_and_voice_run_jarvis_before_single_domain_handlers():
    text_source = inspect.getsource(IPCHandler.handle_send_message)
    voice_source = inspect.getsource(IPCHandler._process_voice_message)

    assert text_source.index("_try_jarvis_multi_action") < text_source.index("_try_reminder_intent")
    assert voice_source.index("_try_jarvis_multi_action") < voice_source.index("_try_reminder_intent")
