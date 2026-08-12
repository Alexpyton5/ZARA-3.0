"""Voice startup must never freeze ZARA's shared asyncio event loop."""

import asyncio
import sys
import time
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, Mock

from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
from core import ipc_handlers
from core.ipc_handlers import IPCHandler, IPCMessage, _canonical_request


@pytest.mark.asyncio
async def test_blocked_audio_open_times_out_without_blocking_event_loop(monkeypatch):
    fake_sounddevice = SimpleNamespace()
    fake_genai = SimpleNamespace()
    fake_types = SimpleNamespace()
    fake_google = SimpleNamespace(genai=fake_genai)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    fake_genai.types = fake_types

    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key="test"))
    heartbeat = asyncio.Event()

    def slow_open(_sd, _generation):
        time.sleep(0.15)
        return False

    monkeypatch.setattr(voice, "_open_streams", slow_open)

    async def tick():
        await asyncio.sleep(0.01)
        heartbeat.set()

    ticker = asyncio.create_task(tick())
    with pytest.raises(RuntimeError, match="VOICE_START_TIMEOUT"):
        await voice.start(timeout=0.03)
    await ticker

    assert heartbeat.is_set()
    assert voice.active is False


@pytest.mark.asyncio
async def test_gemini_transcript_with_wake_routes_through_local_command_pipeline():
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await handler._on_gemini_live_turn("Zara, que horas são?", "draft remoto")

    handler._process_voice_message.assert_awaited_once_with("que horas são?")


def test_voice_and_text_wake_prefixes_share_one_canonical_request():
    expected = "diminua o volume."
    assert _canonical_request("diminua o volume.") == expected
    assert _canonical_request("Zara, diminua o volume.") == expected
    assert _canonical_request("Ei Zara, diminua o volume.") == expected


@pytest.mark.asyncio
async def test_wake_only_arms_one_followup_command():
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await handler._on_gemini_live_turn("Zara", "draft")
    handler._process_voice_message.assert_not_awaited()

    await handler._on_gemini_live_turn("abra o Chrome", "draft")
    handler._process_voice_message.assert_awaited_once_with("abra o Chrome")


@pytest.mark.asyncio
async def test_speech_without_wake_is_ignored():
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await handler._on_gemini_live_turn("conversa ao fundo", "draft")

    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_spoken_zara_stop_interrupts_kore_without_llm_route():
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()
    handler.gemini_live_voice = SimpleNamespace(
        active=True,
        interrupt_speech=AsyncMock(),
    )

    await handler._on_gemini_live_turn("Zara, pare", "draft")

    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()
    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_response_prefers_kore_live_voice_over_windows_fallback(monkeypatch):
    handler = IPCHandler(AsyncMock())
    handler.tts_manager = None
    handler.voice_pipeline = None
    handler.voice_active = True
    handler.send_event = AsyncMock()
    live = SimpleNamespace(
        active=True,
        speak=AsyncMock(return_value=True),
        pause_input=Mock(),
        resume_input=Mock(),
    )
    handler.gemini_live_voice = live
    sapi = Mock()
    monkeypatch.setattr(ipc_handlers, "_speak_windows_sapi", sapi)

    await handler._speak_response("Volume definido para 40%.")

    live.speak.assert_awaited_once_with("Volume definido para 40%.")
    live.pause_input.assert_not_called()
    live.resume_input.assert_not_called()
    sapi.assert_not_called()


@pytest.mark.asyncio
async def test_manual_interrupt_stops_kore_live_output():
    handler = IPCHandler(AsyncMock())
    handler.tts_manager = None
    handler.voice_pipeline = None
    handler.send_event = AsyncMock()
    handler.gemini_live_voice = SimpleNamespace(
        active=True,
        interrupt_speech=AsyncMock(),
    )

    await handler.handle_interrupt(IPCMessage(type="interrupt", request_id="stop"))

    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_interrupt_callback_updates_barge_in_state():
    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler._voice_speaking = True

    await handler._on_gemini_live_interrupt()

    assert handler._voice_speaking is False
    handler.send_event.assert_any_await('state-change', 'LISTENING')
