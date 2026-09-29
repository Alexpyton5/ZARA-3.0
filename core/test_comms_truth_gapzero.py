# -*- coding: utf-8 -*-
"""GAP-ZERO frente 3 — testes da verdade dos canais de comunicacao.

Cada ponto do mapa tem caminho real OU rotulo honesto; o padrao (tudo atalho)
e byte-identico ao golden; e o modo "real" sem provedor e fail-closed
(nunca inventa numero).
"""

import hashlib

import pytest

from core import comms_truth as ct


def test_01_surfaces_enumeradas():
    assert len(ct.SURFACES) >= 8, "o mapa precisa cobrir todos os pontos"
    keys = [s["key"] for s in ct.SURFACES]
    assert len(keys) == len(set(keys)), "chave duplicada no mapa"
    for surface in ct.SURFACES:
        for field in ("key", "label", "file", "line", "finge_ser", "status", "evidencia", "decisao"):
            assert surface.get(field), f"{surface.get('key')}: campo {field!r} vazio"
        assert surface["status"] in ("atalho", "real", "demo"), surface["key"]
        assert "PENDENTE DO ALEX" in surface["decisao"], surface["key"]


def test_02_padrao_e_atalho_e_byte_identico():
    modes = ct.default_modes()
    assert set(modes) == set(ct.CHANNELS)
    assert all(mode == "atalho" for mode in modes.values())
    # o padrao serializado nao mudou nem um byte
    assert hashlib.sha256(ct.DEFAULT_CONFIG_JSON).hexdigest() == ct.GOLDEN_DEFAULT_SHA256
    assert ct.golden_default_sha256() == ct.GOLDEN_DEFAULT_SHA256
    # arquivo ausente/invalido = padrao honesto
    assert ct.load_modes("/caminho/que/nao/existe.json") == modes


def test_03_cada_ponto_tem_caminho_real_ou_rotulo_honesto():
    for channel in ct.CHANNELS:
        resolved = ct.resolve_channel(channel)
        assert resolved["honest_label"], channel
        assert "atalho" in resolved["honest_label"], channel
        assert "PENDENTE DO ALEX" in resolved["pending_decision"], channel
        # sem provedor real registrado: nenhum numero, em nenhum modo
        assert resolved["counts_available"] is False
        assert resolved["unread"] is None
    checked = ct.assert_all_surfaces_honest()
    assert len(checked) == len(ct.SURFACES)


def test_04_modo_real_sem_provedor_e_fail_closed(tmp_path):
    cfg = tmp_path / "comms.json"
    ct.save_mode("gmail", "real", path=cfg)
    assert ct.load_modes(cfg)["gmail"] == "real"
    resolved = ct.resolve_channel("gmail", path=cfg)
    assert resolved["mode"] == "real"
    # fail-closed: flag ligada mas sem fonte real = mostra "—", nunca numero
    assert resolved["counts_available"] is False
    assert resolved["unread"] is None
    assert resolved["source"] is None


def test_05_caminho_real_esta_pronto_para_ligar(tmp_path):
    cfg = tmp_path / "comms.json"
    ct.save_mode("telegram", "real", path=cfg)

    def provedor_teste():
        return {"unread": 3, "source": "provedor-de-teste"}

    ct.register_real_provider("telegram", provedor_teste)
    try:
        resolved = ct.resolve_channel("telegram", path=cfg)
        assert resolved["counts_available"] is True
        assert resolved["unread"] == 3
        assert resolved["source"] == "provedor-de-teste"
    finally:
        ct.unregister_real_provider("telegram")
    # sem o provedor, volta ao fail-closed
    resolved = ct.resolve_channel("telegram", path=cfg)
    assert resolved["counts_available"] is False
    assert resolved["unread"] is None


def test_06_provedor_quebrado_nao_vira_numero(tmp_path):
    cfg = tmp_path / "comms.json"
    ct.save_mode("whatsapp", "real", path=cfg)

    def provedor_quebrado():
        raise RuntimeError("rede caiu")

    def provedor_mentiroso():
        return {"unread": -5, "source": ""}

    ct.register_real_provider("whatsapp", provedor_quebrado)
    try:
        resolved = ct.resolve_channel("whatsapp", path=cfg)
        assert resolved["unread"] is None
    finally:
        ct.unregister_real_provider("whatsapp")
    ct.register_real_provider("whatsapp", provedor_mentiroso)
    try:
        resolved = ct.resolve_channel("whatsapp", path=cfg)
        assert resolved["unread"] is None
        assert resolved["counts_available"] is False
    finally:
        ct.unregister_real_provider("whatsapp")


def test_07_save_mode_valida_entradas(tmp_path):
    cfg = tmp_path / "comms.json"
    with pytest.raises(ValueError):
        ct.save_mode("sinal", "real", path=cfg)
    with pytest.raises(ValueError):
        ct.save_mode("gmail", "talvez", path=cfg)
    assert ct.save_mode("instagram", "atalho", path=cfg) == "atalho"
    assert ct.load_modes(cfg)["instagram"] == "atalho"


def test_08_trava_c3_continua_verde():
    from core.truth_registry import assert_no_fake_backend_strings

    assert assert_no_fake_backend_strings() == []


def test_09_resumo_honesto_publicado():
    summary = ct.honest_summary()
    assert summary["ligado"] == []
    assert len(summary["atalho_honesto"]) == 7
    assert len(summary["demo"]) == 1
    decisions = ct.pending_decisions()
    assert len(decisions) == len(ct.SURFACES)
    assert all("PENDENTE DO ALEX" in text for _, text in decisions)
