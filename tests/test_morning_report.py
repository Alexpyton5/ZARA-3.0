"""Testes da FRENTE H — relatorio da manha no formato do Alex.

Regras testadas: formato exato, resultados primeiro, fonte obrigatoria
(nunca inventa), "a noite falhou" quando nada tocavel, teto de tamanho.
Logica pura — sem disco real, sem rede.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.morning_report import (
    ABERTURA,
    MAX_ITENS,
    NOITE_FALHOU,
    FatosNoite,
    ItemNoite,
    auditoria,
    coletar_fatos,
    gerar_relatorio,
    traduzir,
)


def _item(texto="frase simples", fonte="commit abc1234", tocavel=True):
    return ItemNoite(texto=texto, fonte=fonte, tocavel=tocavel)


# --- formato exato -----------------------------------------------------------

def test_abertura_e_exatamente_a_pedida():
    rel = gerar_relatorio([_item()])
    assert rel.splitlines()[0] == ABERTURA
    assert ABERTURA == "Bom dia Alex, as atualizacoes da Zara de hoje sao essas:"


def test_itens_viram_bullets_na_ordem_recebida():
    rel = gerar_relatorio([_item("primeira"), _item("segunda")])
    linhas = rel.splitlines()
    assert linhas[2] == "- primeira"
    assert linhas[3] == "- segunda"


# --- resultados primeiro / verdade radical ------------------------------------

def test_tocaveis_vem_primeiro():
    rel = gerar_relatorio([
        _item("infra", tocavel=False),
        _item("feature que ele toca", tocavel=True),
    ])
    linhas = rel.splitlines()
    assert linhas[2] == "- feature que ele toca"
    assert "- infra" not in rel  # nao tocavel nao vai p/ o texto dele


def test_sem_nada_tocavel_diz_a_noite_falhou():
    rel = gerar_relatorio([_item("infra", tocavel=False)])
    assert ("- " + NOITE_FALHOU) in rel


def test_lista_vazia_diz_a_noite_falhou():
    rel = gerar_relatorio([])
    assert ("- " + NOITE_FALHOU) in rel


# --- nunca inventa: fonte obrigatoria ------------------------------------------

def test_item_sem_fonte_nao_entra():
    with pytest.raises(ValueError, match="sem fonte"):
        gerar_relatorio([ItemNoite(texto="feature", fonte="", tocavel=True)])


def test_item_sem_texto_nao_entra():
    with pytest.raises(ValueError, match="sem texto"):
        gerar_relatorio([ItemNoite(texto="  ", fonte="quadro", tocavel=True)])


def test_item_longo_demais_nao_entra():
    with pytest.raises(ValueError, match="longo demais"):
        gerar_relatorio([_item(texto="x" * 500)])


def test_teto_maximo_de_itens():
    itens = [_item("item %d" % i) for i in range(MAX_ITENS + 5)]
    rel = gerar_relatorio(itens)
    bullets = [ln for ln in rel.splitlines() if ln.startswith("- ")]
    assert len(bullets) == MAX_ITENS


# --- traducao: commit sem traducao nao vira frase --------------------------------

def test_traduzir_commit_com_traducao_vira_item_com_fonte():
    fatos = FatosNoite(commits=[("47c3234", "Pulso do Lab: faixa viva")])
    itens, sem = traduzir(fatos, {"47c3234": "frase simples"})
    assert len(itens) == 1
    assert itens[0].texto == "frase simples"
    assert "47c3234" in itens[0].fonte
    assert sem == []


def test_traduzir_commit_sem_traducao_nao_inventa():
    fatos = FatosNoite(commits=[("deadbee", "assunto tecnico obscuro")])
    itens, sem = traduzir(fatos, {})
    assert itens == []
    assert sem == ["deadbee assunto tecnico obscuro"]


# --- coleta fail closed ---------------------------------------------------------

def test_coletar_fatos_em_pasta_vazia_nao_inventa_nada(tmp_path):
    fatos = coletar_fatos(tmp_path)
    assert fatos.commits == []
    assert fatos.suite == {}
    assert fatos.concluidos == []


def test_coletar_suite_le_latest_json(tmp_path):
    pasta = tmp_path / ".zara-tests"
    pasta.mkdir()
    (pasta / "latest.json").write_text(json.dumps({
        "run_id": "2026-09-28_16-44-46",
        "result": {"passed": 2776, "failed": 2, "summary_line": "= 2 failed ="},
    }), encoding="utf-8")
    fatos = coletar_fatos(tmp_path)
    assert fatos.suite["passed"] == 2776
    assert fatos.suite["failed"] == 2
    assert fatos.suite["run_id"] == "2026-09-28_16-44-46"


# --- auditoria --------------------------------------------------------------------

def test_auditoria_mostra_fonte_de_cada_item():
    itens = [_item("feature", fonte="commit 47c3234")]
    extras = [_item("infra", fonte="quadro 10:39", tocavel=False)]
    aud = auditoria(itens, extras=extras)
    assert "commit 47c3234" in aud
    assert "quadro 10:39" in aud
    assert "TOCAVEL" in aud
