"""SAFE: modelo de dados puro do Planner. Sem hardware, sem IO, sem rede."""
from core.planner.models import (
    Plan,
    PlannerRequest,
    PlanningContext,
    PlanStatus,
    PlanStep,
    StepStatus,
)


def test_plan_step_defaults():
    step = PlanStep(tool_name="files_list")
    assert step.status == StepStatus.PENDING
    assert step.depends_on == []
    assert step.requires_verification is True
    assert step.id.startswith("step_")


def test_plan_defaults_and_lookup():
    step = PlanStep(tool_name="files_list", id="s1")
    plan = Plan(goal="teste", steps=[step])
    assert plan.status == PlanStatus.CREATED
    assert plan.step_by_id("s1") is step
    assert plan.step_by_id("missing") is None


def test_plan_to_dict_is_json_safe():
    plan = Plan(goal="teste", steps=[PlanStep(tool_name="files_list", id="s1")])
    d = plan.to_dict()
    assert d["goal"] == "teste"
    assert d["status"] == "CREATED"
    assert d["steps"][0]["tool_name"] == "files_list"
    assert isinstance(d["created_at"], str)


def test_planning_context_defaults_closed():
    ctx = PlanningContext()
    assert ctx.pc_control_allowed is False
    assert ctx.medium_risk_open is False
    assert ctx.known_tool_names == frozenset()


def test_planner_request_explicit_steps_optional():
    req = PlannerRequest(goal="teste")
    assert req.explicit_steps is None
    assert isinstance(req.context, PlanningContext)
