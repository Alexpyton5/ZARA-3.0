"""Executable cost and identity policy for internal ZARA Lab workers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
from typing import Iterable

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo


class ResourceClass(str, Enum):
    PLAN_INCLUDED = 'PLAN_INCLUDED'
    OWNER_REPORTED_FREE = 'OWNER_REPORTED_FREE'
    HOSTED_FREE_PROVEN = 'HOSTED_FREE_PROVEN'
    PAID = 'PAID'
    UNKNOWN_COST = 'UNKNOWN_COST'
    UNAVAILABLE = 'UNAVAILABLE'


@dataclass(frozen=True)
class WorkforceDecision:
    allowed: bool
    code: str
    resource_class: ResourceClass
    provider_id: str
    model_id: str
    agent_id: str
    role: str
    team_id: str | None = None


class WorkforcePolicy:
    SAFE_CLASSES = frozenset({ResourceClass.PLAN_INCLUDED, ResourceClass.OWNER_REPORTED_FREE,
                              ResourceClass.HOSTED_FREE_PROVEN})

    @staticmethod
    def default_document() -> dict:
        return {
            'mission_entry_enabled': True,
            'background_enabled': True,
            'paid_allowed': False,
            'resource_classes': {
                'codex_cli/gpt-5.6-luna': 'PLAN_INCLUDED',
                'codex_cli/gpt-5.6-sol': 'PLAN_INCLUDED',
                'codex_cli/gpt-5.6-terra': 'PLAN_INCLUDED',
                'codex_cli/gpt-6-astra': 'UNKNOWN_COST',
                # Re-enabled by Alex on 2026-09-10 (MORNING-01), reverting his own
                # earlier revocation. PLAN_INCLUDED and not PAID because this reuses
                # the Claude Code CLI session already authenticated on this machine —
                # the same subscription that runs Alex's own sessions. No new API key,
                # no new billing relationship was created to enable it.
                'claude_cli/*': 'PLAN_INCLUDED',
                'nvidia/*': 'UNKNOWN_COST',
                'deepseek_harness/*': 'UNKNOWN_COST',
            },
            # Only aliases proven by a real call are listed. `claude_cli/haiku`
            # joined on 2026-09-10 (TASK 2) once it was both proven by a real call
            # (provider reported canonicalModel `claude-haiku-4-5`) and declared in
            # ClaudeCliAdapter.declared_models. Being authorized means "may be used
            # when a mission names it" — it is deliberately absent from
            # role_model_preference below, so nothing selects it automatically.
            'authorized_models': [
                'codex_cli/gpt-5.6-luna', 'codex_cli/gpt-5.6-sol',
                'codex_cli/gpt-5.6-terra',
                'claude_cli/opus', 'claude_cli/sonnet', 'claude_cli/haiku',
            ],
            'authorized_providers': ['codex_cli', 'claude_cli'],
            'authorized_roles': ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER'],
            'max_repair_attempts': 1,
            'cadence_seconds': 60,
            # Cheapest adequate Codex worker first, Claude appended after it in
            # every role so the existing Codex ordering is unchanged while Codex
            # works, and Claude backfills when it does not. Within Claude the
            # order is cheapest-first (sonnet before opus) for the same reason.
            # Roles remain independent from model identity; this is only a
            # selection preference, never a role->model binding.
            # `haiku` is intentionally absent from every list: it is authorized
            # but unranked, so preference_rank() sorts it last and no role ever
            # picks it on its own. A mission that wants Haiku must name it. Do
            # not "fix" this by pinning haiku to a role here — which role uses
            # which model is a mission decision, not an architectural one.
            'role_model_preference': {
                'CEO': ['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'sonnet', 'opus'],
                'BUILDER': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'sonnet', 'opus'],
                'REVIEWER': ['gpt-5.6-terra', 'gpt-5.6-sol', 'gpt-6-astra', 'sonnet', 'opus'],
                'RESEARCHER': ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol', 'gpt-6-astra', 'sonnet', 'opus'],
                'MEMBER': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'sonnet', 'opus'],
            },
        }

    def __init__(self, document: dict):
        merged = self.default_document()
        merged.update(document or {})
        if document and 'authorized_models' in document and 'authorized_providers' not in document:
            merged['authorized_providers'] = sorted({
                str(pattern).split('/', 1)[0]
                for pattern in document.get('authorized_models') or ()
                if '/' in str(pattern)
            })
        self.document = merged

    @property
    def mission_entry_enabled(self) -> bool:
        return self.document.get('mission_entry_enabled') is True

    @property
    def background_enabled(self) -> bool:
        return self.document.get('background_enabled') is True

    def _matches(self, provider_id: str, model_id: str, patterns: Iterable[str]) -> bool:
        key = f'{provider_id}/{model_id}'
        return any(fnmatchcase(key, str(pattern)) for pattern in patterns)

    def resource_class(self, provider_id: str, model_id: str) -> ResourceClass:
        key = f'{provider_id}/{model_id}'
        rules = self.document.get('resource_classes') or {}
        if key in rules:
            value = rules[key]
        else:
            matches = [(pattern, value) for pattern, value in rules.items() if fnmatchcase(key, pattern)]
            value = max(matches, key=lambda item: len(item[0]))[1] if matches else 'UNKNOWN_COST'
        try:
            return ResourceClass(value)
        except (TypeError, ValueError):
            return ResourceClass.UNKNOWN_COST

    def authorize(self, agent: AgentProfile, provider: ProviderInfo | None, *, model_available: bool,
                  team_id: str | None = None) -> WorkforceDecision:
        resource_class = self.resource_class(agent.provider_id, agent.model)
        common = dict(resource_class=resource_class, provider_id=agent.provider_id, model_id=agent.model,
                      agent_id=agent.id, role=agent.role.value, team_id=team_id)
        if not self.mission_entry_enabled:
            return WorkforceDecision(False, 'MISSION_ENTRY_DISABLED', **common)
        # A hardcoded `claude_cli -> OWNER_DISABLED` refusal used to sit here.
        # Alex revoked that revocation on 2026-09-10; the provider is now governed
        # by the same document rules as every other one. If a provider has to be
        # revoked again, do it in the policy document (authorized_providers /
        # resource_classes), never as an identity check in this function.
        if agent.provider_id not in set(self.document.get('authorized_providers') or ()):
            return WorkforceDecision(False, 'PROVIDER_NOT_AUTHORIZED', **common)
        if agent.role.value not in set(self.document.get('authorized_roles') or ()):
            return WorkforceDecision(False, 'ROLE_NOT_AUTHORIZED', **common)
        if not self._matches(agent.provider_id, agent.model, self.document.get('authorized_models') or ()):
            return WorkforceDecision(False, 'MODEL_NOT_AUTHORIZED', **common)
        if (provider is None or provider.availability is not Availability.AVAILABLE or not model_available
                or resource_class is ResourceClass.UNAVAILABLE):
            return WorkforceDecision(False, 'RESOURCE_UNAVAILABLE', **common)
        if resource_class is ResourceClass.UNKNOWN_COST:
            return WorkforceDecision(False, 'UNKNOWN_COST', **common)
        if resource_class is ResourceClass.PAID and self.document.get('paid_allowed') is not True:
            return WorkforceDecision(False, 'PAID_NOT_AUTHORIZED', **common)
        if resource_class not in self.SAFE_CLASSES and resource_class is not ResourceClass.PAID:
            return WorkforceDecision(False, 'RESOURCE_NOT_AUTHORIZED', **common)
        return WorkforceDecision(True, 'AUTHORIZED', **common)

    @staticmethod
    def choose_fallback(decisions: Iterable[WorkforceDecision]) -> WorkforceDecision | None:
        return next((decision for decision in decisions if decision.allowed), None)

    def choose_for_role(self, decisions: Iterable[WorkforceDecision], role: str) -> WorkforceDecision | None:
        """Choose only an authorized resource, preferring the economical role route."""
        allowed = [decision for decision in decisions if decision.allowed and decision.role == role]
        return min(allowed, key=lambda item: (self.preference_rank(item.model_id, role), item.model_id), default=None)

    def preference_rank(self, model_id: str, role: str | None = None) -> int:
        """Stable sort key for Autopilot candidate selection."""
        preferences = self.document.get('role_model_preference') or {}
        order = list(preferences.get(role or '', preferences.get('MEMBER', ())))
        try:
            return order.index(model_id)
        except ValueError:
            return len(order)
