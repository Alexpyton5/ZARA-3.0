from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.perception.vision_fallback import (
    ActionPlan,
    DecisionStatus,
    ExecutionOutcome,
    IntentRequest,
    OutcomeStatus,
    Risk,
    Route,
    VisionFallbackRouter,
)


@dataclass
class FakeAdapter:
    plan: ActionPlan | None
    outcome: ExecutionOutcome = ExecutionOutcome(OutcomeStatus.SUCCESS, "ok")
    resolve_calls: int = 0
    executed: list[ActionPlan] = field(default_factory=list)
    resolve_error: bool = False
    execute_error: bool = False

    def resolve(self, request: IntentRequest) -> ActionPlan | None:
        self.resolve_calls += 1
        if self.resolve_error:
            raise RuntimeError("boom")
        return self.plan

    def execute(self, plan: ActionPlan) -> ExecutionOutcome:
        self.executed.append(plan)
        if self.execute_error:
            raise RuntimeError("boom")
        return self.outcome


@dataclass
class FakeVerifier:
    approved: bool = True
    calls: int = 0

    def verify(self, plan: ActionPlan, proof: object) -> bool:
        self.calls += 1
        return self.approved


def _router(native: FakeAdapter, perception: FakeAdapter, verifier=None) -> VisionFallbackRouter:
    return VisionFallbackRouter(native=native, perception=perception, confirmation_verifier=verifier)


def test_native_action_is_preferred_and_perception_is_not_even_resolved() -> None:
    native = FakeAdapter(ActionPlan("set_volume", 0.99))
    perception = FakeAdapter(ActionPlan("ocr_click", 0.99))

    decision = _router(native, perception).run(IntentRequest("abaixar volume"))

    assert decision.status is DecisionStatus.COMPLETED
    assert decision.route is Route.NATIVE
    assert len(native.executed) == 1
    assert perception.resolve_calls == 0


def test_no_native_plan_uses_perception() -> None:
    native = FakeAdapter(None)
    perception = FakeAdapter(ActionPlan("ocr_read", 0.95))

    decision = _router(native, perception).run(IntentRequest("ler janela"))

    assert decision.status is DecisionStatus.COMPLETED
    assert decision.route is Route.PERCEPTION


def test_low_confidence_native_is_not_executed_and_can_fall_back() -> None:
    native = FakeAdapter(ActionPlan("uncertain_native", 0.2))
    perception = FakeAdapter(ActionPlan("ocr_read", 0.95))

    decision = _router(native, perception).run(IntentRequest("ler janela"))

    assert native.executed == []
    assert decision.route is Route.PERCEPTION


def test_explicit_native_unavailable_can_fall_back() -> None:
    native = FakeAdapter(
        ActionPlan("open_legacy", 0.95),
        ExecutionOutcome(OutcomeStatus.UNAVAILABLE, "adapter nao suporta"),
    )
    perception = FakeAdapter(ActionPlan("ocr_click", 0.95))

    decision = _router(native, perception).run(IntentRequest("abrir legado"))

    assert len(native.executed) == 1
    assert len(perception.executed) == 1
    assert decision.route is Route.PERCEPTION


@pytest.mark.parametrize("status", [OutcomeStatus.FAILED, OutcomeStatus.UNVERIFIED])
def test_native_failure_never_triggers_possible_duplicate_effect(status: OutcomeStatus) -> None:
    native = FakeAdapter(ActionPlan("maybe_ran", 0.95), ExecutionOutcome(status, "incerto"))
    perception = FakeAdapter(ActionPlan("ocr_click", 0.95))

    decision = _router(native, perception).run(IntentRequest("executar"))

    assert decision.route is Route.NATIVE
    assert decision.status is DecisionStatus.FAILED
    assert perception.resolve_calls == 0


def test_low_perception_confidence_blocks_execution() -> None:
    perception = FakeAdapter(ActionPlan("ocr_click", 0.4))

    decision = _router(FakeAdapter(None), perception).run(IntentRequest("clicar"))

    assert decision.status is DecisionStatus.BLOCKED
    assert decision.reason == "insufficient_perception_confidence"
    assert perception.executed == []


def test_risky_plan_requires_external_verified_proof() -> None:
    native = FakeAdapter(ActionPlan("delete", 0.99, risk=Risk.HIGH))

    decision = _router(native, FakeAdapter(None)).run(IntentRequest("apagar"))

    assert decision.status is DecisionStatus.BLOCKED
    assert decision.confirmation_required is True
    assert native.executed == []


def test_minimum_request_risk_cannot_be_downgraded_by_adapter() -> None:
    native = FakeAdapter(ActionPlan("terminal", 0.99, risk=Risk.LOW))

    decision = _router(native, FakeAdapter(None)).run(
        IntentRequest("executar", minimum_risk=Risk.HIGH)
    )

    assert decision.status is DecisionStatus.BLOCKED
    assert native.executed == []


def test_valid_external_confirmation_allows_risky_plan() -> None:
    verifier = FakeVerifier(approved=True)
    native = FakeAdapter(ActionPlan("delete", 0.99, risk=Risk.HIGH))

    decision = _router(native, FakeAdapter(None), verifier).run(
        IntentRequest("apagar"), confirmation_proof=object()
    )

    assert decision.status is DecisionStatus.COMPLETED
    assert verifier.calls == 1
    assert len(native.executed) == 1


def test_rejected_confirmation_fails_closed() -> None:
    verifier = FakeVerifier(approved=False)
    perception = FakeAdapter(ActionPlan("ocr_click_delete", 0.99, risk=Risk.MEDIUM))

    decision = _router(FakeAdapter(None), perception, verifier).run(
        IntentRequest("apagar"), confirmation_proof=object()
    )

    assert decision.status is DecisionStatus.BLOCKED
    assert perception.executed == []


def test_adapter_exception_is_explicit_and_does_not_trigger_fallback() -> None:
    native = FakeAdapter(ActionPlan("native", 0.99), execute_error=True)
    perception = FakeAdapter(ActionPlan("ocr", 0.99))

    decision = _router(native, perception).run(IntentRequest("acao"))

    assert decision.status is DecisionStatus.FAILED
    assert decision.reason == "adapter_execute_error"
    assert perception.resolve_calls == 0


def test_no_adequate_action_is_explicit() -> None:
    decision = _router(FakeAdapter(None), FakeAdapter(None)).run(IntentRequest("desconhecido"))
    assert decision.status is DecisionStatus.NO_ACTION
    assert decision.route is Route.NONE


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_is_rejected(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        ActionPlan("invalid", confidence)
