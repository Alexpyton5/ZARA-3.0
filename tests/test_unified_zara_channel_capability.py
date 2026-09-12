"""Owner physical blocker: text/voice are channels into one capable ZARA."""
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage
from core.reminder_engine import ReminderEngine
from core.reminder_intent import detect_reminder_intent
from core.lab_v1.service import LabV1Service
from test_front_brain import front


def _handler():
    sent = []

    async def send(message):
        sent.append(message)

    handler = IPCHandler(send)
    handler._append_conversation_message = AsyncMock()
    handler._marcar_canal = Mock()
    handler._speak_response = AsyncMock()
    handler._enrich_with_memory = AsyncMock(side_effect=lambda text: text)
    for name in (
        '_try_jarvis_multi_action', '_try_operational_memory_intent',
        '_try_self_knowledge', '_try_file_intent',
        '_try_compound_pc_intent', '_try_pc_intent',
    ):
        setattr(handler, name, AsyncMock(return_value=None))
    return handler, sent


def test_owner_calendar_phrase_creates_persisted_reminder_with_receipt(tmp_path):
    engine = ReminderEngine(tmp_path / 'reminders.db')
    text = (
        'o nome da minha esposa é Alice, ela faz aniversário no dia 18-09 '
        'crie um lembrete para as 10 horas da manhã no dia 18-09-2099 '
        'onde você irá desejar feliz aniversário para ela.'
    )
    result = detect_reminder_intent(text, engine)

    assert result.kind == 'reminder'
    assert result.reminder_id.startswith('REM-')
    stored = ReminderEngine(tmp_path / 'reminders.db').get(result.reminder_id)
    assert stored is not None
    assert stored.id == result.reminder_id
    assert stored.state == 'SCHEDULED'
    assert 'Alice' in stored.message
    due = datetime.fromtimestamp(stored.due_at_utc)
    assert (due.year, due.month, due.day, due.hour, due.minute) == (2099, 9, 18, 10, 0)
    assert result.reminder_id in result.reply


def test_meta_question_about_creating_reminders_has_no_side_effect(tmp_path):
    engine = ReminderEngine(tmp_path / 'reminders.db')
    result = detect_reminder_intent('como criar um lembrete para amanhã?', engine)
    assert result.kind == 'not_reminder'
    assert engine.list() == []


@pytest.mark.asyncio
async def test_text_owner_phrase_uses_real_engine_before_front_brain(tmp_path):
    handler, sent = _handler()
    handler.reminder_engine = ReminderEngine(tmp_path / 'reminders.db')
    handler._front_conversation_reply = AsyncMock(side_effect=AssertionError('model fallback forbidden'))

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='text-reminder', payload={
            'message': (
                'o nome da minha esposa é Alice, ela faz aniversário no dia 18-09 '
                'crie um lembrete para as 10 horas da manhã no dia 18-09-2099 '
                'onde você irá desejar feliz aniversário para ela.'
            )
        },
    ))

    stored = handler.reminder_engine.scheduled()
    assert len(stored) == 1
    assert 'Alice' in stored[0].message
    response = next(frame.response for frame in sent if frame.request_id == 'text-reminder')
    assert response['engine'] == 'reminder'
    assert response['response_origin'] == 'local_deterministic'
    assert stored[0].id in response['response']
    handler._front_conversation_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_reminder_is_factual_and_never_reaches_model():
    handler, sent = _handler()
    handler.reminder_engine = None
    handler._front_conversation_reply = AsyncMock(side_effect=AssertionError('model fallback forbidden'))

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='unavailable', payload={
            'message': 'crie um lembrete para as 10 horas no dia 18-09-2099 para ligar para Alice'
        },
    ))

    response = next(frame.response for frame in sent if frame.request_id == 'unavailable')
    assert response['engine'] == 'reminder'
    assert response['response_origin'] == 'local_deterministic'
    assert 'não está agendado' in response['response'].casefold()
    assert 'vou te lembrar' not in response['response'].casefold()
    handler._front_conversation_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_and_voice_use_same_reminder_engine_and_handler(tmp_path):
    handler, _ = _handler()
    engine = ReminderEngine(tmp_path / 'reminders.db')
    handler.reminder_engine = engine
    handler._front_conversation_reply = AsyncMock(side_effect=AssertionError('model fallback forbidden'))

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='text', payload={
            'message': 'me lembre de tarefa por texto daqui a 30 minutos'
        },
    ))
    await handler._process_voice_message('me lembre de tarefa por voz daqui a 40 minutos')

    assert handler.reminder_engine is engine
    assert {item.message for item in engine.scheduled()} == {'tarefa por texto', 'tarefa por voz'}
    handler._front_conversation_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_front_brain_receives_factual_identity_channel_and_capabilities(front, monkeypatch):
    _, runtime, adapter = front
    handler, _ = _handler()
    service = LabV1Service()
    service._runtime, service._store = runtime, runtime.store
    handler.lab_v1 = service
    handler.reminder_engine = Mock()
    monkeypatch.setattr('core.ipc_handlers._looks_like_unhandled_local_action', lambda _text: False)

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='identity', payload={'message': 'qual é meu nome?'},
    ))
    await handler._process_voice_message('continue a conversa')

    assert len(adapter.calls) == 2
    text_prompt, voice_prompt = adapter.calls[0]['prompt'], adapter.calls[1]['prompt']
    assert 'runtime=ZARA_DESKTOP' in text_prompt
    assert 'identity=ZARA' in text_prompt
    assert 'channel=TEXT' in text_prompt
    assert 'reminders=AVAILABLE' in text_prompt
    assert 'session_id=session_zara_front_v1' in text_prompt
    assert 'channel=VOICE' in voice_prompt
    for call in adapter.calls:
        instructions = call['system']
        assert 'mesma ZARA' in instructions
        assert 'ambiente separado' in instructions


@pytest.mark.asyncio
async def test_front_brain_reports_actual_unavailable_capability_context(front):
    _, runtime, adapter = front
    handler, _ = _handler()
    service = LabV1Service()
    service._runtime, service._store = runtime, runtime.store
    handler.lab_v1 = service
    handler.reminder_engine = None

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='capability', payload={
            'message': 'quais capacidades estão disponíveis?'
        },
    ))

    assert 'runtime=ZARA_DESKTOP' in adapter.calls[0]['prompt']
    assert 'channel=TEXT' in adapter.calls[0]['prompt']
    assert 'reminders=UNAVAILABLE' in adapter.calls[0]['prompt']


@pytest.mark.asyncio
async def test_owner_voice_and_lab_questions_never_reach_front_brain(tmp_path):
    handler, sent = _handler()
    # Restore the production self-knowledge method hidden by the common fixture.
    handler._try_self_knowledge = IPCHandler._try_self_knowledge.__get__(handler, IPCHandler)
    handler.voice_pipeline = object()
    handler.lab = object()
    handler._front_conversation_reply = AsyncMock(
        side_effect=AssertionError('model fallback forbidden')
    )

    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='voice-status', payload={
            'message': 'o sistema novo de voz da zara já foi implementado ou ainda usa gemini?'
        },
    ))
    await handler._process_voice_message('o zara lab já está totalmente funcional?')

    responses = [frame for frame in sent if frame.type in {'response', 'message'}]
    assert len(responses) >= 2
    assert any((getattr(frame, 'response', None) or {}).get('engine') == 'self_knowledge' for frame in responses)
    assert any((getattr(frame, 'message', None) or {}).get('engine') == 'self_knowledge' for frame in responses)
    handler._front_conversation_reply.assert_not_awaited()
