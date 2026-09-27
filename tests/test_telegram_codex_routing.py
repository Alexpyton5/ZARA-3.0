"""Contratos offline do roteamento Codex na ponte Thunderbot/Telegram."""
from __future__ import annotations

import asyncio
import time
from threading import Event

import pytest

from core.telegram_grupo import PonteGrupo
from core.telegram_ponte import PonteTelegram


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("@codex revise isto", ("codex", "revise isto")),
        ("/codex revise isto", ("codex", "revise isto")),
        ("/codex: revise isto", ("codex", "revise isto")),
        ("/codex@Thunderbot revise isto", ("codex", "revise isto")),
        ("/zara@Thunderbot aumente o volume", ("zara", "aumente o volume")),
        ("/comando_desconhecido mantenha isto", ("zara", "/comando_desconhecido mantenha isto")),
    ],
)
def test_roteamento_telegram_preserva_destino_e_fallback(texto, esperado):
    assert PonteTelegram.rotear(texto) == esperado


@pytest.mark.asyncio
async def test_runner_standalone_entrega_codex_sem_chamar_provider(monkeypatch):
    from tools import zara_telegram_bot

    monkeypatch.setattr(
        zara_telegram_bot,
        "_falar_com_codex",
        lambda texto: (f"recebi: {texto}", ""),
    )

    assert await zara_telegram_bot._executar("codex", "revise isto") == (
        "Codex:\n\nrecebi: revise isto"
    )


@pytest.mark.asyncio
async def test_comando_codex_do_thunderbot_executa_e_responde(monkeypatch):
    recebidos: list[tuple[str, str]] = []
    enviados: list[str] = []

    async def executar(destino: str, texto: str) -> str:
        recebidos.append((destino, texto))
        return "resposta do Codex"

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    ponte = PonteTelegram("123:abc", executar, dono=7)
    monkeypatch.setattr(ponte, "avisar", avisar)

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 7},
                "text": "/codex@Thunderbot revise isto",
                "date": int(time.time()),
            }
        }
    )

    assert recebidos == [("codex", "revise isto")]
    assert enviados == ["resposta do Codex"]


@pytest.mark.asyncio
async def test_comando_codex_do_thunderbot_funciona_no_grupo(monkeypatch):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino: str, texto: str) -> str:
        recebidos.append((destino, texto))
        return "ok"

    async def avisar(_texto: str) -> bool:
        return True

    ponte = PonteGrupo("123:abc", executar, grupo_id=77)
    monkeypatch.setattr(ponte, "avisar", avisar)

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 77, "type": "supergroup"},
                "text": "/codex@Thunderbot revise isto",
                "date": int(time.time()),
            }
        }
    )

    assert recebidos == [("codex", "revise isto")]


@pytest.mark.asyncio
async def test_iniciar_cria_polling_e_parar_encerra_tarefa(monkeypatch, tmp_path):
    chamadas: list[str] = []
    polling_iniciado = Event()

    def chamar(_token: str, metodo: str, **_parametros):
        chamadas.append(metodo)
        if metodo == "getMe":
            return {"ok": True, "result": {"username": "Thunderbot"}}
        if metodo == "getUpdates":
            polling_iniciado.set()
        return {"ok": True, "result": []}

    marcador = tmp_path / "telegram_lido.json"
    marcador.write_text('{"ultimo_update": 10, "dono": 7}', encoding="utf-8")
    monkeypatch.setattr("core.telegram_ponte._chamar", chamar)
    monkeypatch.setattr(PonteTelegram, "_arquivo_marcador", staticmethod(lambda: marcador))

    async def executar(_destino: str, _texto: str) -> str:
        return "ok"

    ponte = PonteTelegram("123:abc", executar)
    assert await ponte.iniciar() is True
    assert await asyncio.to_thread(polling_iniciado.wait, 1.0) is True

    tarefa = ponte._tarefa
    assert tarefa is not None
    assert tarefa.get_name() == "zara-telegram"
    assert "getUpdates" in chamadas
    assert ponte.esta_viva is True

    await ponte.parar()
    await asyncio.sleep(0)
    assert ponte._tarefa is None
    assert tarefa.done() is True
