"""SAFE: validação determinística de Plan. Sem hardware, sem IO, sem rede."""
import pytest

from core.planner.models import Plan, PlanStep
from core.planner.validation import PlanValidationError, topological_order, validate_plan

KNOWN = frozenset({"tool_a", "tool_b", "tool_c"})


def test_valid_single_step_plan_passes():
    plan = Plan(goal="g", steps=[PlanStep(tool_name="tool_a", id="s1")])
    validate_plan(plan, known_tool_names=KNOWN)  # não deve levantar


def test_empty_plan_rejected():
    plan = Plan(goal="g", steps=[])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("EMPTY_PLAN" in r for r in exc.value.reasons)


def test_duplicate_step_ids_rejected():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="dup"),
        PlanStep(tool_name="tool_b", id="dup"),
    ])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("DUPLICATE_STEP_ID" in r for r in exc.value.reasons)


def test_unknown_tool_rejected():
    plan = Plan(goal="g", steps=[PlanStep(tool_name="does_not_exist", id="s1")])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("UNKNOWN_TOOL" in r for r in exc.value.reasons)


def test_blocked_tool_rejected():
    plan = Plan(goal="g", steps=[PlanStep(tool_name="tool_a", id="s1")])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN, blocked_tool_names={"tool_a"})
    assert any("BLOCKED_TOOL" in r for r in exc.value.reasons)


def test_missing_dependency_rejected():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="s1", depends_on=["ghost"]),
    ])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("MISSING_DEPENDENCY" in r for r in exc.value.reasons)


def test_self_dependency_rejected():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="s1", depends_on=["s1"]),
    ])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("SELF_DEPENDENCY" in r for r in exc.value.reasons)


def test_dependency_cycle_rejected():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="s1", depends_on=["s2"]),
        PlanStep(tool_name="tool_b", id="s2", depends_on=["s1"]),
    ])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("DEPENDENCY_CYCLE" in r for r in exc.value.reasons)


def test_invalid_arguments_type_rejected():
    step = PlanStep(tool_name="tool_a", id="s1")
    step.arguments = ["not", "a", "dict"]  # type: ignore[assignment]
    plan = Plan(goal="g", steps=[step])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert any("INVALID_ARGUMENTS" in r for r in exc.value.reasons)


def test_multiple_reasons_collected_not_just_first():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="does_not_exist", id="s1", depends_on=["ghost"]),
    ])
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan, known_tool_names=KNOWN)
    assert len(exc.value.reasons) >= 2


def test_topological_order_respects_dependencies():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="s1"),
        PlanStep(tool_name="tool_b", id="s2", depends_on=["s1"]),
        PlanStep(tool_name="tool_c", id="s3", depends_on=["s2"]),
    ])
    order = topological_order(plan)
    assert order.index("s1") < order.index("s2") < order.index("s3")


def test_topological_order_independent_steps_both_present():
    plan = Plan(goal="g", steps=[
        PlanStep(tool_name="tool_a", id="s1"),
        PlanStep(tool_name="tool_b", id="s2"),
    ])
    order = topological_order(plan)
    assert set(order) == {"s1", "s2"}
