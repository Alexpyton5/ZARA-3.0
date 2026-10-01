"""The renderer's AEC PCM must stay local when the offline listener starts."""
import base64
from unittest.mock import AsyncMock, Mock
import pytest

from core.ipc_handlers import IPCHandler, IPCMessage


@pytest.mark.asyncio
async def test_zoe_prefers_available_offline_listener_and_does_not_wait_for_cloud(monkeypatch):
    from core import whisper_local
    listener = Mock(active=True)
    monkeypatch.setattr(whisper_local, 'resolve_local_whisper_model', lambda: 'cached-model', raising=False)
    monkeypatch.setattr(whisper_local, 'LocalWhisperVoice', lambda path, callback: listener)
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler._resolve_gemini_key = lambda: ''
    handler.gemini_live_voice = Mock()
    handler.gemini_live_voice.start = AsyncMock()
    await handler.handle_voice_start(IPCMessage(type='voice-start', request_id='offline', payload={'target': 'zoe'}))
    listener.initialize.assert_called_once()
    listener.start.assert_called_once()
    handler.gemini_live_voice.start.assert_not_awaited()
    reply = next(c.args[0].response for c in sent.await_args_list if c.args[0].type == 'response')
    assert reply['success'] and reply['mode'] == 'whisper_local'
    assert reply['audio_transport'] == 'renderer'


@pytest.mark.asyncio
@pytest.mark.parametrize('active', [True, False])
async def test_voice_status_reports_actual_local_worker_readiness(active):
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler.local_whisper_voice = Mock(active=active, last_error=None)
    handler.voice_mode = 'whisper_local'
    await handler.handle_voice_status(IPCMessage(type='voice-status', request_id='status'))
    reply = sent.await_args.args[0].response
    assert reply['stt_ready'] is active
    assert reply['stt_engine'] == 'faster-whisper'
    assert reply['stt_offline'] is True
    assert reply['pipeline_state'] == ('LISTENING' if active else 'STOPPED')


@pytest.mark.asyncio
async def test_offline_mic_pcm_never_leaks_to_gemini():
    handler = IPCHandler(AsyncMock())
    handler.voice_mode = 'whisper_local'
    handler.local_whisper_voice = Mock()
    handler.gemini_live_voice = Mock(usa_renderer=True)
    pcm = b'\x01\x00' * 320
    await handler.handle_voice_mic_chunk(IPCMessage(type='voice-mic-chunk', payload={'pcm': base64.b64encode(pcm).decode()}))
    handler.local_whisper_voice.feed_pcm.assert_called_once_with(pcm)
    handler.gemini_live_voice.push_mic_pcm.assert_not_called()


@pytest.mark.asyncio
async def test_voice_stop_invalidates_offline_listener():
    handler = IPCHandler(AsyncMock())
    listener = Mock()
    handler.local_whisper_voice = listener
    handler.voice_active = True
    handler.voice_mode = 'whisper_local'
    await handler.handle_voice_stop(IPCMessage(type='voice-stop', request_id='stop'))
    listener.stop.assert_called_once()
    assert not handler.voice_active


@pytest.mark.asyncio
@pytest.mark.parametrize('spoken', ['para', 'Para.', 'pare!'])
async def test_offline_stop_word_cuts_output_without_sending_a_question(spoken):
    handler = IPCHandler(AsyncMock())
    handler._voice_target = 'zoe'
    handler.tts_manager = Mock()
    handler.gemini_live_voice = Mock(active=True)
    handler.gemini_live_voice.interrupt_speech = AsyncMock()
    handler.send_event = AsyncMock()
    await handler._on_whisper_text(spoken)
    handler.tts_manager.interrupt.assert_called_once()
    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()
    handler.send_event.assert_any_await('zoe-voice-input', {'text': '', 'interrupt': True})
    assert not any(c.args[1].get('text') == 'para' for c in handler.send_event.await_args_list if isinstance(c.args[1], dict))


@pytest.mark.asyncio
@pytest.mark.parametrize('cloud_state', ['STANDBY', 'STOPPED', 'CONNECTING'])
async def test_kore_transport_state_does_not_disable_local_microphone(cloud_state):
    handler = IPCHandler(AsyncMock())
    handler.voice_mode = 'whisper_local'
    handler.voice_active = True
    handler.local_whisper_voice = Mock(active=True)
    handler.send_event = AsyncMock()
    await handler._on_gemini_live_state(cloud_state)
    assert handler.voice_active
    handler.send_event.assert_awaited_once_with('state-change', 'LISTENING')
