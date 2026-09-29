"""Normalização de texto PT-BR para TTS.

Motores de TTS (Edge, Kokoro, OmniVoice) leem bem frases corridas, mas
engasgam em símbolos: "R$ 280" sai como "R cifrão duzentos e oitenta",
"26,7%" vira ruído, "14:30" vira "quatorze dois pontos trinta". Este módulo
converte esses trechos para forma falável ANTES da síntese, sem tocar no
resto do texto.

Ponto de uso: `normalize_for_tts()` na entrada do `TTSManager.speak()` —
o funil único da cascata local de TTS. Texto sem símbolo volta idêntico,
então frases normais têm comportamento 100% inalterado.

Se `num2words` não estiver instalado (ex.: backend empacotado sem a
dependência), os números caem para dígitos crus em vez de quebrar — a
conversão do símbolo (R$, %, hora) continua valendo.
"""

from __future__ import annotations

import re

try:  # dependência opcional: sem ela, dígitos crus em vez de exceção
    from num2words import num2words as _num2words
except Exception:  # noqa: BLE001 - qualquer falha de import cai no fallback
    _num2words = None


def _words(value: int | float) -> str:
    """Número por extenso em PT-BR; cai para dígitos se num2words faltar."""
    if _num2words is not None:
        try:
            # O pt_BR do num2words escreve "mil, duzentos..." com vírgula —
            # para o TTS ela vira uma pausa esquisita no meio do número.
            return _num2words(value, lang="pt_BR").replace(",", "")
        except Exception:  # noqa: BLE001 - valor estranho: não quebrar a fala
            pass
    return str(value)


_CURRENCY_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?")


def _currency_to_words(match: re.Match[str]) -> str:
    reais = int(match.group(1).replace(".", ""))
    cents_raw = match.group(2) or ""
    centavos = int(cents_raw.ljust(2, "0")[:2]) if cents_raw else 0
    parts: list[str] = []
    if reais:
        parts.append(f"{_words(reais)} {'real' if reais == 1 else 'reais'}")
    if centavos:
        parts.append(f"{_words(centavos)} {'centavo' if centavos == 1 else 'centavos'}")
    if not parts:
        return "zero reais"
    return " e ".join(parts)


_PERCENT_RE = re.compile(r"(\d+(?:,\d+)?)%")


def _percent_to_words(match: re.Match[str]) -> str:
    value = float(match.group(1).replace(",", "."))
    return f"{_words(value)} por cento"


_CLOCK_RE = re.compile(r"(?<![:\d])(\d{1,2}):([0-5]\d)(?![:\d])")


def _clock_to_words(match: re.Match[str]) -> str:
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23:
        return match.group(0)  # não é hora (ex.: placar), deixa quieto
    if minutes == 0:
        return f"{_words(hours)} horas"
    return f"{_words(hours)} horas e {_words(minutes)} minutos"


_HM_RE = re.compile(r"\b(\d{1,2})h(\d{2})\b")  # 9h30
_H_RE = re.compile(r"\b(\d{1,2})h\b")  # 10h


def _hm_to_words(match: re.Match[str]) -> str:
    hours = int(match.group(1))
    if hours > 23:
        return match.group(0)
    return f"{_words(hours)} horas e {_words(int(match.group(2)))} minutos"


def _h_to_words(match: re.Match[str]) -> str:
    hours = int(match.group(1))
    if hours > 23:
        return match.group(0)
    return f"{_words(hours)} horas"


# Siglas que o TTS costuma ler como palavra estranha; soletrar é mais claro.
_ACRONYMS = (
    "API",
    "URL",
    "SMS",
    "GPS",
    "TV",
    "PC",
    "USB",
    "PDF",
    "CPF",
    "CNPJ",
    "PIX",
    "MCP",
    "LLM",
)
_ACRONYM_RE = re.compile(r"\b(" + "|".join(_ACRONYMS) + r")\b")


def _acronym_to_letters(match: re.Match[str]) -> str:
    return " ".join(match.group(1))


def normalize_for_tts(text: str) -> str:
    """Converte símbolos problemáticos para forma falável em PT-BR.

    "R$ 5,50" -> "cinco reais e cinquenta centavos"; "26,7%" ->
    "vinte e seis vírgula sete por cento"; "14:30" -> "catorze horas e
    trinta minutos"; "API" -> "A P I". Texto sem símbolo volta inalterado.
    """
    if not text:
        return text
    text = _CURRENCY_RE.sub(_currency_to_words, text)
    text = _PERCENT_RE.sub(_percent_to_words, text)
    text = _CLOCK_RE.sub(_clock_to_words, text)
    text = _HM_RE.sub(_hm_to_words, text)
    text = _H_RE.sub(_h_to_words, text)
    text = _ACRONYM_RE.sub(_acronym_to_letters, text)
    return text
