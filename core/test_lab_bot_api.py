"""Peca 3 ("bots faceis"): BotAPI — criar/ler/atualizar/apagar/listar bots.

Roda no PC do Alex contra o .venv real do projeto:
    .venv\\Scripts\\python.exe -m pytest core/test_lab_bot_api.py -q
"""
from __future__ import annotations

import pytest

from core.lab_bot_api import BotAPI, BotAPIError
from core.lab_bot_store import BotStore
from core.lab_v1.store import LabStore


def _api(tmp_path):
    store = BotStore(tmp_path / "bots")
    db = LabStore(tmp_path / "lab.db")
    return BotAPI(store, db), db


def test_create_bot_roundtrip(tmp_path):
    api, db = _api(tmp_path)
    out = api.create_bot(
        {"id": "ajudante", "name": "Ajudante", "instructions": "ajuda o Alex"}
    )
    assert out["id"] == "ajudante"
    assert out["provider_id"] == "nvidia"  # padrao: gratis primeiro
    assert api.get_bot("ajudante")["name"] == "Ajudante"
    agent = db.get_agent("ajudante")
    assert agent is not None and agent.name == "Ajudante"


def test_create_bot_invalido_nao_escreve_nada(tmp_path):
    api, db = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.create_bot({"id": "AJUDANTE!", "name": "Ruim"})
    with pytest.raises(BotAPIError):
        api.get_bot("AJUDANTE!")
    assert db.get_agent("AJUDANTE!") is None


def test_create_bot_rejeita_role_inventada(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.create_bot({"id": "x", "name": "X", "role": "CTO"})


def test_create_bot_rejeita_campo_desconhecido(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.create_bot({"id": "x", "name": "X", "cor_favorita": "azul"})


def test_create_bot_nao_dict(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.create_bot(["id", "x"])


def test_create_bot_perigoso_exige_optin(tmp_path):
    api, db = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.create_bot(
            {"id": "x", "name": "X", "capabilities": ["model.text", "tools.write"]}
        )
    out = api.create_bot(
        {
            "id": "x",
            "name": "X",
            "capabilities": ["model.text", "tools.write"],
            "allow_dangerous": True,
        }
    )
    assert "tools.write" in out["capabilities"]
    assert "tools.write" in db.get_agent("x").capabilities


def test_get_bot_inexistente(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.get_bot("fantasma")


def test_list_bots_ordenado(tmp_path):
    api, _ = _api(tmp_path)
    api.create_bot({"id": "zebra", "name": "Zebra"})
    api.create_bot({"id": "abacaxi", "name": "Abacaxi"})
    assert [b["id"] for b in api.list_bots()] == ["abacaxi", "zebra"]


def test_update_bot_muda_so_o_patch(tmp_path):
    api, db = _api(tmp_path)
    api.create_bot({"id": "ajudante", "name": "Ajudante", "model": "nvidia_glm52"})
    out = api.update_bot("ajudante", {"model": "nvidia_nemotron3"})
    assert out["model"] == "nvidia_nemotron3"
    assert out["name"] == "Ajudante"  # resto intacto
    assert db.get_agent("ajudante").model == "nvidia_nemotron3"  # lab junto


def test_update_bot_id_nao_muda(tmp_path):
    api, _ = _api(tmp_path)
    api.create_bot({"id": "ajudante", "name": "Ajudante"})
    with pytest.raises(BotAPIError):
        api.update_bot("ajudante", {"id": "outro"})
    assert api.get_bot("ajudante")["id"] == "ajudante"


def test_update_bot_inexistente_e_campo_ruim(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.update_bot("fantasma", {"name": "X"})
    api.create_bot({"id": "ajudante", "name": "Ajudante"})
    with pytest.raises(BotAPIError):
        api.update_bot("ajudante", {"typo_de_campo": 1})
    with pytest.raises(BotAPIError):
        api.update_bot("ajudante", "nao-um-dict")


def test_delete_bot_apaga_spec_e_arquiva_agente(tmp_path):
    api, db = _api(tmp_path)
    api.create_bot({"id": "ajudante", "name": "Ajudante"})
    out = api.delete_bot("ajudante")
    assert out == {"id": "ajudante", "spec_deleted": True, "lab_archived": True}
    with pytest.raises(BotAPIError):
        api.get_bot("ajudante")
    agent = db.get_agent("ajudante")
    assert agent is not None and agent.archived is True  # historico preservado


def test_delete_bot_inexistente(tmp_path):
    api, _ = _api(tmp_path)
    with pytest.raises(BotAPIError):
        api.delete_bot("fantasma")


def test_sync_lab_registra_tudo(tmp_path):
    store = BotStore(tmp_path / "bots")
    db = LabStore(tmp_path / "lab.db")
    api = BotAPI(store, db)
    api.create_bot({"id": "um", "name": "Um"})
    api.create_bot({"id": "dois", "name": "Dois"})
    # simula specs salvas fora do Lab (p.ex. apos reboot): limpa o banco
    db2 = LabStore(tmp_path / "lab2.db")
    api2 = BotAPI(store, db2)
    out = api2.sync_lab()
    assert out == {"registered": 2}
    assert db2.get_agent("um") is not None
    assert db2.get_agent("dois") is not None


def test_describe_vocabulario(tmp_path):
    api, _ = _api(tmp_path)
    d = api.describe()
    assert "MEMBER" in d["roles"]
    assert d["defaults"]["role"] in d["roles"]
    assert "model.text" in d["capabilities"]
    assert "tools.write" in d["dangerous_capabilities"]
    assert d["defaults"]["provider_id"] == "nvidia"
    assert d["limits"]["max_turns"] == 25
