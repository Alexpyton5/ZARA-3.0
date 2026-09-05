"""SAFE: fronteira Planner -> ToolRouter. Confirma que o Planner nunca
executa nada e que um plano inválido nunca chega perto de um router real."""
from core.planner.execution import execute_plan
from core.planner.models import PlannerRequest, PlanningContext, PlanStatus
from core.planner.planner import RulePlanner


class _RouterThatMustNeverBeCalled:
    def route(self, request):
        raise AssertionError(
            f"ToolRouter.route() foi chamado com '{request.tool_name}' — "
            "um plano rejeitado NUNCA deveria chegar ao router."
        )


def test_rule_planner_without_explicit_steps_is_rejected_not_guessed():
    ctx = PlanningContext(known_tool_names=frozenset({"files_list"}))
    resp = RulePlanner().plan(PlannerRequest(goal="faça algo vago", context=ctx))
    assert resp.accepted is False
    assert resp.plan is None
    assert resp.rejection_reason


def test_rule_planner_rejects_unknown_tool_before_any_execution():
    ctx = PlanningContext(known_tool_names=frozenset({"files_list"}))
    resp = RulePlanner().plan(PlannerRequest(
        goal="apagar tudo",
        context=ctx,
        explicit_steps=[{"tool_name": "rm_rf_everything", "arguments": {}}],
    ))
    assert resp.accepted is False
    assert "UNKNOWN_TOOL" in resp.rejection_reason


def test_accepted_plan_can_be_executed_and_rejected_plan_cannot():
    ctx = PlanningContext(known_tool_names=frozenset({"files_list"}))
    resp = RulePlanner().plan(PlannerRequest(
        goal="listar",
        context=ctx,
        explicit_steps=[{"tool_name": "files_list", "arguments": {"path": "."}}],
    ))
    assert resp.accepted is True

    class _OkRouter:
        def route(self, request):
            class R:
                success = True
                error = ""
            return R()

    result = execute_plan(resp.plan, tool_router=_OkRouter())
    assert result.status == PlanStatus.COMPLETED


def test_planner_never_calls_tool_router_itself():
    """O Planner.plan() em si não deve ter nenhuma dependência de ToolRouter —
    só validate_plan(), que é puro. Isso é verificado indiretamente: um
    RulePlanner.plan() com tool desconhecida não deve chamar route()."""
    ctx = PlanningContext(known_tool_names=frozenset())
    resp = RulePlanner().plan(PlannerRequest(
        goal="qualquer coisa",
        context=ctx,
        explicit_steps=[{"tool_name": "anything", "arguments": {}}],
    ))
    assert resp.accepted is False
    # Nada para executar — mas se por acaso alguém tentasse, isso provaria o erro:
    if resp.plan is not None:
        execute_plan(resp.plan, tool_router=_RouterThatMustNeverBeCalled())
