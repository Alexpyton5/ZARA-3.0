"""Modelo de domínio do Planner — dados puros, sem execução.

Nenhuma classe aqui chama ToolRouter, subprocess, hardware ou modelo de IA.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PlanStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlanStep:
    """Um passo do plano. Não executa nada por si só."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _new_id("step"))
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    risk_hint: str | None = None
    requires_verification: bool = True
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "risk_hint": self.risk_hint,
            "requires_verification": self.requires_verification,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@dataclass
class Plan:
    """Um plano validável e serializável. Não sabe executar a si mesmo."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: _new_id("plan"))
    status: PlanStatus = PlanStatus.CREATED
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def step_by_id(self, step_id: str) -> PlanStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "steps": [s.to_dict() for s in self.steps],
            "metadata": dict(self.metadata),
        }


@dataclass
class PlanResult:
    """Resultado agregado de uma execução de Plan."""

    plan_id: str
    status: PlanStatus
    step_results: dict[str, Any] = field(default_factory=dict)
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "completed_steps": list(self.completed_steps),
            "failed_steps": list(self.failed_steps),
            "skipped_steps": list(self.skipped_steps),
            "error": self.error,
        }


@dataclass
class PlanningContext:
    """Contexto disponível ao Planner no momento de planejar — dados, não ação."""

    session_id: str | None = None
    pc_control_allowed: bool = False
    medium_risk_open: bool = False
    known_tool_names: frozenset[str] = field(default_factory=frozenset)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerRequest:
    """Entrada do Planner: um objetivo em linguagem natural + contexto."""

    goal: str
    context: PlanningContext = field(default_factory=PlanningContext)
    explicit_steps: list[dict[str, Any]] | None = None
    """Quando um chamador já sabe os passos (ex.: caminho determinístico ou
    saída estruturada de modelo já parseada), pode fornecê-los aqui em vez de
    depender do Planner descobrir sozinho. Cada dict vira um PlanStep depois
    de validado — nunca é executado direto."""


@dataclass
class PlannerResponse:
    """Saída do Planner: ou um Plan validado, ou um motivo de rejeição."""

    plan: Plan | None
    accepted: bool
    rejection_reason: str | None = None
