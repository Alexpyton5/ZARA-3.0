"""The Zoe mic must reach Muse, and speech IPC must reflect finished playback."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage


@pytest.mark.asyncio
async def test_gemini_transcript_reaches_only_zoe():
    handler = IPCHandler(AsyncMock())
    handler._voice_target = "zoe"
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()
    handler._append_conversation_message = AsyncMock()

    await handler._on_gemini_live_turn("Oi, Zoe", "rascunho do Gemini")

    handler.send_event.assert_awaited_once_with(
        "zoe-voice-input", {"text": "Oi, Zoe", "source": "gemini_live"}
    )
    handler._process_voice_message.assert_not_awaited()
    handler._append_conversation_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_zoe_stop_word_interrupts_speech_without_becoming_a_muse_question():
    handler = IPCHandler(AsyncMock())
    handler._voice_target = 'zoe'
    handler.gemini_live_voice = Mock(active=True)
    handler.gemini_live_voice.interrupt_speech = AsyncMock()
    handler._on_gemini_live_interrupt = AsyncMock()
    handler.send_event = AsyncMock()
    await handler._on_gemini_live_turn('para', '')
    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()
    handler._on_gemini_live_interrupt.assert_awaited_once()
    handler.send_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_transcript_rearms_mic_for_next_zoe_turn():
    handler = IPCHandler(AsyncMock())
    handler._voice_target = "zoe"
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()
    handler.voice_pipeline = Mock()

    await handler._on_speech_recognized(" abra o bloco de notas ")

    handler.send_event.assert_awaited_once_with(
        "zoe-voice-input", {"text": "abra o bloco de notas", "source": "local"}
    )
    handler.voice_pipeline.resume_listening.assert_called_once_with(require_wake_word=False)
    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_zoe_uses_live_transcription_without_gemini_answer(monkeypatch):
    class Live:
        active = False

        async def start(self, timeout):
            self.active = True
            return {"session_state": "LISTENING", "audio_transport": "renderer"}

    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler.gemini_live_voice = Live()
    handler._ligar_vigia_das_respostas = AsyncMock()

    await handler.handle_voice_start(
        IPCMessage(type="voice-start", request_id="zoe-1", payload={"target": "zoe"})
    )

    assert handler._voice_target == "zoe"
    assert handler.voice_active is True
    assert handler.gemini_live_voice.can_answer_directly("qualquer coisa") is False
    assert any(call.args[0].type == "response" for call in sent.await_args_list)


@pytest.mark.asyncio
async def test_zoe_speech_response_waits_for_real_local_playback(monkeypatch):
    from core.voice_preferences import load_voice_output_engine

    monkeypatch.setattr("core.voice_preferences.load_voice_output_engine", lambda: "omnivoice")
    timeline: list[str] = []

    async def send(message):
        if message.type == "response":
            timeline.append("response")

    class TTS:
        def initialize(self):
            return None

        def speak(self, text, *, blocking):
            assert text == "Olá Alex"
            assert blocking is True
            timeline.append("playback")
            return True

    handler = IPCHandler(send)
    handler.tts_manager = TTS()
    await handler.handle_zoe_voice_speak(
        IPCMessage(type="zoe-voice-speak", request_id="speak-1", payload={"text": "Olá Alex"})
    )

    assert timeline == ["playback", "response"]


@pytest.mark.asyncio
async def test_zoe_does_not_report_speech_after_interrupted_playback(monkeypatch):
    monkeypatch.setattr("core.voice_preferences.load_voice_output_engine", lambda: "omnivoice")

    class TTS:
        def initialize(self):
            return None

        def speak(self, text, *, blocking):
            return False

    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler.tts_manager = TTS()

    await handler.handle_zoe_voice_speak(
        IPCMessage(type="zoe-voice-speak", request_id="speak-interrupted", payload={"text": "Olá"})
    )

    replies = [call.args[0] for call in sent.await_args_list if call.args[0].type == "response"]
    assert len(replies) == 1
    assert replies[0].response is None
    assert "interrompida" in replies[0].error


@pytest.mark.asyncio
async def test_zoe_kore_speaks_through_live_audio_before_local_fallback(monkeypatch):
    monkeypatch.setattr("core.voice_preferences.load_voice_output_engine", lambda: "kore")

    class Live:
        active = True

        async def speak(self, text, *, timeout):
            self.spoken = text
            return True

        def ultimo_audio_entregue(self):
            return 1.0

    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler._voice_target = "zoe"
    handler.gemini_live_voice = Live()
    handler.tts_manager = None

    await handler.handle_zoe_voice_speak(
        IPCMessage(type="zoe-voice-speak", request_id="speak-2", payload={"text": "Resposta da Zoe"})
    )

    assert handler.gemini_live_voice.spoken == "Resposta da Zoe"
    response = next(call.args[0] for call in sent.await_args_list if call.args[0].type == "response")
    assert response.response == {"success": True, "engine": "kore"}


@pytest.mark.asyncio
async def test_zoe_kore_timeout_falls_back_once_and_recovers_next_reply(monkeypatch):
    from core.voice_fallback import KoreRecoveryPolicy
    monkeypatch.setattr("core.voice_preferences.load_voice_output_engine", lambda: "kore")
    handler = IPCHandler(AsyncMock())
    handler._voice_target = "zoe"
    handler._tts_initialized = True
    handler._kore_recovery_policy = KoreRecoveryPolicy(
        minimum_timeout_seconds=0.01, maximum_timeout_seconds=0.01,
        base_timeout_seconds=0,
    )
    class Live:
        active = True
        calls = 0
        async def speak(self, text, *, timeout):
            self.calls += 1
            if self.calls == 1:
                await asyncio.Event().wait()
            return True
        def ultimo_audio_entregue(self):
            return 1.0 if self.calls > 1 else None
        def pause_input(self): pass
        def resume_input(self): pass
    handler.gemini_live_voice = Live()
    handler.tts_manager = Mock()
    handler.tts_manager.speak.return_value = True
    for text in ['Primeiro', 'Segundo']:
        await asyncio.wait_for(handler.handle_zoe_voice_speak(
            IPCMessage(type='zoe-voice-speak', request_id=text, payload={'text': text})
        ), timeout=0.2)
    handler.tts_manager.speak.assert_called_once_with('Primeiro', blocking=True)
    assert handler.gemini_live_voice.calls == 2
    assert handler._kore_recovery_policy.current_engine == 'kore'


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['interrupted', 'stopped', 'partial-audio'])
async def test_zoe_never_restarts_fallback_after_stop_or_partial_audio(monkeypatch, reason):
    monkeypatch.setattr("core.voice_preferences.load_voice_output_engine", lambda: "kore")
    sent = AsyncMock()
    handler = IPCHandler(sent)
    handler._voice_target = "zoe"
    handler._tts_initialized = True
    class Live:
        active = True
        async def speak(self, text, *, timeout=None):
            if reason == 'interrupted': handler._fala_interrompida = True
            if reason == 'stopped': handler._voice_target = 'zara'
            return False
        def ultimo_audio_entregue(self):
            return 1.0 if reason == 'partial-audio' else None
        def pause_input(self): pass
        def resume_input(self): pass
    handler.gemini_live_voice = Live()
    handler.tts_manager = Mock()
    handler.tts_manager.speak.return_value = True
    await handler.handle_zoe_voice_speak(
        IPCMessage(type='zoe-voice-speak', request_id='cancelled', payload={'text':'Não repita'})
    )
    handler.tts_manager.speak.assert_not_called()
    replies = [c.args[0] for c in sent.await_args_list if c.args[0].type == 'response']
    assert len(replies) == 1
    assert replies[0].error
