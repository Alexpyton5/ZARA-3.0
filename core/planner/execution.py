"""Execução de Plan — a ÚNICA ponte entre Planner e ToolRouter.

Invariante de segurança: nenhuma função aqui chama subprocess, winreg,
ctypes, shell, eval, import dinâmico, ou qualquer API de hardware
diretamente. Toda ação passa por `core.tool_router.get_tool_router().route()`,
que já aplica capability/risk/permission/audit exatamente como qualquer outra
chamada de tool no sistema hoje — o Planner não ganha nenhum privilégio novo.
"""
from __future__ import annotations

from core.planner.models import Plan, PlanResult, PlanStatus, StepStatus
from core.planner.validation import topological_order


def execute_plan(plan: Plan, tool_router=None) -> PlanResult:
    """Executa um Plan JÁ VALIDADO, na ordem de dependências.

    Propagação de falha (Board 9): se um step falha, todo step que dependa
    dele (direta ou indiretamente) fica BLOCKED e não roda. Steps
    independentes continuam normalmente.

    `tool_router` é injetável para teste (SAFE/SANDBOX); em produção usa
    `core.tool_router.get_tool_router()`.
    """
    if tool_router is None:
        from core.tool_router import get_tool_router

        tool_router = get_tool_router()

    if plan.status not in (PlanStatus.VALIDATED, PlanStatus.RUNNING, PlanStatus.PARTIAL):
        return PlanResult(
            plan_id=plan.id,
            status=PlanStatus.BLOCKED,
            error=f"Plan '{plan.id}' não está VALIDATED (status atual: {plan.status.value}) — recuse-se a executar.",
        )

    plan.status = PlanStatus.RUNNING
    result = PlanResult(plan_id=plan.id, status=PlanStatus.RUNNING)
    blocked_ids: set[str] = set()

    from core.tool_router import ToolRequest

    for step_id in topological_order(plan):
        step = plan.step_by_id(step_id)
        if step is None:
            continue

        if any(dep in blocked_ids for dep in step.depends_on):
            step.status = StepStatus.BLOCKED
            blocked_ids.add(step.id)
            result.skipped_steps.append(step.id)
            continue

        step.status = StepStatus.RUNNING
        tool_result = tool_router.route(ToolRequest(tool_name=step.tool_name, parameters=step.arguments))
        step.result = tool_result
        result.step_results[step.id] = tool_result

        succeeded = bool(getattr(tool_result, "success", False))
        if succeeded:
            step.status = StepStatus.VERIFIED if step.requires_verification else StepStatus.RUNNING
            if step.status != StepStatus.VERIFIED:
                step.status = StepStatus.VERIFIED
            result.completed_steps.append(step.id)
        else:
            step.status = StepStatus.FAILED
            step.error = str(getattr(tool_result, "error", "") or "")
            result.failed_steps.append(step.id)
            blocked_ids.add(step.id)

    if result.failed_steps and result.completed_steps:
        plan.status = PlanStatus.PARTIAL
    elif result.failed_steps:
        plan.status = PlanStatus.FAILED
    elif result.skipped_steps:
        plan.status = PlanStatus.PARTIAL
    else:
        plan.status = PlanStatus.COMPLETED

    result.status = plan.status
    return result
