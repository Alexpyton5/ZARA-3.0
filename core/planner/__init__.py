"""Planner foundation — turns a goal into a validated, tool-bound Plan.

O Planner NUNCA executa nada diretamente. Ele produz um `Plan` (dados puros);
quem executa é sempre `core.planner.execution.execute_plan`, que só fala com
`core.tool_router.ToolRouter` — o mesmo caminho de Permission/Execution/
Verification que qualquer outra chamada de tool já usa hoje. Não existe
atalho de shell, Windows API ou import dinâmico aqui.
"""
from __future__ import annotations

from core.planner.execution import execute_plan
from core.planner.models import (
    Plan,
    PlannerRequest,
    PlannerResponse,
    PlanningContext,
    PlanResult,
    PlanStatus,
    PlanStep,
    StepStatus,
)
from core.planner.planner import Planner, RulePlanner
from core.planner.validation import PlanValidationError, validate_plan

__all__ = [
    "Plan",
    "PlanStep",
    "PlanStatus",
    "StepStatus",
    "PlanResult",
    "PlanningContext",
    "PlannerRequest",
    "PlannerResponse",
    "Planner",
    "RulePlanner",
    "validate_plan",
    "PlanValidationError",
    "execute_plan",
]
