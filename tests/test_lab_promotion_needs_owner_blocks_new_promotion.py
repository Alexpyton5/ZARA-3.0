"""An unresolved reconciliation keeps blocking every new promotion.

`RECONCILIATION_NEEDS_OWNER` is not a conclusion: the machine tried to undo an
interrupted promotion, could not prove one single coherent state, and stopped.
The runtime is still owned by that hybrid state. Treating it as terminal made
`pending_promotions()` forget it, which made `promotion_readiness()` accept a
brand new promotion on top of a state no human had ever resolved.

Everything here lives in tmp_path (the fixture from `test_lab_source_promotion`);
the owner's real CURRENT build, real pointers and real Lab database are never
referenced.
"""
import json
from pathlib import Path

import pytest

from core.lab_v1.release import (
    OWNER_RESOLUTION_REQUIRED_STATES,
    RESOLVED_PROMOTION_STATES,
    TERMINAL_PROMOTION_STATES,
    SourcePromotion,
    pending_promotions,
    promotion_readiness,
    reconcile_promotions,
)
from tests import test_lab_promotion_crash_recovery as crash
from tests import test_lab_source_promotion as base
from tools import build_current as build

lab, queued = base.lab, base.queued
journal_of = crash.journal_of


@pytest.fixture
def needs_owner(lab, monkeypatch):
    """A real crash plus a real failed rollback, ending in RECONCILIATION_NEEDS_OWNER.

    Nothing is faked: the promotion is killed after the pointers already point at
    candidate B, and the retained known-good package is damaged so the rollback
    cannot prove the baseline it would have to restore.
    """
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    restart = crash.crash_when(monkeypatch, 'ACTIVATED')
    with pytest.raises(crash.Crash):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback, commit=promotion.commit)
    restart()
    build_journal = next(iter((lab['root'] / 'artifacts/releases').glob('*.json')))
    backup = Path(json.loads(build_journal.read_text())['backup'])
    build.packaged_paths(backup)['EXE_SHA256'].write_text('corrupted-known-good')

    (record,) = reconcile_promotions()

    assert record['action'] == 'BLOCKED'
    assert record['to_state'] == 'RECONCILIATION_NEEDS_OWNER'
    assert journal_of(lab)['state'] == 'RECONCILIATION_NEEDS_OWNER'
    return lab


def test_needs_owner_is_not_a_resolved_state():
    """The set that answers "is anything pending" excludes the failure state."""
    assert 'RECONCILIATION_NEEDS_OWNER' not in RESOLVED_PROMOTION_STATES
    assert OWNER_RESOLUTION_REQUIRED_STATES == frozenset({'RECONCILIATION_NEEDS_OWNER'})
    # It stays final for the machine: automatic reconciliation must never retry
    # an effect it already failed to prove.
    assert 'RECONCILIATION_NEEDS_OWNER' in TERMINAL_PROMOTION_STATES


def test_unresolved_reconciliation_stays_pending_and_refuses_a_new_promotion(needs_owner):
    lab = needs_owner

    pending = pending_promotions()

    assert [item['state'] for item in pending] == ['RECONCILIATION_NEEDS_OWNER']
    assert pending[0]['needs_owner'] is True
    # The actual regression: readiness used to return eligible=True here.
    readiness = promotion_readiness(lab['receipt'], lab['root'])
    assert readiness['eligible'] is False
    assert readiness['reason'] == 'PROMOTION_RECONCILIATION_NEEDS_OWNER'
    assert readiness['pending'] == pending


def test_no_second_promotion_can_be_queued_on_top_of_it(needs_owner):
    lab = needs_owner
    from core.lab_v1.release import ReleaseQueue

    queue = ReleaseQueue(lab['store'])

    with pytest.raises(ValueError) as failure:
        queue.schedule_source_candidate('s2', lab['receipt'], lab['root'])
    assert 'PROMOTION_RECONCILIATION_NEEDS_OWNER' in str(failure.value)
    assert queue.snapshot('s2') is None


def test_time_and_repeated_reconciliation_never_clear_it(needs_owner):
    lab = needs_owner
    before = journal_of(lab)['reconciliations']

    again = reconcile_promotions()
    once_more = reconcile_promotions()

    # No machine retries the uncertain effect...
    assert [r['action'] for r in again + once_more] == ['NONE', 'NONE']
    assert [r['reason'] for r in again + once_more] == ['ALREADY_TERMINAL', 'ALREADY_TERMINAL']
    assert journal_of(lab)['reconciliations'] == before
    # ...and no amount of re-checking makes the pending state disappear.
    assert [item['state'] for item in pending_promotions()] == ['RECONCILIATION_NEEDS_OWNER']
    assert promotion_readiness(lab['receipt'], lab['root'])['eligible'] is False


def test_only_an_explicit_human_resolution_clears_it(needs_owner):
    lab = needs_owner
    journal_path = sorted((lab['root'] / 'artifacts/releases').glob('source-*/SOURCE_PROMOTION.json'))[0]
    document = json.loads(journal_path.read_text(encoding='utf-8'))

    # The owner inspected the machine and declared the outcome on the journal.
    document['state'] = 'RECONCILED_KNOWN_GOOD'
    document['resolved_by_owner'] = True
    build.write_json(journal_path, document)

    assert pending_promotions() == []
