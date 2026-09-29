# -*- coding: utf-8 -*-
"""Testes do daemon do Lab 24/7 (MISSAO GAP-ZERO, frente 5).

Cobre o daemon (heartbeat, parada elegante, ciclo real). Tudo hermetico:
cada teste usa um .lab-vivo temporario via ZARA_LAB24_RAIZ.
O supervisor agora e o script PowerShell tools/zara_lab24_supervisor.ps1
(python como SYSTEM via Agendador falha intermitente na inicializacao).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from core import lab_loop_24x7 as daemon


@pytest.fixture()
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA_LAB24_RAIZ", str(tmp_path))
    monkeypatch.setenv("ZARA_LAB24_CICLO_MIN", "0.02")  # ~1.2s por ciclo
    return tmp_path


def estado(raiz: Path) -> Path:
    d = raiz / ".lab-vivo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_escrever_heartbeat_cria_json_valido(raiz):
    d = estado(raiz)
    arq = daemon.escrever_heartbeat(d, pid=1234, ciclo=7, estado="RODANDO",
                                    detalhe="ok")
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert dados["viva"] is True
    assert dados["pid"] == 1234
    assert dados["ciclo"] == 7
    assert dados["estado"] == "RODANDO"
    assert dados["versao"] == daemon.VERSAO
    assert abs(dados["ts"] - time.time()) < 60


def test_parar_pedido(raiz):
    d = estado(raiz)
    assert daemon.parar_pedido(d) is False
    (d / daemon.PARAR_NOME).write_text("pare", encoding="utf-8")
    assert daemon.parar_pedido(d) is True


def test_dormir_com_parada_respeita_parar(raiz):
    d = estado(raiz)
    (d / daemon.PARAR_NOME).write_text("pare", encoding="utf-8")
    assert daemon.dormir_com_parada(60.0, d) is True


def test_daemon_para_com_parar_sem_rodar_ciclo(raiz):
    d = estado(raiz)
    (d / daemon.PARAR_NOME).write_text("pare", encoding="utf-8")
    rc = daemon.main()
    assert rc == 0
    hb = json.loads((d / daemon.HEARTBEAT_NOME).read_text(encoding="utf-8"))
    assert hb["estado"] == "PARADO"


def test_daemon_roda_um_ciclo_real_e_para_no_teto(raiz, monkeypatch):
    # ciclo de verdade (backlog + turno + worker local), 1 ciclo so.
    monkeypatch.setenv("ZARA_LAB24_MAX_CICLOS", "1")
    rc = daemon.main()
    assert rc == 0
    d = raiz / ".lab-vivo"
    hb = json.loads((d / daemon.HEARTBEAT_NOME).read_text(encoding="utf-8"))
    assert hb["ciclo"] >= 1
    assert hb["pid"] == os.getpid()
    assert (d / "backlog.json").exists()
    assert (d / "logs").is_dir()
