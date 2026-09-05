"""A conversa recebida pelo Telegram continua na memória local."""
from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_comando_do_telegram_registra_pergunta_resposta_e_ultima_frase():
    handler = object.__new__(IPCHandler)
    gravadas: list[tuple[str, str, str]] = []
    handler._marcar_canal = lambda _canal: None

    async def responder(_destino, _texto, _executar):
        return "Tô aqui, Alex."

    async def gravar(papel, conteudo, motor):
        gravadas.append((papel, conteudo, motor))

    handler._responder_ao_celular = responder
    handler._append_conversation_message = gravar
    handler._ultimo_pedido_entendido = ""

    resposta = await handler._executar_do_celular("zara", "lembra do pão")

    assert resposta == "Tô aqui, Alex."
    assert gravadas == [
        ("user", "lembra do pão", "telegram"),
        ("assistant", "Tô aqui, Alex.", "telegram"),
    ]
    assert handler._ultimo_pedido_entendido == "lembra do pão"


def _handler(resposta="Tô aqui."):
    handler = object.__new__(IPCHandler)
    handler.gravadas = []
    handler._ultimo_pedido_entendido = ""
    handler._marcar_canal = lambda _canal: None

    async def responder(_destino, _texto, _executar):
        return resposta

    async def gravar(papel, conteudo, motor):
        handler.gravadas.append((papel, conteudo, motor))

    handler._responder_ao_celular = responder
    handler._append_conversation_message = gravar
    return handler


@pytest.mark.asyncio
async def test_destino_nao_zara_nao_altera_ultima_frase_entendida():
    handler = _handler()

    await handler._executar_do_celular("claude", "conserta o volume")

    assert handler._ultimo_pedido_entendido == ""
    assert handler.gravadas == [
        ("user", "conserta o volume", "telegram"),
        ("assistant", "Tô aqui.", "telegram"),
    ]


@pytest.mark.asyncio
async def test_falha_de_persistencia_nao_suprime_resposta():
    handler = _handler("Volume em 60%.")

    async def gravar_quebrado(*_args, **_kwargs):
        raise RuntimeError("banco travado")

    handler._append_conversation_message = gravar_quebrado

    assert await handler._executar_do_celular("zara", "diminui o volume") == "Volume em 60%."


def _handler(resposta: str = "Tô aqui."):
    handler = object.__new__(IPCHandler)
    handler._marcar_canal = lambda _canal: None
    handler._ultimo_pedido_entendido = ""
    handler.gravadas: list[tuple[str, str, str]] = []

    async def responder(_destino, _texto, _executar):
        return resposta

    async def gravar(papel, conteudo, motor):
        handler.gravadas.append((papel, conteudo, motor))

    handler._responder_ao_celular = responder
    handler._append_conversation_message = gravar
    return handler


@pytest.mark.asyncio
async def test_recado_para_outro_destino_nao_vira_ultima_frase_da_zara():
    handler = _handler()

    await handler._executar_do_celular("claude", "conserta o volume")

    assert handler._ultimo_pedido_entendido == ""
    assert len(handler.gravadas) == 2


@pytest.mark.asyncio
async def test_falha_de_persistencia_nao_suprime_resposta_ao_celular():
    handler = _handler("Volume em 60%.")

    async def gravar_quebrado(*_args, **_kwargs):
        raise RuntimeError("banco travado")

    handler._append_conversation_message = gravar_quebrado

    assert await handler._executar_do_celular("zara", "diminui o volume") == "Volume em 60%."
