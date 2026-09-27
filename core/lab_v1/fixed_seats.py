"""Fixed Lab seats and a fail-closed invitation gate.

Seats are roles, not synthetic agents. An invocation needs an explicit turn,
an active binding, membership and a separate resource authorization.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from core.lab_v1.domain import AgentProfile, RoleName


FIXED_SEATS = (
    RoleName.CEO, RoleName.ARCHITECT, RoleName.UI_DESIGNER,
    RoleName.ENGINEER, RoleName.SCRIBE, RoleName.REVIEWER,
    RoleName.CRITIC, RoleName.SECRETARY, RoleName.TESTER,
    RoleName.RESEARCHER, RoleName.PACKAGER,
)

GATED_TEAM_NAMES = frozenset({'ZARA Core', 'ZARA Autopilot', 'ZARA Lab'})


def requires_fixed_seat(team: Any, role: RoleName) -> bool:
    """Keep unrelated legacy/custom teams working until they opt into seats."""
    return team is not None and team.name in GATED_TEAM_NAMES and role in FIXED_SEATS


class InvitationDenied(ValueError):
    """A seat did not satisfy the prerequisites for this exact turn."""


def _occupant(store: Any, team_id: str, role: RoleName) -> AgentProfile | None:
    binding = store.active_binding(team_id, role)
    if binding is None:
        return None
    agent = store.get_agent(binding.agent_id)
    if agent is None or agent.archived or agent.role is not role:
        return None
    if 'model.text' not in agent.capabilities:
        return None
    if not any(member.agent_id == agent.id and member.left_at is None
               for member in store.list_memberships(team_id)):
        return None
    return agent


def seat_snapshot(store: Any, team_id: str) -> list[dict[str, str | None]]:
    """Show all seats without inventing an agent or granting a turn."""
    return [
        {'role': role.value, 'agent_id': agent.id if (agent := _occupant(store, team_id, role)) else None,
         'status': 'OCCUPIED' if agent else 'VACANT'}
        for role in FIXED_SEATS
    ]


def invited_agents(
    store: Any, team_id: str, roles: Iterable[RoleName],
    *, authorize: Callable[[AgentProfile], bool],
) -> list[AgentProfile]:
    """Resolve only explicitly invited roles; never route to another seat."""
    team = store.get_team(team_id)
    if team is None or team.archived:
        raise InvitationDenied('TEAM_UNAVAILABLE')
    result: list[AgentProfile] = []
    seen: set[RoleName] = set()
    for role in roles:
        if role not in FIXED_SEATS or role in seen:
            raise InvitationDenied('ROLE_NOT_INVITABLE')
        seen.add(role)
        agent = _occupant(store, team_id, role)
        if agent is None:
            raise InvitationDenied(f'SEAT_VACANT:{role.value}')
        if not authorize(agent):
            raise InvitationDenied(f'RESOURCE_NOT_AUTHORIZED:{role.value}')
        result.append(agent)
    return result


def run_invited_turn(
    store: Any, team_id: str, roles: Iterable[RoleName],
    *, authorize: Callable[[AgentProfile], bool], speak: Callable[[AgentProfile], Any],
) -> dict[str, list[str]]:
    """Run an already-authorized turn and return auditable speaker IDs."""
    selected = invited_agents(store, team_id, roles, authorize=authorize)
    occupied = [agent.id for role in FIXED_SEATS
                if (agent := _occupant(store, team_id, role)) is not None]
    spoken: list[str] = []
    for agent in selected:
        speak(agent)
        spoken.append(agent.id)
    return {'spoken_agent_ids': spoken,
            'silent_agent_ids': [agent_id for agent_id in occupied if agent_id not in spoken]}
