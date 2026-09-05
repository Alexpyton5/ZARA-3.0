"""236-239 — reminders: isolamento de dados reais, ciclo de vida, restart e falha honesta.

Todo o teste roda em tmp_path. O banco real do Alex nunca e aberto.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from core.reminder_engine import ReminderEngine

REAL_DB_FRAGMENT = "AppData\\Local\\ZARA3\\data\\reminders"


@pytest.fixture()
def engine(tmp_path):
    return ReminderEngine(db_path=tmp_path / "reminders" / "zara_reminders.db")


# ------------------------------------------------------ 236 real-data guard


def test_zara3_home_override_moves_reminder_db_away_from_real_data(monkeypatch, tmp_path):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path / "isolated"))
    eng = ReminderEngine()
    resolved = str(eng.db_path)
    assert str(tmp_path) in resolved
    assert REAL_DB_FRAGMENT not in resolved


def test_explicit_db_path_never_touches_real_location(engine, tmp_path):
    assert str(tmp_path) in str(engine.db_path)
    assert REAL_DB_FRAGMENT not in str(engine.db_path)


# --------------------------------------------------------- 237 lifecycle


def test_create_readback_and_cancel_roundtrip(engine):
    due = time.time() + 3600
    rem = engine.create("lembrete isolado", due)
    assert rem.id

    listed = {r.id: r for r in engine.list()}
    assert rem.id in listed
    assert listed[rem.id].message == "lembrete isolado"
    assert listed[rem.id].state in {"SCHEDULED", "PENDING"}

    assert engine.cancel(rem.id) is True
    after = {r.id: r for r in engine.list()}
    assert after[rem.id].state == "CANCELLED"


def test_cancel_twice_is_not_a_second_success(engine):
    rem = engine.create("cancelar duas vezes", time.time() + 600)
    assert engine.cancel(rem.id) is True
    assert engine.cancel(rem.id) is False


def test_cancel_unknown_id_fails_honestly(engine):
    assert engine.cancel("REM-DOES-NOT-EXIST") is False


# ---------------------------------------------------- 238 restart recovery


def test_reminder_survives_restart_without_duplicating(engine):
    rem = engine.create("sobrevive ao restart", time.time() + 900)
    db_path = engine.db_path

    reopened = ReminderEngine(db_path=db_path)
    rows = [r for r in reopened.list() if r.id == rem.id]
    assert len(rows) == 1, "reminder duplicado apos restart"
    assert rows[0].message == "sobrevive ao restart"


def test_restart_does_not_resurrect_cancelled_reminder(engine):
    rem = engine.create("cancelado antes do restart", time.time() + 900)
    engine.cancel(rem.id)
    reopened = ReminderEngine(db_path=engine.db_path)
    row = next(r for r in reopened.list() if r.id == rem.id)
    assert row.state == "CANCELLED"


# ----------------------------------------------- 239 idempotency + failure


def test_ids_are_unique_across_rapid_creates(engine):
    ids = {engine.create(f"m{i}", time.time() + 60 + i).id for i in range(20)}
    assert len(ids) == 20


def test_empty_message_is_accepted_today_documented_gap(engine):
    """FACTUAL: hoje o engine aceita mensagem vazia (gap registrado, nao promovido)."""
    rem = engine.create("", time.time() + 60)
    assert rem.id
    assert rem.message == ""


def test_db_failure_is_not_silent_success(engine, monkeypatch):
    from core.reminder_engine import ReminderPersistenceError

    def _locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", _locked)
    with pytest.raises(ReminderPersistenceError):
        engine.create("durante lock", time.time() + 60)


def test_list_on_unwritable_path_does_not_claim_data(tmp_path):
    """Um caminho invalido nao pode devolver lista vazia como se fosse sucesso."""
    bad = tmp_path / "arquivo.txt"
    bad.write_text("nao sou um diretorio", encoding="utf-8")
    with pytest.raises(Exception):
        ReminderEngine(db_path=bad / "sub" / "x.db").create("x", time.time() + 60)
