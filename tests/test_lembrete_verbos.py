"""Lembretes: verbos que faltavam e o "h" órfão dentro da mensagem.

Dois defeitos separados, ambos silenciosos:

1. Só "lembre de ..." era reconhecido. "crie um lembrete...", "agende um
   lembrete...", "marca um lembrete..." caíam no LLM — que responde como se
   tivesse agendado, sem nada ter sido gravado.
2. O padrão de horário casava "às 15" e deixava o "h" para trás DENTRO da
   mensagem: o lembrete gravado virava "tomar água h".
"""

import pytest

from core.reminder_intent import detect_reminder_intent


@pytest.mark.parametrize(
    "frase",
    [
        "crie um lembrete de reunião às 14h",
        "cria um lembrete de reunião às 14h",
        "agende um lembrete de reunião às 14h",
        "marca um lembrete: reunião às 14h",
        "anote um lembrete de reunião às 14h",
        "lembre de reunião às 14h",
        "me lembre de reunião às 14h",
    ],
)
def test_todos_os_verbos_de_lembrete_chegam_na_mesma_intent(frase):
    result = detect_reminder_intent(frase)
    assert result.kind != "not_reminder", frase
    assert result.message == "reunião"


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("lembre de tomar água às 15h", "tomar água"),
        ("lembre de tomar água às 15 horas", "tomar água"),
        ("lembre de tomar água às 15hs", "tomar água"),
        ("lembre de tomar água às 15:30", "tomar água"),
        ("me lembre de ligar pro João amanhã às 9h", "ligar pro João"),
        ("me lembre de tomar água daqui a 10 minutos", "tomar água"),
    ],
)
def test_o_horario_sai_inteiro_da_mensagem(frase, esperado):
    """Nada de "tomar água h": o sufixo de hora faz parte do horário."""
    assert detect_reminder_intent(frase).message == esperado


def test_horario_sem_assunto_pergunta_em_vez_de_cair_no_modelo():
    result = detect_reminder_intent("crie um lembrete para as 15h")
    assert result.kind == "needs_clarification"
    assert result.reply == "Lembrete de quê?"
    assert result.message == ""


def test_assunto_sem_horario_continua_perguntando_a_hora():
    result = detect_reminder_intent("me lembre de tomar água")
    assert result.kind == "needs_clarification"
    assert result.reply == "Que horas?"
    assert result.message == "tomar água"


@pytest.mark.parametrize(
    "frase",
    [
        "me fale sobre lembretes",
        "o que é um lembrete",
        "crie um arquivo novo",
    ],
)
def test_conversa_sobre_lembrete_nao_agenda_nada(frase):
    assert detect_reminder_intent(frase).kind == "not_reminder"
