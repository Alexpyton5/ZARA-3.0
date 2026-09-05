"""SAFE: execução de Plan com ToolRouter FAKE — nunca toca hardware real.

Cada teste injeta seu próprio router falso via `execute_plan(plan, tool_router=...)`.
Nenhum teste aqui chama `core.tool_router.get_tool_router()` de verdade.
"""
from core.planner.execution import execute_plan
from core.planner.models import Plan, PlanStatus, PlanStep, StepStatus


class _FakeResult:
    def __init__(self, success: bool, error: str = ""):
        self.success = success
        self.error = error


class _FakeRouter:
    """Router falso: sucesso, exceto para tool_names na lista `fail_on`."""

    def __init__(self, fail_on: set[str] | None = None):
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    def route(self, request):
        self.calls.append(request.tool_name)
        if request.tool_name in self.fail_on:
            return _FakeResult(False, error=f"{request.tool_name} falhou de propósito")
        return _FakeResult(True)


def _validated(plan: Plan) -> Plan:
    plan.status = PlanStatus.VALIDATED
    return plan


def test_single_successful_step_completes():
    plan = _validated(Plan(goal="g", steps=[PlanStep(tool_name="ok", id="s1")]))
    router = _FakeRouter()
    result = execute_plan(plan, tool_router=router)
    assert result.status == PlanStatus.COMPLETED
    assert result.completed_steps == ["s1"]
    assert router.calls == ["ok"]


def test_unvalidated_plan_refuses_to_run():
    plan = Plan(goal="g", steps=[PlanStep(tool_name="ok", id="s1")])  # status=CREATED
    router = _FakeRouter()
    result = execute_plan(plan, tool_router=router)
    assert result.status == PlanStatus.BLOCKED
    assert router.calls == []  # nunca chamou o router


def test_failed_step_marks_dependents_blocked_not_run():
    plan = _validated(Plan(goal="g", steps=[
        PlanStep(tool_name="a", id="s1"),
        PlanStep(tool_name="fails", id="s2", depends_on=["s1"]),
        PlanStep(tool_name="never_reached", id="s3", depends_on=["s2"]),
    ]))
    router = _FakeRouter(fail_on={"fails"})
    result = execute_plan(plan, tool_router=router)
    assert result.status == PlanStatus.PARTIAL
    assert result.completed_steps == ["s1"]
    assert result.failed_steps == ["s2"]
    assert result.skipped_steps == ["s3"]
    assert "never_reached" not in router.calls  # nunca despachado


def test_independent_step_runs_even_if_sibling_fails():
    plan = _validated(Plan(goal="g", steps=[
        PlanStep(tool_name="fails", id="s1"),
        PlanStep(tool_name="independent", id="s2"),
    ]))
    router = _FakeRouter(fail_on={"fails"})
    result = execute_plan(plan, tool_router=router)
    assert "s2" in result.completed_steps
    assert "independent" in router.calls


def test_all_steps_fail_plan_status_is_failed_not_partial():
    plan = _validated(Plan(goal="g", steps=[PlanStep(tool_name="fails", id="s1")]))
    router = _FakeRouter(fail_on={"fails"})
    result = execute_plan(plan, tool_router=router)
    assert result.status == PlanStatus.FAILED
    assert result.completed_steps == []


def test_step_status_updated_on_plan_object():
    plan = _validated(Plan(goal="g", steps=[
        PlanStep(tool_name="ok", id="s1"),
        PlanStep(tool_name="fails", id="s2"),
    ]))
    router = _FakeRouter(fail_on={"fails"})
    execute_plan(plan, tool_router=router)
    assert plan.step_by_id("s1").status == StepStatus.VERIFIED
    assert plan.step_by_id("s2").status == StepStatus.FAILED
    assert plan.step_by_id("s2").error
