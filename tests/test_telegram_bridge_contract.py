"""Offline contract for Telegram bridges still loaded by the IPC boot path."""
from __future__ import annotations

import importlib
import importlib.util
import json
import time

import pytest

from core.ipc_handlers import IPCHandler
from core.telegram_approval_adapter import TelegramApprovalAdapter
from core.telegram_ponte import PonteTelegram


def test_ipc_telegram_bridge_modules_are_present():
    """The boot path imports both bridge modules lazily, so both must exist."""
    assert importlib.util.find_spec("core.telegram_ponte") is not None
    assert importlib.util.find_spec("core.telegram_grupo") is not None


@pytest.mark.asyncio
async def test_private_bridge_routes_remote_approval_reply_without_network(monkeypatch):
    private_module = importlib.import_module("core.telegram_ponte")
    sent_messages = []
    received = []

    async def execute(destination, text):
        received.append((destination, text))
        return "Anotado, pode seguir: apagar builds velhos"

    monkeypatch.setattr(
        private_module,
        "_chamar",
        lambda *_args, **kwargs: sent_messages.append(kwargs.get("text")) or {"ok": True},
    )
    bridge = private_module.PonteTelegram("test-token", execute, dono=7)

    await bridge._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "date": int(time.time()),
                "text": "zara: sim",
            }
        }
    )

    assert received == [("zara", "sim")]
    assert sent_messages == ["Anotado, pode seguir: apagar builds velhos"]


@pytest.mark.asyncio
async def test_bridge_routes_sim_to_real_ipc_callback_and_records_pending_approval(
    monkeypatch, tmp_path
):
    """`zara: sim` resolves a real queue entry without executing its action."""
    from core import aprovacao_remota

    (tmp_path / "api_keys.json").write_text(
        json.dumps({"telegram_verifier_secret": "test-secret"}), encoding="utf-8"
    )
    monkeypatch.setattr(aprovacao_remota, "config_dir", lambda: tmp_path)

    handler = object.__new__(IPCHandler)
    handler._marcar_canal = lambda _canal: None
    handler._aprovado_por_alex = set()
    mensagens: list[str] = []

    async def gravar(_papel, _conteudo, _motor):
        return None

    async def avisar(texto: str) -> bool:
        mensagens.append(texto)
        return True

    handler._append_conversation_message = gravar
    fila = handler._fila_de_aprovacao()
    pedido = fila.pedir("apagar builds velhos", quem_pediu="Telegram")
    assert pedido is not None
    chamadas_de_executor: list[tuple[tuple, dict]] = []

    async def executor_que_nao_deve_rodar(*args, **kwargs):
        chamadas_de_executor.append((args, kwargs))
        raise AssertionError("resposta de aprovação não pode executar a ação")

    from core import action_registry

    monkeypatch.setattr(action_registry, "execute_action", executor_que_nao_deve_rodar)

    ponte = PonteTelegram("test-token", handler._executar_do_celular, dono=7)
    monkeypatch.setattr(ponte, "avisar", avisar)

    await ponte._tratar(
        {"message": {"chat": {"id": 7}, "date": int(time.time()), "text": "zara: sim"}}
    )

    assert handler.foi_aprovado(pedido.id) is True
    assert fila.get_status(pedido.id) == "approved"
    assert mensagens == ["Anotado, pode seguir: apagar builds velhos"]
    assert chamadas_de_executor == []


@pytest.mark.asyncio
async def test_private_bridge_reports_callback_failure_honestly_without_network(monkeypatch):
    private_module = importlib.import_module("core.telegram_ponte")
    sent_messages = []

    async def fail(_destination, _text):
        raise RuntimeError("executor caiu")

    monkeypatch.setattr(
        private_module,
        "_chamar",
        lambda *_args, **kwargs: sent_messages.append(kwargs.get("text")) or {"ok": True},
    )
    bridge = private_module.PonteTelegram("test-token", fail, dono=7)

    await bridge._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "date": int(time.time()),
                "text": "zara: sim",
            }
        }
    )

    assert sent_messages == ["Não consegui: RuntimeError"]


@pytest.mark.asyncio
async def test_ligar_telegram_initializes_private_bridge_and_approval_adapter_offline(
    monkeypatch, tmp_path
):
    private_module = importlib.import_module("core.telegram_ponte")
    from core import paths

    config = tmp_path / "api_keys.json"
    config.write_text(json.dumps({"telegram_bot_token": "test-token"}), encoding="utf-8")
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path)

    class FakePrivateBridge:
        instances = []

        def __init__(self, token, executar):
            self.token = token
            self.executar = executar
            self.started = False
            self.instances.append(self)

        async def iniciar(self):
            self.started = True
            return True

    monkeypatch.setattr(private_module, "PonteTelegram", FakePrivateBridge)
    handler = object.__new__(IPCHandler)
    handler._telegram = None
    handler._telegram_grupo = None
    handler._telegram_adapter = None

    await IPCHandler._ligar_telegram(handler)

    assert handler._telegram is FakePrivateBridge.instances[0]
    assert handler._telegram.token == "test-token"
    assert handler._telegram.started is True
    assert isinstance(handler._telegram_adapter, TelegramApprovalAdapter)


@pytest.mark.asyncio
async def test_ligar_telegram_failure_does_not_claim_bridge_started(monkeypatch, tmp_path, capsys):
    private_module = importlib.import_module("core.telegram_ponte")
    from core import paths

    config = tmp_path / "api_keys.json"
    config.write_text(json.dumps({"telegram_bot_token": "test-token"}), encoding="utf-8")
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path)

    class FailingPrivateBridge:
        def __init__(self, _token, _executar):
            pass

        async def iniciar(self):
            raise RuntimeError("sem rede")

    monkeypatch.setattr(private_module, "PonteTelegram", FailingPrivateBridge)
    handler = object.__new__(IPCHandler)
    handler._telegram = None
    handler._telegram_grupo = None
    handler._telegram_adapter = None

    await IPCHandler._ligar_telegram(handler)

    assert handler._telegram is None
    assert handler._telegram_adapter is None
    assert "[TELEGRAM] nao ligou: sem rede" in capsys.readouterr().out
