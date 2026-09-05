"""ZARA-NOMES-DA-CASA-001 — o STT insiste em "Cláudio".

No histórico de 15/08, três pedidos seguidos do Alex:

    "leiam o que o Cláudio respondeu."
    "leia o que o Cláudio falou."
    "lê o que o Cláudio respondeu."

Já existe uma instrução de vocabulário no modelo, e ela ajuda — mas pedir ao
modelo é probabilidade, não regra. Aqui a correção é determinística e roda antes
de qualquer intent, no mesmo ponto por onde passam voz e texto.

Só nome próprio da casa entra na tabela: corrigir palavra comum seria reescrever
o que o Alex disse, e isso é pior do que errar um nome.
"""
from __future__ import annotations

import pytest

from core.ipc_handlers import _canonical_request, _corrigir_nomes_da_casa


@pytest.mark.parametrize("ouvido,esperado", [
    ("leiam o que o Cláudio respondeu", "leiam o que o Claude respondeu"),
    ("lê o que o Claudio falou", "lê o que o Claude falou"),
    ("responde pro cláudio", "responde pro Claude"),
    ("o que os cláudios falaram", "o que os Claude falaram"),
    ("abre o cloud code", "abre o Claude Code"),
    ("manda pro codec", "manda pro Codex"),
    ("codec, roda os testes", "Codex, roda os testes"),
    ("a voz da corei", "a voz da Kore"),
    ("a zarah está ouvindo", "a ZARA está ouvindo"),
])
def test_nome_da_casa_e_corrigido(ouvido, esperado):
    assert _corrigir_nomes_da_casa(ouvido) == esperado


# Achado 23 da auditoria: "codec" e palavra legitima. Corrigir sempre
# transformava "pesquise codecs de audio" em "pesquise Codex de audio".
@pytest.mark.parametrize("frase", [
    "pesquise codecs de audio",
    "esse codec nao abre no meu player",
    "abre o youtube",
    "diminui o volume",
    "que horas são",
    "me conta uma piada sobre nuvem",
])
def test_frase_sem_nome_da_casa_nao_e_tocada(frase):
    assert _corrigir_nomes_da_casa(frase) == frase


def test_a_correcao_acontece_no_caminho_canonico():
    """Voz e texto passam pelo mesmo ponto — a correção tem de estar nele."""
    assert "Claude" in _canonical_request("Zara, lê o que o Cláudio falou")


def test_a_correcao_nao_atrapalha_o_wake():
    assert _canonical_request("Zara, abre o YouTube") == "abre o YouTube"
