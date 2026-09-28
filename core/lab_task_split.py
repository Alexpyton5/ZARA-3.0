"""Divisao de tarefa entre assentos do Lab (GIGANTE 2 "LAB VIVO", Fase B).

Logica pura: nenhum modelo, nenhuma rede, nenhum custo.

Uma Task e' o trabalho que a CEO passou para alguem. O split divide uma
tarefa-mae em filhas limitadas (bounded) para assentos diferentes, para que
dois assentos provem que trabalharam na mesma missao em paralelo sem queimar
a cota do Alex para sempre.

Regras (todas aplicadas, todas testadas):
- So' tarefa-mae ASSIGNED ou RUNNING pode ser dividida.
- Toda filha e' limitada: budget_usd e max_turns explicitos. A soma dos
  budgets das filhas nunca passa do budget da mae.
- Filhas herdam o session_id da mae (mesma missao) e registram quem dividiu
  (created_by_agent_id = quem fez o split).
- Uma filha so' e' concluida pelo proprio responsavel (assigned_agent_id).
- A mae so' COMPLETA quando TODAS as filhas COMPLETARAM, com o resultado
  agregado; QUALQUER filha FAILED derruba a mae com o motivo.
- Journal com relogio injetavel: tudo auditavel.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.lab_v1.domain import Task, TaskState


class TaskSplitError(ValueError):
    """Regra do protocolo de divisao violada."""


MAX_CHILDREN = 8


@dataclass
class SplitPart:
    """Uma fatia da tarefa-mae, para um assento especifico."""

    title: str
    instruction: str
    acceptance: str
    assigned_agent_id: str
    budget_usd: float
    max_turns: int = 1


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def split_task(
    parent: Task,
    parts: List[SplitPart],
    splitter_agent_id: str,
    journal: Optional[List[Dict[str, Any]]] = None,
    clock: Callable[[], float] = time.time,
) -> List[Task]:
    """Divide a tarefa-mae em filhas limitadas, uma por parte.

    Levanta TaskSplitError se qualquer regra for violada. Nao mexe na mae.
    """
    if parent.state not in (TaskState.ASSIGNED, TaskState.RUNNING):
        raise TaskSplitError(
            f"so tarefa ASSIGNED ou RUNNING pode ser dividida (mae esta {parent.state.value})"
        )
    if not parts:
        raise TaskSplitError("divisao precisa de pelo menos 1 parte")
    if len(parts) > MAX_CHILDREN:
        raise TaskSplitError(f"maximo de {MAX_CHILDREN} filhas por divisao")
    if not splitter_agent_id or not splitter_agent_id.strip():
        raise TaskSplitError("quem divide precisa ser identificado")

    for i, part in enumerate(parts):
        if not part.title or not part.title.strip():
            raise TaskSplitError(f"parte {i}: titulo vazio")
        if not part.instruction or not part.instruction.strip():
            raise TaskSplitError(f"parte {i}: instrucao vazia")
        if not part.assigned_agent_id or not part.assigned_agent_id.strip():
            raise TaskSplitError(f"parte {i}: sem responsavel")
        if part.budget_usd is None or part.budget_usd <= 0:
            raise TaskSplitError(f"parte {i}: budget precisa ser maior que zero")
        if part.max_turns is None or part.max_turns < 1:
            raise TaskSplitError(f"parte {i}: max_turns precisa ser >= 1")

    if parent.budget_usd is not None:
        total = sum(p.budget_usd for p in parts)
        if total > parent.budget_usd:
            raise TaskSplitError(
                f"soma dos budgets das filhas ({total}) passa do budget da mae ({parent.budget_usd})"
            )

    children: List[Task] = []
    for part in parts:
        child = Task(
            id=_new_id(),
            session_id=parent.session_id,
            title=part.title,
            instruction=f"[parte de {parent.id}] {part.instruction}",
            created_by_agent_id=splitter_agent_id,
            assigned_agent_id=part.assigned_agent_id,
            state=TaskState.ASSIGNED,
            acceptance=part.acceptance,
            max_turns=part.max_turns,
            budget_usd=part.budget_usd,
        )
        children.append(child)
        if journal is not None:
            journal.append(
                {
                    "ts": clock(),
                    "event": "split",
                    "parent_id": parent.id,
                    "child_id": child.id,
                    "assigned_agent_id": child.assigned_agent_id,
                    "budget_usd": child.budget_usd,
                }
            )
    return children


def complete_child(
    task: Task,
    result: str,
    by_agent_id: str,
    journal: Optional[List[Dict[str, Any]]] = None,
    clock: Callable[[], float] = time.time,
) -> Task:
    """O responsavel entrega a filha. So' ele pode concluir."""
    if task.state not in (TaskState.ASSIGNED, TaskState.RUNNING):
        raise TaskSplitError(
            f"so filha ASSIGNED ou RUNNING pode ser concluida (esta {task.state.value})"
        )
    if by_agent_id != task.assigned_agent_id:
        raise TaskSplitError("so o responsavel da filha pode conclui-la")
    if not result or not result.strip():
        raise TaskSplitError("conclusao precisa de resultado")
    task.state = TaskState.COMPLETED
    task.result = result
    task.updated_at = clock()
    if journal is not None:
        journal.append(
            {"ts": clock(), "event": "complete", "child_id": task.id,
             "by_agent_id": by_agent_id}
        )
    return task


def fail_child(
    task: Task,
    reason: str,
    by_agent_id: str,
    journal: Optional[List[Dict[str, Any]]] = None,
    clock: Callable[[], float] = time.time,
) -> Task:
    """O responsavel declara a filha como falha, com motivo."""
    if task.state not in (TaskState.ASSIGNED, TaskState.RUNNING):
        raise TaskSplitError(
            f"so filha ASSIGNED ou RUNNING pode falhar (esta {task.state.value})"
        )
    if by_agent_id != task.assigned_agent_id:
        raise TaskSplitError("so o responsavel da filha pode declara-la falha")
    if not reason or not reason.strip():
        raise TaskSplitError("falha precisa de motivo")
    task.state = TaskState.FAILED
    task.result = reason
    task.updated_at = clock()
    if journal is not None:
        journal.append(
            {"ts": clock(), "event": "fail", "child_id": task.id,
             "by_agent_id": by_agent_id, "reason": reason}
        )
    return task


def parent_outcome(children: List[Task]) -> Tuple[TaskState, str]:
    """O veredito da mae a partir das filhas.

    Retorna (estado, resumo). Todas COMPLETED -> mae COMPLETED com o
    resultado agregado; qualquer FAILED -> mae FAILED com o motivo;
    senao a mae segue RUNNING.
    """
    if not children:
        raise TaskSplitError("veredito precisa de pelo menos 1 filha")
    failed = [c for c in children if c.state == TaskState.FAILED]
    if failed:
        first = failed[0]
        return (
            TaskState.FAILED,
            f"filha '{first.title}' ({first.id}) falhou: {first.result}",
        )
    done = [c for c in children if c.state == TaskState.COMPLETED]
    if len(done) == len(children):
        aggregated = "\n".join(f"[{c.id}] {c.title}: {c.result}" for c in children)
        return (TaskState.COMPLETED, aggregated)
    return (
        TaskState.RUNNING,
        f"{len(done)}/{len(children)} filhas concluidas",
    )
