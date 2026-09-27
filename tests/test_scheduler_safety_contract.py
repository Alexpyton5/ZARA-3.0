from core.lab_v1.service import SCHEDULER_ENABLED, scheduler_enabled


def test_scheduler_is_enabled_by_installation_default_and_persisted_opt_out_wins():
    assert SCHEDULER_ENABLED is True
    assert scheduler_enabled({}) is True
    assert scheduler_enabled({'scheduler_enabled': False}) is False
    assert scheduler_enabled({'scheduler_enabled': True}) is True


def test_scheduler_can_be_enabled_only_by_explicit_process_flag(monkeypatch):
    monkeypatch.setenv('ZARA_LAB_SCHEDULER_ENABLED', '1')
    assert scheduler_enabled({}) is True
