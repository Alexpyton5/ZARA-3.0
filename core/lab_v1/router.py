"""Deterministic role/capability routing; model names are profile data, not policy."""
from dataclasses import dataclass
from core.lab_v1.domain import RoleName
from core.lab_v1.providers.base import InvocationOptions


@dataclass(frozen=True)
class Selection:
    agent_id: str
    provider_id: str
    model: str
    options: InvocationOptions
    reason: str


class TaskRouter:
    ROLES = {'planning': RoleName.CEO, 'implementation': RoleName.BUILDER,
             'review': RoleName.REVIEWER, 'analysis': RoleName.MEMBER,
             'research': RoleName.RESEARCHER}

    def __init__(self, runtime):
        self.runtime = runtime

    def select(self, team_id, task_type, *, complexity='medium', preferred_name=None,
               exclude=(), free_only=False):
        if task_type not in self.ROLES or complexity not in ('low', 'medium', 'high'):
            raise ValueError('UNKNOWN_TASK_POLICY')
        registry = self.runtime.registry
        providers = registry.list_providers()
        eligible = []
        for agent in self.runtime.store.list_agents(team_id=team_id):
            if agent.archived or agent.id in exclude or 'model.text' not in agent.capabilities:
                continue
            if preferred_name and agent.name.casefold() != preferred_name.casefold():
                continue
            adapter = registry.get(agent.provider_id)
            if not adapter or not getattr(adapter, 'controlled_text_only', False):
                continue
            if registry.model_status(agent.provider_id, agent.model, providers=providers)['availability'] != 'AVAILABLE':
                continue
            # There is no account-level zero-incremental-cost proof yet.
            if free_only:
                continue
            descriptor = next((m for m in adapter.declared_models if m.model_id == agent.model), None)
            if descriptor is None:
                continue
            effort = complexity if complexity in descriptor.effort_levels else agent.effort
            if descriptor.supports_effort and effort not in descriptor.effort_levels:
                continue
            if not descriptor.supports_effort:
                effort = None
            # Exact role first; compatible fallback is explicit in the returned reason.
            eligible.append((agent.role != self.ROLES[task_type], agent.created_at, agent, effort))
        if not eligible:
            raise ValueError('WAITING_NAMED_AGENT' if preferred_name else 'NO_PROVEN_COMPATIBLE_AGENT')
        fallback, _, agent, effort = min(eligible, key=lambda item: item[:2])
        return Selection(agent.id, agent.provider_id, agent.model, InvocationOptions(effort),
                         'compatible_role_fallback' if fallback else 'role_capability_health_policy')
