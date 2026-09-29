"""FRENTE D — operação silenciosa: política de notificação + log interno.

ZARA-SILENCIO-001: trabalha quieto; só avisa quando está PRONTO ou quando
trava de verdade. Progresso detalhado vai só para o ops_log interno.
"""
from __future__ import annotations

import pytest

import core.silent_mode as silent_mode_mod
from core.ops_log import OpsLog
from core.reminder_engine import ReminderEngine
from core.silent_mode import (
    NOTIFY_KINDS,
    record_progress,
    route,
    should_notify,
    silent_mode_enabled,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ZARA_SILENT_MODE", raising=False)


# ---------------------------------------------------------------- D2: política


def test_silent_mode_is_on_by_default():
    assert silent_mode_enabled() is True


def test_silent_mode_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ZARA_SILENT_MODE", "0")
    assert silent_mode_enabled() is False


def test_notify_kinds_are_exactly_done_stuck_reminder_critical():
    assert set(NOTIFY_KINDS) == {"done", "stuck", "reminder", "critical"}


@pytest.mark.parametrize("kind", ["done", "stuck", "reminder", "critical"])
def test_important_events_notify(kind):
    assert route(kind) == "notify"
    assert should_notify(kind) is True


@pytest.mark.parametrize(
    "kind", ["progress", "step", "info", "debug", "trace", "telemetry", "whatever"]
)
def test_everything_else_is_log_only(kind):
    assert route(kind) == "log_only"
    assert should_notify(kind) is False


def test_disabled_silent_mode_notifies_everything(monkeypatch):
    monkeypatch.setenv("ZARA_SILENT_MODE", "0")
    assert route("progress") == "notify"
    assert route("debug") == "notify"


# ---------------------------------------------------------------- D3: log interno


def test_record_progress_writes_to_ops_log(tmp_path, monkeypatch):
    import core.ops_log as ops_log_mod

    log = OpsLog(path=tmp_path / "ops.jsonl")
    monkeypatch.setattr(ops_log_mod, "_ops", log)

    record_progress("jarvis_multi_action", "Clausula [OK] Conforto", {"x": 1})

    events = log.recent(10)
    assert len(events) == 1
    assert events[0]["kind"] == "progress"
    assert events[0]["source"] == "jarvis_multi_action"
    assert "Conforto" in events[0]["message"]


def test_ops_log_scrubs_sensitive_details(tmp_path):
    log = OpsLog(path=tmp_path / "ops.jsonl")
    log.record("progress", "src", "msg", {"api_key": "segredo-123", "ok": True})

    events = log.recent(10)
    assert events[0]["details"]["api_key"] == "<redacted>"
    assert events[0]["details"]["ok"] is True
    raw = (tmp_path / "ops.jsonl").read_text(encoding="utf-8")
    assert "segredo-123" not in raw


def test_ops_log_never_raises(tmp_path):
    log = OpsLog(path=tmp_path / "ops.jsonl")
    # detalhes não-serializáveis e caminho estranho: log é acessório, não quebra.
    log.record("progress", "src", "msg", {"x": object()})
    assert log.recent(10)


def test_ops_log_rotation_bounds_size(tmp_path, monkeypatch):
    import core.ops_log as ops_log_mod

    monkeypatch.setattr(ops_log_mod, "_MAX_BYTES", 100)
    log = OpsLog(path=tmp_path / "ops.jsonl")
    for i in range(20):
        log.record("progress", "src", f"mensagem longa numero {i} " + "x" * 50)
    assert (tmp_path / "ops.jsonl.1").is_file()


# ------------------------------------------------- D2: lembrete roteado


def test_reminder_fire_notifies_by_default(tmp_path):
    fired: list = []
    engine = ReminderEngine(db_path=tmp_path / "r.db", on_fire=fired.append)
    engine.create("ligar para o Alex", __import__("time").time() - 1)

    engine.fire_due_now()

    assert len(fired) == 1


def test_reminder_fire_respects_silenced_policy(tmp_path, monkeypatch):
    """Se a política mandar 'reminder' para o log, on_fire não é chamado."""
    fired: list = []
    engine = ReminderEngine(db_path=tmp_path / "r2.db", on_fire=fired.append)
    monkeypatch.setattr(silent_mode_mod, "NOTIFY_KINDS", frozenset())
    import time

    engine.create("teste silencioso", time.time() - 1)

    engine.fire_due_now()

    assert fired == []
