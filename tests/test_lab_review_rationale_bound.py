"""A reviewer cut off mid-sentence is not a reviewer.

Observed 2026-09-11, LAB-13 mission ``session_ff9f6c94874e`` (clean isolated run,
planner=Haiku / builder=Sonnet / reviewer=Opus, all real provider Runs). The
independent reviewer answered three times. One of those answers was a genuine
**PASS**. All three were thrown away by the local verifier with::

    SOURCE_VERIFICATION:attempt_d51025137422
    {"passed": false, "error": "review rationale must be bounded non-empty text"}

The reviewer had done nothing wrong. ``validate_reviewer_result`` bounded the
rationale at 2000 characters while the reviewer prompt demanded "concrete
findings" over a 46k-char source view, a 44k-char diff/test packet and a
preservation receipt, and never mentioned any size limit. The three real
rationales measured 3504, 4228 and 4411 characters.

Two separate defects came out of that, and both are pinned here:

1. **The bound was wrong.** A PASS was refused for being well argued. The limit
   now matches what the prompt asks for, and the prompt now states the limit.
2. **The repair went to the wrong worker.** The refused step was ``review``, so
   ``SourceMission.repair`` restarted the frontier at ``patch:draft`` - sending
   the BUILDER back to redesign code the reviewer had just approved. A malformed
   reviewer ANSWER says nothing about the patch; only the review must re-run.

What these tests must ALSO pin, so the fix cannot rot into a lie:

* an empty, blank, non-text or genuinely unbounded rationale is still refused -
  the bound was raised, not removed;
* a real FAIL verdict about the code still restarts the BUILDER, because that
  one IS a statement about the patch.
"""
from __future__ import annotations

import json

import pytest

from core.lab_v1.domain import Availability, ProviderResult, Run, RunState
from core.lab_v1.real_work_contract import (
    REVIEW_RATIONALE_LIMIT,
    RealWorkContractError,
    ReviewResponseContractError,
    validate_reviewer_result,
)
from core.lab_v1.source_mission import SourceMission

# The whole isolated engine (tmp workspace, tmp DB, fixture providers, real
# pytest subprocesses) already exists. Reusing it keeps this file about the
# defect instead of about scaffolding.
from tests.test_lab_source_mission import source_engine as source_engine  # noqa: F401

OBJECTIVE = 'Corrija a ZARA core/example.py: twice deve duplicar tambem negativos.'

# Verbatim reviewer answer from LAB-13 run 1, artifact
# ``response:attempt_d51025137422``. Real Opus output, not a fixture.
REAL_PASS_REVIEW = json.loads("{\"verdict\": \"PASS\", \"rationale\": \"MECHANISM: the race was real and the fix is structural, not cosmetic. The old test raced a fixed asyncio.sleep(0.04) against the loop's 0.01s cadence plus two asyncio.to_thread round trips (tick + record_background_error), so two full iterations were not guaranteed to fit the window. The patch adds an opt-in completed-cycle signal in core/lab_v1/service.py: __init__ sets self._background_cycle_event: asyncio.Event|None = None and self._background_cycles = 0; _background_loop increments the counter and, only when the event is not None, sets it once per completed cycle, after the success path AND after the recorded-failure path, i.e. after the error is captured, so a waiter that observes cycle N is guaranteed the N-th tick's outcome is already recorded. The waiter (clear() -> re-check counter -> await wait_for(..., timeout=5.0)) is a correct lost-wakeup-free pattern: clear/re-check contains no await, so on a single-threaded loop the counter cannot advance between them, and the counter (not the edge) is the authority. Determinism now comes from causality, not margin.\\nTEST VALIDITY: nothing was weakened. Both original assertions survive verbatim -- ticks.call_count >= 2 (loop survived the RuntimeError and ticked again) and recorded[0].startswith('RuntimeError: boom') (the error was captured with type+message). The RuntimeError('boom') side_effect scenario is unchanged and still the thing under observation; the test is strictly stricter than before, since it now waits for two REAL cycles rather than hoping 0.04s covered them. No assertion, timeout-as-skip, retry decorator, xfail, or loosened matcher was introduced.\\nNO NEW TIMING DEPENDENCY / NO PRODUCTION CHANGE: the only production-path cost is an unconditional int increment plus a None check; with the hook left at its default None (every non-test caller) behavior is bit-identical -- no new sleep, no new await, no lock, no change to cadence or to the max(BACKGROUND_LOOP_MIN_INTERVAL_SECONDS, ...) sleep, which is only a naming of the pre-existing 0.01 floor. The outer except handler also bumps/sets before dying, which cannot manufacture a false green: if the loop dies after one cycle the waiter is released but ticks.call_count >= 2 then FAILS loudly instead of hanging 5s. Observable service API (start_background/stop_background return shapes, _background_error) is untouched.\\nFABRICATION CHECK: receipt REAL_TESTS:attempt_617ec43e6aa2 shows the new regression file failing 4/4 on the UNPATCHED baseline with AttributeError: 'LabV1Service' object has no attribute '_background_cycles' and passing 4/4 on the candidate, with identical test_hashes (0f2f4d...) on both sides -- the mechanism is genuinely new, the tests were not rewritten between runs, and the pass is not a no-op. tests/test_zara_mission_regression.py reruns the exact previously-flaky scenario 20x in-process, plus a 10-cycle interleaved failure/success case asserting exact recorded-error count and per-index message text, plus a healthy-path control asserting record_background_error is never called and _background_error stays None -- so the failure scenario remains fully testable and observable.\\nRESIDUAL (non-blocking) NOTES: (a) the shown pytest nodeids cover only tests/test_zara_mission_regression.py, not tests/test_lab_policy_facade.py::test_background_task_failure_is_visible_and_loop_survives itself; the repeat-proof is by an exact structural replica rather than the original nodeid, acceptable here because the waiter is byte-identical in logic and determinism is structural, but rerunning the original nodeid N times would be the cleaner artifact. (b) len(recorded) == len(failures) in the alternating test relies on stop_background winning against the loop's next iteration; the margin is a call_soon resumption versus a full 10ms sleep on a single-threaded loop, so it holds, but it is the one equality that is ordering-sensitive rather than causally pinned. (c) PRESERVATION: LOCAL_PRESERVATION:attempt_617ec43e6aa2 and LOCAL_PRESERVATION_REVIEW_INPUT:attempt_d51025137422 both report status NO_PROMOTION with matches:true; all 8 CURRENT entries (including the production tests/test_lab_policy_facade.py b9406e88... and core/lab_v1/service.py 9e0a6d90...) are byte-identical before and after, ZARA CURRENT BUILD exe/asar/backend untouched, rollback_basis CURRENT_RETAINED_NO_REFERENCED_PREVIOUS. Work stayed in the isolated copy as required.\", \"evidence_refs\": {\"artifact_hashes\": [\"170108e044615147f93718f913c9e9b8a67f2d0829b3436eee028c69eb8dfcae\", \"07e2f85cd20ecd95973d4cb047b8fb71235ad7a03d3bfbe2de8bd4a1ad832d8e\", \"0f2f4dcbdb4084d163c29d4bfc62c4954b33cd0e172956a6d8b1467cf37e1a3a\"], \"test_receipt_ids\": [\"REAL_TESTS:attempt_617ec43e6aa2\", \"LOCAL_PRESERVATION:attempt_617ec43e6aa2\", \"LOCAL_PRESERVATION_REVIEW_INPUT:attempt_d51025137422\"]}}")
REAL_PASS_RATIONALE = REAL_PASS_REVIEW['rationale']

# The exact cap that refused it, kept as a number so the regression is explicit.
HISTORICAL_CAP_THAT_REFUSED_A_PASS = 2000


def _run(run_id, agent, provider, model, *, task_id='task'):
    return Run(id=run_id, session_id='session', agent_id=agent, provider_id=provider, model=model,
               model_reported=f'reported-{model}', provider_session_id=f'provider-{run_id}',
               task_id=task_id, state=RunState.COMPLETED, started_at=10.0, ended_at=11.0,
               input_tokens=2, output_tokens=3)


def _validate(review):
    """Validate against three independent Runs, the way the mission does."""
    return validate_reviewer_result(
        review,
        reviewer_run=_run('review', 'reviewer', 'claude_cli', 'opus'),
        planner_run=_run('plan', 'planner', 'claude_cli', 'haiku'),
        builder_runs=[_run('build', 'builder', 'claude_cli', 'sonnet')],
        artifact_hashes=review['evidence_refs']['artifact_hashes'],
        test_receipt_ids=review['evidence_refs']['test_receipt_ids'])


# --------------------------------------------------------------------------
# 1. The exact LAB-13 killer: a real, well-argued PASS is a PASS.
# --------------------------------------------------------------------------

def test_the_real_4411_character_opus_pass_is_accepted_in_full():
    assert REAL_PASS_REVIEW['verdict'] == 'PASS'
    assert len(REAL_PASS_RATIONALE) == 4411

    verified = _validate(dict(REAL_PASS_REVIEW))

    assert verified['verdict'] == 'PASS'
    # Accepted whole: the reviewer's findings are not silently shortened.
    assert len(verified['rationale']) == len(REAL_PASS_RATIONALE)
    assert verified['rationale'].endswith('Work stayed in the isolated copy as required.')
    assert verified['reviewer_run_id'] == 'review'


def test_the_old_bound_is_what_refused_it_and_cannot_come_back():
    """Pins the number, not just the behaviour: 2000 could not hold a review."""
    assert len(REAL_PASS_RATIONALE) > HISTORICAL_CAP_THAT_REFUSED_A_PASS
    assert REVIEW_RATIONALE_LIMIT > len(REAL_PASS_RATIONALE)
    # All three real LAB-13 rationales fit now (3504, 4228, 4411).
    assert REVIEW_RATIONALE_LIMIT >= 6000
    # The failure it produced was attributable to the reviewer's answer, not to
    # the reviewed patch.
    too_long = dict(REAL_PASS_REVIEW, rationale='x' * (REVIEW_RATIONALE_LIMIT + 1))
    with pytest.raises(ReviewResponseContractError):
        _validate(too_long)


# --------------------------------------------------------------------------
# 2. The bound was raised, not removed.
# --------------------------------------------------------------------------

@pytest.mark.parametrize('rationale', ['', '   \n\t ', None, 123, ['findings'],
                                       'x' * (REVIEW_RATIONALE_LIMIT + 1)])
def test_an_empty_or_unbounded_rationale_is_still_refused(rationale):
    with pytest.raises(RealWorkContractError):
        _validate(dict(REAL_PASS_REVIEW, rationale=rationale))


def test_the_reviewer_prompt_states_the_limit_it_is_measured_against(source_engine):
    """The prompt that refused a PASS never mentioned a size. Now it must."""
    sid = source_engine.start(OBJECTIVE)['session_id']
    assert source_engine.run(sid)['state'] == 'COMPLETED'
    mission = SourceMission(source_engine, sid)

    class _Dispatch:
        step_id = mission.meta['review_step']
        task_id = sid + ':' + mission.meta['review_step']
        attempt_id = 'attempt_prompt_probe'

        class context:
            @staticmethod
            def render():
                return ''

    system, _prompt = mission.model_input(_Dispatch())
    assert str(REVIEW_RATIONALE_LIMIT) in system
    assert 'rationale' in system


# --------------------------------------------------------------------------
# 3. A malformed reviewer ANSWER restarts the reviewer, not the builder.
# --------------------------------------------------------------------------

def _drive_reviewer(source_engine, monkeypatch, bad_reviews):
    """Return ``bad_reviews`` from the reviewer, then the fixture's good one."""
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    calls = {'builder': 0, 'reviewer': 0, 'planner': 0}

    def sequenced(**kwargs):
        model = kwargs['model']
        calls[model] = calls.get(model, 0) + 1
        result = original(**kwargs)
        if model != 'reviewer' or calls['reviewer'] > len(bad_reviews):
            return result
        answer = dict(json.loads(result.text), **bad_reviews[calls['reviewer'] - 1])
        return ProviderResult(True, text=json.dumps(answer), availability=Availability.AVAILABLE,
                              model_reported='reviewer', provider_session_id='unit-fixture',
                              input_tokens=1, output_tokens=1)

    monkeypatch.setattr(adapter, 'complete', sequenced)
    sid = source_engine.start(OBJECTIVE)['session_id']
    return sid, source_engine.run(sid), calls


def _verification_errors(source_engine, sid):
    return [json.loads(a.body).get('error', '') for a in source_engine.store.list_artifacts(sid)
            if a.kind == 'SOURCE_VERIFICATION']


def test_an_overlong_rationale_sends_the_review_back_not_the_builder(source_engine, monkeypatch):
    """The LAB-13 waste, reproduced and fixed on the real engine.

    The reviewer answers once with a rationale past the bound. The patch, the
    applied diff and the test receipts are untouched by that, so the builder
    must NOT be asked to redesign anything.
    """
    sid, result, calls = _drive_reviewer(
        source_engine, monkeypatch, [{'rationale': 'y' * (REVIEW_RATIONALE_LIMIT + 500)}])

    assert result['state'] == 'COMPLETED', _verification_errors(source_engine, sid)
    # The malformed answer was genuinely refused, not quietly accepted.
    assert any('review rationale must be bounded' in error
               for error in _verification_errors(source_engine, sid))
    # The reviewer answered twice; the builder was never asked again.
    assert calls['reviewer'] == 2
    assert calls['builder'] == 1
    steps = {step['id']: step for step in result['mission']['steps']}
    assert len(steps['review']['repairs']) == 1
    assert steps['patch:draft'].get('repairs', []) == []
    assert steps['tests'].get('repairs', []) == []


@pytest.mark.parametrize('malformed', [
    {'rationale': ''},
    {'failure_kind': 'CODE_OR_TEST'},                      # PASS may not carry one
    {'evidence_refs': {'artifact_hashes': ['not-a-real-hash'],
                       'test_receipt_ids': ['not-a-real-receipt']}},
])
def test_any_reviewer_envelope_defect_routes_to_the_reviewer(source_engine, monkeypatch, malformed):
    sid, result, calls = _drive_reviewer(source_engine, monkeypatch, [malformed])

    assert result['state'] == 'COMPLETED', _verification_errors(source_engine, sid)
    assert calls['builder'] == 1, 'the builder must not redesign an approved patch'
    assert calls['reviewer'] == 2
    meta = source_engine.metrics(sid)['source_work']
    # The defect was attributed to the reviewer's answer while it was refused,
    # and cleared once a well-formed answer arrived.
    assert meta['review_response_defect'] is None
    assert meta['review_count'] >= 1


def test_a_real_code_verdict_still_restarts_the_builder(source_engine, monkeypatch):
    """FAIL about the code IS a statement about the patch. Nothing narrows here."""
    sid, result, calls = _drive_reviewer(source_engine, monkeypatch, [
        {'verdict': 'FAIL', 'failure_kind': 'CODE_OR_TEST',
         'rationale': 'Contraexemplo: twice(-2) nao foi coberto pelo teste de regressao.'}])

    assert result['state'] == 'COMPLETED', _verification_errors(source_engine, sid)
    assert calls['builder'] == 2, 'a code counterexample must reach the builder'
    steps = {step['id']: step for step in result['mission']['steps']}
    assert len(steps['patch:draft']['repairs']) == 1
