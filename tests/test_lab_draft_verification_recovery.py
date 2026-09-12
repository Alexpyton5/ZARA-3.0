"""A refused draft is feedback the worker can act on, not the end of the mission.

Companion to ``test_lab_draft_rejection_recovery.py``. That file covers the draft
the local EXECUTOR refuses (``apply_edits`` raising before its first write). This
file covers the draft the local VERIFIER refuses, which is a different road to the
same dead end and was still open after that correction.

Observed on 2026-09-10, LAB-12 mission ``session_8ed4613ef1eb`` (third clean-run
attempt of the night). Real trace, real models:

    patch:draft   VERIFYING -> verification FAIL: REAL_REGRESSION_TEST_REQUIRED
    mission       BLOCKED / VERIFICATION_FAIL    -> dead

``Autopilot.run`` routed that to ``SourceMission.repair``, whose gate only ever
accepted the review step, so the call returned ``False`` and the mission died
holding a perfectly actionable error message. The builder had been told exactly
what was missing and was never allowed to answer.

The three steps repaired here are all local verifications of MODEL output - the
reviewer's verdict, the draft's own schema check, and the deterministic
before-fail/after-pass postcondition. Nothing was promoted in any of them and the
verifier names the defect, so one more bounded draft is an honest answer.

What these tests must ALSO pin, so the fix cannot rot into a lie:

* the refused rule is still refused (the bad draft never becomes acceptable);
* the real-effect ACTION steps (``source.apply``, ``source.build``) are still
  NOT repairable here - those wrote/packaged bytes, and "just do it again" is
  precisely the unsafe move;
* the recovery spends the EXISTING repair budget, so a mission cannot loop.
"""
from __future__ import annotations

import json

import pytest

from core.lab_v1.domain import Availability, ProviderResult
from core.lab_v1.source_mission import SourceMission

# The whole isolated engine (tmp workspace, tmp DB, fixture providers, real
# pytest subprocesses) already exists. Reusing it keeps this file about the
# defect instead of about scaffolding.
from tests.test_lab_source_mission import source_engine as source_engine  # noqa: F401

OBJECTIVE = 'Corrija a ZARA core/example.py: twice deve duplicar também negativos.'

GOOD_TEST = ('from core.example import twice\ndef test_behavior():\n'
             '    assert twice(3) == 6\n    assert twice(-2) == -4\n    assert twice(0) == 0\n')
GOOD_SOURCE = 'def twice(n):\n    return n * 2\n'

# Refused by SourceMission.verify with REAL_REGRESSION_TEST_REQUIRED: it never
# creates the regression test the plan demands. This is the LAB-12 draft.
DRAFT_WITHOUT_REGRESSION_TEST = {
    'edits': [{'path': 'core/example.py', 'content': GOOD_SOURCE}],
    'summary': 'Source touched, required regression test omitted.',
}

# Applies cleanly, but the "regression" test also passes on the ORIGINAL source
# (2 + 2 == 2 * 2), so the before-fail/after-pass postcondition is not met.
DRAFT_WITH_WEAK_TEST = {
    'edits': [
        {'path': 'core/example.py', 'content': GOOD_SOURCE},
        {'path': 'tests/test_zara_mission_regression.py', 'content':
            'from core.example import twice\ndef test_behavior():\n    assert twice(2) == 4\n'},
    ],
    'summary': 'A test that cannot tell the defect from the fix.',
}


def _drive_builder(source_engine, monkeypatch, bad_drafts):
    """Return the first ``len(bad_drafts)`` drafts, then the fixture's good one."""
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    calls = {'builder': 0, 'reviewer': 0, 'planner': 0}

    def sequenced(**kwargs):
        model = kwargs['model']
        calls[model] = calls.get(model, 0) + 1
        if model != 'builder' or calls['builder'] > len(bad_drafts):
            return original(**kwargs)
        return ProviderResult(True, text=json.dumps(bad_drafts[calls['builder'] - 1]),
                              availability=Availability.AVAILABLE, model_reported='builder',
                              provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)

    monkeypatch.setattr(adapter, 'complete', sequenced)
    sid = source_engine.start(OBJECTIVE)['session_id']
    return sid, source_engine.run(sid), calls


def _verification_errors(source_engine, sid):
    return [json.loads(a.body).get('error', '') for a in source_engine.store.list_artifacts(sid)
            if a.kind == 'SOURCE_VERIFICATION']


# --------------------------------------------------------------------------
# 1. The exact LAB-12 killer: a refused draft now gets one bounded answer.
# --------------------------------------------------------------------------

def test_a_draft_refused_by_the_verifier_is_redrafted_instead_of_killing_the_mission(
        source_engine, monkeypatch):
    sid, result, calls = _drive_builder(source_engine, monkeypatch, [DRAFT_WITHOUT_REGRESSION_TEST])

    assert result['state'] == 'COMPLETED', _verification_errors(source_engine, sid)
    # The builder was asked twice: the refusal, then the answer.
    assert calls['builder'] == 2
    patch_step = next(s for s in result['mission']['steps'] if s['id'] == 'patch:draft')
    assert len(patch_step['repairs']) == 1
    # The rejected attempt is retained as evidence, not erased.
    assert patch_step['repairs'][0]['receipt']
    assert patch_step['repairs'][0]['verification']['verdict'] == 'FAIL'


def test_the_refused_rule_is_not_relaxed_and_the_worker_is_told_what_broke(
        source_engine, monkeypatch):
    sid, result, _ = _drive_builder(source_engine, monkeypatch, [DRAFT_WITHOUT_REGRESSION_TEST])

    # The bad draft was genuinely refused; the mission did not simply accept it.
    assert 'REAL_REGRESSION_TEST_REQUIRED' in _verification_errors(source_engine, sid)
    # And the reason travelled back to the builder as the repair reason, which
    # MissionController renders into the next prompt's context packet.
    patch_step = next(s for s in result['mission']['steps'] if s['id'] == 'patch:draft')
    assert 'REAL_REGRESSION_TEST_REQUIRED' in patch_step['repairs'][0]['reason']
    # The candidate really is repaired, proven by the real subprocess evidence.
    meta = source_engine.metrics(sid)['source_work']
    assert meta['test_evidence']['baseline']['exit_code'] == 1
    assert meta['test_evidence']['candidate']['exit_code'] == 0


# --------------------------------------------------------------------------
# 2. A failed test postcondition goes back to the builder, not to a re-run.
# --------------------------------------------------------------------------

def test_a_weak_regression_test_routes_back_to_the_builder(source_engine, monkeypatch):
    """Re-running deterministic pytest over unchanged source repeats the result.

    Only a new draft can turn a test that cannot see the defect into one that
    can, so the repair frontier must restart at the draft.
    """
    sid, result, calls = _drive_builder(source_engine, monkeypatch, [DRAFT_WITH_WEAK_TEST])

    assert result['state'] == 'COMPLETED', _verification_errors(source_engine, sid)
    assert 'REAL_BEFORE_FAIL_AFTER_PASS_REQUIRED' in _verification_errors(source_engine, sid)
    assert calls['builder'] == 2
    patch_step = next(s for s in result['mission']['steps'] if s['id'] == 'patch:draft')
    tests_step = next(s for s in result['mission']['steps'] if s['id'] == 'tests')
    assert len(patch_step['repairs']) == 1
    assert len(tests_step['repairs']) == 1


def test_a_stale_evidence_only_verdict_cannot_shrink_a_draft_repair(source_engine, monkeypatch):
    """EVIDENCE_ONLY describes a REVIEW. It must not narrow a draft restart.

    If a previous review said "only the receipt is missing" and a later draft is
    refused, restarting at the tests step would re-run pytest over source the
    verifier just rejected - spending budget to reproduce the same failure.
    """
    sid, _, _ = _drive_builder(source_engine, monkeypatch, [])
    mission = SourceMission(source_engine, sid)
    mission.save_meta(review_failure_kind='EVIDENCE_ONLY')

    # Put the mission back into the exact refused-draft state and repair it.
    with source_engine.controller._transaction() as conn:
        doc, _row = source_engine.controller._load(conn, sid)
        for step in doc['steps']:
            if step['id'] in ('patch:draft', 'patch:apply', 'tests', 'review', 'candidate_build'):
                step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
        draft = next(s for s in doc['steps'] if s['id'] == 'patch:draft')
        draft.update(status='VERIFYING', attempt_id='attempt_x',
                     receipt={'artifact_ref': 'r', 'summary': 's'},
                     verification={'verdict': 'FAIL', 'evidence_ref': 'e'})
        doc['state'], doc['blocker'] = 'BLOCKED', 'VERIFICATION_FAIL'
        conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0 WHERE session_id=?', (sid,))
        source_engine.controller._save(conn, doc, 'test.refused_draft')

    assert SourceMission(source_engine, sid).repair('REAL_REGRESSION_TEST_REQUIRED') is True

    repaired = source_engine.controller.snapshot(sid)
    draft = next(s for s in repaired['steps'] if s['id'] == 'patch:draft')
    assert draft['status'] == 'PENDING', 'the draft itself must restart, not just the tests'


# --------------------------------------------------------------------------
# 3. What must NOT become repairable: steps that really changed something.
# --------------------------------------------------------------------------

@pytest.mark.parametrize('action_step', ['patch:apply', 'candidate_build'])
def test_real_effect_action_steps_are_still_not_repaired_here(source_engine, action_step):
    """source.apply wrote bytes and source.build packaged a desktop candidate.

    Their verification failure is not "a model said something wrong", so the
    widened gate must still refuse them. Loosening this would be the evidence
    rule told backwards: treating a real, possibly half-done effect as if it
    were a harmless retry.
    """
    sid = source_engine.start(OBJECTIVE)['session_id']
    assert source_engine.run(sid)['state'] == 'COMPLETED'

    with source_engine.controller._transaction() as conn:
        doc, _row = source_engine.controller._load(conn, sid)
        step = next(s for s in doc['steps'] if s['id'] == action_step)
        step.update(status='VERIFYING', verification={'verdict': 'FAIL', 'evidence_ref': 'e'})
        doc['state'], doc['blocker'] = 'BLOCKED', 'VERIFICATION_FAIL'
        conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0 WHERE session_id=?', (sid,))
        source_engine.controller._save(conn, doc, 'test.action_step_failed')

    assert SourceMission(source_engine, sid).repair('NO_SOURCE_CHANGE') is False
    assert source_engine.controller.snapshot(sid)['state'] == 'BLOCKED'


# --------------------------------------------------------------------------
# 4. The recovery is bounded by the budget that already existed.
# --------------------------------------------------------------------------

def test_endless_draft_refusals_exhaust_the_shared_budget_and_stop(source_engine, monkeypatch):
    """No new counter, no infinite loop: the same repair budget ends the mission."""
    sid, result, calls = _drive_builder(source_engine, monkeypatch,
                                        [DRAFT_WITHOUT_REGRESSION_TEST] * 40)
    if result['state'] not in ('BLOCKED_NEEDS_OWNER', 'BLOCKED', 'FAILED'):
        result = source_engine.run(sid)

    assert result['state'] == 'BLOCKED_NEEDS_OWNER'
    meta = source_engine.metrics(sid)['source_work']
    # The existing budget fields are the only ones spent: one replan, then stop.
    assert meta['repair_replans'] == 1
    assert meta['replan_blocked'] is True
    assert meta['repair_cycle_count'] == meta['repair_limit']
    # One repair per refused draft, plus the final call that found the budget
    # spent and recorded the stop: 7 redrafts after the first draft, then the
    # exhausting eighth. The counter tracks repair decisions, not just retries.
    assert calls['builder'] == 8
    assert meta['repair_count'] == 8
    # Nothing was ever packaged from a refused draft.
    assert 'candidate_build' not in meta
