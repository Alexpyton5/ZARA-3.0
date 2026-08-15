"""ZARA-MEMORIA-AUTOMATICA-001 — ela anota sozinha, sem virar transcrição.

A gaveta de memória já existia; ninguém colocava nada dentro. Estes testes
travam as duas metades do acerto:

  1. o que É preferência ou fato sobre o Alex vira memória;
  2. o que NÃO é — comando, pergunta, conversa fiada, segredo — fica de fora.

A segunda metade importa mais. Uma memória que guarda tudo não é memória: é
transcrição, e polui a busca a ponto de valer menos que nada.
"""
from __future__ import annotations

import pytest

from core.memoria_automatica import _parecidas, classificar, guardar_se_valer


class _MemoriaFalsa:
    def __init__(self, existentes=None):
        self.guardados = []
        self._existentes = existentes or []

    def search(self, query, category=None, limit=5, **_):
        return [{"fact": f} for f in self._existentes]

    def add(self, fact, *, category="semantic_fact", confidence=0.6, source="manual", **_):
        registro = {"fact": fact, "category": category,
                    "confidence": confidence, "source": source}
        self.guardados.append(registro)
        return registro


@pytest.mark.parametrize("frase,categoria", [
    ("eu prefiro respostas curtas e diretas", "preference"),
    ("eu não gosto de relatório grande", "preference"),
    ("de agora em diante me poupe dos detalhes técnicos", "preference"),
    ("eu não quero menu abrindo quando eu pedir algo", "preference"),
    ("eu sou o Alex e não entendo de programação", "semantic_fact"),
    ("meu objetivo é transformar a ZARA na Jarvis de verdade", "semantic_fact"),
    ("estou tentando fazer ela responder mais rápido", "semantic_fact"),
])
def test_o_que_importa_vira_memoria(frase, categoria):
    resultado = classificar(frase)
    assert resultado is not None, f"perdeu: {frase}"
    assert resultado[0] == categoria


@pytest.mark.parametrize("frase", [
    # comando do momento — não é fato sobre ele
    "abre o YouTube e coloca o volume em 30",
    "Zara, diminui o volume",
    "lê o que o Claude falou",
    "me lembre de comprar pão daqui a 2 minutos",
    # pergunta não é afirmação
    "eu prefiro qual dos dois?",
    "que horas são",
    # conversa fiada
    "oi tudo bem",
    "obrigado",
    "ok",
    # curto demais para significar algo
    "eu sou",
])
def test_o_que_nao_importa_fica_de_fora(frase):
    assert classificar(frase) is None, f"guardou lixo: {frase}"


@pytest.mark.parametrize("frase", [
    "eu prefiro que a senha seja 1234abcd",
    "meu token é sk-abc123def456",
    "eu uso a chave api do gemini que é AIzaSy",
])
def test_segredo_nunca_vira_memoria(frase):
    """Guardar segredo em banco de fatos é vazamento, não memória."""
    assert classificar(frase) is None


def test_frase_gigante_nao_vira_memoria():
    assert classificar("eu prefiro " + "muito " * 100) is None


def test_guarda_de_verdade_na_gaveta():
    mem = _MemoriaFalsa()

    resultado = guardar_se_valer(mem, "eu prefiro respostas curtas", origem="voz")

    assert resultado is not None
    assert len(mem.guardados) == 1
    assert mem.guardados[0]["category"] == "preference"
    assert mem.guardados[0]["source"] == "voz"


def test_nao_repete_o_que_ja_esta_guardado():
    """Sem isto, a mesma preferência vira dez registros em uma semana."""
    mem = _MemoriaFalsa(existentes=["eu prefiro respostas curtas e diretas"])

    resultado = guardar_se_valer(mem, "eu prefiro respostas bem curtas")

    assert resultado is None
    assert mem.guardados == []


def test_fato_diferente_e_guardado_mesmo_havendo_outros():
    mem = _MemoriaFalsa(existentes=["eu prefiro respostas curtas"])

    resultado = guardar_se_valer(mem, "eu não gosto de menu abrindo na tela")

    assert resultado is not None
    assert len(mem.guardados) == 1


def test_memoria_quebrada_nao_derruba_a_conversa():
    """Falha ao anotar é irrelevante para o Alex; travar a resposta não é."""
    class MemoriaQuebrada:
        def search(self, *a, **k):
            raise RuntimeError("banco fora do ar")

        def add(self, *a, **k):
            raise RuntimeError("banco fora do ar")

    assert guardar_se_valer(MemoriaQuebrada(), "eu prefiro respostas curtas") is None


def test_sem_memoria_configurada_nao_explode():
    assert guardar_se_valer(None, "eu prefiro respostas curtas") is None


def test_comparacao_de_frases_parecidas():
    assert _parecidas("eu prefiro respostas curtas", "prefiro respostas bem curtas") is True
    assert _parecidas("eu prefiro respostas curtas", "eu moro em Salvador") is False
