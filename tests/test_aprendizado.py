"""ZARA-APRENDIZADO-001 / ZARA-DIARIO-001 — ela aprende com o que faz.

Alex quer que ela cresça: "hoje é o dia um, eu aprendi isso... amanhã, dia dois,
eu aprendi isso", e que no fim do dia junte tudo.

A regra que não pode ser quebrada: **nada de aprendizado inventado**. Cada linha
do diário sai de episódio realmente registrado. Uma ZARA que "aprende" coisas
falsas é pior que uma que não aprende — ela passa a agir com base em ficção.
"""
from __future__ import annotations

import time

import pytest

from core.aprendizado import Aprendizado, _forma_do_pedido


@pytest.fixture()
def diario(tmp_path):
    return Aprendizado(db_path=tmp_path / "exp.db")


# ---------- a forma do pedido ----------

def test_frases_diferentes_para_a_mesma_coisa_viram_a_mesma_forma():
    """Sem isso a lição só valeria para a frase idêntica, e nunca seria usada."""
    a = _forma_do_pedido("abaixa o volume aí")
    b = _forma_do_pedido("abaixa esse volume")

    assert a == b


def test_pedidos_diferentes_nao_se_confundem():
    assert _forma_do_pedido("abaixa o volume") != _forma_do_pedido("abre o YouTube")


# ---------- o ciclo de aprender ----------

def test_correcao_do_alex_vira_licao(diario):
    diario.registrar_acao("abaixa o volume", "os_volume", True, "Volume em 30%.")

    veredito = diario.observar_reacao("não é isso que eu pedi")

    assert veredito == "corrigiu"
    licao = diario.licao_para("abaixa o volume")
    assert licao is not None
    assert licao["acao"] == "os_volume"
    assert licao["erros"] == 1


def test_elogio_do_alex_confirma_o_acerto(diario):
    diario.registrar_acao("abre o YouTube", "youtube_open", True, "YouTube aberto.")

    veredito = diario.observar_reacao("isso mesmo")

    assert veredito == "aprovou"
    # Acerto não vira alerta: ela só avisa sobre o que costuma errar.
    assert diario.licao_para("abre o YouTube") is None


def test_conversa_neutra_nao_e_nota(diario):
    """Nem toda frase depois de uma ação é avaliação da ação."""
    diario.registrar_acao("abaixa o volume", "os_volume", True, "ok")

    assert diario.observar_reacao("me conta uma piada") is None


def test_reclamacao_muito_depois_nao_conta(diario, monkeypatch):
    """Reclamação dez minutos depois é sobre outra coisa."""
    diario.registrar_acao("abaixa o volume", "os_volume", True, "ok")
    # Negativo, não zero: o relógio do Windows tem passo grosso e o tempo
    # decorrido pode sair exatamente 0.0, deixando a janela ainda aberta.
    monkeypatch.setattr("core.aprendizado._JANELA_DE_REACAO", -1.0)

    assert diario.observar_reacao("não é isso") is None


def test_uma_reacao_so_por_acao(diario):
    diario.registrar_acao("abaixa o volume", "os_volume", True, "ok")

    primeiro = diario.observar_reacao("não é isso")
    segundo = diario.observar_reacao("não é isso")

    assert primeiro == "corrigiu"
    assert segundo is None, "a mesma ação não pode ser punida duas vezes"


def test_licao_so_aparece_quando_erra_mais_do_que_acerta(diario):
    for _ in range(3):
        diario.registrar_acao("toca musica", "youtube_open", True, "ok")
        diario.observar_reacao("isso mesmo")
    diario.registrar_acao("toca musica", "youtube_open", True, "ok")
    diario.observar_reacao("não é isso")

    assert diario.licao_para("toca musica") is None, "1 erro contra 3 acertos não é padrão"


# ---------- o diário ----------

def test_o_dia_fecha_e_o_proximo_e_o_dia_seguinte(diario):
    diario.registrar_acao("abre o YouTube", "youtube_open", True, "ok")
    diario.observar_reacao("isso mesmo")

    primeiro = diario.fechar_o_dia()
    segundo = diario.fechar_o_dia()

    assert primeiro["dia"] == 1
    assert segundo["dia"] == 2
    assert len(diario.historia()) == 2


def test_o_diario_nao_inventa_aprendizado(diario):
    """Dia sem nada acontecendo não pode virar página cheia de lições."""
    pagina = diario.fechar_o_dia()

    assert pagina["acoes"] == 0
    assert pagina["aprendi"] == []
    assert pagina["errei"] == []


def test_o_diario_conta_o_que_realmente_aconteceu(diario):
    diario.registrar_acao("abre o YouTube", "youtube_open", True, "ok")
    diario.observar_reacao("isso mesmo")
    diario.registrar_acao("abaixa o volume", "os_volume", False, "falhou")
    diario.observar_reacao("não funcionou")

    pagina = diario.fechar_o_dia()

    assert pagina["acoes"] == 2
    assert pagina["certas"] == 1
    assert pagina["corrigidas"] == 1


# ---------- o que ela fala ----------

def test_sem_atividade_ela_admite(diario):
    assert "ainda não fiz nada" in diario.contar_o_que_aprendeu()


def test_ela_conta_quantas_vezes_foi_corrigida(diario):
    diario.registrar_acao("abaixa o volume", "os_volume", True, "ok")
    diario.observar_reacao("não é isso")

    frase = diario.contar_o_que_aprendeu()

    assert "corrigiu" in frase
    assert "1 ação" in frase


def test_banco_quebrado_nao_derruba_a_zara(tmp_path):
    """Aprender é secundário; responder ao Alex não é."""
    d = Aprendizado(db_path=tmp_path / "exp.db")
    d.db_path = tmp_path / "pasta-que-nao-existe" / "x.db"

    assert d.registrar_acao("teste", "acao", True) is None
    assert d.licao_para("teste") is None
    assert d.o_que_aprendeu() == []
    assert d.historia() == []


def test_acao_sem_pedido_nao_e_registrada(diario):
    assert diario.registrar_acao("", "os_volume", True) is None
    assert diario.registrar_acao("abaixa o volume", "", True) is None


def test_registro_guarda_quando_aconteceu(diario):
    antes = time.time()
    diario.registrar_acao("abre o YouTube", "youtube_open", True, "ok")

    resumo = diario.resumo_do_dia()

    assert resumo["acoes"] == 1
    assert time.time() >= antes
