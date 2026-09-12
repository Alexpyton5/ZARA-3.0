"""Crash recovery proof for source promotion, entirely inside tmp_path.

A crash is simulated with a ``BaseException`` so that no ``except Exception``
compensation in the promotion code can run: the process simply stops writing,
exactly like a power loss. Restart then calls ``reconcile_promotions`` and every
scenario must end in ONE coherent state: source + EXE + ASAR + BACKEND +
pointers all known-good A, or all candidate B. Never a mixture.
"""
import hashlib
import json
from pathlib import Path

import pytest

from core.lab_v1.release import (
    SourcePromotion,
    known_good,
    pending_promotions,
    promotion_evidence,
    promotion_readiness,
    reconcile_promotions,
)
from tests import test_lab_source_promotion as base
from tools import build_current as build

# Reuse the isolated known-good-A / candidate-B fixture, unchanged.
lab, queued, sha = base.lab, base.queued, base.sha


class Crash(BaseException):
    """Not an Exception: no handler in the promotion code may catch it."""


#: Field that only exists in the promotion journal / only in the build journal.
PROMOTION_JOURNAL = 'candidate_source_sha256'
BUILD_JOURNAL = 'previous_pointers'


def crash_when(monkeypatch, state, journal=PROMOTION_JOURNAL):
    """Kill the process at the exact moment a journal state is written.

    Returns a ``restart`` callable that disarms only this seam. ``monkeypatch``
    is never undone here: it also holds the tmp_path sandbox redirection, and
    reverting it would point the recovery at the real workspace.
    """
    original = build.write_json
    armed = [True]

    def guarded(path, data):
        if armed[0] and isinstance(data, dict) and data.get('state') == state and journal in data:
            raise Crash(state)
        original(path, data)
    monkeypatch.setattr(build, 'write_json', guarded)
    return lambda: armed.__setitem__(0, False)


def assert_all_known_good(lab):
    """Every layer is A: source, sidecar, package artifacts and pointers."""
    info = build.verify_package(lab['current'])
    assert info['BUILD_ID'] == 'A'
    assert build.source_identity()['sha256'] == lab['source_a']
    assert (lab['root'] / 'core/example.py').read_text() == 'def twice(n):\n    return n + 2\n'
    assert not (lab['root'] / 'tests/test_regression.py').exists()
    assert sha(lab['sidecar']) == hashlib.sha256(b'A-BACKEND_SHA256').hexdigest()
    for key, path in build.packaged_paths(lab['current']).items():
        assert build.digest(path) == info[key]
        assert build.digest(path) == hashlib.sha256(('A-' + key).encode()).hexdigest()
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'A'
    assert (lab['root'] / 'ZARA_ACTIVE_BUILD.txt').read_text() == 'A-pointer\n'
    assert known_good()['build_id'] == 'A'


def assert_all_candidate(lab):
    """Every layer is B, and A is still retained as the rollback target."""
    info = build.verify_package(lab['current'])
    assert info['BUILD_ID'] == 'B'
    assert build.source_identity()['sha256'] == lab['source_b']
    assert (lab['root'] / 'core/example.py').read_text() == 'def twice(n):\n    return n * 2\n'
    assert (lab['root'] / 'tests/test_regression.py').is_file()
    assert sha(lab['sidecar']) == lab['receipt']['backend_sha256']
    for key, path in build.packaged_paths(lab['current']).items():
        assert build.digest(path) == info[key]
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'B'
    assert known_good()['build_id'] == 'B'
    backup = Path(json.loads(Path(info['ROLLBACK_JOURNAL']).read_text())['backup'])
    assert backup.is_dir(), 'known-good A package must be preserved'


def no_staging_left(lab):
    return not list((lab['root'] / 'frontend').glob('.current-build-staging-promote-*'))


def journal_of(lab):
    found = sorted((lab['root'] / 'artifacts/releases').glob('source-*/SOURCE_PROMOTION.json'))
    assert len(found) == 1
    return json.loads(found[0].read_text())


def test_scenario_a_crash_before_the_journal_exists_changes_nothing(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'PREPARED')

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)

    restart()
    assert reconcile_promotions() == []  # nothing was ever journalled
    assert_all_known_good(lab)


def test_scenario_a2_crash_at_prepare_state_reconciles_to_known_good(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'SOURCE_WRITING')  # backups taken, no source written yet

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()
    assert journal_of(lab)['state'] == 'PREPARED'

    (record,) = reconcile_promotions()

    assert record['action'] == 'NO_CHANGE_TO_UNDO'
    assert record['to_state'] == 'RECONCILED_KNOWN_GOOD'
    assert record['evidence']['coherent_state'] == 'KNOWN_GOOD'
    assert_all_known_good(lab)
    assert no_staging_left(lab)


def test_scenario_b_crash_after_source_promoted_rolls_back(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'SOURCE_PROMOTED')  # source+sidecar are B, package still A

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()
    assert journal_of(lab)['state'] == 'SOURCE_WRITING'
    assert build.source_identity()['sha256'] == lab['source_b']  # hybrid before recovery

    (record,) = reconcile_promotions()

    assert record['action'] == 'ROLLED_BACK'
    assert record['evidence']['coherent_state'] == 'MIXED'
    assert record['evidence']['verdicts'] == {'source': 'CANDIDATE', 'sidecar': 'CANDIDATE',
                                              'package': 'KNOWN_GOOD', 'pointer': 'KNOWN_GOOD'}
    assert record['package_result'] == 'PACKAGE_NEVER_ACTIVATED'
    assert record['evidence_after']['coherent_state'] == 'KNOWN_GOOD'
    assert_all_known_good(lab)


def test_scenario_c_crash_after_pointer_swap_before_health_rolls_back(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'ACTIVATED')  # package and pointers are already B

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()
    assert journal_of(lab)['state'] == 'PACKAGE_ACTIVATING'
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'B'

    (record,) = reconcile_promotions()

    assert record['action'] == 'ROLLED_BACK'
    assert record['reason'] == 'INTERRUPTED_PROMOTION_WAS_NOT_PROVEN_HEALTHY'
    assert record['package_result'] == 'PACKAGE_ROLLED_BACK'
    assert_all_known_good(lab)
    assert no_staging_left(lab)


def test_scenario_c2_crash_inside_the_package_swap_restores_the_baseline(lab, monkeypatch):
    """Hardest case: activate_package died after moving the pointers, before its
    own journal could say ACTIVATED. Recovery uses the evidence, not the claim."""
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'ACTIVATED', journal=BUILD_JOURNAL)

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()
    build_journal = sorted((lab['root'] / 'artifacts/releases').glob('*.json'))
    assert [json.loads(p.read_text())['state'] for p in build_journal] == ['PREPARED']
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'B'

    (record,) = reconcile_promotions()

    assert record['action'] == 'ROLLED_BACK'
    assert record['package_result'] == 'PACKAGE_RESTORED_FROM_INTERRUPTED_ACTIVATION'
    assert_all_known_good(lab)
    assert no_staging_left(lab)


def test_scenario_d_crash_after_health_passed_completes_the_promotion(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'COMMITTED')

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback, commit=promotion.commit)
    restart()
    assert journal_of(lab)['state'] == 'HEALTH_PASSED'

    (record,) = reconcile_promotions()

    assert record['action'] == 'COMPLETED_PROMOTION'
    assert record['to_state'] == 'RECONCILED_COMMITTED'
    assert record['evidence']['coherent_state'] == 'CANDIDATE'
    assert_all_candidate(lab)
    assert queue.snapshot('s1')['state'] == 'ACTIVE'


def test_scenario_e_crash_during_rollback_finishes_the_rollback(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    original = build.rollback_package
    armed = [True]

    def half_rollback(journal_path):
        result = original(journal_path)  # package and pointers return to A
        if armed[0]:
            raise Crash('ROLLING_BACK')  # source and sidecar are still B
        return result

    monkeypatch.setattr(build, 'rollback_package', half_rollback)

    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=lambda info: False,
                      rollback=promotion.rollback)
    armed[0] = False
    assert journal_of(lab)['state'] == 'ROLLING_BACK'

    (record,) = reconcile_promotions()

    assert record['action'] == 'ROLLED_BACK'
    assert record['package_result'] == 'PACKAGE_ALREADY_RESTORED'
    assert_all_known_good(lab)


def test_reconciliation_is_idempotent_and_never_replays(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'ACTIVATED')
    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()

    first = reconcile_promotions()[0]
    second = reconcile_promotions()[0]

    assert first['action'] == 'ROLLED_BACK'
    assert second['action'] == 'NONE' and second['reason'] == 'ALREADY_TERMINAL'
    assert len(journal_of(lab)['reconciliations']) == 1
    assert_all_known_good(lab)


def test_no_second_promotion_starts_on_top_of_an_unreconciled_crash(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'SOURCE_PROMOTED')
    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()

    assert [item['state'] for item in pending_promotions()] == ['SOURCE_WRITING']
    refused = promotion_readiness(lab['receipt'], lab['root'])
    assert refused['eligible'] is False
    assert refused['reason'] == 'PROMOTION_RECONCILIATION_PENDING'

    reconcile_promotions()

    assert pending_promotions() == []
    assert_all_known_good(lab)
    assert promotion_readiness(lab['receipt'], lab['root'])['eligible'] is True


def test_evidence_reads_disk_and_contradicts_a_lying_journal(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash_when(monkeypatch, 'SOURCE_PROMOTED')
    with pytest.raises(Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)
    restart()
    journal_path = sorted((lab['root'] / 'artifacts/releases').glob('source-*/SOURCE_PROMOTION.json'))[0]
    lying = json.loads(journal_path.read_text())
    lying['state'] = 'HEALTH_PASSED'       # the journal claims the promotion succeeded
    lying['new_build_id'] = 'B'
    build.write_json(journal_path, lying)

    evidence = promotion_evidence(lying)
    assert evidence['coherent_state'] == 'MIXED'

    (record,) = reconcile_promotions()

    assert record['action'] == 'ROLLED_BACK'  # disk beats the claim
    assert_all_known_good(lab)
