"""ZARA-CORE-STATE-002 — as fases do Core têm que ser as fases REAIS.

O Core foi desenhado com estados de entender / executar / verificar, e o
backend só sabia dizer THINKING e STANDBY. Pior: quando passou a dizer
SUCCESS, dizia logo depois do executor — antes do readback. Isso é o falso
sucesso de sempre, só que em forma de animação: a tela ficava verde antes de
alguém conferir o Windows.

Estes testes prendem a ordem. Se alguém emitir SUCCESS antes de VERIFYING de
novo, eles quebram.
"""

from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler


def _handler_capturando_estados(monkeypatch):
    """IPCHandler real com a emissão de estado capturada em lista."""
    emitidos: list[str] = []
    handler = IPCHandler(AsyncMock())

    async def capturar(estado):
        emitidos.append(estado)

    monkeypatch.setattr(handler, "_emitir_estado_do_core", capturar)
    return handler, emitidos


@pytest.mark.asyncio
async def test_comando_bem_sucedido_verifica_antes_de_dizer_sucesso(monkeypatch):
    handler, emitidos = _handler_capturando_estados(monkeypatch)

    async def fake_execute_action(action, **params):
        return type("Result", (), {"success": True, "error": "", "output": "", "data": None})()

    # "volume em 30%" é absoluto: a única leitura é o readback pós-ação.
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)
    monkeypatch.setattr("core.ipc_handlers._read_windows_volume", lambda: 30)

    resposta = await handler._executar_intent_de_pc("volume em 30%")

    assert resposta == "Volume definido para 30%."
    assert emitidos == ["UNDERSTANDING", "EXECUTING", "VERIFYING", "SUCCESS"]
    # A ordem é o ponto: SUCCESS depois de VERIFYING, nunca antes.
    assert emitidos.index("SUCCESS") > emitidos.index("VERIFYING")


@pytest.mark.asyncio
async def test_executor_que_falha_nao_passa_por_verificacao(monkeypatch):
    handler, emitidos = _handler_capturando_estados(monkeypatch)

    async def fake_execute_action(action, **params):
        return type("Result", (), {"success": False, "error": "falhou", "output": "", "data": None})()

    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)
    monkeypatch.setattr("core.ipc_handlers._read_windows_volume", lambda: 50)

    await handler._executar_intent_de_pc("volume em 30%")

    # Não há o que verificar quando o executor já falhou.
    assert "VERIFYING" not in emitidos
    assert emitidos[-1] == "ERROR"


@pytest.mark.asyncio
async def test_frase_que_nao_e_comando_nao_acende_estado_nenhum(monkeypatch):
    handler, emitidos = _handler_capturando_estados(monkeypatch)

    resposta = await handler._executar_intent_de_pc("me conta uma história sobre o mar")

    assert resposta is None
    assert emitidos == []


@pytest.mark.asyncio
async def test_comando_entendido_mas_bloqueado_para_em_understanding(monkeypatch):
    handler, emitidos = _handler_capturando_estados(monkeypatch)

    # "deixa um pouco mais alto" sem contexto de volume verificado é
    # reconhecido como intent e bloqueado pelo gate — entendeu, não executou.
    resposta = await handler._executar_intent_de_pc("deixa um pouco mais alto")

    assert resposta is not None
    assert emitidos == ["UNDERSTANDING"]
    assert "EXECUTING" not in emitidos
    assert "SUCCESS" not in emitidos
