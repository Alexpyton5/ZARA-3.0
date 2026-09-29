"""FRENTE 2 (GAP-ZERO) - Cadastro de identidade ponta a ponta.

Valida o fluxo REAL do script scripts/cadastrar_identidade.py, de ponta
a ponta, com DADOS SINTETICOS (--simulacao). NUNCA dados reais do Alex.

Fluxo validado: captura (fake) -> extracao de referencia -> armazenamento
em disco (só hash SHA-256 + metadados) -> verificacao posterior com o
store recarregado do disco: reconhece o "usuario de teste" e rejeita
estranho com a frase exata.

O store de teste fica isolado via ZARA3_HOME (tmp_path): o cadastro real
do Alex nunca e tocado.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.identidade_rosto_voz import (
    FRASE_ESTRANHO,
    IdentityGate,
    IdentityStore,
    ProvedorSimulacao,
)

RAIZ = Path(__file__).resolve().parents[1]
CLI = RAIZ / "scripts" / "cadastrar_identidade.py"

PAPEIS = ("dono", "esposa")
MODALIDADES = ("rosto", "voz")


def _referencias_json(home: Path) -> Path:
    # ZARA3_HOME e usado verbatim como base (core/paths.py: sem sufixo extra)
    return home / "data" / "identidade" / "referencias.json"


def _rodar_cli(papel: str, modalidade: str, home: Path):
    """Roda o script de cadastro de verdade, com amostras fake."""
    env = dict(os.environ)
    env["ZARA3_HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, str(CLI),
         "--papel", papel, "--modalidade", modalidade, "--simulacao"],
        capture_output=True, text=True, cwd=str(RAIZ), env=env, timeout=120,
    )
    return proc


@pytest.fixture()
def home_teste(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    return tmp_path


# --- o CLI cadastra sem erro e persiste só hash + metadados ---------------------

def test_cli_cadastra_os_quatro_templates(home_teste):
    for papel in PAPEIS:
        for modalidade in MODALIDADES:
            proc = _rodar_cli(papel, modalidade, home_teste)
            assert proc.returncode == 0, proc.stderr + proc.stdout
            assert "[OK]" in proc.stdout

    dados = json.loads(_referencias_json(home_teste).read_text(encoding="utf-8"))
    assert set(dados["pessoas"]) == {"dono", "esposa"}
    for papel, pessoa in dados["pessoas"].items():
        for modalidade in MODALIDADES:
            tpl = pessoa[modalidade]
            assert tpl["hash_embedding"], "hash ausente"
            assert tpl["modalidade"] == modalidade
            assert tpl["papel"] == papel
            assert tpl["amostras"] >= 3

    # nenhum dado cru (amostra fake) vaza para o disco
    bruto = _referencias_json(home_teste).read_text(encoding="utf-8")
    for modalidade in MODALIDADES:
        for i in range(3):
            assert f"simulacao-{modalidade}-{i}" not in bruto


def test_cli_sem_simulacao_nao_finge_captura(home_teste):
    # home fresco: nenhum cadastro previo
    assert not _referencias_json(home_teste).exists()
    env = dict(os.environ)
    env["ZARA3_HOME"] = str(home_teste)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--papel", "dono", "--modalidade", "voz"],
        capture_output=True, text=True, cwd=str(RAIZ), env=env, timeout=120,
    )
    # provedor real ainda nao plugado: erro honesto, sem inventar cadastro
    assert proc.returncode == 2
    assert not _referencias_json(home_teste).exists()


# --- verificacao posterior: reconhece o usuario de teste ------------------------

def test_verificacao_posterior_reconhece_usuario_de_teste(home_teste):
    proc = _rodar_cli("dono", "voz", home_teste)
    assert proc.returncode == 0

    # "verificacao posterior": store NOVO, lido do disco
    store = IdentityStore()  # ZARA3_HOME ja aponta para home_teste
    assert store.algum_cadastro() is True

    gate = IdentityGate(
        store=store,
        prov_voz=ProvedorSimulacao({("dono", "voz"): 0.92}),
    )
    decisao = gate.gate_interaction({"voz": b"amostra-sintetica"})
    assert decisao.decisao == "autorizado"
    assert decisao.pessoa == "dono"
    assert decisao.ignorar is False
    assert decisao.fala is None


# --- verificacao posterior: rejeita estranho ------------------------------------

def test_verificacao_posterior_rejeita_estranho(home_teste):
    proc = _rodar_cli("dono", "voz", home_teste)
    assert proc.returncode == 0

    store = IdentityStore()
    gate = IdentityGate(store=store, prov_voz=ProvedorSimulacao({}))
    decisao = gate.gate_interaction({"voz": b"amostra-sintetica"})
    assert decisao.decisao == "estranho"
    assert decisao.fala == FRASE_ESTRANHO
    assert decisao.ignorar is True


def test_usuario_de_teste_nao_confunde_papeis(home_teste):
    # cadastrou o "dono"; a "esposa" com outro score continua autorizada
    for papel in PAPEIS:
        assert _rodar_cli(papel, "voz", home_teste).returncode == 0

    store = IdentityStore()
    gate = IdentityGate(
        store=store,
        prov_voz=ProvedorSimulacao({("esposa", "voz"): 0.88}),
    )
    decisao = gate.gate_interaction({"voz": b"amostra-sintetica"})
    assert decisao.decisao == "autorizado"
    assert decisao.pessoa == "esposa"
