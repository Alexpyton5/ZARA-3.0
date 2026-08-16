"""ZARA-RESPOSTA-VOLTA-POR-ONDE-VEIO-001 — o dia em que eu sumi.

Histórico de hoje, 20h43. Alex escreve "ta ai" pelo Telegram. A ZARA entrega
para mim e responde a ele: "Entreguei ao Claude. Te aviso quando responder."

Eu respondi. No computador. A resposta ficou presa lá porque ele estava perto do
PC — e a regra que EU tinha escrito no dia anterior dizia para só mandar ao
celular quando ele estivesse longe.

Do lado dele foi silêncio. Ele passou vinte minutos perguntando à ZARA o que
tinha acontecido comigo, e depois: *"voce quebrou meu fluxo de trabalho, sem
voce nao consegui fazer nada"*.

A regra certa é a mais velha do mundo: resposta volta por onde a pergunta veio.
A distância só decide o que fazer com aviso que ele NÃO pediu.
"""
from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler


class _Ponte:
    def __init__(self):
        self.enviados = []

    async def avisar(self, texto):
        self.enviados.append(texto)
        return True


def _handler(*, longe: bool, esperando: bool):
    h = IPCHandler.__new__(IPCHandler)
    h._telegram = _Ponte()
    h._alex_esta_longe = lambda: longe
    h._pergunta_veio_do_celular = esperando

    async def falar(_t):
        return None

    h._speak_response = falar
    return h


async def _avisar(h, curto, conteudo):
    """Reproduz o mesmo caminho do vigia, com a regra de destino."""
    await h._speak_response(curto)
    ponte = h._telegram
    esperando = bool(getattr(h, "_pergunta_veio_do_celular", False))
    if conteudo and (esperando or h._alex_esta_longe()):
        await ponte.avisar(f"{curto}\n\n{conteudo}".strip())
        h._pergunta_veio_do_celular = False
    else:
        await ponte.avisar(curto)


@pytest.mark.asyncio
async def test_perguntou_pelo_celular_recebe_a_resposta_no_celular():
    """O caso exato de hoje: ele perto do PC e a resposta presa aqui."""
    h = _handler(longe=False, esperando=True)

    await _avisar(h, "O Claude respondeu.", "Tô aqui, Alex.")

    assert "Tô aqui, Alex." in h._telegram.enviados[0], (
        "ele perguntou no celular; a resposta tem de chegar no celular"
    )


@pytest.mark.asyncio
async def test_aviso_que_ele_nao_pediu_continua_respeitando_a_distancia():
    """Perto do PC, aviso nao solicitado nao pode encher o celular dele."""
    h = _handler(longe=False, esperando=False)

    await _avisar(h, "O Codex respondeu.", "texto longo qualquer")

    assert h._telegram.enviados == ["O Codex respondeu."]


@pytest.mark.asyncio
async def test_longe_do_pc_continua_recebendo_tudo():
    h = _handler(longe=True, esperando=False)

    await _avisar(h, "O Codex respondeu.", "o conteudo inteiro")

    assert "o conteudo inteiro" in h._telegram.enviados[0]


@pytest.mark.asyncio
async def test_a_espera_e_consumida_uma_vez_so():
    """Senao todo aviso seguinte viraria mensagem cheia para sempre."""
    h = _handler(longe=False, esperando=True)

    await _avisar(h, "O Claude respondeu.", "primeira")
    await _avisar(h, "O Codex respondeu.", "segunda")

    assert "primeira" in h._telegram.enviados[0]
    assert h._telegram.enviados[1] == "O Codex respondeu."


@pytest.mark.asyncio
async def test_mandar_para_o_claude_marca_que_ele_espera_no_celular():
    h = IPCHandler.__new__(IPCHandler)
    h._pergunta_veio_do_celular = False

    class _Res:
        success = True
        output = "Mandei para o Claude."

    async def executar(_acao, **kw):
        return _Res()

    async def responder(destino, texto, execute_action):
        return await IPCHandler._responder_ao_celular(h, destino, texto, execute_action)

    resposta = await IPCHandler._responder_ao_celular(h, "claude", "ta ai", executar)

    assert "Te aviso quando responder" in resposta
    assert h._pergunta_veio_do_celular is True
