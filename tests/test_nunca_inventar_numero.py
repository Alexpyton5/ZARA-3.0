"""ZARA-NUNCA-INVENTAR-NUMERO-001 — precisão inventada é pior que "não sei".

Alex perguntou "quanto tempo você demorou?" três vezes seguidas e recebeu
"2,01 segundos" nas três. Ele desconfiou sozinho:

    "você não tá me enganando com essa informação, não, porque toda hora você
     dá a mesma?"

Estava. O número não veio de medição nenhuma — a pergunta não casava com o
padrão (ele disse "demorou", o padrão exigia "demora"), caía no modelo, e o
modelo produziu uma frase que soa técnica.

Um número inventado é mais perigoso que uma recusa: ele convence, e destrói a
confiança em todo o resto quando é descoberto.
"""
from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.parametrize("frase", [
    # as três formas exatas que ele usou no dia 15/08
    "quanto tempo você demorou?",
    "quanto tempo você tá demorando?",
    "você entendeu? quanto tempo demorou",
    # variações plausíveis dele
    "quanto tempo você levou pra responder",
    "quanto tempo isso demorou",
    "qual a sua latência",
    "qual sua velocidade",
    "você está lenta",
    "você tá demorando demais",
    "onde está o tempo",
    "demorou quanto pra responder",
])
def test_pergunta_de_tempo_nunca_chega_no_modelo(frase):
    assert IPCHandler._PERGUNTA_DE_LATENCIA.search(frase), frase


@pytest.mark.parametrize("frase", [
    "abre o youtube",
    "que horas são",
    "me conta uma piada",
    "diminui o volume",
    "quanto custa um carro novo",
    "quanto tempo faz que a gente se conhece",
])
def test_conversa_normal_nao_vira_relatorio_de_latencia(frase):
    """Interceptar demais transformaria papo em relatório técnico."""
    assert not IPCHandler._PERGUNTA_DE_LATENCIA.search(frase), frase


def test_sem_medicao_ela_diz_que_nao_mediu(monkeypatch):
    """O ponto inteiro: sem dado, ela admite — não preenche com um número."""
    monkeypatch.setattr(
        "core.cronometro.relatorio", lambda *a, **k: {"turnos": 0, "aviso": "nada medido"}
    )

    resposta = IPCHandler._contar_a_latencia()

    assert resposta
    assert "ainda não medi" in resposta.casefold()
    assert "segundo" not in resposta.casefold(), "não pode aparecer número nenhum"


def test_com_medicao_ela_devolve_o_numero_real(monkeypatch):
    monkeypatch.setattr("core.cronometro.relatorio", lambda *a, **k: {
        "turnos": 12,
        "total_ms_mediano": 2400,
        "etapas_ms_medianas": {"antes_de_falar": 400},
    })

    resposta = IPCHandler._contar_a_latencia()

    assert "12 turnos" in resposta
    assert "2.4" in resposta or "2,4" in resposta
    assert "0.4" in resposta or "0,4" in resposta, "tem de separar pensar de falar"


# ---------- ZARA-CONFIRMACAO-VAZIA-001 ----------
#
# No log de 15/08, tres vezes seguidas:
#   Alex: "voce entendeu?"                 ZARA: "Sim, entendi com certeza!"
#   Alex: "voce entendeu o que eu falei?"  ZARA: "Sim, entendi com clareza."
# Numa delas ela ainda CHUTOU o assunto e errou.
#
# Ele chamou de robotico. E pior: e uma confirmacao que nao confirma nada.


@pytest.mark.parametrize("frase", [
    "você entendeu?",
    "você entendeu o que eu falei?",
    "você entendeu a última pergunta que eu fiz?",
    "vc me entendeu",
    "tá me ouvindo?",
    "você tá aí?",
])
def test_pergunta_de_confirmacao_e_interceptada(frase):
    assert IPCHandler._PERGUNTA_SE_ENTENDEU.search(frase), frase


@pytest.mark.parametrize("frase", [
    "abre o youtube",
    "me explica o que você entende de música",
    "diminui o volume",
])
def test_conversa_normal_nao_vira_confirmacao(frase):
    assert not IPCHandler._PERGUNTA_SE_ENTENDEU.search(frase), frase


def test_ela_cita_o_pedido_em_vez_de_afirmar_que_entendeu():
    h = IPCHandler.__new__(IPCHandler)
    h._ultimo_pedido_entendido = "me dá as principais notícias do mundo da IA hoje"

    r = h._confirmar_o_que_entendeu()

    assert "notícias do mundo da IA" in r, "tem de CITAR, nao so dizer que sim"


def test_sem_nada_guardado_ela_admite_em_vez_de_fingir():
    """O caso que gerou o bug: ela dizia "sim, entendi" sem ter entendido."""
    h = IPCHandler.__new__(IPCHandler)
    h._ultimo_pedido_entendido = ""

    r = h._confirmar_o_que_entendeu()

    assert "não peguei" in r.casefold()
    assert "sim" not in r.casefold()[:10], "nao pode comecar confirmando"


def test_frase_longa_e_cortada_sem_virar_monologo():
    h = IPCHandler.__new__(IPCHandler)
    h._ultimo_pedido_entendido = "palavra " * 60

    r = h._confirmar_o_que_entendeu()

    assert len(r) < 200
    assert '..."' in r
