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
import unicodedata
from dataclasses import dataclass

from core.reminder_engine import ReminderEngine, parse_natural_due

_INTRO = re.compile(
    r"^\s*(?:zara[\s,]*)?(?:me\s+)?(?:lembre|lembra|lembrar)\s+(?:de\s+|me\s+)?(?:de\s+)?",
    re.IGNORECASE,
)

_LIST = re.compile(
    r"^\s*(?:zara[, ]*)?(?:quais\s+sao\s+(?:(?:os|meus)\s+)?lembretes|"
    r"liste?\s+(?:(?:os|meus)\s+)?lembretes|"
    r"mostre\s+(?:(?:os|meus)\s+)?lembretes)\b",
    re.IGNORECASE,
)
_CANCEL = re.compile(r"^\s*(?:zara[, ]*)?cancele?\s+(?:o\s+)?lembrete\b", re.IGNORECASE)
_COMPLETE = re.compile(r"^\s*(?:zara[, ]*)?conclua?\s+(?:o\s+)?lembrete\b", re.IGNORECASE)
_REMINDER_ID = re.compile(r"\bREM-[A-Z0-9]+-[A-F0-9]+\b", re.IGNORECASE)

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
    reminder_id: str = ""
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

    plain = "".join(
        char for char in unicodedata.normalize("NFD", raw)
        if unicodedata.category(char) != "Mn"
    )

    if _LIST.match(plain):
        if engine is None:
            return _failed(raw, "Não consigo consultar os lembretes agora.")
        try:
            reminders = engine.list()
            if not reminders:
                return IntentResult(kind="list", reply="Você não tem lembretes registrados.", raw=raw)
            lines = [f"{item.id}: {item.message} ({item.state})" for item in reminders]
            return IntentResult(kind="list", reply="Seus lembretes:\n" + "\n".join(lines), raw=raw)
        except Exception:
            return _failed(raw, "Não consegui consultar os lembretes agora.")

    action = "cancel" if _CANCEL.match(plain) else "complete" if _COMPLETE.match(plain) else None
    if action:
        match = _REMINDER_ID.search(raw)
        if not match:
            return IntentResult(kind="not_reminder", raw=raw)
        reminder_id = match.group(0)
        if engine is None:
            return _failed(raw, "Não consegui atualizar esse lembrete.")
        expected_state = "CANCELLED" if action == "cancel" else "COMPLETED"
        try:
            changed = engine.cancel(reminder_id) if action == "cancel" else engine.complete(reminder_id)
            stored = engine.get(reminder_id)
            if not changed or stored is None or stored.state != expected_state:
                return _failed(raw, "Não consegui confirmar a atualização desse lembrete.")
            verb = "cancelado" if action == "cancel" else "concluído"
            return IntentResult(
                kind=action, reminder_id=reminder_id, message=stored.message,
                reply=f"Lembrete {verb}: {reminder_id}.", raw=raw,
            )
        except Exception:
            return _failed(raw, "Não consegui confirmar a atualização desse lembrete.")

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
            reminder = engine.create(message, due, timezone="local", source="voice")
            return IntentResult(
                kind="reminder",
                reminder_id=reminder.id,
                message=message,
                due_at_utc=due,
                human_due=human_due,
                reply=f"Certo. Vou te lembrar de {message} {human_due}. ID: {reminder.id}.",
                raw=raw,
            )
        except Exception:
            return _failed(raw, "Não consegui criar esse lembrete. Ele não está agendado.")

    return _failed(raw, "Não consigo salvar esse lembrete agora. Ele não está agendado.")


def _failed(raw: str, reply: str) -> IntentResult:
    return IntentResult(kind="reminder_failed", reply=reply, raw=raw)


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
