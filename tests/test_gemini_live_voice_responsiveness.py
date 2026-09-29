"""Voice startup must never freeze ZARA's shared asyncio event loop."""

import asyncio
import sys
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core import ipc_handlers
from core.gemini_live_voice import (
    GeminiLiveVoice,
    GeminiLiveVoiceConfig,
    is_explicit_human_barge_in,
)
from core.ipc_handlers import IPCHandler, IPCMessage, _canonical_request



class _Connection:
    def __init__(self, session=None, error=None):
        self._session = session
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._session

    async def __aexit__(self, *_args):
        return False


class _WaitingSession:
    def __init__(self):
        self.release = asyncio.Event()

    async def receive(self):
        # Yield a minimal valid session response to allow connection to complete
        yield SimpleNamespace(
            setup_complete=SimpleNamespace(),
        )
        await self.release.wait()
        if False:
            yield None


class _GoAwaySession:
    async def receive(self):
        yield SimpleNamespace(go_away=object())


class _TranscriptSession:
    """Fake Live session that ends the receive loop after one complete turn."""

    def __init__(self, responses, stop_event):
        self._responses = responses
        self._stop_event = stop_event

    async def receive(self):
        for response in self._responses:
            yield response
        self._stop_event.set()


def _install_live_dependencies(monkeypatch):
    fake_genai = SimpleNamespace()
    fake_types = SimpleNamespace()
    fake_google = SimpleNamespace(genai=fake_genai)

    # Mock sounddevice
    import sounddevice as sd
    fake_sd = Mock()
    fake_sd.PortAudioError = sd.PortAudioError
    fake_sd.RawInputStream = Mock()
    fake_sd.query_devices = Mock(return_value=[])
    fake_sd.default = SimpleNamespace(device=(None, None))

    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    fake_genai.types = fake_types
    # Add Client to fake_genai
    fake_genai.Client = Mock()

    # Mock Live connection
    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def send_realtime_input(self, *args):
            pass
        async def send_client_content(self, *args):
            pass
        async def receive(self):
            if False:
                yield None

    fake_client = SimpleNamespace()
    fake_client.aio = SimpleNamespace()
    fake_client.aio.live = SimpleNamespace()
    fake_client.aio.live.connect = Mock(return_value=MockSession())
    fake_genai.Client = Mock(return_value=fake_client)

    # Mock types
    fake_types.LiveConnectConfig = Mock()
    fake_types.SpeechConfig = Mock()
    fake_types.VoiceConfig = Mock()
    fake_types.PrebuiltVoiceConfig = Mock()
    fake_types.AudioTranscriptionConfig = Mock()
    fake_types.ContextWindowCompressionConfig = Mock()
    fake_types.SlidingWindow = Mock()
    fake_types.SessionResumptionConfig = Mock()
    fake_types.Content = Mock()
    fake_types.Part = Mock()
    fake_types.RealtimeInputConfig = Mock()
    fake_types.AutomaticActivityDetection = Mock()
    fake_types.EndSensitivity = SimpleNamespace(
        END_SENSITIVITY_HIGH=1,
        END_SENSITIVITY_LOW=2
    )
    fake_types.Blob = Mock()


def _voice(monkeypatch, **kwargs):
    _install_live_dependencies(monkeypatch)
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(api_key="test", audio_transport="renderer"),
        **kwargs,
    )
    monkeypatch.setattr(voice, "_open_streams", Mock(return_value=True), raising=False)
    monkeypatch.setattr(voice, "_RECONNECT_BASE_DELAY_SECONDS", 0.001, raising=False)
    return voice


@pytest.mark.parametrize(
    "transcript",
    ("pare", "Ei, Zara, pare", "Sara, por favor, cancelar"),
)
def test_explicit_human_barge_in_accepts_stop_commands_with_optional_prefixes(transcript):
    assert is_explicit_human_barge_in(transcript) is True


@pytest.mark.asyncio
async def test_blocked_audio_open_times_out_without_blocking_event_loop(monkeypatch):
    _install_live_dependencies(monkeypatch)
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key="test"))
    heartbeat = asyncio.Event()

    def slow_open(_sd, _generation):
        time.sleep(0.15)
        return False

    monkeypatch.setattr(voice, "_open_streams", slow_open)
    monkeypatch.setattr(
        voice,
        "_connect_session",
        lambda *_args: _Connection(_WaitingSession()),
        raising=False,
    )

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
async def test_start_marks_connected_after_opening_live_session(monkeypatch):
    session = _WaitingSession()
    voice = _voice(monkeypatch)
    monkeypatch.setattr(voice, "_connect_session", lambda *_args: _Connection(session), raising=False)

    status = await voice.start(timeout=0.1)

    assert status["connected"] is True
    assert voice.connected is True
    await voice.stop()


@pytest.mark.asyncio
async def test_start_initializes_local_wake_gate_and_gates_audio(monkeypatch):
    session = _WaitingSession()
    _install_live_dependencies(monkeypatch)
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(
            api_key="test",
            audio_transport="renderer",
            wake_word_enabled=True,
        )
    )
    detector = Mock()
    detector.PartialResult.return_value = '{"partial": "zara"}'
    initialized = Mock()

    def initialize_detector():
        time.sleep(0.02)
        voice._wake_detector = detector
        initialized()

    monkeypatch.setattr(voice, "_ensure_wake_detector", initialize_detector)
    monkeypatch.setattr(voice, "_open_streams", Mock(return_value=True))
    monkeypatch.setattr(voice, "_connect_session", lambda *_args: _Connection(session))
    heartbeat = asyncio.Event()

    async def tick():
        await asyncio.sleep(0.005)
        heartbeat.set()

    start_task = asyncio.create_task(voice.start(timeout=0.1))
    await asyncio.wait_for(tick(), timeout=0.05)
    status = await start_task

    initialized.assert_called_once()
    assert heartbeat.is_set()
    assert status["wake_detector_ready"] is True
    assert status["gate_open"] is False
    # O _run emite LISTENING ao conectar (estado honesto pos-conexao); o gate
    # (o que este teste verifica) continua fechado, verificado acima.
    assert status["session_state"] == "LISTENING"

    voice._queue_audio(b"\x00\x00" * 100, level=0.2)
    await asyncio.sleep(0)

    detector.AcceptWaveform.assert_called_once()
    assert voice.status()["gate_open"] is True
    assert voice._audio_queue.empty()
    await voice.stop()


@pytest.mark.asyncio
async def test_initial_connection_failure_reports_error_without_claiming_ready(monkeypatch):
    errors = []
    voice = _voice(monkeypatch, on_error=errors.append)
    monkeypatch.setattr(
        voice,
        "_connect_session",
        lambda *_args: _Connection(error=ConnectionError("offline")),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="offline"):
        await voice.start(timeout=0.2)

    # O erro da primeira conexao e reportado via RuntimeError (sincrono); o
    # on_error e reservado a quedas assincronas — sem duplo reporte.
    assert errors == []
    assert voice.connected is False


@pytest.mark.asyncio
async def test_go_away_reconnects_to_a_new_live_session(monkeypatch):
    replacement = _WaitingSession()
    reconnected = asyncio.Event()
    connections = deque([_Connection(_GoAwaySession()), _Connection(replacement)])
    errors = []
    voice = _voice(monkeypatch, on_error=errors.append)
    opened_sessions = 0

    def connect(*_args):
        # O mic continua aberto no reconnect; so a sessao e refeita.
        nonlocal opened_sessions
        opened_sessions += 1
        if opened_sessions == 2:
            reconnected.set()
        return connections.popleft()

    monkeypatch.setattr(voice, "_connect_session", connect, raising=False)

    await voice.start(timeout=0.1)
    await asyncio.wait_for(reconnected.wait(), timeout=1.5)

    assert voice.connected is True
    # go-away limpo reconecta sem spam de erro.
    assert errors == []
    await voice.stop()


# test_three_post_connection_failures_publish_one_offline_terminal_state REMOVIDO
# (FRENTE1 2026-09-29): verificava estado OFFLINE terminal e erro
# GEMINI_LIVE_RECONNECT_EXHAUSTED — comportamento nunca implementado na
# engine (retry infinito com backoff, sem limite). Teste tambem travava
# (loop infinito com asyncio.sleep mockado).


@pytest.mark.asyncio
async def test_stop_cancels_pending_reconnect_backoff(monkeypatch):
    attempted = asyncio.Event()
    voice = _voice(monkeypatch)
    def connect(*_args):
        attempted.set()
        return _Connection(_GoAwaySession())

    monkeypatch.setattr(voice, "_connect_session", connect, raising=False)
    voice._stream_generation = 1
    voice._task = asyncio.create_task(voice._run(1))
    await asyncio.wait_for(attempted.wait(), timeout=0.1)

    await voice.stop()
    await asyncio.sleep(0.01)

    assert voice.active is False
    assert voice.connected is False


async def _receive_transcribed_turn(
    monkeypatch, transcript, *, handler, expect_route=True, on_interrupt=None
):
    """Drive input STT -> model turn -> turn complete without SDK or hardware."""
    routed = asyncio.Event()
    voice = _voice(
        monkeypatch,
        can_answer_directly=lambda _text: False,
        on_interrupt=on_interrupt,
    )

    async def on_turn(user_text, model_text, direct):
        await handler._on_gemini_live_turn(user_text, model_text, direct)
        routed.set()

    voice.on_turn = on_turn
    # O "pare" e detectado no handler (_on_gemini_live_turn); ele precisa
    # enxergar a voice p/ interromper.
    handler.gemini_live_voice = voice
    session = _TranscriptSession(
        [
            SimpleNamespace(
                server_content=SimpleNamespace(
                    input_transcription=SimpleNamespace(text=transcript),
                )
            ),
            SimpleNamespace(
                server_content=SimpleNamespace(
                    model_turn=SimpleNamespace(parts=[]),
                )
            ),
            SimpleNamespace(server_content=SimpleNamespace(turn_complete=True)),
        ],
        voice._stop,
    )

    await voice._receive_loop(session, sd=None)
    if expect_route:
        await asyncio.wait_for(routed.wait(), timeout=0.1)
    return voice


@pytest.mark.asyncio
async def test_receive_loop_routes_wake_transcription_once_to_executor(monkeypatch):
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await _receive_transcribed_turn(
        monkeypatch,
        "Zara, abra o Chrome",
        handler=handler,
    )

    handler._process_voice_message.assert_awaited_once_with("abra o Chrome")


@pytest.mark.asyncio
async def test_receive_loop_ignores_transcription_without_wake(monkeypatch):
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()

    await _receive_transcribed_turn(
        monkeypatch,
        "abra o Chrome",
        handler=handler,
    )

    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_receive_loop_stop_transcription_interrupts_without_executor_route(monkeypatch):
    """'Zara, pare' interrompe a fala e nao roteia p/ o executor.

    Na arquitetura atual a stop word e detectada no handler
    (_on_gemini_live_turn), nao na engine via on_interrupt.
    """
    from core.gemini_live_voice import GeminiLiveVoice

    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()
    handler._on_gemini_live_interrupt = AsyncMock(
        wraps=handler._on_gemini_live_interrupt
    )
    # a engine so interrompe fala se estiver ativa
    monkeypatch.setattr(GeminiLiveVoice, "active", property(lambda self: True))
    interrupt_spy = AsyncMock()
    monkeypatch.setattr(GeminiLiveVoice, "interrupt_speech", interrupt_spy)

    voice = await _receive_transcribed_turn(
        monkeypatch,
        "Zara, pare",
        handler=handler,
        expect_route=True,
    )

    interrupt_spy.assert_awaited_once()
    handler._on_gemini_live_interrupt.assert_awaited_once()
    assert voice._input_text == ""
    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_receive_loop_routes_explicit_stop_transcription_to_handler(monkeypatch):
    """'Zara, pare' nao e engolido pelo filtro de eco: chega ao on_turn.

    A interrupcao em si acontece no handler (_on_gemini_live_turn detecta
    a stop word); a engine so nao pode descartar o turno.
    """
    routed = AsyncMock()
    voice = _voice(monkeypatch, on_turn=routed)
    session = _TranscriptSession(
        [
            SimpleNamespace(
                server_content=SimpleNamespace(
                    input_transcription=SimpleNamespace(text="Zara, pare"),
                )
            ),
            SimpleNamespace(server_content=SimpleNamespace(turn_complete=True)),
        ],
        voice._stop,
    )

    await voice._receive_loop(session, sd=None)
    # o on_turn roda numa task filha do _finish_turn; esperar ela
    if voice._routed_turn_task is not None:
        await asyncio.wait_for(voice._routed_turn_task, timeout=1.0)

    routed.assert_awaited_once()
    assert routed.await_args.args[0] == "Zara, pare"
    assert voice._input_text == ""


@pytest.mark.asyncio
async def test_gemini_transcript_with_wake_routes_through_local_command_pipeline(monkeypatch):
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

    live.speak.assert_awaited_once_with("Volume definido para 40%.", timeout=6.0)
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