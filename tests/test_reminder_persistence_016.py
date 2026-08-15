from datetime import datetime

from core.reminder_engine import ReminderEngine, parse_natural_due
from core.reminder_intent import detect_reminder_intent


def test_create_list_reload_order_and_missing_file(tmp_path):
    path = tmp_path / "isolated" / "reminders.db"
    first = ReminderEngine(path)
    later = first.create("mais tarde", 2000)
    sooner = first.create("mais cedo", 1000)
    assert [item.id for item in first.scheduled()] == [sooner.id, later.id]
    reloaded = ReminderEngine(path)
    assert [item.message for item in reloaded.scheduled()] == ["mais cedo", "mais tarde"]


def test_natural_list_cancel_and_complete_require_exact_id(tmp_path):
    engine = ReminderEngine(tmp_path / "reminders.db")
    cancel_me = engine.create("cancelar", 2000)
    complete_me = engine.create("concluir", 3000)
    listed = detect_reminder_intent("quais são meus lembretes?", engine)
    assert cancel_me.id in listed.reply and complete_me.id in listed.reply
    assert detect_reminder_intent(f"cancele o lembrete {cancel_me.id}", engine).kind == "cancel"
    assert detect_reminder_intent(f"conclua o lembrete {complete_me.id}", engine).kind == "complete"
    assert engine.get(cancel_me.id).state == "CANCELLED"
    assert engine.get(complete_me.id).state == "COMPLETED"
    assert detect_reminder_intent("cancele o lembrete", engine).kind == "not_reminder"


def test_invalid_or_past_clock_time_is_rejected():
    now = datetime(2026, 8, 9, 12, 0)
    assert parse_natural_due("hoje às 25:00", now) is None
    assert parse_natural_due("hoje às 09:00", now) is None
