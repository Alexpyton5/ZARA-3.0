"""Roteador seguro: acao nativa primeiro, percepcao visual como ultimo recurso.

Todos os adaptadores sao injetados. Este modulo nao captura tela, nao acessa a
rede e nao conhece o registro global de acoes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Route(StrEnum):
    NATIVE = "native"
    PERCEPTION = "perception"
    NONE = "none"


class OutcomeStatus(StrEnum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class DecisionStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NO_ACTION = "no_action"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IntentRequest:
    intent: str
    minimum_risk: Risk = Risk.LOW

    def __post_init__(self) -> None:
        if not isinstance(self.intent, str) or not self.intent.strip():
            raise ValueError("intent nao pode ser vazio")
        if not isinstance(self.minimum_risk, Risk):
            raise ValueError("minimum_risk precisa ser Risk")


@dataclass(frozen=True, slots=True)
class ActionPlan:
    action: str
    confidence: float
    risk: Risk = Risk.LOW
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action.strip():
            raise ValueError("action nao pode ser vazia")
        if not isinstance(self.risk, Risk):
            raise ValueError("risk precisa ser Risk")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence precisa ser numero")
        if not math.isfinite(float(self.confidence)) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence precisa estar entre 0 e 1")


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    status: OutcomeStatus
    observed: str = ""


@dataclass(frozen=True, slots=True)
class FallbackDecision:
    status: DecisionStatus
    route: Route
    reason: str
    plan: ActionPlan | None = None
    outcome: ExecutionOutcome | None = None
    confirmation_required: bool = False


class ActionAdapter(Protocol):
    def resolve(self, request: IntentRequest) -> ActionPlan | None: ...

    def execute(self, plan: ActionPlan) -> ExecutionOutcome: ...


class ConfirmationVerifier(Protocol):
    def verify(self, plan: ActionPlan, proof: object) -> bool: ...


_RISK_LEVEL = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2}


class VisionFallbackRouter:
    def __init__(
        self,
        *,
        native: ActionAdapter,
        perception: ActionAdapter,
        confirmation_verifier: ConfirmationVerifier | None = None,
        native_min_confidence: float = 0.75,
        perception_min_confidence: float = 0.85,
    ) -> None:
        self._validate_threshold(native_min_confidence, "native_min_confidence")
        self._validate_threshold(perception_min_confidence, "perception_min_confidence")
        self._native = native
        self._perception = perception
        self._confirmation_verifier = confirmation_verifier
        self._native_min_confidence = native_min_confidence
        self._perception_min_confidence = perception_min_confidence

    @staticmethod
    def _validate_threshold(value: float, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} precisa ser numero")
        if not math.isfinite(float(value)) or not 0 <= value <= 1:
            raise ValueError(f"{name} precisa estar entre 0 e 1")

    @staticmethod
    def _effective_risk(request: IntentRequest, plan: ActionPlan) -> Risk:
        return max((request.minimum_risk, plan.risk), key=_RISK_LEVEL.__getitem__)

    def _authorization_failure(
        self,
        request: IntentRequest,
        plan: ActionPlan,
        proof: object | None,
        route: Route,
    ) -> FallbackDecision | None:
        if self._effective_risk(request, plan) is Risk.LOW:
            return None
        if proof is None or self._confirmation_verifier is None:
            return FallbackDecision(
                status=DecisionStatus.BLOCKED,
                route=route,
                reason="confirmation_required",
                plan=plan,
                confirmation_required=True,
            )
        try:
            approved = self._confirmation_verifier.verify(plan, proof)
        except Exception:
            approved = False
        if approved is not True:
            return FallbackDecision(
                status=DecisionStatus.BLOCKED,
                route=route,
                reason="confirmation_rejected",
                plan=plan,
                confirmation_required=True,
            )
        return None

    @staticmethod
    def _adapter_error(route: Route, reason: str) -> FallbackDecision:
        return FallbackDecision(status=DecisionStatus.FAILED, route=route, reason=reason)

    def _execute(
        self,
        *,
        request: IntentRequest,
        plan: ActionPlan,
        proof: object | None,
        route: Route,
        adapter: ActionAdapter,
    ) -> FallbackDecision:
        authorization_failure = self._authorization_failure(request, plan, proof, route)
        if authorization_failure is not None:
            return authorization_failure
        try:
            outcome = adapter.execute(plan)
        except Exception:
            return self._adapter_error(route, "adapter_execute_error")
        if not isinstance(outcome, ExecutionOutcome):
            return self._adapter_error(route, "invalid_adapter_outcome")
        status = DecisionStatus.COMPLETED if outcome.status is OutcomeStatus.SUCCESS else DecisionStatus.FAILED
        return FallbackDecision(
            status=status,
            route=route,
            reason=f"{route.value}_{outcome.status.value}",
            plan=plan,
            outcome=outcome,
        )

    def run(self, request: IntentRequest, *, confirmation_proof: object | None = None) -> FallbackDecision:
        """Executa no maximo uma rota com potencial de efeito por chamada.

        Uma falha nativa comum ou resultado nao verificado NAO dispara visao,
        evitando duplicar uma acao que talvez ja tenha acontecido. A visao so
        entra quando nao existe plano nativo adequado ou o adaptador declara
        explicitamente ``UNAVAILABLE``.
        """

        try:
            native_plan = self._native.resolve(request)
        except Exception:
            return self._adapter_error(Route.NATIVE, "native_resolve_error")

        if native_plan is not None:
            if not isinstance(native_plan, ActionPlan):
                return self._adapter_error(Route.NATIVE, "invalid_native_plan")
            if native_plan.confidence >= self._native_min_confidence:
                native_decision = self._execute(
                    request=request,
                    plan=native_plan,
                    proof=confirmation_proof,
                    route=Route.NATIVE,
                    adapter=self._native,
                )
                if (
                    native_decision.outcome is None
                    or native_decision.outcome.status is not OutcomeStatus.UNAVAILABLE
                ):
                    return native_decision

        try:
            perception_plan = self._perception.resolve(request)
        except Exception:
            return self._adapter_error(Route.PERCEPTION, "perception_resolve_error")
        if perception_plan is None:
            return FallbackDecision(
                status=DecisionStatus.NO_ACTION,
                route=Route.NONE,
                reason="no_adequate_action",
            )
        if not isinstance(perception_plan, ActionPlan):
            return self._adapter_error(Route.PERCEPTION, "invalid_perception_plan")
        if perception_plan.confidence < self._perception_min_confidence:
            return FallbackDecision(
                status=DecisionStatus.BLOCKED,
                route=Route.PERCEPTION,
                reason="insufficient_perception_confidence",
                plan=perception_plan,
            )
        return self._execute(
            request=request,
            plan=perception_plan,
            proof=confirmation_proof,
            route=Route.PERCEPTION,
            adapter=self._perception,
        )
