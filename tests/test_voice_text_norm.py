"""Normalização PT-BR para TTS: símbolos viram forma falável.

Ponto fraco real que isto cobre: a ZARA falava "R$ 280" como "R cifrão
duzentos e oitenta" e "14:30" como "quatorze dois pontos trinta" — os
motores (Edge/Kokoro) não expandem esses símbolos sozinhos.
"""
from __future__ import annotations

from core.voice_text_norm import normalize_for_tts


def test_plain_sentence_comes_back_identical():
    text = "Bom dia Alex, o sistema está funcionando normalmente."
    assert normalize_for_tts(text) == text


def test_empty_and_none_safe():
    assert normalize_for_tts("") == ""
    assert normalize_for_tts(None) is None


def test_currency_reais_only():
    assert normalize_for_tts("custa R$ 280") == "custa duzentos e oitenta reais"


def test_currency_singular_real():
    assert normalize_for_tts("R$ 1,00") == "um real"


def test_currency_with_centavos():
    assert normalize_for_tts("R$ 5,50") == "cinco reais e cinquenta centavos"


def test_currency_thousands_brazilian_format():
    out = normalize_for_tts("total R$ 1.234,56")
    assert out == "total mil duzentos e trinta e quatro reais e cinquenta e seis centavos"


def test_currency_only_centavos():
    assert normalize_for_tts("R$ 0,50") == "cinquenta centavos"


def test_percent_decimal_comma():
    assert normalize_for_tts("cresceu 26,7%") == "cresceu vinte e seis vírgula sete por cento"


def test_percent_integer():
    assert normalize_for_tts("100% concluído") == "cem por cento concluído"


def test_clock_time():
    assert normalize_for_tts("às 14:30") == "às catorze horas e trinta minutos"


def test_clock_time_round_hour():
    assert normalize_for_tts("às 9:00") == "às nove horas"


def test_clock_does_not_match_duration():
    # "12:34:56" não é hora do dia — não mexer
    assert normalize_for_tts("duração 12:34:56") == "duração 12:34:56"


def test_hour_abbreviation():
    assert normalize_for_tts("te vejo às 10h") == "te vejo às dez horas"


def test_hour_abbreviation_with_minutes():
    assert normalize_for_tts("às 9h30") == "às nove horas e trinta minutos"


def test_acronyms_are_spelled_out():
    assert normalize_for_tts("a API caiu") == "a A P I caiu"
    assert normalize_for_tts("manda por SMS") == "manda por S M S"


def test_combined_sentence():
    out = normalize_for_tts("O plano de R$ 5,50 subiu 26,7% e a reunião é às 14:30.")
    assert out == (
        "O plano de cinco reais e cinquenta centavos subiu "
        "vinte e seis vírgula sete por cento e a reunião é às "
        "catorze horas e trinta minutos."
    )
