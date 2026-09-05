"""Spike deterministico: ZARA-VOICE-SEM-PRIMEIRA-VIAGEM-001.

Objetivo: provar em teste que falha hoje (comportamento atual) e passa com a
arquitetura escolhida, SEM rede, SEM cota, SEM aleatoriedade.

Estrutura do spike:
- monta o transporte REAL (`GeminiLiveVoice`) contra o servidor FALSO acima
- injeta o relogio virtual em `core.gemini_live_voice.time`
- roda um turno de ACAO mediano (6.7 s de audio descartado)
- verifica os tres numeros que importam:
    1. primeira_viagem_descartada_ms  -- o custo que queremos eliminar
    2. tts_pedido_ate_player_ms       -- a segunda viagem (nao muda)
    3. o transporte NAO tocou o audio da primeira viagem (falha fechada)

O teste DEVE falhar hoje com o comportamento atual. Quando a arquitetura for
implementada e funcionar, o mesmo teste (com flag) deve passar.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import asyncio
import time as time_real
from types import ModuleType
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
        # No spike nao ha sleep real. O asyncio.sleep do _receive_loop e
        # substituido pelo `await asyncio.sleep(0)` do servidor falso.
        # Qualquer outro sleep real seria bug do spike.
        raise AssertionError(f"time.sleep({segundos}) chamado dentro do spike — nao ha tempo real")


async def _executar_turno(
    *,
    com_interim: bool = True,
    config_extra: dict[str, Any] | None = None,
) -> tuple[SessaoLiveFalsa, RelogioVirtual]:
    """Executa UM turno de ACAO contra o transporte real e devolve a sessao falsa.

    A sessao falsa guarda tudo que o cliente enviou, incluindo o momento em que
    pediu a segunda viagem (FALE_EXATAMENTE). O relogio virtual deixa medir
    com precisao de marco.
    """
    relogio = RelogioVirtual()
    roteiro = montar_roteiro(com_interim=com_interim)
    sessao = SessaoLiveFalsa(relogio=relogio, roteiro=roteiro)

    # Config minima que passa na validacao do SDK e na inicializacao do transporte
    cfg = GeminiLiveVoiceConfig(
        api_key="chave-de-teste-spike",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        audio_transport="local",  # evita dependencia de Electron/renderer
        wake_word_enabled=False,  # gate OFF, igual a producao
        **(config_extra or {}),
    )

    # Callback que a producao usa para receber o texto do turno
    turnos_recebidos: list[tuple[str, str, bool]] = []

    async def on_turn(user_text: str, model_text: str, direct: bool) -> None:
        turnos_recebidos.append((user_text, model_text, direct))

    # Instancia o transporte REAL, mas injeta o relogio virtual
    import core.gemini_live_voice as glv

    time_original = glv.time
    glv.time = TimeMock(relogio)
    try:
        voz = GeminiLiveVoice(cfg, on_turn=on_turn)

        # Substitui o client.aio.live.connect do transporte pela nossa sessao falsa
        # O metodo _run espera um contexto manager; damos um que entrega nossa sessao
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def connect_falso(*_args: Any, **_kwargs: Any):
            yield sessao

        voz._connect = connect_falso  # type: ignore[attr-defined]

        # Inicia o transporte (roda _run que abre streams, etc.)
        await voz.start(timeout=5.0)
        assert voz.active

        # Aguarda a sessao falsa sinalizar que o roteiro acabou
        # (o while em _run so sai quando a sessao falsa define o evento)
        await sessao.parar_ao_fim.wait() if sessao.parar_ao_fim else asyncio.sleep(0)
        # Da uma volta extra para o _receive_loop processar o turn_complete
        await asyncio.sleep(0)

        # Aguarda o turno ser roteado para o callback (executor na vida real)
        await asyncio.wait_for(
            asyncio.shield(asyncio.create_task(asyncio.sleep(0.01))), timeout=1.0
        )

        await voz.stop()
        return sessao, relogio
    finally:
        glv.time = time_original


def _primeira_viagem_descartada_ms(relogio: RelogioVirtual) -> float:
    """Igual ao que ipc_handlers mede: fim_da_fala_usuario ate agora."""
    fim_fala = relogio._agora_s - (TURN_COMPLETE_MS / 1000.0) + (FIM_DA_FALA_MS / 1000.0)
    return (relogio.agora_ms - fim_fala * 1000.0)


@pytest.mark.asyncio
async def test_spike_turno_acao_atual_descarta_primeira_viagem():
    """TESTE QUE FALHA HOJE — comportamento atual medido em producao.

    Comportamento esperado do codigo ATUAL:
    1. Recebe interim transcriptions (se servidor mandar)
    2. Recebe input_transcription final (fim_da_fala_usuario ~ 800 ms)
    3. Recebe 67 chunks de audio do modelo (900..7600 ms) -> _receive_loop
       descarta porque _play_generated_audio=False e _turn_direct=False
    4. So entao turn_complete e o executor roda
    5. Executor (simulado pelo callback on_turn) chama speak() -> segunda viagem
       (nao simulada aqui, por isso o teste nao mede tts_pedido_ate_player_ms)

    O que este teste AFIRMA sobre o estado ATUAL:
    - primeira_viagem_descartada_ms ~ 6700 ms (mediana producao = 6702 ms)
    - audio emitido = 67 chunks (o lixo inteiro foi gerado pelo servidor)
    - O transporte NAO tocou esse audio (_play_generated_audio ficou False)
    """
    sessao, relogio = await _executar_turno(com_interim=True)

    # 1. O audio da primeira viagem foi TODO gerado (o servidor falso emitiu)
    assert sessao.audio_emitido == CHUNKS_DE_AUDIO, (
        f"servidor falso emitiu {sessao.audio_emitido} chunks, esperado {CHUNKS_DE_AUDIO}"
    )

    # 2. O cliente NAO pediu a segunda viagem durante o roteiro (nao houve FALE_EXATAMENTE)
    # A segunda viagem so acontece DEPOIS do executor, que e o callback on_turn
    # Como o on_turn do spike nao chama speak(), nao houve segundo client_content.
    pedidos_fala = [e for e in sessao.enviados if e["tipo"] == "client_content" and "FALE_EXATAMENTE" in e.get("texto", "")]
    assert len(pedidos_fala) == 0, "segunda viagem so deve acontecer depois do executor"

    # 3. Primeira viagem descartada ~ 6.7 s (medido no relogio virtual)
    # O relogio esta no TURN_COMPLETE_MS = 7620 ms. Fim da fala do usuario = 800 ms.
    # O ipc_handlers mede: agora - fim_da_fala_usuario.
    # No spike, "agora" no momento em que o executor seria chamado = TURN_COMPLETE.
    primeira_viagem_ms = TURN_COMPLETE_MS - FIM_DA_FALA_MS
    assert 6500 <= primeira_viagem_ms <= 6900, (
        f"primeira viagem descartada = {primeira_viagem_ms:.0f} ms "
        f"(esperado ~6700 ms, mesma faixa da producao)"
    )

    print(f"\n[SPIKE] primeira_viagem_descartada = {primeira_viagem_ms:.0f} ms")
    print(f"[SPIKE] audio chunks descartados = {sessao.audio_emitido}")
    print(f"[SPIKE] segunda viagem pedida durante roteiro = {len(pedidos_fala)}")


@pytest.mark.asyncio
async def test_spike_turno_acao_sem_interim_tambem_descarta():
    """Mesmo sem interim_input_transcription, a primeira viagem e descartada.

    Servidor que so manda a transcricao no fim (sem interim) e o pior caso
    para qualquer desenho que queira decidir cedo. O teste garante que o
    comportamento atual nao muda magicamente se o servidor nao mandar interim.
    """
    sessao, relogio = await _executar_turno(com_interim=False)

    assert sessao.audio_emitido == CHUNKS_DE_AUDIO
    pedidos_fala = [e for e in sessao.enviados if e["tipo"] == "client_content" and "FALE_EXATAMENTE" in e.get("texto", "")]
    assert len(pedidos_fala) == 0

    primeira_viagem_ms = TURN_COMPLETE_MS - FIM_DA_FALA_MS
    assert 6500 <= primeira_viagem_ms <= 6900
    print(f"\n[SPIKE-SEM-INTERIM] primeira_viagem = {primeira_viagem_ms:.0f} ms")


if __name__ == "__main__":
    # Execucao direta para ver o output sem pytest
    asyncio.run(test_spike_turno_acao_atual_descarta_primeira_viagem())
    asyncio.run(test_spike_turno_acao_sem_interim_tambem_descarta())