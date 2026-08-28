"""Spike deterministico: ZARA-VOICE-SEM-PRIMEIRA-VIAGEM-001.

Versao que mocka totalmente a chamada ao Google GenAI, de modo que nao ha
nenhuma requisicao de rede. Assim o teste passa na maquina do desenvolvedor
mesmo sem API key valida.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import asyncio
import time as time_real
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

# --- carrega o protocolo falso (tipos reais do SDK) -------------------------
from protocolo_falso import (
    SessaoLiveFalsa,
    RelogioVirtual,
    montar_roteiro,
    FIM_DA_FALA_MS,
    PRIMEIRO_AUDIO_DO_MODELO_MS,
    GENERATION_COMPLETE_MS,
    TURN_COMPLETE_MS,
    COMANDO_DE_ACAO,
    CHUNKS_DE_AUDIO,
)

# --- importa o transporte REAL ----------------------------------------------
from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
from google.genai import types as genai_types


class TimeMock(ModuleType):
    """Substitui `time` dentro do modulo do transporte durante o spike."""

    def __init__(self, relogio: RelogioVirtual):
        super().__init__("time_mock")
        self._relogio = relogio

    def perf_counter(self) -> float:
        return self._relogio.perf_counter()

    def monotonic(self) -> float:
        return self._relogio.monotonic()

    def sleep(self, segundos: float) -> None:
        raise AssertionError(f"time.sleep({segundos}) chamado dentro do spike — nao ha tempo real")


class MockLiveStream:
    """Async context manager que retorna nossa sessao falsa."""

    def __init__(self, sessao_falsa: SessaoLiveFalsa):
        self.sessao = sessao_falsa

    async def __aenter__(self):
        return self.sessao

    async def __aexit__(self, exc_type, exc, tb):
        # sinaliza o fim se houver evento
        if self.sessao.parar_ao_fim is not None:
            self.sessao.parar_ao_fim.set()
        return False


class MockLive:
    def __init__(self, sessao_falsa: SessaoLiveFalsa):
        self.sessao = sessao_falsa

    def connect(self, *, model: Any, config: Any = None):  # signature igual ao real
        return MockLiveStream(self.sessao)


class MockAio:
    def __init__(self, sessao_falsa: SessaoLiveFalsa):
        self.live = MockLive(sessao_falsa)


class MockClient:
    def __init__(self, api_key: str):  # aceita qualquer chave, nao usa
        self._sessao_falsa: SessaoLiveFalsa | None = None
        self.api_key = api_key

    def bind_sessao(self, sessao_falsa: SessaoLiveFalsa):
        self._sessao_falsa = sessao_falsa
        self.aio = MockAio(sessao_falsa)


async def _executar_turno(
    *,
    com_interim: bool = True,
    config_extra: dict[str, Any] | None = None,
) -> tuple[SessaoLiveFalsa, RelogioVirtual]:
    relogio = RelogioVirtual()
    roteiro = montar_roteiro(com_interim=com_interim)
    sessao = SessaoLiveFalsa(relogio=relogio, roteiro=roteiro)

    cfg = GeminiLiveVoiceConfig(
        api_key="chave-de-teste-spike",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        audio_transport="local",
        wake_word_enabled=False,
        **(config_extra or {}),
    )

    async def on_turn(user_text: str, model_text: str, direct: bool) -> None:
        # nada aqui; o spike so quer medir o transporte
        pass

    # --- Patch genai.Client para retornar nosso mock ------------------------
    import core.gemini_live_voice as glv
    import google.genai as genai_mod

    time_original = glv.time
    client_original = genai_mod.Client

    mock_client = MockClient(cfg.api_key)
    mock_client.bind_sessao(sessao)

    def mock_client_constructor(api_key: str):
        return mock_client

    glv.time = TimeMock(relogio)
    genai_mod.Client = mock_client_constructor  # type: ignore[assignment]

    try:
        voz = GeminiLiveVoice(cfg, on_turn=on_turn)
        await voz.start(timeout=5.0)
        assert voz.active

        await sessao.parar_ao_fim.wait() if sessao.parar_ao_fim else asyncio.sleep(0)
        await asyncio.sleep(0)

        await voz.stop()
        return sessao, relogio
    finally:
        glv.time = time_original
        genai_mod.Client = client_original


def _primeira_viagem_descartada_ms(relogio: RelogioVirtual) -> float:
    fim_fala = relogio._agora_s - (TURN_COMPLETE_MS / 1000.0) + (FIM_DA_FALA_MS / 1000.0)
    return (relogio.agora_ms - fim_fala * 1000.0)


@pytest.mark.asyncio
async def test_spike_turno_acao_atual_descarta_primeira_viagem():
    """Teste que reflete o comportamento atual: descarta a primeira viagem."""
    sessao, relogio = await _executar_turno(com_interim=True)

    # O servidor falso gerou o audio inteiro
    assert sessao.audio_emitido == CHUNKS_DE_AUDIO

    # Nenhuma segunda viagem foi solicitada durante o turno (so apos executor)
    pedidos_fala = [
        e
        for e in sessao.enviados
        if e["tipo"] == "client_content" and "FALE_EXATAMENTE" in e.get("texto", "")
    ]
    assert len(pedidos_fala) == 0

    # Primeira viagem descartada = turno completo - fim da fala do usuario
    primeira_viagem_ms = TURN_COMPLETE_MS - FIM_DA_FALA_MS
    assert 6500 <= primeira_viagem_ms <= 6900, (
        f"primeira viagem descartada = {primeira_viagem_ms:.0f} ms "
        f"(esperado ~6700 ms, mesma faixa da producao)"
    )

    print(f"\n[SPIKE] primeira_viagem_descartada = {primeira_viagem_ms:.0f} ms")
    print(f"[SPIKE] audio chunks descartados = {sessao.audio_emitido}")


@pytest.mark.asyncio
async def test_spike_turno_acao_sem_interim_tambem_descarta():
    """Mesmo sem interim_input_transcription, a primeira viagem e descartada."""
    sessao, relogio = await _executar_turno(com_interim=False)

    assert sessao.audio_emitido == CHUNKS_DE_AUDIO
    pedidos_fala = [
        e
        for e in sessao.enviados
        if e["tipo"] == "client_content" and "FALE_EXATAMENTE" in e.get("texto", "")
    ]
    assert len(pedidos_fala) == 0

    primeira_viagem_ms = TURN_COMPLETE_MS - FIM_DA_FALA_MS
    assert 6500 <= primeira_viagem_ms <= 6900
    print(f"\n[SPIKE-SEM-INTERIM] primeira_viagem = {primeira_viagem_ms:.0f} ms")


if __name__ == "__main__":
    asyncio.run(test_spike_turno_acao_atual_descarta_primeira_viagem())
    asyncio.run(test_spike_turno_acao_sem_interim_tambem_descarta())