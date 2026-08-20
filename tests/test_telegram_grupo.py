"""Testes da ponte de grupo (ZARA-TELEGRAM-GRUPO-001).

O ponto central aqui é autorização: a ponte do grupo NÃO obedece a qualquer
chat, só ao grupo autorizado (ou ao privado do Alex, quando configurado).
Sem isso, quem descobrisse o nome do bot comandaria o PC do Alex.
"""
from __future__ import annotations

import time

import pytest

from core.telegram_grupo import PonteGrupo


def _grupo(grupo_id=777, dono_privado=None):
    recebidos: list[tuple[str, str]] = []

    async def executar(destino, texto):
        recebidos.append((destino, texto))
        return "ok"

    p = PonteGrupo(
        "123:abc",
        executar,
        grupo_id=grupo_id,
        dono_privado=dono_privado,
    )
    p._recebidos = recebidos
    return p


def _msg(texto, chat, tipo="group", date=None):
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat, "type": tipo},
            "text": texto,
            "date": int(date or time.time()),
        },
    }


# ---------- autorização ----------

@pytest.mark.asyncio
async def test_grupo_autorizado_e_atendido(monkeypatch):
    p = _grupo(grupo_id=777)
    monkeypatch.setattr(p, "avisar", lambda t: _ok())
    await p._tratar(_msg("hermes: qual seu nome?", 777))
    assert p._recebidos == [("hermes", "qual seu nome")]


@pytest.mark.asyncio
async def test_outro_grupo_e_ignorado(monkeypatch):
    p = _grupo(grupo_id=777)
    enviados = []
    monkeypatch.setattr(p, "avisar", lambda t: enviados.append(t) or _ok())
    await p._tratar(_msg("hermes: oi", 999))
    assert p._recebidos == [], "executou ordem de grupo nao autorizado"
    assert enviados == [], "nem responde para grupo nao autorizado"


@pytest.mark.asyncio
async def test_privado_do_alex_funciona_quando_configurado(monkeypatch):
    # ZARA-TELEGRAM-GRUPO-002: o bot novo atende o privado do Alex sem grupo.
    p = _grupo(grupo_id=None, dono_privado=8989543338)
    monkeypatch.setattr(p, "avisar", lambda t: _ok())
    await p._tratar(_msg("codex: roda os testes", 8989543338, tipo="private"))
    assert p._recebidos == [("codex", "roda os testes")]


@pytest.mark.asyncio
async def test_privado_de_estranho_e_ignorado(monkeypatch):
    p = _grupo(grupo_id=None, dono_privado=8989543338)
    enviados = []
    monkeypatch.setattr(p, "avisar", lambda t: enviados.append(t) or _ok())
    await p._tratar(_msg("hermes: oi", 12345, tipo="private"))
    assert p._recebidos == []
    assert enviados == []


@pytest.mark.asyncio
async def test_grupo_sem_id_nao_liga(monkeypatch):
    p = PonteGrupo("123:abc", lambda d, t: "ok")
    monkeypatch.setattr("core.telegram_ponte._chamar", lambda *a, **k: {"ok": True})
    assert await p.iniciar() is False


# ---------- roteamento reaproveitado ----------

@pytest.mark.asyncio
async def test_todos_os_prefixos_roteiam_no_grupo(monkeypatch):
    # O roteamento remove o prefixo do conteudo (ex.: "claude: oi" -> "oi").
    p = _grupo(grupo_id=777)
    monkeypatch.setattr(p, "avisar", lambda t: _ok())
    casos = [
        ("claude: oi", "claude", "oi"),
        ("codex: oi", "codex", "oi"),
        ("hermes: oi", "hermes", "oi"),
        ("zara: oi", "zara", "oi"),
        ("todos: oi", "todos", "oi"),
        ("so texto", "zara", "so texto"),
    ]
    for texto, destino, conteudo in casos:
        p._recebidos.clear()
        await p._tratar(_msg(texto, 777))
        assert p._recebidos == [(destino, conteudo)], texto


# ---------- robustez herdada ----------

@pytest.mark.asyncio
async def test_mensagem_velha_no_grupo_nao_executa(monkeypatch):
    p = _grupo(grupo_id=777)
    enviados = []
    monkeypatch.setattr(p, "avisar", lambda t: enviados.append(t) or _ok())
    await p._tratar(_msg("hermes: oi", 777, date=int(time.time()) - 7200))
    assert p._recebidos == [], "pedido de horas atras nao executa sozinho"
    assert enviados and "não executei" in enviados[0]


async def _ok():
    return True
