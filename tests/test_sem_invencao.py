"""ZARA-SEM-INVENCAO-001 — a ZARA não preenche vazio com coisa que soa bem.

Alex, depois de pegar ela mentindo:

    "tente deixar ela sem mentiras e sem chutes ou invenções; se não souber, ela
     deve ser sempre transparente... tem que ser o mais próximo de uma conversa
     entre humanos em todos os sentidos."

O que ele pegou, no histórico de 15/08:
  - perguntou três vezes quanto ela demorava e ouviu "2,01 segundos" nas três,
    um número que nunca foi medido por ninguém;
  - perguntou "você entendeu?" e ouviu "sim, entendi com certeza", seguido de um
    chute errado sobre o assunto.

As duas falhas têm a mesma raiz: preencher o vazio com algo plausível. Um número
inventado é pior que um "não sei", porque convence.

Estes testes travam a instrução no lugar. Eles não provam que o modelo obedece —
isso só o uso real prova. Provam que a ordem existe e não sumiu num refactor.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.gemini_live_voice import GeminiLiveVoiceConfig

# A instrução vive como valor padrão de um campo da config, não como constante
# solta — leio de lá para o teste não depender de um apelido que pode sumir.
INSTRUCAO = next(
    c.default for c in dataclasses.fields(GeminiLiveVoiceConfig)
    if c.name == "system_instruction"
)


@pytest.mark.parametrize("proibicao", [
    "NUNCA invente número",
    "medida",
    "duração",
    "estatística",
])
def test_a_proibicao_de_inventar_dado_esta_escrita(proibicao):
    assert proibicao.casefold() in INSTRUCAO.casefold(), proibicao


def test_ela_e_mandada_admitir_que_nao_sabe():
    baixo = INSTRUCAO.casefold()
    assert "diga que não tem" in baixo
    assert "diga que não sabe" in baixo


def test_confirmacao_vazia_e_proibida_por_escrito():
    """"Sim, entendi" sem dizer o quê era a resposta que irritou o Alex."""
    baixo = INSTRUCAO.casefold()
    assert "nunca responda 'sim, entendi'" in baixo
    assert "o que entendeu" in baixo


def test_disfarce_de_chute_e_proibido():
    assert "aproximadamente" in INSTRUCAO.casefold(), (
        "sem isto ela troca o chute por um chute com cara de estimativa"
    )


def test_a_regra_antiga_de_nao_alegar_acao_continua_viva():
    """Regressão: a proibição nova não pode ter empurrado a antiga para fora."""
    baixo = INSTRUCAO.casefold()
    assert "você não executa ações" in baixo
    assert "não descreva sucesso" in baixo


def test_o_vocabulario_da_casa_continua_vivo():
    """Ela voltou a ouvir "Cláudio" em 15/08; a regra tem de estar aqui."""
    assert "NUNCA escreva Cláudio" in INSTRUCAO


def test_a_ordem_de_falar_como_gente_esta_la():
    baixo = INSTRUCAO.casefold()
    assert "fale como uma pessoa falaria" in baixo
    assert "sem fórmula pronta" in baixo
