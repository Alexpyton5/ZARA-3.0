"""SAFE: construção e validação das receitas multi-step do Planner.

Nenhum teste aqui toca rede, browser real, ou tela real — todos usam um
ToolRouter FAKE. A prova de execução real (browser de verdade) é manual,
documentada em PLANNER_REAL_USE_CASES.md, não faz parte da suíte
automatizada (rede/browser real = LIVE, proibido em pytest por padrão).
"""
import pytest

from core.planner.execution import execute_plan
from core.planner.models import PlannerRequest, PlanningContext, PlanStatus
from core.planner.planner import RulePlanner
from core.planner.recipes import (
    browser_search_and_extract,
    browser_search_and_screenshot,
    list_folder_and_summarize_file,
    screenshot_and_ocr,
)

KNOWN_TOOLS = frozenset({
    "browser_navigate", "browser_screenshot", "browser_extract",
    "vision_screenshot", "vision_ocr",
    "files_list", "files_text_summary",
})


class _FakeSuccess:
    success = True
    error = ""


class _FakeRouter:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def route(self, request):
        self.calls.append((request.tool_name, dict(request.parameters)))
        return _FakeSuccess()


def _plan_and_run(explicit_steps):
    ctx = PlanningContext(known_tool_names=KNOWN_TOOLS)
    resp = RulePlanner().plan(PlannerRequest(goal="teste", context=ctx, explicit_steps=explicit_steps))
    assert resp.accepted, resp.rejection_reason
    router = _FakeRouter()
    result = execute_plan(resp.plan, tool_router=router)
    return result, router


def test_browser_search_and_screenshot_builds_valid_two_step_plan():
    steps = browser_search_and_screenshot("gatos fofos")
    result, router = _plan_and_run(steps)
    assert result.status == PlanStatus.COMPLETED
    assert router.calls[0][0] == "browser_navigate"
    assert "gatos" in router.calls[0][1]["url"] or "gatos+fofos" in router.calls[0][1]["url"]
    assert router.calls[1][0] == "browser_screenshot"


def test_browser_search_and_screenshot_rejects_empty_query():
    with pytest.raises(ValueError):
        browser_search_and_screenshot("")


def test_browser_search_and_screenshot_passes_explicit_path():
    steps = browser_search_and_screenshot("teste", screenshot_path="/tmp/x.png")
    screenshot_step = next(s for s in steps if s["id"] == "screenshot")
    assert screenshot_step["arguments"]["path"] == "/tmp/x.png"


def test_browser_search_and_extract_builds_valid_plan():
    steps = browser_search_and_extract("python", selectors={"title": "h3"})
    result, router = _plan_and_run(steps)
    assert result.status == PlanStatus.COMPLETED
    assert router.calls[1] == ("browser_extract", {"selectors": {"title": "h3"}})


def test_browser_search_and_extract_rejects_empty_selectors():
    with pytest.raises(ValueError):
        browser_search_and_extract("python", selectors={})


def test_screenshot_and_ocr_uses_same_path_in_both_steps():
    steps = screenshot_and_ocr("/tmp/capture.png")
    result, router = _plan_and_run(steps)
    assert result.status == PlanStatus.COMPLETED
    assert router.calls[0] == ("vision_screenshot", {"path": "/tmp/capture.png"})
    assert router.calls[1][0] == "vision_ocr"
    assert router.calls[1][1]["image_path"] == "/tmp/capture.png"


def test_screenshot_and_ocr_rejects_empty_path():
    with pytest.raises(ValueError):
        screenshot_and_ocr("")


def test_list_folder_and_summarize_file_builds_valid_plan():
    steps = list_folder_and_summarize_file("C:/some/folder", "C:/some/folder/README.md")
    result, router = _plan_and_run(steps)
    assert result.status == PlanStatus.COMPLETED
    assert router.calls[0] == ("files_list", {"path": "C:/some/folder"})
    assert router.calls[1] == ("files_text_summary", {"path": "C:/some/folder/README.md"})


def test_list_folder_and_summarize_file_rejects_missing_args():
    with pytest.raises(ValueError):
        list_folder_and_summarize_file("", "x")
    with pytest.raises(ValueError):
        list_folder_and_summarize_file("x", "")


def test_all_recipes_second_step_depends_on_first():
    """Garantia estrutural: se o primeiro step falhar, o segundo nunca despacha."""
    for steps in (
        browser_search_and_screenshot("q"),
        browser_search_and_extract("q", {"a": "b"}),
        screenshot_and_ocr("/tmp/x.png"),
        list_folder_and_summarize_file("a", "a/b"),
    ):
        assert steps[1]["depends_on"] == [steps[0]["id"]]
