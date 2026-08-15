"""Core persistence and delivery regressions for reminders."""

import time
from datetime import datetime

from core.reminder_engine import ReminderEngine, parse_natural_due


def test_reminder_persists_across_reopen_and_fires_once(tmp_path):
    db_path = tmp_path / "reminders.db"
    created = ReminderEngine(db_path).create("café e pão", time.time() - 1)

    delivered: list[str] = []
    engine = ReminderEngine(db_path, on_fire=lambda reminder: delivered.append(reminder.id))

    assert engine.get(created.id).message == "café e pão"
    assert engine.fire_due_now() == 1
    assert delivered == [created.id]
    assert engine.get(created.id).state == "FIRED"
    assert engine.fire_due_now() == 0


def test_parse_bare_clock_time_for_today():
    now = datetime(2026, 8, 11, 10, 15, 30)

    due = parse_natural_due("às 16:40", now=now)

    assert due == datetime(2026, 8, 11, 16, 40).timestamp()
    assert parse_natural_due("às 09:00", now=now) is None
