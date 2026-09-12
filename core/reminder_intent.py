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
    r"(?:^\s*(?:zara[\s,]*)?(?:me\s+)?(?:lembre|lembra|lembrar)\s+"
    r"(?:de\s+|me\s+)?(?:de\s+)?|"
    r"\b(?:crie|agende|quero\s+(?:criar|agendar))\s+(?:um\s+)?lembrete(?:\s+para)?\s+)",
    re.IGNORECASE,
)

_TIME_PATTERNS = [
    # data absoluta com horário antes: "às 10 horas no dia 18-09-2026"
    re.compile(
        r"(?:para\s+)?(?:às|as)?\s*\d{1,2}(?::\d{2})?\s*(?:h|horas?)?"
        r"(?:\s+da\s+(?:manhã|manha|tarde|noite))?\s+(?:no\s+dia\s+|em\s+)?"
        r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", re.IGNORECASE,
    ),
    # data absoluta com horário depois: "18-09-2026 às 10"
    re.compile(
        r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s+(?:às|as|a)?\s*\d{1,2}"
        r"(?::\d{2})?\s*(?:h|horas?)?(?:\s+da\s+(?:manhã|manha|tarde|noite))?",
        re.IGNORECASE,
    ),
    # daqui a N minutos/horas
    re.compile(r"daqui a (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", re.IGNORECASE),
    # amanhã às H(:MM)? / hoje às H(:MM)? (aceita amanha/amanhã sem acento)
    re.compile(r"(amanh[ãa]|hoje)(?: às| as| a)?\s*(\d{1,2})(?::(\d{2}))?", re.IGNORECASE),
    # horário explícito no mesmo dia: "às 16" / "as 16:30"
    re.compile(r"(?:às|as)\s*(\d{1,2})(?::(\d{2}))?", re.IGNORECASE),
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

    lowered = raw.casefold().strip(" .?!")
    if lowered in {"quais são meus lembretes", "quais sao meus lembretes", "liste meus lembretes"}:
        if engine is None:
            return IntentResult(kind="list", reply="Não há armazenamento de lembretes disponível.", raw=raw)
        pending = engine.scheduled()
        if not pending:
            return IntentResult(kind="list", reply="Você não tem lembretes pendentes.", raw=raw)
        summary = "; ".join(f"{item.id}: {item.message}" for item in pending)
        return IntentResult(kind="list", reply=f"Lembretes pendentes: {summary}", raw=raw)

    management = re.fullmatch(
        r"(?:cancele|cancelar|conclua|complete)\s+(?:o\s+)?lembrete\s+(REM-[A-Z0-9-]+)",
        raw,
        re.IGNORECASE,
    )
    if management:
        rid = management.group(1).upper()
        completing = management.group(0).casefold().startswith(("conclua", "complete"))
        changed = bool(engine and (engine.complete(rid) if completing else engine.cancel(rid)))
        verb = "concluído" if completing else "cancelado"
        return IntentResult(
            kind="complete" if completing else "cancel",
            reminder_id=rid,
            reply=f"Lembrete {rid} {verb}." if changed else f"Não encontrei o lembrete pendente {rid}.",
            raw=raw,
        )

    # Um pedido pode trazer contexto antes do imperativo, como no turno físico
    # "... crie um lembrete ...". Só imperativos explícitos entram aqui.
    m = _INTRO.search(raw)
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
    message = re.sub(
        r"^(?:para\s+|onde\s+(?:voce|você)\s+(?:ira|irá)\s+)", "", message,
        flags=re.IGNORECASE,
    ).strip(" ,;:-.")
    prefix = raw[:m.start()]
    spouse = re.search(r"nome\s+da\s+minha\s+esposa\s+[ée]\s+([\wÀ-ÿ'-]+)", prefix, re.IGNORECASE)
    if spouse:
        message = re.sub(r"\bela\b", spouse.group(1), message, flags=re.IGNORECASE)
    if not message:
        return IntentResult(kind="not_reminder", raw=raw)

    due = parse_natural_due(time_match.group(0))
    if due is None:
        return IntentResult(kind="needs_clarification", message=message, reply="Esse horário é inválido. Qual horário devo usar?", raw=raw)

    human_due = _humanize_due(time_match.group(0), due)

    if engine is not None:
        try:
            reminder = engine.create(message, due, timezone="local", source="zara_desktop")
        except Exception as exc:
            # BUG-001: create/commit/readback nao provado -> falha explicita
            return IntentResult(
                kind="reminder_failed",
                message=message,
                due_at_utc=due,
                human_due=human_due,
                reply=(
                    "Não consegui criar esse lembrete: falha ao salvar/confirmar "
                    f"no armazenamento ({exc}). Ele NÃO está agendado."
                ),
                raw=raw,
            )
        return IntentResult(
            kind="reminder",
            reminder_id=reminder.id,
            message=message,
            due_at_utc=due,
            human_due=human_due,
            reply=f"Certo. Vou te lembrar de {message} {human_due}. (id {reminder.id})",
            raw=raw,
        )

    # engine=None: nao ha storage -> NUNCA prometer "vou te lembrar" (BUG-001).
    # retorna falha explicita, sem mensagem falsa de sucesso.
    return IntentResult(
        kind="reminder_failed",
        message=message,
        due_at_utc=due,
        human_due=human_due,
        reply=(
            "Não consigo criar esse lembrete agora: o armazenamento de "
            "lembretes não está disponível. Ele NÃO está agendado."
        ),
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
    m = re.match(r"(?:às|as)\s*(\d{1,2})(?::(\d{2}))?", t)
    if m:
        return f"às {m.group(1)}:{m.group(2) or '00'}"
    m = re.match(r"em (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", t)
    if m:
        return f"em {m.group(1)} minuto(s) ou hora(s)"
    return time_text
