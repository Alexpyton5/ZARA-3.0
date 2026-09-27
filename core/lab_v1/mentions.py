"""Canonical mention resolution for Lab V1 agent communication.

Mentions are an addressing convenience only.  They never grant membership or
permission: every result is resolved against the persisted team membership
and, for role mentions, the active role binding.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from core.lab_v1.domain import RoleName

__all__ = [
    "MentionResolutionError",
    "extract_mentions",
    "resolve_mentions",
    "resolve_recipient_ids",
]


class MentionResolutionError(ValueError):
    """The text could not be mapped to one canonical team participant."""


# Keep the grammar deliberately small.  A mention is an address, not a free
# form natural-language parser.  Unicode ``\\w`` permits names used by the
# Portuguese UI while the boundary prevents email addresses from becoming
# accidental routing instructions.
_MENTION = re.compile(r"(?<![\w@])@([\w][\w.-]{0,79})", re.UNICODE)


def extract_mentions(text: str | None) -> list[str]:
    """Return unique mention tokens in source order, without the ``@``."""
    seen: set[str] = set()
    result: list[str] = []
    for match in _MENTION.finditer(str(text or "")):
        token = match.group(1).strip()
        folded = token.casefold()
        if folded not in seen:
            seen.add(folded)
            result.append(token)
    return result


def _active_members(store: Any, team_id: str) -> list[Any]:
    membership_ids = {
        membership.agent_id
        for membership in store.list_memberships(team_id)
        if membership.left_at is None
    }
    return [
        agent
        for agent in (store.get_agent(agent_id) for agent_id in membership_ids)
        if agent is not None and not agent.archived
    ]


def _role_agent_id(store: Any, team_id: str, token: str) -> str | None:
    try:
        role = RoleName(token.strip().upper())
    except ValueError:
        return None
    binding = store.active_binding(team_id, role)
    if binding is None:
        raise MentionResolutionError(
            f"Nenhum agente ocupa o papel {role.value} neste time."
        )
    active_ids = {agent.id for agent in _active_members(store, team_id)}
    if binding.agent_id not in active_ids:
        raise MentionResolutionError(
            f"O ocupante do papel {role.value} nao esta em membership ativo."
        )
    return binding.agent_id


def resolve_mentions(store: Any, team_id: str, text: str | None) -> list[str]:
    """Resolve all mentions to canonical ``agent_id`` values.

    Display names are accepted only as an input convenience and only when
    they are unique among active members.  The returned value is always the
    persisted id; callers must never route using the display name.
    """
    members = _active_members(store, team_id)
    by_id = {agent.id.casefold(): agent.id for agent in members}
    by_name: dict[str, list[str]] = {}
    for agent in members:
        by_name.setdefault(agent.name.casefold(), []).append(agent.id)

    resolved: list[str] = []
    for token in extract_mentions(text):
        folded = token.casefold()
        agent_id = by_id.get(folded)
        if agent_id is None:
            role_agent_id = _role_agent_id(store, team_id, token)
            if role_agent_id is not None:
                agent_id = role_agent_id
        if agent_id is None:
            matches = by_name.get(folded, [])
            if len(matches) == 1:
                agent_id = matches[0]
            elif len(matches) > 1:
                raise MentionResolutionError(
                    f"A mention @{token} e ambigua entre membros do time."
                )
        if agent_id is None:
            raise MentionResolutionError(
                f"A mention @{token} nao corresponde a um membro com membership ativo do time."
            )
        if agent_id not in resolved:
            resolved.append(agent_id)
    return resolved


def resolve_recipient_ids(
    store: Any,
    *,
    team_id: str,
    text: str | None = None,
    to_agent_id: str | None = None,
    task_id: str | None = None,
) -> tuple[list[str], dict[str, str] | None]:
    """Resolve explicit id, mentions, or a canonical task assignment.

    The optional assignment is returned as metadata so the caller can expose
    why a route was selected without replacing the persisted message model.
    """
    mentioned: list[str] = []
    assignment: dict[str, str] | None = None
    if task_id:
        task = store.get_task(task_id)
        if task is None or task.session_id is None:
            raise MentionResolutionError(f"Tarefa '{task_id}' nao encontrada.")
        assigned = task.assigned_agent_id
        if not assigned:
            raise MentionResolutionError(
                f"Tarefa '{task_id}' nao possui assigned_agent_id canonico."
            )
        assignment = {"task_id": task_id, "assigned_agent_id": assigned}
        if assigned not in {
            member.agent_id
            for member in store.list_memberships(team_id)
            if member.left_at is None
        }:
            raise MentionResolutionError(
                f"Agente atribuido a tarefa '{task_id}' nao esta em membership ativo."
            )
        if to_agent_id and to_agent_id != assigned:
            raise MentionResolutionError(
                "O destinatario explicito diverge do assigned_agent_id canonico."
            )
        to_agent_id = assigned

        # Check the canonical task route before resolving display mentions.
        # A malformed mention must not hide a more specific assignment
        # divergence (the persisted task is the authority).
        if to_agent_id and to_agent_id != assigned:
            raise MentionResolutionError(
                "A mention diverge do assigned_agent_id canonico."
            )
        mentioned = resolve_mentions(store, team_id, text)
        if mentioned and any(agent_id != assigned for agent_id in mentioned):
            raise MentionResolutionError(
                "A mention diverge do assigned_agent_id canonico."
            )
    else:
        mentioned = resolve_mentions(store, team_id, text)

    if to_agent_id:
        active_ids = {
            member.agent_id
            for member in store.list_memberships(team_id)
            if member.left_at is None
        }
        agent = store.get_agent(to_agent_id)
        if to_agent_id not in active_ids or agent is None or agent.archived:
            raise MentionResolutionError(
                "O destinatario precisa ser um agente com membership ativo."
            )
        if mentioned and any(agent_id != to_agent_id for agent_id in mentioned):
            raise MentionResolutionError(
                "A mention diverge do destinatario canonico informado."
            )
        return [to_agent_id], assignment

    if mentioned:
        return mentioned, assignment
    raise MentionResolutionError(
        "Mensagem agent-to-agent precisa de to_agent_id, task assignment ou mention."
    )


def active_member_ids(store: Any, team_id: str) -> set[str]:
    """Small public helper used by the message bus and tests."""
    return {
        membership.agent_id
        for membership in store.list_memberships(team_id)
        if membership.left_at is None
    }
