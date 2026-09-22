"""Real text/voice IPC entry paths with isolated fake transport and no hardware."""
import asyncio
import threading
from array import array
from unittest.mock import AsyncMock, Mock

import pytest
from core.ipc_handlers import IPCHandler, IPCMessage
from core.conversation_history import ConversationHistory
from core.lab_v1.domain import Availability, ProviderResult
from core.lab_v1.service import LabV1Service
import memory.episodic_memory as episodic_memory
from memory.memory_manager import MemoryManager
from test_front_brain import front


@pytest.fixture
def handler(front, monkeypatch):
    brain, runtime, adapter = front
    h = IPCHandler(AsyncMock())
    service = LabV1Service()
    service._runtime, service._store = runtime, runtime.store
    h.lab_v1 = service
    h.orchestrator = Mock()
    h.orchestrator.process_message = AsyncMock(side_effect=AssertionError('Legacy fallback forbidden'))
    h._append_conversation_message = AsyncMock()
    h._marcar_canal = Mock()
    h._speak_response = AsyncMock()
    h._enrich_with_memory = AsyncMock(side_effect=lambda text: text)
    for name in ('_try_jarvis_multi_action', '_try_reminder_intent', '_try_operational_memory_intent',
                 '_try_self_knowledge', '_try_file_intent', '_try_compound_pc_intent', '_try_pc_intent'):
        setattr(h, name, AsyncMock(return_value=None))
    monkeypatch.setattr('core.ipc_handlers._looks_like_unhandled_local_action', lambda text: False)
    return h, brain, adapter


def test_text_and_voice_share_selected_brain_and_context(handler):
    h, brain, adapter = handler
    async def run():
        await h.handle_send_message(IPCMessage(type='send-message', request_id='t', payload={'message': 'Projeto Horizonte'}))
        await h.handle_engine_change(IPCMessage(type='engine-change', request_id='s', payload={'engine': 'gpt-6-astra'}))
        await h._process_voice_message('Qual e o projeto?')
    asyncio.run(run())
    assert [c['model'] for c in adapter.calls] == ['gpt-5.6-luna', 'gpt-6-astra']
    assert 'Horizonte' in adapter.calls[-1]['prompt']
    h.orchestrator.process_message.assert_not_called()
    h._speak_response.assert_awaited_once()


def test_home_ipc_returns_factual_provenance_for_luna_and_astra(handler):
    h, brain, adapter = handler
    async def run():
        await h.handle_send_message(IPCMessage(type='send-message', request_id='luna', payload={
            'message': 'Ola Luna', 'engine': 'gpt-5.6-luna'}))
        adapter.answer = ProviderResult(True, text='Astra respondeu', availability=Availability.AVAILABLE,
                                        model_reported='gpt-6-astra')
        await h.handle_engine_change(IPCMessage(type='engine-change', request_id='select', payload={
            'engine': 'gpt-6-astra'}))
        await h.handle_send_message(IPCMessage(type='send-message', request_id='astra', payload={
            'message': 'Ola Astra', 'engine': 'gpt-6-astra'}))
    asyncio.run(run())
    responses = {call.args[0].request_id: call.args[0].response for call in h.send.call_args_list
                 if call.args[0].type == 'response'}
    luna = responses['luna']
    assert luna['response_origin'] == 'front_brain_run'
    assert luna['run_id'] and luna['model_requested'] == luna['engine'] == 'gpt-5.6-luna'
    assert luna['model_reported'] is None and luna['provider'] == 'codex_cli'
    astra = responses['astra']
    assert astra['run_id'] and astra['model_requested'] == astra['model_reported'] == 'gpt-6-astra'
    assert astra['provider'] == 'codex_cli' and astra['provenance_status'] == 'MATCHED'
    assert brain.runtime.store.get_run(astra['run_id']).model_reported == 'gpt-6-astra'


def test_model_mismatch_survives_home_ipc_with_run_evidence(handler):
    h, brain, adapter = handler
    adapter.answer = ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE,
                                    error='CODEX_MODEL_MISMATCH', model_reported='gpt-5.6-sol')
    asyncio.run(h.handle_send_message(IPCMessage(type='send-message', request_id='mismatch', payload={
        'message': 'Nao aceite reroute', 'engine': 'gpt-5.6-luna'})))
    frame = next(call.args[0] for call in h.send.call_args_list if call.args[0].request_id == 'mismatch')
    assert frame.error is None
    assert frame.response['success'] is False and frame.response['code'] == 'CODEX_MODEL_MISMATCH'
    assert frame.response['response_origin'] == 'front_brain_run'
    assert frame.response['model_requested'] == 'gpt-5.6-luna'
    assert frame.response['model_reported'] == 'gpt-5.6-sol'
    assert brain.runtime.store.get_run(frame.response['run_id']).model_reported == 'gpt-5.6-sol'


def test_voice_event_carries_success_and_mismatch_provenance(handler):
    h, _, adapter = handler
    asyncio.run(h._process_voice_message('Primeiro turno de voz'))
    success = next(call.args[0].message for call in h.send.call_args_list
                   if call.args[0].type == 'message' and isinstance(call.args[0].message, dict)
                   and call.args[0].message.get('run_id'))
    assert success['model_requested'] == success['engine'] == 'gpt-5.6-luna'
    assert success['model_reported'] is None and success['provider'] == 'codex_cli'

    h.send.reset_mock()
    adapter.answer = ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE,
                                    error='CODEX_MODEL_MISMATCH', model_reported='gpt-5.6-sol')
    asyncio.run(h._process_voice_message('Segundo turno de voz'))
    mismatch = next(call.args[0].message for call in h.send.call_args_list
                    if call.args[0].type == 'message' and isinstance(call.args[0].message, dict)
                    and call.args[0].message.get('run_id'))
    assert mismatch['success'] is False and mismatch['code'] == 'CODEX_MODEL_MISMATCH'
    assert mismatch['model_requested'] == 'gpt-5.6-luna'
    assert mismatch['model_reported'] == 'gpt-5.6-sol'
    assert mismatch['provenance_status'] == 'MISMATCH_REJECTED'


def test_voice_speaks_without_waiting_for_slow_memory_persistence(handler):
    h, _, _ = handler
    persistence_release = asyncio.Event()
    persistence_started = asyncio.Event()

    class SlowMemory:
        async def add_conversation(self, *_args):
            persistence_started.set()
            await persistence_release.wait()
            return 'episode-slow'

    h.memory = SlowMemory()

    async def run():
        await h._process_voice_message('Responda sem esperar o disco')
        assert h._speak_response.await_count == 1
        await asyncio.sleep(0)
        assert persistence_started.is_set()
        assert any(not task.done() for task in h._voice_persistence_tasks)
        persistence_release.set()
        await asyncio.gather(*tuple(h._voice_persistence_tasks))

    asyncio.run(run())


def test_telegram_uses_selected_front_brain_and_canonical_history(handler):
    h, brain, adapter = handler
    h.conversation_history = Mock()
    h.conversation_history.list_recent.return_value = [
        {'role': 'user', 'content': 'Meu marcador anterior e TELEGRAM-HISTORY'},
    ]
    async def run():
        first = await h._responder_ao_celular('zara', 'Qual era meu marcador?', Mock())
        await h.handle_engine_change(IPCMessage(type='engine-change', request_id='premium', payload={
            'engine': 'gpt-6-astra'}))
        second = await h._responder_ao_celular('zara', 'E agora?', Mock())
        return first, second
    first, second = asyncio.run(run())
    assert first and second
    assert [call['model'] for call in adapter.calls] == ['gpt-5.6-luna', 'gpt-6-astra']
    assert 'TELEGRAM-HISTORY' in adapter.calls[0]['prompt']
    assert 'Qual era meu marcador?' in adapter.calls[1]['prompt']
    h.orchestrator.process_message.assert_not_called()
    assert brain.snapshot()['current'] == 'gpt-6-astra'


def test_telegram_never_premium_falls_back_when_luna_is_unavailable(handler):
    h, brain, adapter = handler
    adapter.answer = ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='quota')
    reply = asyncio.run(h._responder_ao_celular('zara', 'Converse comigo', Mock()))
    assert 'quota' in reply.lower() or 'responder' in reply.lower()
    assert [call['model'] for call in adapter.calls] == ['gpt-5.6-luna']
    assert brain.snapshot()['current'] == 'gpt-5.6-luna'
    h.orchestrator.process_message.assert_not_called()


def test_config_set_cannot_bypass_front_selection_policy(handler):
    h, brain, adapter = handler
    asyncio.run(h.handle_config_set(IPCMessage(type='config-set', request_id='c', payload={'key': 'engine', 'value': 'auto_fast'})))
    assert brain.snapshot()['current'] == 'gpt-5.6-luna'
    assert h.send.call_args.args[0].error
    assert not adapter.calls


def test_payload_override_rejected_and_engine_list_has_no_side_effect(handler):
    h, brain, adapter = handler
    async def run():
        await h.handle_send_message(IPCMessage(type='send-message', request_id='p', payload={'message': 'Ola', 'engine': 'gpt-6-astra'}))
        rejected = next(c.args[0] for c in h.send.call_args_list if c.args[0].request_id == 'p')
        assert rejected.error is None and rejected.response['success'] is False
        assert rejected.response['code'] == 'FRONT_SELECTION_CHANGED'
        await h.handle_engine_list(IPCMessage(type='engine-list', request_id='l'))
    asyncio.run(run())
    result = h.send.call_args.args[0].response
    assert result['current'] == 'gpt-5.6-luna'
    assert len(result['engines']) == 4 and not adapter.calls


def test_local_action_keeps_deterministic_path(handler):
    h, brain, adapter = handler
    h.lab_v1._runtime.registry.record_result(
        'codex_cli', 'gpt-5.6-luna',
        ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='quota'),
    )
    h._try_pc_intent = AsyncMock(return_value='Volume verificado.')
    asyncio.run(h.handle_send_message(IPCMessage(type='send-message', request_id='a', payload={'message': 'Abaixe o volume'})))
    assert not adapter.calls
    response = next(c.args[0].response for c in h.send.call_args_list if c.args[0].request_id == 'a')
    assert response['engine'] == 'pc_control'
    assert response['response_origin'] == 'local_deterministic'


def test_lab_submit_is_not_falsely_queued(handler):
    h, _, adapter = handler
    asyncio.run(h.handle_lab_v1_submit(IPCMessage(type='lab-v1-submit', request_id='m', payload={'session_id': 'historical', 'text': 'Trabalhe'})))
    response = h.send.call_args.args[0].response
    assert response['success'] is False and response['code'] == 'WORKFORCE_POLICY_REQUIRED'
    assert not h._lab_v1_background_tasks and not adapter.calls


def test_real_voice_entry_ignores_remote_direct_answer(handler):
    h, _, adapter = handler
    assert h._voice_is_authorized_conversation('Zara, qual e o projeto?') is True
    assert h._voice_can_answer_directly('Zara, qual e o projeto?') is False
    asyncio.run(h._on_gemini_live_turn('Zara, qual e o projeto?', 'Resposta remota proibida', direct=True))
    assert [c['model'] for c in adapter.calls] == ['gpt-5.6-luna']
    assert not any('Resposta remota proibida' in str(c) for c in h._append_conversation_message.call_args_list)


def test_canonical_old_history_and_large_mentor_survive_both_channels(handler):
    h, _, adapter = handler
    h.conversation_history = Mock()
    h.conversation_history.list_recent.return_value = [{'role': 'user', 'content': 'Meu projeto anterior e Aurora'}]
    h.mentor_context = 'Contexto mentor ' * 3000
    asyncio.run(h.handle_send_message(IPCMessage(type='send-message', request_id='old', payload={'message': 'Qual projeto?'})))
    asyncio.run(h._process_voice_message('E o contexto?'))
    assert len(adapter.calls) == 2
    for call in adapter.calls:
        assert 'Aurora' in call['prompt'] and 'Contexto mentor' in call['prompt']
        assert len(call['prompt']) <= 40000


def test_barge_in_fences_blocked_front_result_and_next_turn_recovers(handler):
    h, brain, adapter = handler

    async def run():
        adapter.hold = threading.Event()
        stale = asyncio.create_task(h._process_voice_message('Turno antigo'))
        assert await asyncio.to_thread(adapter.entered.wait, 10)
        await h._on_gemini_live_interrupt()
        adapter.hold.set()
        await stale

        h._speak_response.assert_not_awaited()
        assert not any(
            message.author == 'Alex' and message.content == 'Turno antigo'
            for message in brain.runtime.store.list_messages('session_zara_front_v1')
        )
        assert not any(
            message.author == 'ZARA' and message.content == 'Resposta real do transporte de teste'
            for message in brain.runtime.store.list_messages('session_zara_front_v1')
        )
        assert not any(
            call.args[0].type == 'message'
            and isinstance(call.args[0].message, dict)
            and call.args[0].message.get('content') == 'Resposta real do transporte de teste'
            for call in h.send.call_args_list
        )

        adapter.hold = None
        adapter.entered.clear()
        h._speak_response.reset_mock()
        await h._process_voice_message('Turno novo')
        h._speak_response.assert_awaited_once()

    asyncio.run(run())


def test_real_voice_entry_barge_in_purges_all_context_but_keeps_run(
    handler, tmp_path, monkeypatch
):
    h, brain, _ = handler
    text = 'Retorno antes do pare'
    answer = 'Resposta real do transporte de teste'
    h.conversation_history = ConversationHistory(tmp_path / 'home-history.sqlite3')
    episode_store = episodic_memory.EpisodicMemory(tmp_path / 'episodes.sqlite3')
    monkeypatch.setattr(episodic_memory, '_default_store', episode_store)
    monkeypatch.setattr(
        episodic_memory, '_embed',
        lambda _text: array('f', [0.0]) * episodic_memory.VECTOR_SIZE,
    )
    entered = threading.Event()
    release = threading.Event()
    original_add = episode_store.add

    def hold_episode(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original_add(*args, **kwargs)

    monkeypatch.setattr(episode_store, 'add', hold_episode)
    h.memory = MemoryManager()

    async def run():
        stale = asyncio.create_task(h._on_speech_recognized(text))
        assert await asyncio.to_thread(entered.wait, 10)
        await h._on_gemini_live_interrupt()
        release.set()
        await stale
        if h._voice_persistence_tasks:
            await asyncio.gather(*tuple(h._voice_persistence_tasks))

    asyncio.run(run())
    # The answer may already have started speaking while persistence runs;
    # the live interrupt owns stopping playback. The stale durable context is
    # still purged after the blocked write completes.
    assert h._speak_response.await_count <= 1
    assert not any(message['content'] == text for message in h.conversation_history.list_recent())
    assert not any(
        message.content in {text, answer}
        for message in brain.runtime.store.list_messages('session_zara_front_v1')
    )
    runs = brain.runtime.store.list_runs('session_zara_front_v1')
    assert len(runs) == 1 and brain.runtime.store.get_run(runs[0].id) is not None
    with episode_store._connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM episodes').fetchone()[0] == 0
    # The background write may be attempted, but its durable row is removed
    # above when the generation changes.
