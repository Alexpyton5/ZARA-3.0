"""Plantão elástico do Lab V1 (on-call roster).

O que é plantão
---------------
Plantão é capacidade elástica, não assento fixo. Os "313 de plantão" não
existem como linhas no banco: o conceito é que o time pode crescer sob
demanda. O roster de plantão começa vazio e cresce via
`register_oncall` — normalmente depois que um agente prova chamada real
(ver `fleet.py`, `FleetCertification.register_proven_agent`).

Como o @ funciona
------------------
Assim que o plantonista vira membro ativo do time, ele é endereçável por
`@nome` automaticamente: `mentions.resolve_mentions(store, team_id, text)`
resolve contra os membros ativos, sem nenhum passo extra aqui. Quando o
plantão termina, `stand_down` encerra a membership e o `@nome` dele deixa
de resolver — o histórico (agente + membership com `left_at`) é preservado.

Fora deste módulo
-----------------
Promover um plantonista a assento fixo (lifecycle PERMANENT, role binding)
é decisão separada e não existe aqui. Este módulo só abre e fecha
plantões temporários.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.lab_v1.domain import (
    AgentProfile,
    Lifecycle,
    RoleName,
    TeamMembership,
    new_id,
    now,
)

__all__ = [
    "OncallError",
    "register_oncall",
    "list_oncall",
    "stand_down",
    "count_oncall",
]

MAX_NAME_CHARS = 80


class OncallError(ValueError):
    """O plantão não pôde ser aberto, listado ou encerrado."""


def _active_members(store: Any, team_id: str) -> list[tuple[Any, AgentProfile]]:
    """Pares (membership, agent) com membership aberto e agente não arquivado."""
    result: list[tuple[Any, AgentProfile]] = []
    for membership in store.list_memberships(team_id):
        if membership.left_at is not None:
            continue
        agent = store.get_agent(membership.agent_id)
        if agent is None or agent.archived:
            continue
        result.append((membership, agent))
    return result


def _check_name(name: str) -> str:
    cleaned = str(name or "").strip()
    if not (1 <= len(cleaned) <= MAX_NAME_CHARS):
        raise OncallError(
            "O nome do plantonista precisa ter entre 1 e "
            f"{MAX_NAME_CHARS} caracteres."
        )
    return cleaned


def register_oncall(
    store: Any,
    team_id: str,
    *,
    name: str,
    provider_id: str,
    model: str,
    role: RoleName = RoleName.MEMBER,
    capabilities: Iterable[str] = ("model.text",),
) -> AgentProfile:
    """Abre um plantão: cria o agente (TEMPORARY) e sua membership ativa.

    Falha se já houver um membro ativo com o mesmo nome (ignorando
    maiúsculas/minúsculas): dois nomes iguais deixariam o `@nome` ambíguo
    e o `mentions.py` rejeitaria a mensagem.
    """
    cleaned_name = _check_name(name)
    if not str(provider_id or "").strip():
        raise OncallError("O plantonista precisa de um provider_id.")
    if not str(model or "").strip():
        raise OncallError("O plantonista precisa de um model.")
    try:
        resolved_role = role if isinstance(role, RoleName) else RoleName(str(role))
    except ValueError:
        raise OncallError(f"O papel '{role}' não existe no Lab V1.") from None

    folded = cleaned_name.casefold()
    for _membership, agent in _active_members(store, team_id):
        if agent.name.casefold() == folded:
            raise OncallError(
                f"Já existe um membro ativo chamado '{agent.name}' neste time. "
                "Escolha outro nome para o @ não ficar ambíguo."
            )

    agent = AgentProfile(
        id=new_id("agent"),
        name=cleaned_name,
        provider_id=str(provider_id).strip(),
        model=str(model).strip(),
        role=resolved_role,
        capabilities=[str(capability) for capability in capabilities],
        lifecycle=Lifecycle.TEMPORARY,
    )
    store.save_agent(agent)
    store.save_membership(
        TeamMembership(id=new_id("membership"), team_id=team_id, agent_id=agent.id)
    )
    return agent


def list_oncall(store: Any, team_id: str) -> list[AgentProfile]:
    """Plantonistas ativos do time (lifecycle TEMPORARY), ordenados por nome."""
    agents = [
        agent
        for _membership, agent in _active_members(store, team_id)
        if agent.lifecycle is Lifecycle.TEMPORARY
    ]
    agents.sort(key=lambda agent: agent.name.casefold())
    return agents


def stand_down(store: Any, team_id: str, agent_id: str) -> None:
    """Encerra o plantão: fecha a membership (`left_at` = agora).

    O agente sai do time e deixa de ser endereçável por `@nome`, mas o
    histórico é preservado — a membership continua no banco com `left_at`
    preenchido e o `AgentProfile` não é apagado.
    """
    for membership, _agent in _active_members(store, team_id):
        if membership.agent_id == agent_id:
            membership.left_at = now()
            store.save_membership(membership)
            return
    raise OncallError("Esse agente não está de plantão neste time.")


def count_oncall(store: Any, team_id: str) -> int:
    """Quantos plantonistas estão ativos no time agora."""
    return len(list_oncall(store, team_id))
