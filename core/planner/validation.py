"""Validação determinística de Plan — sem modelo, sem IA, sem execução.

Um Plan inválido nunca deve chegar ao ToolRouter em silêncio. Toda falha de
validação levanta `PlanValidationError` com uma lista de motivos —
`validate_plan` nunca retorna "meio válido".
"""
from __future__ import annotations

from core.planner.models import Plan


class PlanValidationError(Exception):
    """Um Plan falhou validação determinística. `.reasons` lista cada motivo."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def validate_plan(
    plan: Plan,
    known_tool_names: frozenset[str] | set[str],
    blocked_tool_names: frozenset[str] | set[str] = frozenset(),
) -> None:
    """Valida um Plan. Levanta PlanValidationError se algo estiver errado.

    Não valida permissão/risco de execução (isso é responsabilidade do
    ToolRouter no momento de rodar, com o estado real do Supercérebro) — aqui
    só a FORMA do plano é validada: isso é o que pode e deve ser checado sem
    depender de estado de runtime.
    """
    reasons: list[str] = []

    if not plan.steps:
        reasons.append("EMPTY_PLAN: plano sem nenhum step")

    seen_ids: set[str] = set()
    for step in plan.steps:
        if not step.id:
            reasons.append("MISSING_STEP_ID: step sem id")
            continue
        if step.id in seen_ids:
            reasons.append(f"DUPLICATE_STEP_ID: '{step.id}' aparece mais de uma vez")
        seen_ids.add(step.id)

        if not step.tool_name:
            reasons.append(f"MISSING_TOOL_NAME: step '{step.id}' sem tool_name")
        elif step.tool_name in blocked_tool_names:
            reasons.append(f"BLOCKED_TOOL: step '{step.id}' usa tool bloqueada '{step.tool_name}'")
        elif step.tool_name not in known_tool_names:
            reasons.append(f"UNKNOWN_TOOL: step '{step.id}' referencia tool inexistente '{step.tool_name}'")

        if not isinstance(step.arguments, dict):
            reasons.append(f"INVALID_ARGUMENTS: step '{step.id}' tem arguments que não é um dict")

    for step in plan.steps:
        for dep_id in step.depends_on:
            if dep_id == step.id:
                reasons.append(f"SELF_DEPENDENCY: step '{step.id}' depende de si mesmo")
            elif dep_id not in seen_ids:
                reasons.append(f"MISSING_DEPENDENCY: step '{step.id}' depende de '{dep_id}', que não existe no plano")

    cycle = _find_cycle(plan)
    if cycle:
        reasons.append(f"DEPENDENCY_CYCLE: {' -> '.join(cycle)}")

    if reasons:
        raise PlanValidationError(reasons)


def _find_cycle(plan: Plan) -> list[str] | None:
    """DFS clássico com marcação de cor (branco/cinza/preto) para achar 1 ciclo."""
    graph = {step.id: list(step.depends_on) for step in plan.steps}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node not in graph:
            return None
        color[node] = GRAY
        path.append(node)
        for dep in graph[node]:
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for node in graph:
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def topological_order(plan: Plan) -> list[str]:
    """Ordem de execução respeitando dependências. Assume plano já validado
    (sem ciclo). Usado por `execution.py` — não chama validate_plan de novo."""
    graph = {step.id: list(step.depends_on) for step in plan.steps}
    order: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        order.append(node)

    for step_id in graph:
        visit(step_id)
    return order
