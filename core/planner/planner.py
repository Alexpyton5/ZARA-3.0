"""Planner — produz Plan a partir de PlannerRequest. Nunca executa.

`plan()` é puro em relação a hardware/rede: só lê `known_tool_names` do
contexto e monta objetos de dados. Chamar `plan()` duas vezes com a mesma
entrada não tem efeito colateral algum.
"""
from __future__ import annotations

from core.planner.models import (
    Plan,
    PlannerRequest,
    PlannerResponse,
    PlanStep,
    _new_id,
)
from core.planner.validation import PlanValidationError, validate_plan


class Planner:
    """Interface base. `RulePlanner` é a única implementação nesta fase —
    `LLMPlanner`/`HybridPlanner` ficam para quando houver output estruturado
    de modelo confiável o suficiente para virar Plan (ver Board 19 do
    NIGHT_MISSION_04, não implementado nesta sessão)."""

    def plan(self, request: PlannerRequest) -> PlannerResponse:
        raise NotImplementedError


class RulePlanner(Planner):
    """Planner determinístico, sem modelo de IA.

    Regra KISS (Board 5 do NIGHT_MISSION_04): se o chamador já forneceu os
    passos (`explicit_steps` — o caso comum é um intent simples resolvido
    fora daqui, ex. "abra o bloco de notas" -> 1 tool conhecida), o Planner
    só valida e empacota. Não existe hoje um classificador de linguagem
    natural aqui dentro que invente múltiplos passos sozinho — isso é
    trabalho de uma fase futura (LLMPlanner), não desta foundation.
    """

    def plan(self, request: PlannerRequest) -> PlannerResponse:
        if not request.explicit_steps:
            return PlannerResponse(
                plan=None,
                accepted=False,
                rejection_reason=(
                    "RulePlanner precisa de explicit_steps nesta fase — não há "
                    "raciocínio de linguagem natural implementado ainda "
                    "(ver Board 19, não feito nesta missão)."
                ),
            )

        steps = [
            PlanStep(
                tool_name=str(raw.get("tool_name", "")),
                arguments=dict(raw.get("arguments") or {}),
                description=str(raw.get("description", "")),
                depends_on=list(raw.get("depends_on") or []),
                risk_hint=raw.get("risk_hint"),
                requires_verification=bool(raw.get("requires_verification", True)),
                id=str(raw["id"]) if raw.get("id") else _new_id("step"),
            )
            for raw in request.explicit_steps
        ]

        plan = Plan(goal=request.goal, steps=steps)

        try:
            validate_plan(plan, known_tool_names=request.context.known_tool_names)
        except PlanValidationError as exc:
            return PlannerResponse(
                plan=None,
                accepted=False,
                rejection_reason="; ".join(exc.reasons),
            )

        from core.planner.models import PlanStatus

        plan.status = PlanStatus.VALIDATED
        return PlannerResponse(plan=plan, accepted=True)
