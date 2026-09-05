"""BUG-001: reminder false-success / integrity.

Sucesso so pode ser emitido apos create -> commit -> readback do MESMO id.
"""
from __future__ import annotations

import time

import pytest

from core.reminder_engine import ReminderEngine, ReminderPersistenceError
from core.reminder_intent import detect_reminder_intent


def _engine(tmp_path) -> ReminderEngine:
    return ReminderEngine(tmp_path / "reminders.db")


# 1. Caminho nominal: create -> commit -> readback do mesmo id
def test_nominal_create_commit_readback_same_id(tmp_path):
    engine = _engine(tmp_path)
    due = time.time() + 600
    created = engine.create("tomar remedio", due)

    reloaded = ReminderEngine(tmp_path / "reminders.db")
    stored = reloaded.get(created.id)
    assert stored is not None
    assert stored.id == created.id
    assert stored.message == "tomar remedio"
    assert abs(stored.due_at_utc - due) < 1e-6
    assert stored.state == "SCHEDULED"


# 2. Falha de commit -> sem false-success
def test_commit_failure_raises_and_never_reports_success(tmp_path, monkeypatch):
    engine = _engine(tmp_path)

    class _BoomConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **k):
            raise RuntimeError("disk I/O error")

        def commit(self):
            raise RuntimeError("disk I/O error")

    monkeypatch.setattr(engine, "_connect", lambda: _BoomConn())
    with pytest.raises(ReminderPersistenceError) as exc:
        engine.create("falha commit", time.time() + 60)
    assert "commit falhou" in str(exc.value)

    res = detect_reminder_intent("me lembre de falha commit daqui a 10 minutos", engine)
    assert res.kind == "reminder_failed"
    assert res.reminder_id == ""
    assert "não consegui" in res.reply.casefold()
    assert "vou te lembrar" not in res.reply.casefold()


# 3a. Readback ausente -> sem false-success
def test_readback_missing_raises(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(engine, "get", lambda rid: None)
    with pytest.raises(ReminderPersistenceError) as exc:
        engine.create("some", time.time() + 60)
    assert "readback nao encontrou" in str(exc.value)


# 3b. Readback divergente -> sem false-success
def test_readback_divergent_raises_and_intent_fails(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    real_get = engine.get

    def _divergent(rid):
        stored = real_get(rid)
        if stored is not None:
            stored.message = "OUTRA COISA"
        return stored

    monkeypatch.setattr(engine, "get", _divergent)
    with pytest.raises(ReminderPersistenceError) as exc:
        engine.create("mensagem certa", time.time() + 60)
    assert "readback divergente" in str(exc.value)

    res = detect_reminder_intent("me lembre de mensagem certa daqui a 5 minutos", engine)
    assert res.kind == "reminder_failed"
    assert "vou te lembrar" not in res.reply.casefold()


# 4. Sucesso somente apos readback valido
def test_success_only_after_valid_readback(tmp_path):
    engine = _engine(tmp_path)
    res = detect_reminder_intent("me lembre de beber agua daqui a 15 minutos", engine)
    assert res.kind == "reminder"
    assert res.reminder_id.startswith("REM-")
    assert "vou te lembrar" in res.reply.casefold()
    # o id anunciado ao usuario existe de fato no armazenamento
    persisted = ReminderEngine(tmp_path / "reminders.db").get(res.reminder_id)
    assert persisted is not None and persisted.message == "beber agua"
    assert res.reminder_id in res.reply


# 5. engine=None (sem storage) -> NUNCA prometer "vou te lembrar" (BUG-001)
def test_no_engine_never_false_success():
    res = detect_reminder_intent("me lembre de pagar conta daqui a 20 minutos", None)
    assert res.kind == "reminder_failed"
    assert res.reminder_id == ""
    r = res.reply.casefold()
    assert "vou te lembrar" not in r
    assert "não está agendado" in r or "nao esta agendado" in r
