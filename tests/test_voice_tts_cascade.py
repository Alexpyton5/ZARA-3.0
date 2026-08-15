"""Cascata de vozes: a ZARA nunca cai da Kore direto para o SAPI robotico.

Ordem contratada: Kore (Gemini Live) -> Edge neural gratuita -> Kokoro local
-> Gemini HTTP -> Windows SAPI. Estes testes travam os degraus que existiam so
na intencao antes desta tarefa.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core import voice_tts
from core.ipc_handlers import IPCHandler
from core.voice_tts import TTSConfig, TTSManager


class _FakeEngine:
    """Engine de voz que registra o que foi falado, sem tocar audio."""

    def __init__(self, *, fails: bool = False):
        self.fails = fails
        self.spoken: list[str] = []
        self.stopped = False

    def play(self, text, voice=None, speed=1.0, blocking=True):
        if self.fails:
            raise RuntimeError("engine indisponivel")
        self.spoken.append(text)

    def stop(self):
        self.stopped = True


def test_speak_prefers_edge_over_kokoro():
    """Edge e neural e sem cota; Kokoro e a rede de seguranca, nao a padrao."""
    mgr = TTSManager(TTSConfig())
    mgr.edge = _FakeEngine()
    mgr.kokoro = _FakeEngine()

    mgr.speak("Bom dia, Alex.")

    assert mgr.edge.spoken == ["Bom dia, Alex."]
    assert mgr.kokoro.spoken == []


def test_edge_failure_falls_back_to_kokoro_and_never_goes_silent():
    """Sem internet a Edge falha — e a voz local tem de assumir sozinha."""
    mgr = TTSManager(TTSConfig())
    mgr.edge = _FakeEngine(fails=True)
    mgr.kokoro = _FakeEngine()

    mgr.speak("Volume em 40 por cento.")

    assert mgr.kokoro.spoken == ["Volume em 40 por cento."]


def test_interrupt_stops_edge_playback():
    """A Edge toca via MCI, fora do sounddevice: barge-in tem de alcancar ela."""
    mgr = TTSManager(TTSConfig())
    mgr.edge = _FakeEngine()

    mgr.interrupt()

    assert mgr.edge.stopped is True


def test_manager_survives_with_edge_only():
    """Pesos do Kokoro ausentes e sem chave Gemini nao podem deixar a ZARA muda."""
    mgr = TTSManager(TTSConfig(prefer_local=False, gemini_api_key=""))
    mgr.edge = _FakeEngine()

    mgr.speak("Estou aqui.")

    assert mgr.edge.spoken == ["Estou aqui."]


def test_edge_engine_reports_its_own_voice_name_not_gemini_voice():
    """[VOICE_TRACE] tem de nomear a voz que realmente falou."""
    from core.ipc_handlers import _tts_voice_name

    config = TTSConfig(edge_voice="pt-BR-FranciscaNeural", gemini_voice="Puck")
    engine = Mock(spec=["voice_name"])
    engine.voice_name = config.edge_voice

    assert _tts_voice_name(engine) == "pt-BR-FranciscaNeural"


@pytest.mark.asyncio
async def test_speak_response_uses_edge_when_kore_is_unavailable(monkeypatch):
    """Cota da Kore estourada nao pode virar voz robotica do Windows."""
    sapi_calls: list[str] = []
    monkeypatch.setattr(
        "core.ipc_handlers._speak_windows_sapi",
        lambda text: sapi_calls.append(text),
    )

    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler.gemini_live_voice = None
    handler.voice_active = False
    handler.voice_pipeline = None
    handler._tts_initialized = True

    edge = _FakeEngine()
    edge.voice_name = "pt-BR-FranciscaNeural"
    handler.tts_manager = Mock()
    handler.tts_manager.edge = edge
    handler.tts_manager.kokoro = None
    handler.tts_manager.gemini = None

    await handler._speak_response("A cota da Kore acabou.")

    assert edge.spoken == ["A cota da Kore acabou."]
    assert sapi_calls == []


# --------------------------------------------------------------------------
# ZARA-VOZ-UNICA-002 — só Kore e Edge. A voz do Windows saiu de cena.
#
# Alex, depois de ouvir as duas na mesma frase: "eu odeio esta voz". Pior: ele
# interrompeu a Kore no meio de um recado e a voz do Windows continuou lendo o
# texto inteiro, sem obedecer a nenhum pedido de parar.
# --------------------------------------------------------------------------

def _handler_de_voz(**kw):
    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler.gemini_live_voice = kw.get("live")
    handler.voice_active = False
    handler.voice_pipeline = None
    handler._tts_initialized = True
    handler.tts_manager = Mock()
    handler.tts_manager.edge = kw.get("edge")
    handler.tts_manager.kokoro = kw.get("kokoro")
    handler.tts_manager.gemini = kw.get("gemini")
    return handler


@pytest.mark.asyncio
async def test_a_voz_do_windows_nunca_mais_e_chamada(monkeypatch):
    """Nenhuma voz disponível: ela fica calada, não chama o SAPI."""
    chamadas: list[str] = []
    monkeypatch.setattr(
        "core.ipc_handlers._speak_windows_sapi", lambda t: chamadas.append(t)
    )

    handler = _handler_de_voz(edge=None, kokoro=None, gemini=None)

    await handler._speak_response("Ninguém pode falar agora.")

    assert chamadas == [], "a voz do Windows voltou à cascata"


@pytest.mark.asyncio
async def test_interromper_a_kore_nao_faz_outra_voz_recomecar(monkeypatch):
    """Parar é ordem de Alex, não falha da Kore.

    A Kore devolve "não falei" quando é interrompida. A cascata lia isso como
    falha e recomeçava o mesmo texto na voz seguinte — foi assim que ele ouviu
    a voz do Windows terminar de ler um recado que ele tinha mandado parar.
    """
    chamadas: list[str] = []
    monkeypatch.setattr(
        "core.ipc_handlers._speak_windows_sapi", lambda t: chamadas.append(t)
    )

    live = Mock()
    live.active = True
    edge = _FakeEngine()

    async def falar_e_ser_interrompida(_texto, **_kw):
        handler._fala_interrompida = True   # Alex mandou parar no meio
        return False

    live.speak = falar_e_ser_interrompida
    handler = _handler_de_voz(live=live, edge=edge)

    await handler._speak_response("Um recado bem longo do Claude.")

    assert edge.spoken == [], "outra voz recomeçou depois do pedido de parar"
    assert chamadas == []


@pytest.mark.asyncio
async def test_sem_interrupcao_a_edge_ainda_assume(monkeypatch):
    """O degrau legítimo continua: Kore indisponível, Edge fala."""
    monkeypatch.setattr("core.ipc_handlers._speak_windows_sapi", lambda t: None)

    live = Mock()
    live.active = True

    async def nao_falou(_texto, **_kw):
        return False

    live.speak = nao_falou
    edge = _FakeEngine()
    handler = _handler_de_voz(live=live, edge=edge)

    await handler._speak_response("Volume em 30 por cento.")

    assert edge.spoken == ["Volume em 30 por cento."]


def test_chunk_source_returns_partial_data_instead_of_waiting_for_full_block():
    """Bloquear ate encher o bloco anulava o streaming: a ZARA so falava depois
    de sintetizar tudo. Leitura curta e o que faz ela comecar a falar cedo."""
    source = voice_tts._EdgeChunkSource()
    source.feed(b"123")

    assert source.read(4096) == b"123"


def test_chunk_source_signals_end_of_stream_when_finished():
    source = voice_tts._EdgeChunkSource()
    source.feed(b"abc")
    source.finish()

    assert source.read(1024) == b"abc"
    assert source.read(1024) == b""


def test_chunk_source_returns_nothing_after_barge_in():
    """Barge-in tem de cortar o decoder, nao so parar o alto-falante."""
    source = voice_tts._EdgeChunkSource()
    source.feed(b"audio que nao deve mais tocar")
    source.close()

    assert source.read(1024) == b""


def test_edge_requires_backend_installed(monkeypatch):
    """Sem edge-tts instalado, falha honesta e nomeada — nunca silencio."""
    monkeypatch.setattr(voice_tts, "EDGE_TTS_AVAILABLE", False)
    with pytest.raises(Exception) as exc:
        voice_tts.EdgeTTS(TTSConfig())
    assert "TTS_BACKEND_NOT_CONFIGURED" in str(exc.value)
