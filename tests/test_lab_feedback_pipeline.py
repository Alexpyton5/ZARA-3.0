import asyncio
import json
from types import SimpleNamespace

from core.lab_v1.domain import (AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName,
                                Team, TeamMembership)
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.feedback_inbox import FeedbackInbox, looks_like_product_criticism
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from core.lab_v1.autopilot import Autopilot


class CodexSolAdapter(ProviderAdapter):
    """Unit-only adapter proving selection without making a provider call."""
    id = 'codex_cli'
    label = 'Codex'
    controlled_text_only = True

    def probe(self):
        return ProviderInfo(self.id, self.label, 'test', Availability.AVAILABLE,
                            models=['gpt-5.6-sol'])

    def complete(self, **kwargs):
        raise AssertionError('architect provisioning must not call the provider')


def test_real_owner_criticism_is_persisted_once(tmp_path):
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    inbox = FeedbackInbox(store)
    text = 'O ZARA Lab não funciona e demora para responder.'
    assert looks_like_product_criticism(text)
    first = inbox.record(text, channel='voice')
    second = inbox.record(text, channel='voice')
    assert first['id'] == second['id']
    assert inbox.counts() == {'RECEIVED': 1}
    assert first['channel'] == 'voice' and first['text'] == text
    assert not looks_like_product_criticism('Abra o YouTube')


def test_service_captures_criticism_without_model_call(tmp_path):
    from core.lab_v1.service import LabV1Service
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    svc = LabV1Service(); svc._runtime = SimpleNamespace(store=store); svc._store = store
    result = asyncio.run(svc.capture_feedback('Isso está lento e precisa melhorar.', channel='text'))
    assert result == {'success': True, 'captured': True}
    assert FeedbackInbox(store).counts() == {'RECEIVED': 1}


def test_sol_is_provisioned_as_architect_and_owns_planning(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    adapter = CodexSolAdapter(); registry.register(adapter)
    registry.record_result('codex_cli', 'gpt-5.6-sol',
                           ProviderResult(True, availability=Availability.AVAILABLE))
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'ZARA Core'))
    sol = AgentProfile('sol', 'Sol', 'codex_cli', 'gpt-5.6-sol',
                       role=RoleName.CEO, capabilities=['model.text'])
    store.save_agent(sol); store.save_membership(TeamMembership('member:sol', 'team', 'sol'))
    policy = WorkforcePolicy({'authorized_providers': ['codex_cli'],
        'authorized_models': ['codex_cli/gpt-5.6-sol'],
        'resource_classes': {'codex_cli/gpt-5.6-sol': 'PLAN_INCLUDED'}})
    engine = Autopilot(runtime, root=tmp_path / 'missions', policy=policy)
    started = engine.start('Crítica observada', mission_kind='PRODUCT_CRITICISM_REVIEW',
                           evidence={'feedback_text': 'Falhou', 'evidence_sha256': 'x'})
    metrics = engine.metrics(started['session_id'])
    architect = store.get_agent(metrics['planner_id'])
    assert architect.id == 'sol' and architect.name == 'Sol'
    assert architect.model == 'gpt-5.6-sol' and architect.role is RoleName.CEO
    assert len(store.list_agents(team_id='team')) == 1
    assert metrics['planner_function'] == 'ARCHITECT'
    base = {'mission': 'Plan', 'plan_version': 1, 'tasks': [{
        'id': 'review', 'title': 'Revisar plano', 'instruction': 'Revise a proposta',
        'role': 'REVIEWER', 'capability': 'artifact.text', 'path': 'review.md',
        'depends_on': [], 'risk': 'LOW', 'repair_budget': 1,
        'acceptance': {'method': 'constraints', 'min_chars': 20, 'max_chars': 1000,
                       'required_sections': []}}]}
    engine.validate_plan(started['session_id'], base)
    base['tasks'][0]['role'] = 'BUILDER'
    import pytest
    with pytest.raises(ValueError, match='INDEPENDENT_REVIEW_REQUIRED'):
        engine.validate_plan(started['session_id'], base)
