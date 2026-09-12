"""TASK 2 (2026-09-10) — `claude_cli/haiku` as a recognized Lab model.

Haiku 4.5 was enabled through the exact path opus/sonnet already use: one
alias in `ClaudeCliAdapter._CLI_MODELS`, one entry in the policy document's
`authorized_models`. No new provider, no new billing relationship — the same
already-authenticated Claude Code CLI session.

The real-call proof lives in `test_live_haiku_alias_really_answers_as_haiku_4_5`,
marked `live` and therefore skipped by default (see conftest). It was run once
on 2026-09-10 against the real CLI; the provider's own `modelUsage` named
exactly one model, `claude-haiku-4-5-20251001` / canonical `claude-haiku-4-5`.
The other tests here are offline structure/policy checks and must never be
read as evidence that the model answers.
"""
from __future__ import annotations

import pytest

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, RoleName
from core.lab_v1.providers.claude_cli import ClaudeCliAdapter
from core.lab_v1.workforce_policy import ResourceClass, WorkforcePolicy

ROLES = ('CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER')


def _agent(model: str, role: RoleName = RoleName.BUILDER) -> AgentProfile:
    return AgentProfile('agent:' + model, model, 'claude_cli', model, role=role,
                        capabilities=['model.text'])


def _info() -> ProviderInfo:
    return ProviderInfo('claude_cli', 'claude_cli', 'claude_cli', Availability.AVAILABLE,
                        authenticated=True, quota_available=True)


def test_haiku_is_declared_by_the_same_adapter_as_opus_and_sonnet():
    """No second provider: one adapter, three declared models."""
    adapter = ClaudeCliAdapter()
    declared = {item.model_id for item in adapter.declared_models}
    assert declared == {'opus', 'sonnet', 'haiku'}
    assert all(item.provider_id == 'claude_cli' for item in adapter.declared_models)
    # The probe advertises the same list it declares; a model visible in one and
    # not the other is how a model becomes unreachable through the service gate.
    assert 'haiku' in adapter.probe().models


def test_haiku_still_runs_through_the_restricted_text_only_session():
    """Enabling a model must not widen what the Lab can touch on this machine."""
    adapter = ClaudeCliAdapter()
    assert adapter.controlled_text_only is True


def test_policy_authorizes_claude_cli_haiku_as_plan_included():
    decision = WorkforcePolicy({}).authorize(_agent('haiku'), _info(), model_available=True)
    assert decision.allowed
    assert decision.code == 'AUTHORIZED'
    assert decision.resource_class is ResourceClass.PLAN_INCLUDED
    assert (decision.provider_id, decision.model_id) == ('claude_cli', 'haiku')


def test_authorizing_haiku_does_not_bind_it_to_any_role():
    """Provider != Model != Role. Authorization says "may be used", never "is used
    for X". Haiku is unranked, so it loses to every ranked model in every role."""
    policy = WorkforcePolicy({})
    for role in ROLES:
        assert policy.preference_rank('haiku', role) >= policy.preference_rank('sonnet', role)
        assert policy.preference_rank('haiku', role) >= policy.preference_rank('opus', role)


def test_haiku_is_never_auto_selected_over_a_ranked_model():
    """Regression guard for silent promotion: if someone pins haiku into
    role_model_preference, this fails."""
    policy = WorkforcePolicy({})
    for role in ROLES:
        decisions = [
            policy.authorize(_agent(model, RoleName(role)), _info(), model_available=True)
            for model in ('haiku', 'sonnet', 'opus')
        ]
        assert all(item.allowed for item in decisions)
        assert policy.choose_for_role(decisions, role).model_id != 'haiku'


def test_a_mission_that_names_only_haiku_for_a_role_gets_haiku():
    """The flip side: unranked must mean "not preferred", not "unusable".
    An explicit mission assignment still resolves."""
    policy = WorkforcePolicy({})
    for role in ROLES:
        decision = policy.authorize(_agent('haiku', RoleName(role)), _info(), model_available=True)
        assert policy.choose_for_role([decision], role).model_id == 'haiku'


def test_an_undeclared_claude_alias_is_still_refused():
    """Authorizing one more model must not authorize the provider's catalog."""
    decision = WorkforcePolicy({}).authorize(_agent('fable'), _info(), model_available=True)
    assert not decision.allowed and decision.code == 'MODEL_NOT_AUTHORIZED'


@pytest.mark.live
def test_live_haiku_alias_really_answers_as_haiku_4_5():
    """REAL call. Skipped by default; run with ALLOW_LIVE_TESTS=1.

    Asserts the provider itself reports Haiku 4.5 — not that our code asked for
    it. A silent substitution to sonnet/opus would fail here, which is the whole
    point of checking `model_reported` instead of the request.
    """
    result = ClaudeCliAdapter().complete(
        prompt='Reply with exactly one word: ok',
        model='haiku',
        timeout_s=180,
    )
    assert result.ok, f'chamada real falhou: {result.error}'
    assert result.availability is Availability.AVAILABLE
    assert result.model_reported is not None
    assert 'haiku-4-5' in result.model_reported, (
        f'provedor respondeu como {result.model_reported!r}, nao como Haiku 4.5'
    )
