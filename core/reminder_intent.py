"""
ZARA Reminder Voice Binding (ZARA-REMINDER-VOICE-BINDING-001).

Intent determinístico (NÃO LLM) para transformar frases faladas/digitadas
em reminders usando o Reminder Core + parser temporal já existentes.

Frases suportadas:
  me lembre de <X> daqui a N minutos
  me lembre de <X> daqui a N horas
  me lembre de <X> amanhã às H(:MM)
  me lembre de <X> hoje às H(:MM)
  lembra de ... | me lembra de ... (variações)

Retorno:
  (IntentResult) com kind=reminder, message, due_at_utc OU
  kind=not_reminder | needs_clarification
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.reminder_engine import ReminderEngine, parse_natural_due

_INTRO = re.compile(
    r"^\s*(?:zara[\s,]*)?(?:me\s+)?(?:lembre|lembra|lembrar)\s+(?:de\s+|me\s+)?(?:de\s+)?",
    re.IGNORECASE,
)

_TIME_PATTERNS = [
    # daqui a N minutos/horas
    re.compile(r"daqui a (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", re.IGNORECASE),
    # amanhã às H(:MM)? / hoje às H(:MM)? (aceita amanha/amanhã sem acento)
    re.compile(r"(amanh[ãa]|hoje)(?: às| as| a)?\s*(\d{1,2})(?::(\d{2}))?", re.IGNORECASE),
    # em N minutos/horas
    re.compile(r"em (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", re.IGNORECASE),
]


@dataclass
class IntentResult:
    kind: str  # reminder | not_reminder | needs_clarification
    message: str = ""
    due_at_utc: float | None = None
    human_due: str = ""
    reply: str = ""
    raw: str = ""


def detect_reminder_intent(text: str, engine: ReminderEngine | None = None) -> IntentResult:
    """Deterministic reminder intent detection (never an LLM decision)."""
    raw = (text or "").strip()
    if not raw:
        return IntentResult(kind="not_reminder", raw=raw)

    # precisa comecar com "lembre de ..." (apos opcional "zara")
    m = _INTRO.match(raw)
    if not m:
        return IntentResult(kind="not_reminder", raw=raw)

    body = raw[m.end():].strip()
    if not body:
        return IntentResult(kind="not_reminder", raw=raw)

    # descobre o componente temporal
    time_match = None
    for pat in _TIME_PATTERNS:
        tm = pat.search(body)
        if tm:
            time_match = tm
            break

    if not time_match:
        # "me lembre de <X>" sem horario -> precisa esclarecer
        return IntentResult(
            kind="needs_clarification",
            message=body,
            reply="Que horas?",
            raw=raw,
        )

    # separa a mensagem do componente temporal
    message = (body[:time_match.start()] + " " + body[time_match.end():]).strip()
    message = re.sub(r"\s+", " ", message).strip(" ,;:-")
    if not message:
        return IntentResult(kind="not_reminder", raw=raw)

    due = parse_natural_due(time_match.group(0))
    if due is None:
        return IntentResult(kind="not_reminder", raw=raw)

    human_due = _humanize_due(time_match.group(0), due)

    if engine is not None:
        try:
            engine.create(message, due, timezone="local", source="voice")
            return IntentResult(
                kind="reminder",
                message=message,
                due_at_utc=due,
                human_due=human_due,
                reply=f"Certo. Vou te lembrar de {message} {human_due}.",
                raw=raw,
            )
        except Exception:
            return IntentResult(
                kind="not_reminder",
                reply="Não consegui criar esse lembrete.",
                raw=raw,
            )

    return IntentResult(
        kind="reminder",
        message=message,
        due_at_utc=due,
        human_due=human_due,
        reply=f"Certo. Vou te lembrar de {message} {human_due}.",
        raw=raw,
    )


def _humanize_due(time_text: str, due_epoch: float) -> str:
    """Return a readable due description for the confirmation reply."""
    t = time_text.lower().strip()
    m = re.match(r"daqui a (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", t)
    if m:
        n = m.group(1)
        unit = "minuto(s)" if m.group(2).startswith("min") else "hora(s)"
        return f"daqui a {n} {unit}"
    m = re.match(r"(amanha|hoje)(?: às| as| a)?\s*(\d{1,2})(?::(\d{2}))?", t)
    if m:
        day = "amanhã" if m.group(1) == "amanha" else "hoje"
        hh = m.group(2)
        mm = m.group(3) or "00"
        return f"{day} às {hh}:{mm}"
    m = re.match(r"em (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", t)
    if m:
        return f"em {m.group(1)} minuto(s) ou hora(s)"
    return time_text
