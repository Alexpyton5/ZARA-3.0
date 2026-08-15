"""ZARA-SE-CONSERTA-SOZINHA-001 e ZARA-TELEGRAM-VIVA-001.

Alex, saindo de casa: *"se cair ou parar você corrige tudo, automaticamente"*.

O pedido nasceu de um susto real. Fui conferir se estava tudo de pé antes de ele
sair e achei o Telegram MUDO: a ZARA aberta, o processo vivo, a tarefa
existindo — e o bot sem escutar ninguém. Se ele tivesse saído, teria mandado
mensagem para o vazio e só descobriria ao voltar.

O ponto não é ter caído. É ninguém ter notado. Serviço que falha em silêncio
some da cabeça de todo mundo até doer.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from core.ipc_handlers import IPCHandler
from core.telegram_ponte import PonteTelegram


def _ponte(**kw):
    async def executar(destino, texto):
        return "ok"
    return PonteTelegram(kw.pop("token", "123:abc"), executar, **kw)


# ---------- o que prova que a ponte está viva ----------

def test_ponte_sem_tarefa_nao_esta_viva():
    p = _ponte()

    assert p.esta_viva is False


@pytest.mark.asyncio
async def test_tarefa_existir_nao_basta():
    """Foi exatamente este o defeito: a tarefa existia e o bot estava mudo.

    O que conta é ter FALADO com o Telegram, não estar na lista de tarefas.
    """
    p = _ponte()

    async def dormir():
        await asyncio.sleep(60)

    p._tarefa = asyncio.create_task(dormir())
    p._ultimo_sucesso = time.time() - 600  # dez minutos sem dar uma volta

    assert p.esta_viva is False
    p._tarefa.cancel()


@pytest.mark.asyncio
async def test_volta_recente_prova_que_esta_viva():
    p = _ponte()

    async def dormir():
        await asyncio.sleep(60)

    p._tarefa = asyncio.create_task(dormir())
    p._ultimo_sucesso = time.time()

    assert p.esta_viva is True
    p._tarefa.cancel()


@pytest.mark.asyncio
async def test_tarefa_morta_nao_esta_viva():
    p = _ponte()

    async def morrer():
        return

    p._tarefa = asyncio.create_task(morrer())
    await asyncio.sleep(0)
    p._ultimo_sucesso = time.time()

    assert p.esta_viva is False


# ---------- o vigia ----------

class _PonteFalsa:
    def __init__(self, viva):
        self.configurado = True
        self.esta_viva = viva
        self.parou = False
        self.avisos = []

    async def parar(self):
        self.parou = True

    async def avisar(self, texto):
        self.avisos.append(texto)
        return True


@pytest.mark.asyncio
async def test_o_vigia_reergue_a_ponte_caida(monkeypatch):
    h = IPCHandler.__new__(IPCHandler)
    h._INTERVALO_DO_VIGIA = 0.01
    caida = _PonteFalsa(viva=False)
    h._telegram = caida
    nova = _PonteFalsa(viva=True)

    async def religar():
        h._telegram = nova

    h._ligar_telegram = religar

    tarefa = asyncio.create_task(h._cuidar_das_pontes())
    for _ in range(60):
        if nova.avisos:
            break
        await asyncio.sleep(0.02)
    tarefa.cancel()

    assert caida.parou is True, "a ponte morta tem de ser derrubada antes"
    assert h._telegram is nova
    assert nova.avisos, "ele precisa saber que caiu; consertar calado esconde o problema"


@pytest.mark.asyncio
async def test_o_vigia_nao_mexe_no_que_esta_funcionando():
    """Reiniciar sem motivo derrubaria a conversa dele no meio."""
    h = IPCHandler.__new__(IPCHandler)
    h._INTERVALO_DO_VIGIA = 0.01
    viva = _PonteFalsa(viva=True)
    h._telegram = viva

    async def religar():
        raise AssertionError("nao devia religar nada")

    h._ligar_telegram = religar

    tarefa = asyncio.create_task(h._cuidar_das_pontes())
    await asyncio.sleep(0.08)
    tarefa.cancel()

    assert viva.parou is False
    assert viva.avisos == []


@pytest.mark.asyncio
async def test_falha_do_vigia_nao_derruba_a_zara():
    """Um vigia que morre ao primeiro erro é pior que não ter vigia."""
    h = IPCHandler.__new__(IPCHandler)
    h._INTERVALO_DO_VIGIA = 0.01
    h._telegram = _PonteFalsa(viva=False)

    async def religar():
        raise RuntimeError("boom")

    h._ligar_telegram = religar

    tarefa = asyncio.create_task(h._cuidar_das_pontes())
    await asyncio.sleep(0.08)

    assert not tarefa.done(), "o vigia tem de continuar tentando"
    tarefa.cancel()
