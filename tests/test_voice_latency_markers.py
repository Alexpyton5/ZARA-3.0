import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.cronometro import Cronometro
from core.ipc_handlers import IPCHandler


def test_voice_turn_records_pre_brain_latency_markers():
    handler = IPCHandler.__new__(IPCHandler)
    now = time.perf_counter()
    handler.gemini_live_voice = SimpleNamespace(
        ultimo_fim_de_fala=lambda: now - 0.120,
        ultima_transcricao_pronta=lambda: now - 0.080,
    )
    handler._cronometro = Cronometro("Zara, teste", origem="voz")

    speech_end = handler.gemini_live_voice.ultimo_fim_de_fala()
    transcript = handler.gemini_live_voice.ultima_transcricao_pronta()
    handler._cronometro._speech_end_at = speech_end
    handler._cronometro._transcript_ready_at = transcript
    handler._marcar_valor_no_cronometro(
        "speech_end_to_transcript_ms", (transcript - speech_end) * 1000.0
    )

    assert handler._cronometro._marcas["speech_end_to_transcript_ms"] == pytest.approx(40, abs=2)


def test_voice_turn_records_all_requested_latency_deltas():
    handler = IPCHandler.__new__(IPCHandler)
    handler._cronometro = Cronometro("Zara, teste", origem="voz")
    base = time.perf_counter()
    anchors = {
        "speech_end": base,
        "transcript_ready": base + 0.040,
        "brain_request_start": base + 0.055,
        "brain_first_output": base + 0.455,
        "tts_start": base + 0.465,
        "first_audio_played": base + 0.765,
    }
    handler._cronometro._speech_end_at = anchors["speech_end"]
    handler._cronometro._transcript_ready_at = anchors["transcript_ready"]
    handler._cronometro._brain_request_start_at = anchors["brain_request_start"]
    handler._cronometro._brain_first_output_at = anchors["brain_first_output"]
    handler._cronometro._tts_start_at = anchors["tts_start"]

    intervals = {
        "speech_end_to_transcript_ms": (anchors["transcript_ready"] - anchors["speech_end"]) * 1000,
        "speech_end_to_brain_start_ms": (anchors["brain_request_start"] - anchors["speech_end"]) * 1000,
        "brain_start_to_first_output_ms": (anchors["brain_first_output"] - anchors["brain_request_start"]) * 1000,
        "brain_first_output_to_tts_start_ms": (anchors["tts_start"] - anchors["brain_first_output"]) * 1000,
        "tts_start_to_first_audio_ms": (anchors["first_audio_played"] - anchors["tts_start"]) * 1000,
        "speech_end_to_first_audio_ms": (anchors["first_audio_played"] - anchors["speech_end"]) * 1000,
    }
    markers = {
        "speech_end_ms": 0.0,
        "transcript_ready_ms": intervals["speech_end_to_transcript_ms"],
        "brain_request_start_ms": intervals["speech_end_to_brain_start_ms"],
        "brain_first_output_ms": (anchors["brain_first_output"] - anchors["speech_end"]) * 1000,
        "tts_start_ms": (anchors["tts_start"] - anchors["speech_end"]) * 1000,
        "first_audio_played_ms": intervals["speech_end_to_first_audio_ms"],
    }
    for name, value in {**markers, **intervals}.items():
        handler._marcar_valor_no_cronometro(name, value)

    assert set(markers).issubset(handler._cronometro._marcas)
    assert set(intervals).issubset(handler._cronometro._marcas)
    assert handler._cronometro._marcas["first_audio_played_ms"] == pytest.approx(765, abs=2)


@pytest.mark.asyncio
async def test_kore_speak_closes_compact_record_with_first_audio(monkeypatch):
    records = []
    monkeypatch.setattr("core.cronometro._gravar", records.append)

    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler.voice_active = False
    handler.voice_pipeline = None
    handler.tts_manager = None
    now = time.perf_counter()

    live = Mock()
    live.active = True
    live.voice_name = "Kore"
    live.speak = AsyncMock(return_value=True)
    live.marcos_da_segunda_viagem.return_value = {
        "tts_pedido_ate_player_ms": 300,
    }
    live.ultimo_audio_entregue.return_value = now + 0.300
    handler.gemini_live_voice = live

    handler._cronometro = Cronometro("Zara, teste", origem="voz")
    handler._cronometro._speech_end_at = now - 0.500
    handler._cronometro._brain_first_output_at = now - 0.010
    for name, value in {
        "speech_end_ms": 0,
        "transcript_ready_ms": 40,
        "brain_request_start_ms": 55,
        "brain_first_output_ms": 490,
        "speech_end_to_transcript_ms": 40,
        "speech_end_to_brain_start_ms": 55,
        "brain_start_to_first_output_ms": 435,
    }.items():
        handler._marcar_valor_no_cronometro(name, value)

    await handler._speak_response("Resposta curta da Zara.")

    assert len(records) == 1
    stages = records[0]["etapas"]
    expected = {
        "speech_end_ms",
        "transcript_ready_ms",
        "brain_request_start_ms",
        "brain_first_output_ms",
        "tts_start_ms",
        "first_audio_played_ms",
        "speech_end_to_transcript_ms",
        "speech_end_to_brain_start_ms",
        "brain_start_to_first_output_ms",
        "brain_first_output_to_tts_start_ms",
        "tts_start_to_first_audio_ms",
        "speech_end_to_first_audio_ms",
    }
    assert expected.issubset(stages)
    assert stages["speech_end_to_first_audio_ms"] >= stages["tts_start_to_first_audio_ms"]
