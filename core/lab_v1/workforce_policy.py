"""Executable cost and identity policy for internal ZARA Lab workers."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from fnmatch import fnmatchcase
from typing import Iterable

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, RoleName


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


@dataclass(frozen=True)
class BotResource:
    """The (provider, model) pair a bot actually runs on right now.

    Never constructed by guessing: `WorkforcePolicy.effective_resource()` is
    the only place that decides between an owner override and the agent's
    own profile, so there is exactly one answer to "what does this bot use".
    """

    provider_id: str
    model_id: str


class WorkforcePolicy:
    SAFE_CLASSES = frozenset({ResourceClass.PLAN_INCLUDED, ResourceClass.OWNER_REPORTED_FREE,
                              ResourceClass.HOSTED_FREE_PROVEN})

    @staticmethod
    def default_document() -> dict:
        return {
            'mission_entry_enabled': True,
            'background_enabled': True,
            'paid_allowed': False,
            # The reauthorized Claude CLI participates through the same
            # allow-list and resource-class checks as every other provider.
            # An owner can still put it on standby through the persisted policy
            # document; the default must not silently contradict the approved
            # `claude_cli/*` PLAN_INCLUDED entries below.
            'standby_providers': [],
            # Owner-set, per-bot provider/model choice (2026-09-12, "bots
            # customizaveis"). Empty by default: with no entry here an agent
            # keeps using its own AgentProfile.provider_id/model exactly as
            # before -- this key existing at all must never change behaviour
            # for a Lab that never touches it. Set only through
            # WorkforcePolicy.with_bot_override(), which validates first
            # (see validate_bot_configuration) and never applies silently.
            'agent_model_overrides': {},
            # Optional absolute path to agency-agents.json. Catalog discovery
            # alone never grants a team membership or authorizes dispatch.
            'agency_roster_path': None,
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
                # `nvidia/*` stays UNKNOWN_COST as the fallback for every NVIDIA
                # model *except* the two named below: it must never render as
                # free just because it is discovered in the catalog. Alex told
                # us his NVIDIA API-catalog key runs Nemotron for free (he
                # already uses it this way in another project); on 2026-09-12
                # a real call confirmed the key and endpoint work end to end
                # (see nvidia.py verification: GET /v1/models listed both ids,
                # and a real chat completion on each echoed the exact prompt
                # and reported its own canonical model id back). That is
                # proof the integration works, not proof of NVIDIA's billing,
                # so this is OWNER_REPORTED_FREE (Alex's word on cost), never
                # HOSTED_FREE_PROVEN (which would need independently verified
                # zero cost). More specific pattern wins over `nvidia/*` in
                # resource_class(), so only these two named ids get it.
                #
                # The key doubles "nvidia/" on purpose, not a typo: this dict
                # is keyed by `f'{provider_id}/{model}'` (see resource_class()
                # below), our provider id is "nvidia", and NVIDIA's own API
                # catalog namespaces its first-party models as "nvidia/<name>"
                # (the same way it namespaces "mistralai/mistral-nemotron").
                # `agent.model` has to carry that real id verbatim -- it is
                # what actually gets sent to NVIDIA's API -- so the composite
                # policy key is genuinely "nvidia/nvidia/nemotron-...".
                'nvidia/*': 'UNKNOWN_COST',
                'nvidia/nvidia/nemotron-3-super-120b-a12b': 'OWNER_REPORTED_FREE',
                'nvidia/nvidia/nemotron-3-ultra-550b-a55b': 'OWNER_REPORTED_FREE',
                'deepseek_harness/*': 'UNKNOWN_COST',
                'nine_router/*': 'OWNER_REPORTED_FREE',
            },
            # Only aliases proven by a real call are listed. `claude_cli/haiku`
            # joined on 2026-09-10 (TASK 2) once it was both proven by a real call
            # (provider reported canonicalModel `claude-haiku-4-5`) and declared in
            # ClaudeCliAdapter.declared_models. Being authorized means "may be used
            # when a mission names it" — it is deliberately absent from
            # role_model_preference below, so nothing selects it automatically.
            # The same rule gates the two `nvidia/*` ids added on 2026-09-12: each
            # was proven by an actual chat-completion call that echoed our prompt
            # and reported its own model id back (see nvidia.py). A model never
            # gets into this list on catalog presence alone -- that is what keeps
            # a manual bot model change (workforce_policy.WorkforcePolicy.
            # validate_bot_configuration) from ever selecting an uncertified
            # model: it can only choose what is already curated here.
            'authorized_models': [
                'codex_cli/gpt-5.6-luna', 'codex_cli/gpt-5.6-sol',
                'codex_cli/gpt-5.6-terra',
                'claude_cli/opus', 'claude_cli/sonnet', 'claude_cli/haiku',
                # See the "nvidia/*" comment in resource_classes above for why
                # "nvidia/" appears twice: provider id "nvidia" + NVIDIA's own
                # real model id "nvidia/nemotron-...".
                'nvidia/nvidia/nemotron-3-super-120b-a12b', 'nvidia/nvidia/nemotron-3-ultra-550b-a55b',
                'nine_router/alex', 'nine_router/oc/muse-spark-1.2-contributor-free', 'nine_router/oc/muse-spark-1.3-contributor-free', 'nine_router/*',
            ],
            'authorized_providers': ['codex_cli', 'claude_cli', 'nvidia', 'nine_router', 'opencode'],
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
            # The two nvidia/nemotron ids are absent for the same reason, and
            # for an extra one: Provider != Model != Agent != Role != Team, so
            # nothing here should hard-code "role X always uses Nemotron".
            # Being authorized-but-unranked is exactly what makes it a real
            # fallback: preference_rank() sorts it last, so choose_for_role()
            # only ever picks it when it is the last authorized+available
            # candidate standing (e.g. codex_cli and claude_cli both out of
            # quota) -- see tests/test_lab_workforce_bot_customization.py.
            'role_model_preference': {
                'CEO': ['gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'oc/muse-spark-1.3-contributor-free', 'oc/nemotron-3.5-lightning-free', 'sonnet', 'opus'],
                'BUILDER': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'oc/muse-spark-1.3-contributor-free', 'oc/nemotron-3.5-lightning-free', 'oc/mimo-v2.5-free', 'sonnet', 'opus'],
                'REVIEWER': ['gpt-5.6-terra', 'gpt-5.6-sol', 'gpt-6-astra', 'oc/muse-spark-1.3-contributor-free', 'sonnet', 'opus'],
                'RESEARCHER': ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol', 'gpt-6-astra', 'oc/muse-spark-1.3-contributor-free', 'oc/nemotron-3.5-lightning-free', 'sonnet', 'opus'],
                'MEMBER': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-6-astra', 'oc/muse-spark-1.3-contributor-free', 'oc/mimo-v2.5-free', 'sonnet', 'opus'],
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
        if agent.provider_id in set(self.document.get('standby_providers') or ()):
            return WorkforceDecision(False, 'PROVIDER_STANDBY', **common)
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

    # ------------------------------------------------------------------
    # Bot customization surface (2026-09-12) — "bots customizaveis"
    #
    # Everything below is what a future screen calls to let Alex see and
    # change which provider/model each Lab bot runs on. It never touches
    # storage: `agent_model_overrides` lives in the same policy document
    # WorkforcePolicy already wraps (persisted wherever the caller already
    # persists `lab_autonomy_policy` — no second config system). Applying an
    # override is still just "return a new document"; whoever owns writing
    # that document back (service/supervisor) does the actual save in a
    # separate task.
    # ------------------------------------------------------------------

    def bot_override(self, agent_id: str) -> BotResource | None:
        """The owner's explicit choice for this bot, if any was ever set."""
        raw = (self.document.get('agent_model_overrides') or {}).get(agent_id)
        if not isinstance(raw, dict):
            return None
        provider_id, model_id = raw.get('provider_id'), raw.get('model_id')
        if not provider_id or not model_id:
            return None
        return BotResource(str(provider_id), str(model_id))

    def effective_resource(self, agent: AgentProfile) -> BotResource:
        """What `agent` actually runs on: the owner override, or its own profile.

        This is the single place that answers that question, so "list bots"
        and "pick a worker for a role" can never quietly disagree about it.
        """
        return self.bot_override(agent.id) or BotResource(agent.provider_id, agent.model)

    def describe_bots(self, agents: Iterable[AgentProfile], registry=None) -> list[dict]:
        """One row per bot for the future screen: identity, current resource, cost.

        `registry` is optional so a caller that only wants names/roles/models
        (no live availability) can skip probing; passing it fills in
        `provider_availability` from a real (cheap, no-token) probe.
        """
        providers = {info.id: info for info in registry.list_providers()} if registry is not None else {}
        rows = []
        for agent in agents:
            choice = self.effective_resource(agent)
            resource_class = self.resource_class(choice.provider_id, choice.model_id)
            provider_info = providers.get(choice.provider_id)
            rows.append({
                'agent_id': agent.id,
                'name': agent.name,
                'role': agent.role.value,
                'provider_id': choice.provider_id,
                'model_id': choice.model_id,
                'custom_override': self.bot_override(agent.id) is not None,
                'provider_availability': (provider_info.availability.value if provider_info is not None
                                          else Availability.UNKNOWN.value),
                'resource_class': resource_class.value,
                'cost_label': COST_LABELS.get(resource_class, COST_LABELS[ResourceClass.UNKNOWN_COST]),
            })
        return rows

    def describe_models(self, registry) -> list[dict]:
        """Every model the registry actually knows about, with an honest cost label.

        Only ever reads `registry.list_providers()` / `list_models()` (no
        network I/O — see their docstrings), so this is safe to call every
        time the future screen renders, exactly like the provider list today.
        """
        providers = {info.id: info for info in registry.list_providers()}
        rows = []
        for entry in registry.list_models():
            provider_id, model_id = entry['provider_id'], entry['model_id']
            provider_info = providers.get(provider_id)
            resource_class = self.resource_class(provider_id, model_id)
            authorized = (
                provider_id in set(self.document.get('authorized_providers') or ())
                and self._matches(provider_id, model_id, self.document.get('authorized_models') or ())
            )
            rows.append({
                'provider_id': provider_id,
                'model_id': model_id,
                'display_name': entry.get('display_name', model_id),
                'provider_availability': (provider_info.availability.value if provider_info is not None
                                          else Availability.UNKNOWN.value),
                'authorized': authorized,
                'resource_class': resource_class.value,
                'cost_label': COST_LABELS.get(resource_class, COST_LABELS[ResourceClass.UNKNOWN_COST]),
            })
        return rows

    _BUILDER_LIKE_ROLES = frozenset({RoleName.CEO.value, RoleName.BUILDER.value})

    def _reviewer_independence_conflict(
        self, agent: AgentProfile, provider_id: str, model_id: str, team_agents: Iterable[AgentProfile],
    ) -> AgentProfile | None:
        """Would this change leave a REVIEWER on the same (provider, model) as
        whoever it would review (or vice versa)? Mirrors the check
        `real_work_contract.validate_reviewer_result()` makes on actual Runs
        after the fact — this makes the same rule apply *before* the pick is
        saved, so a bad choice never has to be caught after it already ran.
        """
        pair = (provider_id, model_id)
        others = [item for item in team_agents if item.id != agent.id and not item.archived]
        if agent.role is RoleName.REVIEWER:
            opposite = [item for item in others if item.role.value in self._BUILDER_LIKE_ROLES]
        elif agent.role.value in self._BUILDER_LIKE_ROLES:
            opposite = [item for item in others if item.role is RoleName.REVIEWER]
        else:
            return None
        for other in opposite:
            choice = self.effective_resource(other)
            if (choice.provider_id, choice.model_id) == pair:
                return other
        return None

    def validate_bot_configuration(
        self, *, agent: AgentProfile, provider_id: str, model_id: str, registry,
        team_agents: Iterable[AgentProfile] = (),
    ) -> WorkforceDecision:
        """Validate — never apply — a manual provider/model change for `agent`.

        Reuses `authorize()`, the exact gate every automatic worker selection
        already goes through, so a manually chosen resource is never scrutinized
        less than an automatic one: unauthorized provider, unauthorized role,
        model missing from the catalog, model missing from `authorized_models`,
        provider not AVAILABLE, unknown/paid cost — all the same refusals.

        `authorized_models` is a curated allow-list (see `default_document()`):
        an id only lands there after a real proven call, so this cannot select
        a never-certified model just because the provider's catalog lists it —
        that is the certification gate, expressed as policy data instead of a
        code path, so it applies here for free.
        """
        candidate = replace(agent, provider_id=provider_id, model=model_id)
        providers = registry.list_providers()
        provider_info = next((item for item in providers if item.id == provider_id), None)
        model_available = any(
            row['provider_id'] == provider_id and row['model_id'] == model_id
            for row in registry.list_models(provider_id)
        )
        decision = self.authorize(candidate, provider_info, model_available=model_available)
        if not decision.allowed:
            return decision
        if self._reviewer_independence_conflict(agent, provider_id, model_id, team_agents) is not None:
            return replace(decision, allowed=False, code='REVIEWER_NOT_INDEPENDENT')
        return decision

    def with_bot_override(
        self, *, agent: AgentProfile, provider_id: str, model_id: str, registry,
        team_agents: Iterable[AgentProfile] = (),
    ) -> tuple[WorkforceDecision, dict | None]:
        """Validate a bot model change and, only if allowed, return the new document.

        Never mutates `self.document` — returns a fresh dict for the caller to
        persist (wherever `lab_autonomy_policy` is already persisted) and to
        build a new `WorkforcePolicy` from. On refusal, returns `(decision,
        None)`: nothing is applied, and `decision.code` plus `human_message()`
        give a plain reason.
        """
        decision = self.validate_bot_configuration(
            agent=agent, provider_id=provider_id, model_id=model_id,
            registry=registry, team_agents=team_agents,
        )
        if not decision.allowed:
            return decision, None
        overrides = dict(self.document.get('agent_model_overrides') or {})
        overrides[agent.id] = {'provider_id': provider_id, 'model_id': model_id}
        new_document = {**self.document, 'agent_model_overrides': overrides}
        return decision, new_document

    def without_bot_override(self, agent_id: str) -> dict:
        """New document with `agent_id`'s override removed (back to its own profile)."""
        overrides = dict(self.document.get('agent_model_overrides') or {})
        overrides.pop(agent_id, None)
        return {**self.document, 'agent_model_overrides': overrides}


COST_LABELS: dict[ResourceClass, str] = {
    ResourceClass.PLAN_INCLUDED: 'Incluso no plano mensal do Alex',
    ResourceClass.OWNER_REPORTED_FREE: 'Gratuito (informado pelo dono)',
    ResourceClass.HOSTED_FREE_PROVEN: 'Gratuito (comprovado por chamada real)',
    ResourceClass.PAID: 'Pago',
    ResourceClass.UNKNOWN_COST: 'Custo desconhecido',
    ResourceClass.UNAVAILABLE: 'Indisponivel',
}

# Plain-language refusal text for Alex — he is not a programmer, so this is
# what a future screen shows verbatim: no stack trace, no jargon, no code.
REFUSAL_MESSAGES: dict[str, str] = {
    'MISSION_ENTRY_DISABLED': 'O Lab esta com entrada de missao desligada agora; nenhuma troca e aplicada.',
    'PROVIDER_NOT_AUTHORIZED': 'Esse provedor ainda nao esta liberado para uso no Lab.',
    'ROLE_NOT_AUTHORIZED': 'Esse papel ainda nao esta liberado para uso no Lab.',
    'MODEL_NOT_AUTHORIZED': 'Esse modelo ainda nao esta na lista de modelos liberados do Lab.',
    'RESOURCE_UNAVAILABLE': 'Esse modelo nao esta respondendo agora (fora do ar ou sem cota). Escolha outro ou tente mais tarde.',
    'UNKNOWN_COST': 'Ainda nao sabemos se esse modelo e pago ou gratuito, entao ele fica bloqueado por seguranca.',
    'PAID_NOT_AUTHORIZED': 'Esse modelo e pago e o uso de recursos pagos nao esta autorizado agora.',
    'RESOURCE_NOT_AUTHORIZED': 'Esse recurso nao esta autorizado para uso automatico no Lab.',
    'REVIEWER_NOT_INDEPENDENT': (
        'Essa troca deixaria o revisor no mesmo provedor e modelo de quem construiu. '
        'O revisor precisa ser diferente, entao a troca nao foi aplicada.'
    ),
    'AUTHORIZED': 'Liberado.',
}


def human_message(decision: WorkforceDecision) -> str:
    """Plain-language version of `decision.code`, safe to show Alex as-is."""
    return REFUSAL_MESSAGES.get(decision.code, 'Essa troca nao pode ser confirmada agora; nada foi alterado.')
