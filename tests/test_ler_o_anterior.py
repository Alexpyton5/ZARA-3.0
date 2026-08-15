"""ZARA-LER-O-ANTERIOR-001 — pedir de novo não pode devolver o mesmo.

No histórico de 15/08, Alex pediu três vezes seguidas para a ZARA ler o que o
Claude tinha escrito. As três respostas foram idênticas — inclusive quando ele
foi explícito:

    00:16:18  "lê o que o Cláudio respondeu."      -> "Carimbado na fila..."
    00:17:04  "leia o texto inteiro..."            -> "Carimbado na fila..."
    00:17:39  "leia o último texto do Claude,
               ANTES da minha última pergunta."    -> "Carimbado na fila..."

Ela lia sempre a fala mais recente. Entre pessoas isso não acontece: quem acabou
de ler um trecho e é chamado de novo entende que o outro quer o de antes.
"""
from __future__ import annotations

import pytest

from core.actions import ponte_claude as ponte


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    ponte._esquecer_o_que_ja_leu()
    monkeypatch.setattr(ponte, "_arquivos_de_conversa", lambda: ["fake.jsonl"])
    yield
    ponte._esquecer_o_que_ja_leu()


def _falas(monkeypatch, *textos):
    monkeypatch.setattr(ponte, "_falas_do_claude", lambda quantas=6: list(textos))


def test_a_primeira_leitura_traz_a_mais_nova(monkeypatch):
    _falas(monkeypatch, "terceira", "segunda", "primeira")

    texto, erro = ponte._ultima_fala_do_claude()

    assert erro == ""
    assert texto == "terceira"


def test_pedir_de_novo_anda_para_tras(monkeypatch):
    """O bug exato: três pedidos, três vezes o mesmo texto."""
    _falas(monkeypatch, "terceira", "segunda", "primeira")

    lidos = [ponte._ultima_fala_do_claude()[0] for _ in range(3)]

    assert lidos == ["terceira", "segunda", "primeira"], "cada pedido traz um novo"


def test_pedido_explicito_do_anterior_pula_o_que_ja_foi_lido(monkeypatch):
    _falas(monkeypatch, "terceira", "segunda", "primeira")
    ponte._ultima_fala_do_claude()

    texto, _ = ponte._ultima_fala_do_claude(anterior=True)

    assert texto == "segunda"


def test_quando_chega_coisa_nova_ela_volta_para_a_mais_recente(monkeypatch):
    """Se eu escrevi algo enquanto isso, é ISSO que ele quer ouvir."""
    _falas(monkeypatch, "terceira", "segunda", "primeira")
    ponte._ultima_fala_do_claude()

    _falas(monkeypatch, "QUARTA", "terceira", "segunda", "primeira")
    texto, _ = ponte._ultima_fala_do_claude()

    assert texto == "QUARTA"


def test_no_fim_da_pilha_ela_diz_que_acabou(monkeypatch):
    """Melhor dizer que acabou do que repetir o mesmo trecho para sempre."""
    _falas(monkeypatch, "unica")
    ponte._ultima_fala_do_claude()

    texto, erro = ponte._ultima_fala_do_claude()

    assert texto is None
    assert "nao tem mais nada novo" in erro.casefold().replace("ã", "a").replace("ú", "u")


def test_sem_conversa_nenhuma_ela_avisa(monkeypatch):
    monkeypatch.setattr(ponte, "_arquivos_de_conversa", lambda: [])

    texto, erro = ponte._ultima_fala_do_claude()

    assert texto is None
    assert "ainda não há conversa" in erro.casefold()
