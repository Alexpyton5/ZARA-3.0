from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.pilot_commands import execute_pilot_command


def host():
    names = ('_try_jarvis_multi_action', '_try_reminder_intent', '_try_operational_memory_intent',
             '_try_self_knowledge', '_try_file_intent', '_try_compound_pc_intent',
             '_try_pc_intent', '_try_computer_agent_intent')
    return SimpleNamespace(**{name: AsyncMock(return_value=None) for name in names},
                           _append_conversation_message=AsyncMock())


@pytest.mark.asyncio
async def test_natural_order_uses_existing_pc_executor_and_observed_result():
    target = host()
    async def pc(text):
        target._ultimo_resultado_de_acao = SimpleNamespace(success=True, verificado=True)
        return 'Volume confirmado em 20%'
    target._try_pc_intent.side_effect = pc
    result = await execute_pilot_command(target, 'volume em 20%', channel='whatsapp')
    assert result['handled'] and result['success'] and result['verified']
    target._try_pc_intent.assert_awaited_once_with('volume em 20%')
    target._try_computer_agent_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_does_not_become_success_even_when_reply_is_nonempty():
    target = host()
    async def pc(text):
        target._ultimo_resultado_de_acao = SimpleNamespace(success=False, verificado=False)
        return 'Nao consegui mudar o volume'
    target._try_pc_intent.side_effect = pc
    result = await execute_pilot_command(target, 'volume em 20%')
    assert result['handled'] and not result['success'] and not result['verified']


@pytest.mark.asyncio
async def test_conversation_is_left_to_pilot_without_claiming_pc_action():
    target = host()
    result = await execute_pilot_command(target, 'oi Zoe como vai?')
    assert not result['handled'] and result['response'] == ''
    target._append_conversation_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_file_or_reminder_reply_without_receipt_cannot_claim_success():
    for name in ['_try_file_intent', '_try_reminder_intent']:
        target = host()
        getattr(target, name).return_value = 'Nao consegui concluir'
        result = await execute_pilot_command(target, 'ordem')
        assert result['handled'] and not result['success']


@pytest.mark.asyncio
async def test_malformed_commands_never_reach_executor():
    target = host()
    for value in [{"text": "apague"}, ['abra app'], 9, None]:
        assert not (await execute_pilot_command(target, value))['success']
    target._try_jarvis_multi_action.assert_not_awaited()
