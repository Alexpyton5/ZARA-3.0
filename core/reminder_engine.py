"""
ZARA Reminder Core — motor persistente de lembretes (ZARA-REMINDER-CORE-001).

Spec do Mentor:
- DB: %LOCALAPPDATA%\\ZARA3\\data\\reminders\\zara_reminders.db (SQLite)
- Tabela reminders: id, message, due_at_utc, timezone, state, created_at,
  updated_at, fired_at, cancelled_at, source
- Estados: SCHEDULED -> FIRING -> FIRED | CANCELLED | MISSED
- Instante absoluto em UTC + timezone original (nunca apenas "09:00")
- Scheduler leve (1-5s), sobrevive a restart/crash, nunca dispara 2x
- Overdue: atraso pequeno (ate 24h) dispara uma vez como overdue; muito
  antigo -> MISSED (nao perder silenciosamente)
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from core.paths import user_data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    due_at_utc REAL NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'local',
    state TEXT NOT NULL DEFAULT 'SCHEDULED',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    fired_at REAL,
    cancelled_at REAL,
    source TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at_utc);
CREATE INDEX IF NOT EXISTS idx_reminders_state ON reminders(state);
"""

OVERDUE_WINDOW_SECONDS = 24 * 3600  # dispara como overdue se atraso <= 24h


@dataclass
class Reminder:
    id: str
    message: str
    due_at_utc: float
    timezone: str = "local"
    state: str = "SCHEDULED"
    created_at: float = field(default_factory=time.time)
    fired_at: float | None = None
    source: str = "manual"

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "due_at_utc": self.due_at_utc,
            "timezone": self.timezone,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at if hasattr(self, "updated_at") else self.created_at,
            "fired_at": self.fired_at,
            "source": self.source,
        }


class ReminderEngine:
    """Persistent reminder store + scheduler (thread-safe, restart-safe)."""

    def __init__(self, db_path: Path | None = None, on_fire: Callable[[Reminder], None] | None = None):
        self.db_path = db_path or (user_data_dir() / "data" / "reminders" / "zara_reminders.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.on_fire = on_fire
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # reconcilia FIRING de crash anterior -> volta a SCHEDULED
            conn.execute(
                "UPDATE reminders SET state='SCHEDULED', updated_at=? WHERE state='FIRING'",
                (time.time(),),
            )
            conn.commit()

    # ---- CRUD ----

    def create(self, message: str, due_at_utc: float, timezone: str = "local",
               source: str = "manual") -> Reminder:
        """Create a reminder. due_at_utc is an absolute epoch timestamp."""
        rid = f"REM-{int(time.time() * 1000)}-{abs(hash((message, due_at_utc))) % 0xFFFF:04X}"
        now = time.time()
        r = Reminder(id=rid, message=message, due_at_utc=due_at_utc,
                     timezone=timezone, created_at=now, source=source)
        r.updated_at = now
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO reminders (id, message, due_at_utc, timezone, state, "
                    "created_at, updated_at, source) VALUES (?,?,?,?,?,?,?,?)",
                    (r.id, r.message, r.due_at_utc, r.timezone, r.state,
                     r.created_at, r.updated_at, r.source),
                )
                conn.commit()
        return r

    def get(self, rid: str) -> Reminder | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
        if not row:
            return None
        return self._row_to_reminder(row)

    def cancel(self, rid: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE reminders SET state='CANCELLED', cancelled_at=?, updated_at=? "
                    "WHERE id=? AND state='SCHEDULED'",
                    (time.time(), time.time(), rid),
                )
                conn.commit()
                return cur.rowcount > 0

    def list(self, state: str | None = None) -> list[Reminder]:
        with self._lock:
            with self._connect() as conn:
                if state:
                    rows = conn.execute(
                        "SELECT * FROM reminders WHERE state=? ORDER BY due_at_utc", (state,)
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM reminders ORDER BY due_at_utc").fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def due(self, now: float | None = None) -> list[Reminder]:
        """Reminders SCHEDULED with due_at_utc <= now (not yet claimed)."""
        now = now or time.time()
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM reminders WHERE state='SCHEDULED' AND due_at_utc <= ?",
                    (now,),
                ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def scheduled(self) -> list[Reminder]:
        return self.list("SCHEDULED")

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> Reminder:
        r = Reminder(
            id=row["id"], message=row["message"], due_at_utc=row["due_at_utc"],
            timezone=row["timezone"], state=row["state"],
            created_at=row["created_at"], fired_at=row["fired_at"],
            source=row["source"],
        )
        r.updated_at = row["updated_at"]
        return r

    # ---- scheduler ----

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ReminderScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                now = time.time()
                for r in self._claim_due(now):
                    self._fire(r, overdue=now - r.due_at_utc > 5.0)
                self._stop.wait(2.0)  # 2s tick (spec: 1-5s)
            except Exception:
                self._stop.wait(2.0)

    def _claim_due(self, now: float) -> list[Reminder]:
        """Atomically claim due SCHEDULED reminders; mark ancient ones MISSED."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM reminders WHERE state='SCHEDULED' AND due_at_utc <= ?", (now,)
                ).fetchall()
                claimed = []
                for r in rows:
                    late = now - r["due_at_utc"]
                    if late > OVERDUE_WINDOW_SECONDS:
                        # muito antigo: marca MISSED (nao perde silenciosamente)
                        conn.execute(
                            "UPDATE reminders SET state='MISSED', updated_at=? WHERE id=? AND state='SCHEDULED'",
                            (now, r["id"]),
                        )
                        continue
                    # registra FIRING antes de entregar (crash-safe)
                    cur = conn.execute(
                        "UPDATE reminders SET state='FIRING', updated_at=? "
                        "WHERE id=? AND state='SCHEDULED'",
                        (now, r["id"]),
                    )
                    if cur.rowcount > 0:
                        rem = self._row_to_reminder(r)
                        rem.state = "FIRING"
                        claimed.append(rem)
                conn.commit()
        return claimed

    def _fire(self, r: Reminder, overdue: bool = False) -> None:
        fired_at = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE reminders SET state='FIRED', fired_at=?, updated_at=? WHERE id=?",
                    (fired_at, fired_at, r.id),
                )
                conn.commit()
        r.state = "FIRED"
        r.fired_at = fired_at
        if self.on_fire:
            try:
                self.on_fire(r)
            except Exception:
                pass

    def fire_due_now(self) -> int:
        """Sync helper (tests): claim + fire all currently due reminders."""
        due = self._claim_due(time.time())
        for r in due:
            self._fire(r)
        return len(due)


# ---- NLP barato (opcional, spec item 14) ----
def parse_natural_due(text: str, now: datetime | None = None) -> float | None:
    """Parse frases simples -> epoch UTC.

    Suporta: 'amanha as 9', 'hoje as 18:30', 'daqui a 30 minutos',
    'daqui a 2 horas'. Retorna None se nao reconhecer.
    """
    if not text:
        return None
    now = now or datetime.now()
    t = text.lower().strip()

    # daqui a N minutos/horas
    m = re.search(r"daqui a (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("min"):
            return (now + timedelta(minutes=n)).timestamp()
        return (now + timedelta(hours=n)).timestamp()

    # amanhã as H(:MM)? / hoje as H(:MM)? (aceita amanha sem acento)
    m = re.search(r"(amanh[ãa]|hoje)(?: às| as| a)?\s*(\d{1,2})(?::(\d{2}))?", t)
    if m:
        day = now + timedelta(days=1 if m.group(1).startswith("amanh") else 0)
        hh = int(m.group(2))
        mm = int(m.group(3) or 0)
        due = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return due.timestamp()

    # apenas 'em 30 minutos'
    m = re.search(r"em (\d+)\s*(minutos?|min\b|hora|horas?|h\b)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("min"):
            return (now + timedelta(minutes=n)).timestamp()
        return (now + timedelta(hours=n)).timestamp()

    return None


def create_reminder_engine(db_path: Path | None = None,
                           on_fire: Callable[[Reminder], None] | None = None) -> ReminderEngine:
    return ReminderEngine(db_path=db_path, on_fire=on_fire)
