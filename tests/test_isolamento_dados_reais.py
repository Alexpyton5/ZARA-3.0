"""O incidente NIGHT-03B não pode acontecer de novo: teste não escreve no Lab real.

Na madrugada de 2026-09-10 uma suíte de não-regressão construiu um
`LabV1Service()` real. O serviço resolve o caminho do banco sozinho
(`core/lab_v1/service.py:716` → `LabStore()` sem argumento →
`data_dir()/lab/zara_lab_v1.db`) e o boot ainda grava a linha `@last_boot`.
Resultado: o banco real do Alex ganhou uma tabela e uma linha durante
`pytest -q`.

Estes testes provam a rede de segurança de `tests/conftest.py` — não o contrário:
se alguém remover o isolamento automático, eles ficam vermelhos ANTES de o banco
do Alex ser tocado.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from core.lab_v1.store import LabStore
from core.paths import data_dir, user_data_dir
from tests.conftest import _REAL_ZARA3_HOME


def _real_lab_db() -> Path:
    return _REAL_ZARA3_HOME / "data" / "lab" / "zara_lab_v1.db"


def test_a_arvore_de_dados_do_teste_nunca_e_a_do_alex():
    assert os.environ["ZARA3_HOME"] != str(_REAL_ZARA3_HOME)
    assert _REAL_ZARA3_HOME not in user_data_dir().resolve().parents
    assert user_data_dir().resolve() != _REAL_ZARA3_HOME


def test_labstore_padrao_cai_na_home_isolada_e_nao_toca_o_banco_do_alex():
    """`LabStore()` sem argumento é exatamente o que o boot do Lab faz."""
    real = _real_lab_db()
    antes = (hashlib.sha256(real.read_bytes()).hexdigest(), real.stat().st_mtime) if real.exists() else None

    store = LabStore()
    store.initialize()

    assert store.db_path.resolve() == (data_dir() / "lab" / "zara_lab_v1.db").resolve()
    assert _REAL_ZARA3_HOME not in store.db_path.resolve().parents
    assert store.db_path.exists()  # escreveu — só que na pasta do teste

    if antes is not None:
        depois = (hashlib.sha256(real.read_bytes()).hexdigest(), real.stat().st_mtime)
        assert depois == antes, "o banco real do Lab foi tocado por um teste"


def test_abrir_o_banco_real_pelo_caminho_fixo_e_erro_e_nao_escrita():
    """Segunda camada: nem um caminho hardcoded passa."""
    with pytest.raises(RuntimeError, match="dados reais do Alex"):
        sqlite3.connect(str(_real_lab_db()))


def test_memoria_e_arquivo_temporario_continuam_livres(tmp_path):
    """A guarda é cirúrgica: só a árvore real é bloqueada."""
    sqlite3.connect(":memory:").close()
    sqlite3.connect(str(tmp_path / "qualquer.db")).close()
