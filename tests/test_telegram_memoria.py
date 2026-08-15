"""ZARA-TELEGRAM-MEMORIA-001 — o que ele fala pelo celular tem de ficar.

Descoberto olhando o histórico depois que Alex mandou "Zara me responda oi" pelo
celular: a mensagem chegou, foi processada, foi respondida — e sumiu. Nada do
que ele fala pelo Telegram entrava na conversa dela.

O efeito é pior do que "falta um registro". Significa que ela conversa com ele o
dia inteiro pelo celular e, ao voltar para o computador, não lembra de nada:
nem para citar quando ele pergunta "você entendeu?", nem para o diário, nem para
a memória automática. Metade da vida dela acontecia e não existia.
"""
from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler


def _handler(resposta="Tô aqui."):
    h = IPCHandler.__new__(IPCHandler)
    h.gravadas = []
    h._ultimo_pedido_entendido = ""

    async def responder(destino, texto, executar):
        return resposta

    async def gravar(papel, conteudo, motor):
        h.gravadas.append((papel, conteudo, motor))

    h._responder_ao_celular = responder
    h._append_conversation_message = gravar
    return h


@pytest.mark.asyncio
async def test_a_pergunta_dele_e_a_resposta_dela_ficam_gravadas():
    h = _handler("Tô aqui, Alex.")

    await h._executar_do_celular("zara", "me responda oi")

    assert h.gravadas == [
        ("user", "me responda oi", "telegram"),
        ("assistant", "Tô aqui, Alex.", "telegram"),
    ]


@pytest.mark.asyncio
async def test_o_que_ele_diz_a_ela_vira_a_ultima_frase_entendida():
    """Assim "você entendeu?" pelo computador cita o que ele falou no celular."""
    h = _handler()

    await h._executar_do_celular("zara", "lembra de comprar pão")

    assert h._ultimo_pedido_entendido == "lembra de comprar pão"


@pytest.mark.asyncio
async def test_recado_para_o_claude_nao_vira_fala_com_ela():
    """"claude, conserta isso" e um recado, nao uma frase dita a ela."""
    h = _handler()

    await h._executar_do_celular("claude", "conserta o volume")

    assert h._ultimo_pedido_entendido == "", "recado para outro nao e conversa dela"
    assert len(h.gravadas) == 2, "mas continua ficando registrado que passou por aqui"


@pytest.mark.asyncio
async def test_falha_ao_gravar_nao_engole_a_resposta_dele():
    """Perder o registro e chato; deixar ele sem resposta e inaceitavel."""
    h = _handler("Volume em 60%.")

    async def gravar_quebrado(*a, **k):
        raise RuntimeError("banco travado")

    h._append_conversation_message = gravar_quebrado

    resposta = await h._executar_do_celular("zara", "diminui o volume")

    assert resposta == "Volume em 60%."
