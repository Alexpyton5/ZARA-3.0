"""The Lab boot reconciles an interrupted promotion by itself, or refuses to work.

`reconcile_promotions` was already proven in `test_lab_promotion_crash_recovery`,
but nothing in the product ever called it: recovery existed and was not autonomous.
These tests never call it. They kill a promotion mid-flight, then boot a brand new
`LabV1Service` through a normal entrypoint (`snapshot`, the same call the UI makes)
and require that the boot alone left exactly one coherent state on disk.

Everything lives in tmp_path: the real CURRENT build, the real pointers and the
real Lab database are never referenced.
"""
import asyncio
import json
from pathlib import Path

import pytest

from core.lab_v1 import service as service_module
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.release import SourcePromotion, pending_promotions
from core.lab_v1.service import LAST_BOOT_ROW, LabV1Service
from core.lab_v1.store import LabStore
from tests import test_lab_promotion_crash_recovery as crash
from tests import test_lab_source_promotion as base
from tools import build_current as build

# Same isolated known-good-A / candidate-B workspace used by the recovery proof.
lab, queued = base.lab, base.queued
Crash, crash_when = crash.Crash, crash.crash_when
assert_all_known_good, assert_all_candidate = crash.assert_all_known_good, crash.assert_all_candidate
journal_of, no_staging_left = crash.journal_of, crash.no_staging_left


@pytest.fixture
def boot(lab, tmp_path, monkeypatch):
    """Return a callable that performs one full Lab boot over the same database.

    Only the store path and the provider registry are redirected — the boot
    sequence itself (`LabV1Service()` → first entrypoint → `_get_runtime`) is the
    production one, unpatched.
    """
    database = lab['store'].db_path
    monkeypatch.setattr(service_module, 'LabStore', lambda *a, **k: LabStore(database))
    monkeypatch.setattr(service_module, 'default_registry',
                        lambda: ProviderRegistry(tmp_path / 'provider_health.json'))

    def boot_the_lab():
        service = LabV1Service()          # a brand new process would do exactly this
        snapshot = asyncio.run(service.snapshot())
        return service, snapshot

    return boot_the_lab


def boot_rows(lab):
    with lab['store']._connect() as conn:
        return {row[0]: json.loads(row[1]) for row in
                conn.execute('SELECT journal, document FROM lab_boot_reconciliation')}


def interrupt_promotion(lab, monkeypatch, state, journal=crash.PROMOTION_JOURNAL):
    """Kill a real promotion at `state`, leaving whatever it left on disk."""
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, state, journal)
    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback, commit=promotion.commit)
    restart()
    return queue


def test_boot_reconciles_an_interrupted_promotion_without_being_asked(lab, monkeypatch, boot):
    interrupt_promotion(lab, monkeypatch, 'ACTIVATED')  # pointers already B, health never ran
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'B'
    assert [item['state'] for item in pending_promotions()] == ['PACKAGE_ACTIVATING']

    service, snapshot = boot()

    # Nobody called reconcile: the boot did it before serving anything.
    report = snapshot['boot_reconciliation']
    assert report['state'] == 'RECONCILED'
    assert [item['state'] for item in report['pending_before']] == ['PACKAGE_ACTIVATING']
    (record,) = report['records']
    assert record['action'] == 'ROLLED_BACK'
    assert record['reason'] == 'INTERRUPTED_PROMOTION_WAS_NOT_PROVEN_HEALTHY'
    assert record['evidence_after']['coherent_state'] == 'KNOWN_GOOD'
    assert report['unresolved'] == []
    # One coherent state on disk, and the journal says so durably.
    assert_all_known_good(lab)
    assert no_staging_left(lab)
    assert journal_of(lab)['state'] == 'RECONCILED_KNOWN_GOOD'
    assert pending_promotions() == []
    # Persisted receipt, not just an in-memory claim.
    rows = boot_rows(lab)
    assert rows[record['journal']]['action'] == 'ROLLED_BACK'
    assert rows[LAST_BOOT_ROW]['state'] == 'RECONCILED'
    assert service.boot_reconciliation()['state'] == 'RECONCILED'


def test_boot_completes_a_promotion_whose_health_already_passed(lab, monkeypatch, boot):
    interrupt_promotion(lab, monkeypatch, 'COMMITTED')  # only the commit was missing
    assert journal_of(lab)['state'] == 'HEALTH_PASSED'

    _, snapshot = boot()

    (record,) = snapshot['boot_reconciliation']['records']
    assert record['action'] == 'COMPLETED_PROMOTION'
    assert record['evidence']['coherent_state'] == 'CANDIDATE'
    assert_all_candidate(lab)  # proven healthy: finished, not rolled back
    assert journal_of(lab)['state'] == 'RECONCILED_COMMITTED'


def test_boot_without_a_pending_journal_changes_nothing(lab, boot):
    before = {key: build.digest(path) for key, path in build.packaged_paths(lab['current']).items()}
    before_source = build.source_identity()['sha256']

    _, snapshot = boot()

    report = snapshot['boot_reconciliation']
    assert report == {'checked_at': report['checked_at'], 'state': 'CLEAN',
                      'pending_before': [], 'records': [], 'unresolved': []}
    assert {key: build.digest(path) for key, path in build.packaged_paths(lab['current']).items()} == before
    assert build.source_identity()['sha256'] == before_source
    assert_all_known_good(lab)
    assert list(boot_rows(lab)) == [LAST_BOOT_ROW]
    assert not (lab['root'] / 'artifacts').exists()


def test_repeated_restarts_never_duplicate_the_effect(lab, monkeypatch, boot):
    interrupt_promotion(lab, monkeypatch, 'ACTIVATED')

    first = boot()[1]['boot_reconciliation']
    second = boot()[1]['boot_reconciliation']
    third = boot()[1]['boot_reconciliation']

    assert first['records'][0]['action'] == 'ROLLED_BACK'
    # Nothing left to reconcile, so later boots do not even look at a journal.
    assert (second['state'], second['pending_before'], second['records']) == ('CLEAN', [], [])
    assert (third['state'], third['pending_before'], third['records']) == ('CLEAN', [], [])
    assert len(journal_of(lab)['reconciliations']) == 1
    # The real receipt is never overwritten by a later, emptier boot.
    assert boot_rows(lab)[first['records'][0]['journal']]['action'] == 'ROLLED_BACK'
    assert_all_known_good(lab)
    assert no_staging_left(lab)


def test_a_reconciliation_that_fails_is_persisted_and_blocks_mission_entry(lab, monkeypatch, boot):
    interrupt_promotion(lab, monkeypatch, 'ACTIVATED')
    # The retained known-good package is damaged: rollback cannot prove the
    # baseline, so no machine may decide this one.
    build_journal = next(path for path in (lab['root'] / 'artifacts/releases').glob('*.json'))
    backup = Path(json.loads(build_journal.read_text())['backup'])
    build.packaged_paths(backup)['EXE_SHA256'].write_text('corrupted-known-good')

    service, snapshot = boot()

    report = snapshot['boot_reconciliation']
    assert report['state'] == 'NEEDS_OWNER'
    (record,) = report['records']
    assert record['action'] == 'BLOCKED'
    assert record['to_state'] == 'RECONCILIATION_NEEDS_OWNER'
    assert 'Rollback baseline failed integrity check' in record['reason']
    assert [item['journal'] for item in report['unresolved']] == [record['journal']]
    # Explicit and durable: a later boot cannot present this machine as healthy.
    assert boot_rows(lab)[record['journal']]['to_state'] == 'RECONCILIATION_NEEDS_OWNER'
    later, later_snapshot = boot()
    assert later_snapshot['boot_reconciliation']['state'] == 'NEEDS_OWNER'
    assert later_snapshot['boot_reconciliation']['unresolved'] == report['unresolved']
    # And the Lab refuses to start missions on top of it.
    refused = asyncio.run(later.start_autopilot('Melhore a ZARA'))
    assert refused['success'] is False
    assert refused['code'] == 'PROMOTION_RECONCILIATION_NEEDS_OWNER'
    assert refused['state'] == 'BLOCKED_NEEDS_OWNER'
    assert service.boot_reconciliation()['state'] == 'NEEDS_OWNER'
