"""ZARA-JANELA-DE-CONVERSA-001 e ZARA-SILENCIO-VISIVEL-001.

Alex, depois de conversar com ela:

    "na medida que a gente conversava ela às vezes ouvia um comando e não me
     respondia nada... eu tinha que ficar falando 'Zara, você me entendeu?',
     aí ela ressuscitava. Isso é muito robótico, quero a conversação natural."

Duas causas, e as duas estavam no mesmo lugar:

1. A janela de continuação durava 8 e 12 segundos. Os intervalos REAIS entre as
   frases dele, medidos no histórico de 15/08, foram 17, 29, 36, 48, 55, 66, 69
   e 86 segundos — ele lê, pensa, responde. Quase toda frase caía fora.

2. O descarte era INVISÍVEL. O banco de conversa só guarda turno aceito, então
   o histórico mostrava um diálogo perfeito enquanto ele falava sozinho na sala.
   Bug invisível vira adivinhação, e adivinhação custou semanas a este projeto.
"""
from __future__ import annotations

import json

import pytest

from core import cronometro
from core.ipc_handlers import IPCHandler


@pytest.fixture(autouse=True)
def _arquivo_isolado(monkeypatch, tmp_path):
    alvo = tmp_path / "latencia.jsonl"
    monkeypatch.setattr(cronometro, "_arquivo", lambda: alvo)
    return alvo


# ---------- a janela ----------

@pytest.mark.parametrize("pausa", [17, 29, 36, 48, 55, 66, 69])
def test_as_pausas_reais_dele_cabem_na_janela(pausa):
    """Cada um destes é um intervalo medido no histórico do dia 15/08.

    Com a janela antiga de 8 s, TODOS eram descartados em silêncio.
    """
    assert pausa < IPCHandler._JANELA_DE_CONVERSA, (
        f"pausa de {pausa}s continuaria sendo ignorada"
    )


def test_a_janela_nao_e_eterna():
    """Janela infinita transformaria conversa de fundo e TV em comando."""
    assert IPCHandler._JANELA_DE_CONVERSA <= 120.0


def test_a_janela_cresceu_de_verdade():
    assert IPCHandler._JANELA_DE_CONVERSA > 12.0, "12 s era o valor que falhava"


# ---------- o silêncio visível ----------

def test_descarte_deixa_rastro(_arquivo_isolado):
    cronometro.anotar_descarte("me da as noticias de hoje", "sem_wake_e_fora_da_janela")

    linhas = _arquivo_isolado.read_text(encoding="utf-8").strip().splitlines()
    r = json.loads(linhas[0])
    assert r["rota"] == "descartado"
    assert r["motivo"] == "sem_wake_e_fora_da_janela"
    # ZARA-DESCARTE-SEM-SEGREDO-001: a fala inteira nao vai mais para o disco.
    # Ficam as primeiras palavras, que bastam para eu reconhecer o que se perdeu
    # sem transcrever a sala do Alex.
    assert "me da as noticias" in r["inicio"]
    assert "frase" not in r


def test_o_motivo_do_descarte_distingue_eco_de_janela(_arquivo_isolado):
    """São defeitos diferentes e o conserto de cada um é diferente."""
    cronometro.anotar_descarte("bom dia alex", "eco_da_propria_voz")
    cronometro.anotar_descarte("abre o youtube", "sem_wake_e_fora_da_janela")

    motivos = [json.loads(x)["motivo"]
               for x in _arquivo_isolado.read_text(encoding="utf-8").strip().splitlines()]
    assert motivos == ["eco_da_propria_voz", "sem_wake_e_fora_da_janela"]


def test_anotar_descarte_nunca_derruba_a_voz(monkeypatch):
    monkeypatch.setattr(cronometro, "_arquivo", lambda: (_ for _ in ()).throw(OSError("cheio")))

    cronometro.anotar_descarte("qualquer coisa", "seja_qual_for")  # não pode levantar


def test_o_handler_engole_falha_do_registro(monkeypatch):
    """Observar não pode atrapalhar: se o registro quebrar, a voz continua."""
    h = IPCHandler.__new__(IPCHandler)
    monkeypatch.setattr(
        cronometro, "anotar_descarte",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    h._anotar_turno_descartado("oi", "motivo")  # não pode levantar


# ---------- ZARA-JANELA-DE-CONVERSA-002 ----------
#
# A janela era armada quando o comando CHEGAVA, ou seja antes de ela responder.
# Uma resposta longa comia o proprio tempo de conversa: ela falava trinta
# segundos e sobravam quarenta e cinco para ele reagir, embora a conversa so
# tenha recomecado quando ela calou a boca.


@pytest.mark.asyncio
async def test_a_janela_recomeca_quando_ela_termina_de_falar(monkeypatch):
    import time as _t

    h = IPCHandler.__new__(IPCHandler)
    h._gemini_wake_armed_until = 0.0

    # Simula o fim de uma fala: e esse o momento em que o relogio da vez dele
    # tem de comecar.
    agora = _t.monotonic()
    h._gemini_wake_armed_until = agora + IPCHandler._JANELA_DE_CONVERSA

    sobra = h._gemini_wake_armed_until - agora
    assert sobra == pytest.approx(IPCHandler._JANELA_DE_CONVERSA, abs=0.01), (
        "depois de ela falar, ele tem a janela INTEIRA, nao o que sobrou dela"
    )


def test_a_constante_e_uma_so():
    """Dois valores diferentes de janela foi o defeito original (8 s e 12 s)."""
    import inspect

    from core import ipc_handlers

    fonte = inspect.getsource(ipc_handlers)
    assert "monotonic() + 8.0" not in fonte
    assert "monotonic() + 12.0" not in fonte
    assert fonte.count("_JANELA_DE_CONVERSA") >= 4


# ---------- ZARA-JANELA-DE-CONVERSA-003 ----------
#
# Medido na madrugada de 15/08, no arquivo de descartes: com a TV ligada, treze
# falas de novela chegaram ao microfone. O portao as descartou porque a janela
# estava fechada.
#
# Abrir a janela para 75 s conserta a queixa dele (ser ignorado) e cria a queixa
# inversa: a TV virar dona do computador. Trocar uma pela outra nao e conserto.


@pytest.mark.parametrize("fala", [
    # frases REAIS capturadas do microfone naquela madrugada
    "Respira mais alto, Rosa, ajuda muito.",
    "aqui podem beber oleo de ricino.",
    "no canguru. Eles nao aceitaram nenhuma das minhas ideias.",
    "pai, me desculpa, pai",
    "Alem disso, uma mulher tem necessidade",
    "continuar nessa miseria?",
])
def test_a_novela_nao_deve_comandar_o_computador(fala):
    h = IPCHandler.__new__(IPCHandler)
    dirigido = h._parece_dirigido_a_ela(fala)
    # "pai, me desculpa" tem "me", e "miseria?" tem interrogacao: esses passam
    # de proposito, porque errar para o lado de ouvir e o lado certo de errar.
    if "me " in fala or "?" in fala:
        assert dirigido is True
    else:
        assert dirigido is False, fala


@pytest.mark.parametrize("fala", [
    "abre o youtube",
    "você entendeu?",
    "me lembra de comprar pão",
    "diminui o volume",
    "zara, que horas são",
    "pode repetir",
    "e daí, o que você acha disso",
])
def test_uma_frase_dirigida_a_ela_passa(fala):
    h = IPCHandler.__new__(IPCHandler)

    assert h._parece_dirigido_a_ela(fala) is True, fala


def test_qualquer_pergunta_passa():
    """Pergunta descartada irrita mais que novela respondida."""
    h = IPCHandler.__new__(IPCHandler)

    assert h._parece_dirigido_a_ela("e aquilo lá, resolveu?") is True


def test_a_replica_livre_e_curta_e_a_janela_e_longa():
    """Dois tempos diferentes de propósito: impulso primeiro, filtro depois."""
    assert IPCHandler._REPLICA_LIVRE < IPCHandler._JANELA_DE_CONVERSA
    assert IPCHandler._REPLICA_LIVRE >= 15.0, "curta demais volta a cortar a réplica"


# ---------- auditoria do Codex, achado 7 ----------
#
# Ele listou o que o filtro jogaria fora: "sim", "nao", "isso mesmo", "o azul",
# "mais baixo", "de novo", "nao, o outro". Sao todas replicas legitimas — e sao
# a resposta a uma pergunta que a propria ZARA acabou de fazer.


@pytest.mark.parametrize("replica", [
    "sim",
    "não",
    "isso mesmo",
    "a segunda opção",
    "o azul",
    "mais baixo",
    "de novo",
    "não, o outro",
    "às sete da manhã",
])
def test_replica_curta_do_alex_nao_e_descartada(replica):
    """Ela pergunta "qual dos dois?" e ele responde "o azul". Isso e conversa."""
    h = IPCHandler.__new__(IPCHandler)

    assert h._parece_dirigido_a_ela(replica) is True, replica


@pytest.mark.parametrize("novela", [
    "Alem disso, uma mulher tem necessidade de ser ouvida sempre",
    "no canguru. Eles nao aceitaram nenhuma das minhas ideias naquele dia",
    "aqui podem beber oleo de ricino que faz muito bem para todos",
])
def test_fala_longa_de_novela_continua_fora(novela):
    """O corte de tamanho nao pode abrir a porta para narracao de televisao."""
    h = IPCHandler.__new__(IPCHandler)

    assert h._parece_dirigido_a_ela(novela) is False, novela
