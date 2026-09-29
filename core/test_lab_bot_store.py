"""Peca 2 ("bots faceis"): BotStore + register no LabStore.

Roda no PC do Alex contra o .venv real do projeto:
    .venv\\Scripts\\python.exe -m pytest core/test_lab_bot_store.py -q
"""
from __future__ import annotations

import json

import pytest

from core.lab_bot_spec import BotSpecError, from_dict
from core.lab_bot_store import (
    BotStore,
    BotStoreError,
    register,
    register_by_id,
    spec_from_agent,
)
from core.lab_v1.domain import RoleName
from core.lab_v1.store import LabStore


def _spec(**kw):
    base = {"id": "ajudante", "name": "Ajudante"}
    base.update(kw)
    return from_dict(base)


def test_roundtrip_preserva_tudo(tmp_path):
    store = BotStore(tmp_path)
    spec = _spec(
        instructions="ajuda o Alex com recados",
        role=RoleName.MEMBER,
        capabilities=["model.text", "tools.read"],
        max_turns=3,
        reports_to="zoe",
    )
    path = store.save(spec)
    assert path.is_file()
    assert path.suffix == ".json"
    assert store.load("ajudante") == spec


def test_list_ordenado_por_id(tmp_path):
    store = BotStore(tmp_path)
    store.save(_spec(id="zebra", name="Zebra"))
    store.save(_spec(id="abacaxi", name="Abacaxi"))
    assert [s.id for s in store.list()] == ["abacaxi", "zebra"]


def test_delete_e_inexistente(tmp_path):
    store = BotStore(tmp_path)
    store.save(_spec())
    assert store.exists("ajudante")
    store.delete("ajudante")
    assert not store.exists("ajudante")
    with pytest.raises(BotStoreError):
        store.delete("ajudante")
    with pytest.raises(BotStoreError):
        store.load("ajudante")


def test_arquivo_corrompido_nao_vira_default(tmp_path):
    store = BotStore(tmp_path)
    (tmp_path / "quebrado.json").write_text("{nao e json", encoding="utf-8")
    with pytest.raises(BotStoreError):
        store.load("quebrado")


def test_campo_desconhecido_rejeitado(tmp_path):
    store = BotStore(tmp_path)
    (tmp_path / "typo.json").write_text(
        json.dumps({"id": "typo", "name": "Typo", "nmae": "escrevi errado"}),
        encoding="utf-8",
    )
    with pytest.raises(BotStoreError):
        store.load("typo")


def test_register_salva_agent_real_no_lab(tmp_path):
    bots = BotStore(tmp_path / "bots")
    db = LabStore(tmp_path / "lab.db")
    db.initialize()
    spec = _spec(role=RoleName.MEMBER, capabilities=["model.text"])
    profile = register(db, spec)
    got = db.get_agent("ajudante")
    assert got is not None
    assert got.id == profile.id == "ajudante"
    assert got.name == "Ajudante"
    assert "model.text" in got.capabilities
    assert got.provider_id == "nvidia"


def test_register_by_id_ponta_a_ponta(tmp_path):
    bots = BotStore(tmp_path / "bots")
    db = LabStore(tmp_path / "lab.db")
    db.initialize()
    bots.save(_spec(name="Pelo ID"))
    profile = register_by_id(bots, db, "ajudante")
    assert profile.name == "Pelo ID"
    assert db.get_agent("ajudante").name == "Pelo ID"


def test_register_atualiza_spec_existente(tmp_path):
    bots = BotStore(tmp_path / "bots")
    db = LabStore(tmp_path / "lab.db")
    db.initialize()
    register(db, _spec(name="V1"))
    register(db, _spec(name="V2"))
    assert db.get_agent("ajudante").name == "V2"


def test_spec_from_agent_volta_igual(tmp_path):
    db = LabStore(tmp_path / "lab.db")
    db.initialize()
    spec = _spec(instructions="oi", max_turns=5)
    register(db, spec)
    assert spec_from_agent(db.get_agent("ajudante")) == spec


def test_spec_from_agent_marca_opt_in_perigoso(tmp_path):
    db = LabStore(tmp_path / "lab.db")
    db.initialize()
    spec = _spec(capabilities=["model.text", "tools.write"], allow_dangerous=True)
    register(db, spec)
    back = spec_from_agent(db.get_agent("ajudante"))
    assert back.allow_dangerous is True
    assert back == spec


def test_perigoso_sem_opt_in_nem_chega_no_store(tmp_path):
    with pytest.raises(BotSpecError):
        _spec(capabilities=["model.text", "tools.write"])
