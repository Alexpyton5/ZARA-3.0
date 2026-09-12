import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import IPCHandler
from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig


@pytest.mark.asyncio
@pytest.mark.parametrize('intent,steps', [
    ('abra o youtube e pesquise Bruno Mars e de play no video e se tiver anuncios pule', 4),
    ('abra o youtube e toque uma playlist chill e coloque o volume em 70% e diminua o brilho ao maximo', 4),
])
async def test_owner_compound_examples_without_comma(intent, steps):
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock(return_value='Confirmado pelo executor.')
    result = await handler._try_compound_pc_intent(intent)
    assert 'Resultado por etapa' in result
    assert handler._try_pc_intent.await_count == steps


@pytest.mark.asyncio
async def test_dependent_actions_stop_after_failure():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock(return_value='Não consegui abrir o YouTube.')
    result = await handler._try_compound_pc_intent('abra o youtube e pesquise Bruno Mars')
    assert 'seguintes não foram executadas' in result
    assert handler._try_pc_intent.await_count == 1


@pytest.mark.asyncio
async def test_owner_revoked_announcer_cannot_restart():
    handler = IPCHandler(AsyncMock())
    watcher = SimpleNamespace(parar=AsyncMock())
    handler._vigia = watcher
    await handler._ligar_vigia_das_respostas()
    await handler._ligar_vigia_das_respostas()
    watcher.parar.assert_awaited_once()
    assert handler._vigia is None


@pytest.mark.asyncio
async def test_interrupt_suppresses_late_direct_audio_and_clears_pending_speech():
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key='test'))
    voice._speech_queue = asyncio.Queue()
    done = asyncio.Event()
    await voice._speech_queue.put(('stale announcement', done))
    voice._turn_direct = True
    voice._flush_output = Mock()
    await voice.interrupt_speech()
    assert voice._turn_route_decided and not voice._turn_direct
    assert voice._speech_queue.empty() and done.is_set()
    voice._flush_output.assert_called_once()


@pytest.mark.asyncio
async def test_tts_requests_are_serialized_and_expired_requests_skipped():
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key='test'))
    voice._speech_queue = asyncio.Queue()
    session = SimpleNamespace(send_client_content=AsyncMock())
    types = SimpleNamespace(Content=lambda **kw: kw, Part=lambda **kw: kw)
    first, expired, second = asyncio.Event(), asyncio.Event(), asyncio.Event()
    expired.set()
    for text, done in [('first', first), ('expired', expired), ('second', second)]:
        await voice._speech_queue.put((text, done))
    task = asyncio.create_task(voice._send_speech_loop(session, types))
    try:
        await asyncio.sleep(0)
        assert session.send_client_content.await_count == 1
        first.set()
        await asyncio.sleep(0)
        assert session.send_client_content.await_count == 2
        assert voice._speech_done is second
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
