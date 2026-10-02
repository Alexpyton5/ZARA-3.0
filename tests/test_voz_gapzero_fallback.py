"""GAP-ZERO — FRENTE 1 (Voz): a cadeia de voz degrada graciosamente.

Cascata oficial (02/10, decisao do Alex): Kore -> Edge -> Kokoro (reserva
local). O OmniVoice foi removido do sistema — estes testes provam que o app
NUNCA quebra por voz faltando: a Kore falha -> a Edge assume -> e mesmo sem
voz nenhuma o app continua funcionando (fica calado, texto na tela).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.voice_engine_policy import voice_output_order
from core.voice_fallback import KoreRecoveryPolicy


class _KoreMorta:
    """Kore configurada mas sem rede/cota: falha de verdade."""

    active = True

    def __init__(self):
        self.calls = 0

    async def speak(self, text: str, *, timeout: float) -> bool:
        self.calls += 1
        raise ConnectionError("Kore indisponivel (sem rede/cota)")

    def ultimo_audio_entregue(self):
        return None


class _EdgeLocal:
    """Edge neural local/gratuita: a rede de seguranca da cascata."""

    voice_name = "gapzero-edge"

    def __init__(self):
        self.spoken: list[str] = []

    def play(self, text, voice=None, speed=1.0, blocking=True):
        self.spoken.append(text)


def _politica_rapida() -> KoreRecoveryPolicy:
    return KoreRecoveryPolicy(
        minimum_timeout_seconds=0.01,
        maximum_timeout_seconds=0.01,
        base_timeout_seconds=0,
    )


def _handler(kore, tts_manager) -> IPCHandler:
    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler._tts_initialized = True
    handler._kore_recovery_policy = _politica_rapida()
    handler.gemini_live_voice = kore
    handler.tts_manager = tts_manager
    return handler


@pytest.mark.asyncio
async def test_cascata_cai_na_edge_quando_kore_morre():
    """Kore morta: a Edge fala, sem excecao."""
    edge = _EdgeLocal()
    manager = SimpleNamespace(edge=edge, kokoro=None, gemini=None)
    handler = _handler(_KoreMorta(), manager)

    await handler._speak_response("A voz local assume quando a Kore cai.")

    assert edge.spoken == ["A voz local assume quando a Kore cai."]


@pytest.mark.asyncio
async def test_sem_nenhuma_voz_o_app_continua_funcionando():
    """Pior caso: Kore inativa, Edge/Kokoro/Gemini None.

    O app nao pode levantar excecao: ele fica calado, o texto aparece
    na tela e o estado volta para STANDBY.
    """
    manager = SimpleNamespace(edge=None, kokoro=None, gemini=None)
    kore = _KoreMorta()
    kore.active = False
    handler = _handler(kore, manager)

    await handler._speak_response("Ninguem pode falar agora.")

    standby = [
        call for call in handler.send_event.await_args_list
        if call.args == ("state-change", "STANDBY")
    ]
    assert standby, "o app deve voltar ao estado STANDBY mesmo sem voz"


def test_ordem_de_voz_nunca_contem_omnivoice():
    """O OmniVoice nao existe mais: a ordem nunca pode conte-lo, mesmo se
    alguem pedir pelo nome antigo (mapeia pra kore)."""
    ordem = voice_output_order(
        "omnivoice",
        kore_ready=False,
        edge_ready=True,
        kokoro_ready=False,
    )
    assert "omnivoice" not in ordem
    assert ordem == ("edge",)

    ordem_vazia = voice_output_order(
        "omnivoice",
        kore_ready=False,
        edge_ready=False,
        kokoro_ready=False,
    )
    assert ordem_vazia == ()


def test_ordem_oficial_e_kore_edge_kokoro():
    ordem = voice_output_order(
        "kore",
        kore_ready=True,
        edge_ready=True,
        kokoro_ready=True,
    )
    assert ordem == ("kore", "edge", "kokoro")
