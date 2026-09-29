"""GAP-ZERO — FRENTE 1 (Voz): a cadeia de voz degrada graciosamente
quando o runtime OmniVoice está ausente.

Estado real no PC do Alex (2026-09-28): o runtime nunca foi instalado
(sem venv em %LOCALAPPDATA%\\ZARA3\\runtimes\\omnivoice e sem ready.json).
Estes testes simulam exatamente esse estado e provam que o app NUNCA
quebra por voz faltando: a Kore falha -> o OmniVoice ausente é pulado
sem ser chamado -> a Edge local assume -> e mesmo sem voz nenhuma o
app continua funcionando (fica calado, texto na tela).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.omnivoice_runtime import OmniVoiceWorkerTTS
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


def _runtime_ausente(tmp_path) -> OmniVoiceWorkerTTS:
    """OmniVoiceWorkerTTS real apontando para pastas vazias.

    É exatamente o estado do PC do Alex: o objeto existe no tts_manager,
    mas available é False porque venv e ready.json não existem.
    """
    worker = tmp_path / "omnivoice_worker.py"
    worker.write_text("# worker ausente", encoding="utf-8")
    return OmniVoiceWorkerTTS(
        runtime_root=tmp_path / "runtime",
        data_root=tmp_path / "data",
        worker_path=worker,
    )


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


def test_runtime_ausente_marca_available_false(tmp_path):
    runtime = _runtime_ausente(tmp_path)
    assert runtime.available is False


@pytest.mark.asyncio
async def test_cascata_pula_omnivoice_ausente_e_cai_na_edge(tmp_path):
    """Kore morta + OmniVoice ausente: a Edge fala, sem excecao."""
    omni = _runtime_ausente(tmp_path)
    edge = _EdgeLocal()
    manager = SimpleNamespace(omnivoice=omni, edge=edge, kokoro=None, gemini=None)
    handler = _handler(_KoreMorta(), manager)

    await handler._speak_response("A voz local assume quando a Kore cai.")

    assert omni.available is False
    assert edge.spoken == ["A voz local assume quando a Kore cai."]


@pytest.mark.asyncio
async def test_sem_nenhuma_voz_o_app_continua_funcionando():
    """Pior caso: Kore inativa, OmniVoice ausente, Edge/Kokoro/Gemini None.

    O app nao pode levantar excecao: ele fica calado, o texto aparece
    na tela e o estado volta para STANDBY.
    """
    omni = SimpleNamespace(available=False)
    manager = SimpleNamespace(omnivoice=omni, edge=None, kokoro=None, gemini=None)
    kore = _KoreMorta()
    kore.active = False
    handler = _handler(kore, manager)

    await handler._speak_response("Ninguem pode falar agora.")

    standby = [
        call for call in handler.send_event.await_args_list
        if call.args == ("state-change", "STANDBY")
    ]
    assert standby, "o app deve voltar ao estado STANDBY mesmo sem voz"


def test_ordem_de_voz_nunca_inventa_omnivoice_ausente():
    """Mesmo com OmniVoice selecionado, se o runtime sumiu a ordem nao
    pode conter 'omnivoice': cai para kore/edge ou fica vazia."""
    ordem = voice_output_order(
        "omnivoice",
        kore_ready=False,
        omnivoice_ready=False,
        edge_ready=True,
        kokoro_ready=False,
    )
    assert "omnivoice" not in ordem
    assert ordem == ("edge",)

    ordem_vazia = voice_output_order(
        "omnivoice",
        kore_ready=False,
        omnivoice_ready=False,
        edge_ready=False,
        kokoro_ready=False,
    )
    assert ordem_vazia == ()


def test_ordem_com_omnivoice_presente_mantem_o_local_primeiro():
    ordem = voice_output_order(
        "omnivoice",
        kore_ready=True,
        omnivoice_ready=True,
        edge_ready=True,
        kokoro_ready=False,
    )
    assert ordem[0] == "omnivoice"
