"""Item 17 — guard anti-alucinação no ditado (FRENTE 2, 2026-09-29).

Regra de ouro: a IA nunca reescreve o que o Alex não disse. Antes de colar
qualquer reescrita por IA do transcript, o guard mede a similaridade entre o
texto cru e o limpo; se a limpeza se afastar demais (threshold configurável),
o transcript cru vence.

Tudo aqui é função pura — nenhum teste toca rede, modelo ou hardware.
"""
from __future__ import annotations

import pytest

from core.ditado_guard import (
    THRESHOLD_PADRAO,
    ResultadoGuard,
    aplicar_limpeza_com_guard,
    guard_transcript,
    normalizar_para_comparar,
    similaridade_transcricao,
)


# ---------------------------------------------------------------------------
# normalização e similaridade
# ---------------------------------------------------------------------------


def test_normalizar_ignora_caixa_pontuacao_e_espacos():
    assert normalizar_para_comparar("Olá,  MUNDO!") == "olá mundo"
    assert normalizar_para_comparar("  14:30... ") == "14 30"


def test_similaridade_identicos_e_1():
    assert similaridade_transcricao("abre o excel", "abre o excel") == 1.0


def test_similaridade_ignora_caixa_pontuacao_e_ordem():
    assert similaridade_transcricao("oi tudo bem", "Oi, tudo bem?") == 1.0
    assert similaridade_transcricao("excel abre por favor", "por favor excel abre") == 1.0


def test_similaridade_nada_em_comum_e_0():
    assert similaridade_transcricao("abre o excel", "tempo bom hoje") == 0.0


def test_similaridade_vazios():
    assert similaridade_transcricao("", "") == 1.0
    assert similaridade_transcricao("algo", "") == 0.0
    assert similaridade_transcricao("", "algo") == 0.0


def test_similaridade_remocao_de_filler_continua_alta():
    # Tirar "uh" de 8 palavras: 7/8 = 0.875 — limpeza legítima passa.
    sim = similaridade_transcricao(
        "uh eu quero abrir o excel por favor", "eu quero abrir o excel por favor"
    )
    assert sim == pytest.approx(0.875)
    assert sim >= THRESHOLD_PADRAO


# ---------------------------------------------------------------------------
# guard_transcript — caminho feliz
# ---------------------------------------------------------------------------


def test_identico_usa_o_limpo():
    r = guard_transcript("abre o excel", "abre o excel")
    assert r == ResultadoGuard(
        final="abre o excel", usou_cru=False, similaridade=1.0, motivo="identico"
    )


def test_limpeza_legitima_de_filler_usa_o_limpo():
    r = guard_transcript(
        "uh eu quero abrir o excel por favor", "Eu quero abrir o Excel, por favor."
    )
    assert not r.usou_cru
    assert r.final == "Eu quero abrir o Excel, por favor."
    assert r.motivo == "ok"
    assert r.similaridade >= THRESHOLD_PADRAO


def test_limpeza_so_de_pontuacao_usa_o_limpo():
    r = guard_transcript("oi tudo bem", "Oi, tudo bem?")
    assert not r.usou_cru
    assert r.final == "Oi, tudo bem?"


# ---------------------------------------------------------------------------
# guard_transcript — casos que DEVEM cair no fallback (o coração do item)
# ---------------------------------------------------------------------------


def test_ia_inventou_palavra_cai_no_fallback():
    # "e o balanço anual" não foi dito — quebra de confiança se colar.
    r = guard_transcript(
        "me manda o relatório de vendas",
        "me manda o relatório de vendas e o balanço anual",
    )
    assert r.usou_cru
    assert r.final == "me manda o relatório de vendas"
    assert r.motivo == "abaixo_do_threshold"
    assert r.similaridade < THRESHOLD_PADRAO


def test_ia_trocou_o_sentido_cai_no_fallback():
    r = guard_transcript("liga pra minha esposa", "liga para o meu chefe agora")
    assert r.usou_cru
    assert r.final == "liga pra minha esposa"
    assert r.motivo == "abaixo_do_threshold"


def test_ia_reescreveu_tudo_cai_no_fallback():
    r = guard_transcript("abre o excel", "o tempo está bom hoje")
    assert r.usou_cru
    assert r.final == "abre o excel"


def test_ia_cortou_o_nao_cai_no_fallback():
    # Tirar o "não" inverte o sentido — o guard precisa pegar.
    r = guard_transcript("não abre o excel nunca", "abre o excel")
    assert r.usou_cru
    assert r.final == "não abre o excel nunca"
    assert r.motivo == "abaixo_do_threshold"


def test_limpeza_vazia_usa_o_cru():
    r = guard_transcript("abre o excel", "")
    assert r.usou_cru
    assert r.final == "abre o excel"
    assert r.motivo == "limpeza_vazia"


def test_limpeza_so_espacos_usa_o_cru():
    r = guard_transcript("abre o excel", "   ")
    assert r.usou_cru
    assert r.motivo == "limpeza_vazia"


# ---------------------------------------------------------------------------
# threshold configurável
# ---------------------------------------------------------------------------


def test_threshold_rigoroso_rejeita_limpeza_bordeline():
    # "abre o excel favor": 4/5 = 0.80 — exatamente na borda do padrão.
    # Com threshold 0.99 cai no fallback...
    r = guard_transcript("abre o excel por favor", "abre o excel favor", threshold=0.99)
    assert r.usou_cru
    assert r.motivo == "abaixo_do_threshold"
    # ...com threshold 0.70, passa.
    r2 = guard_transcript("abre o excel por favor", "abre o excel favor", threshold=0.70)
    assert not r2.usou_cru
    assert r2.final == "abre o excel favor"


def test_threshold_padrao_e_0_80():
    assert THRESHOLD_PADRAO == 0.80


# ---------------------------------------------------------------------------
# aplicar_limpeza_com_guard — o funil completo
# ---------------------------------------------------------------------------


def test_aplicacao_ok_passando_pelo_guard():
    def ia_limpar(texto):
        return texto.replace("uh ", "").strip().capitalize() + "."

    r = aplicar_limpeza_com_guard("uh abre o excel por favor agora", ia_limpar)
    assert not r.usou_cru
    assert r.final == "Abre o excel por favor agora."


def test_ia_quebrou_nao_quebra_o_ditado():
    def ia_limpar(_texto):
        raise RuntimeError("LLM fora do ar")

    r = aplicar_limpeza_com_guard("abre o excel", ia_limpar)
    assert r.usou_cru
    assert r.final == "abre o excel"
    assert r.motivo == "limpeza_falhou"


def test_ia_alucinou_no_funil_completo_cai_no_cru():
    def ia_limpar(texto):
        return texto + " e depois me traz um café"

    r = aplicar_limpeza_com_guard("abre o excel", ia_limpar)
    assert r.usou_cru
    assert r.final == "abre o excel"


def test_sem_funcao_de_limpeza_usa_o_cru():
    r = aplicar_limpeza_com_guard("abre o excel", None)
    assert r.usou_cru
    assert r.final == "abre o excel"
    assert r.motivo == "limpeza_vazia"
