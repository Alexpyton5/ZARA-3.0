"""Contratos offline da ponte Telegram de grupo."""
from __future__ import annotations

import time

import pytest

from core.telegram_grupo import PonteGrupo


def _grupo(*, grupo_id=77, dono_privado=7):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino: str, texto: str) -> str:
        recebidos.append((destino, texto))
        return "ok"

    ponte = PonteGrupo("123:abc", executar, grupo_id=grupo_id, dono_privado=dono_privado)
    ponte._recebidos = recebidos
    return ponte


@pytest.mark.asyncio
async def test_grupo_autorizado_transcreve_audio_e_nao_atende_outro_grupo(monkeypatch):
    ponte = _grupo()
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    monkeypatch.setattr(
        "core.telegram_audio.transcrever",
        lambda _token, _mensagem: ("hermes: oi", ""),
    )

    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 77, "type": "supergroup"},
                "voice": {"file_id": "abc"},
                "date": int(time.time()),
            }
        }
    )
    await ponte._tratar(
        {
            "message": {
                "chat": {"id": 99, "type": "supergroup"},
                "text": "zara: nao execute",
                "date": int(time.time()),
            }
        }
    )

    assert ponte._recebidos == [("hermes", "oi")]
    assert enviados == ['Ouvi: "hermes: oi"\n\nok']


def _mensagem(texto, chat, tipo="group", date=None):
    return {
        "message": {
            "chat": {"id": chat, "type": tipo},
            "text": texto,
            "date": int(date or time.time()),
        }
    }


@pytest.mark.asyncio
async def test_grupo_autorizado_e_atendido(monkeypatch):
    ponte = _grupo()
    monkeypatch.setattr(ponte, "avisar", lambda texto: _ok(texto))

    await ponte._tratar(_mensagem("hermes: qual seu nome?", 77))

    assert ponte._recebidos == [("hermes", "qual seu nome")]


@pytest.mark.asyncio
async def test_outro_grupo_e_ignorado_sem_resposta(monkeypatch):
    ponte = _grupo()
    enviados: list[str] = []
    monkeypatch.setattr(ponte, "avisar", lambda texto: enviados.append(texto) or _ok(texto))

    await ponte._tratar(_mensagem("hermes: oi", 99))

    assert ponte._recebidos == []
    assert enviados == []


@pytest.mark.asyncio
async def test_privado_do_dono_e_atendido_quando_configurado(monkeypatch):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino, texto):
        recebidos.append((destino, texto))
        return "ok"

    ponte = PonteGrupo("123:abc", executar, grupo_id=None, dono_privado=7)
    monkeypatch.setattr(ponte, "avisar", lambda texto: _ok(texto))

    await ponte._tratar(_mensagem("codex: roda os testes", 7, tipo="private"))
    await ponte._tratar(_mensagem("hermes: oi", 99, tipo="private"))

    assert recebidos == [("codex", "roda os testes")]


@pytest.mark.asyncio
async def test_grupo_sem_alvo_autorizado_nao_liga(monkeypatch):
    ponte = PonteGrupo("123:abc", lambda _destino, _texto: "ok")
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *_args, **_kwargs: {"ok": True})

    assert await ponte.iniciar() is False


@pytest.mark.asyncio
async def test_prefixos_reaproveitam_roteamento_no_grupo(monkeypatch):
    ponte = _grupo()
    monkeypatch.setattr(ponte, "avisar", lambda texto: _ok(texto))

    for texto, esperado in [
        ("claude: oi", ("claude", "oi")),
        ("codex: oi", ("codex", "oi")),
        ("hermes: oi", ("hermes", "oi")),
        ("zara: oi", ("zara", "oi")),
        ("todos: oi", ("todos", "oi")),
        ("sem prefixo", ("zara", "sem prefixo")),
    ]:
        ponte._recebidos.clear()
        await ponte._tratar(_mensagem(texto, 77))
        assert ponte._recebidos == [esperado]


@pytest.mark.asyncio
async def test_mensagem_antiga_no_grupo_avisa_sem_executar(monkeypatch):
    ponte = _grupo()
    enviados: list[str] = []
    monkeypatch.setattr(ponte, "avisar", lambda texto: enviados.append(texto) or _ok(texto))

    await ponte._tratar(_mensagem("hermes: oi", 77, date=int(time.time()) - 7200))

    assert ponte._recebidos == []
    assert enviados and "não executei" in enviados[0]


async def _ok(_texto: str) -> bool:
    return True


def _msg(texto: str, chat: int, *, tipo: str = "group", date: int | None = None) -> dict:
    return {
        "message": {
            "chat": {"id": chat, "type": tipo},
            "text": texto,
            "date": int(time.time()) if date is None else date,
        }
    }


@pytest.mark.asyncio
async def test_grupo_autorizado_executa_texto(monkeypatch):
    ponte = _grupo(grupo_id=77, dono_privado=None)
    monkeypatch.setattr(ponte, "avisar", _ok)

    await ponte._tratar(_msg("hermes: qual seu nome?", 77))

    assert ponte._recebidos == [("hermes", "qual seu nome")]


@pytest.mark.asyncio
async def test_privado_do_dono_configurado_executa(monkeypatch):
    ponte = _grupo(grupo_id=None, dono_privado=7)
    monkeypatch.setattr(ponte, "avisar", _ok)

    await ponte._tratar(_msg("codex: roda os testes", 7, tipo="private"))

    assert ponte._recebidos == [("codex", "roda os testes")]


@pytest.mark.asyncio
async def test_privado_de_estranho_e_ignorado(monkeypatch):
    ponte = _grupo(grupo_id=None, dono_privado=7)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    await ponte._tratar(_msg("zara: nao execute", 99, tipo="private"))

    assert ponte._recebidos == []
    assert enviados == []


@pytest.mark.asyncio
async def test_grupo_sem_alvo_configurado_nao_inicia(monkeypatch):
    ponte = PonteGrupo("123:abc", lambda _destino, _texto: "ok")
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *_args, **_kwargs: {"ok": True})

    assert await ponte.iniciar() is False


@pytest.mark.asyncio
async def test_prefixos_roteiam_no_grupo(monkeypatch):
    ponte = _grupo(grupo_id=77, dono_privado=None)
    monkeypatch.setattr(ponte, "avisar", _ok)
    casos = [
        ("claude: oi", "claude", "oi"),
        ("codex: oi", "codex", "oi"),
        ("hermes: oi", "hermes", "oi"),
        ("zara: oi", "zara", "oi"),
        ("todos: oi", "todos", "oi"),
        ("so texto", "zara", "so texto"),
    ]

    for texto, destino, conteudo in casos:
        ponte._recebidos.clear()
        await ponte._tratar(_msg(texto, 77))
        assert ponte._recebidos == [(destino, conteudo)]


@pytest.mark.asyncio
async def test_mensagem_velha_do_grupo_nao_e_executada(monkeypatch):
    ponte = _grupo(grupo_id=77, dono_privado=None)
    enviados: list[str] = []

    async def avisar(texto: str) -> bool:
        enviados.append(texto)
        return True

    monkeypatch.setattr(ponte, "avisar", avisar)
    await ponte._tratar(_msg("hermes: oi", 77, date=int(time.time()) - 7200))

    assert ponte._recebidos == []
    assert enviados and "não executei" in enviados[0]


async def _ok(_texto: str) -> bool:
    return True
