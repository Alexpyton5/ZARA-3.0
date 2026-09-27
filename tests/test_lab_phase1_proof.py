"""Astra Phase 1 proof closure.

Three running-code proofs, end to end through the production Autopilot path:

1. A completed mission with accepted artifacts promotes its verified outcome
   into central memory (UserMemoryCore fact + LESSON_MARKED_VERIFIED lesson),
   idempotently, with a source event ref.
2. A new mission run by a different engine instance, different agent and
   different model recovers Mission A's verified discovery with its source.
3. HandoffCheckpoint is a live runtime path: a controller-verified step
   persists a stage baton and a failover run injects it back into context.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.lab_v1.agent_continuity import AgentContinuity
from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (
    AgentProfile,
    Availability,
    EventType,
    ProviderInfo,
    ProviderResult,
    RoleName,
    Session,
    Team,
    TeamMembership,
)
from core.lab_v1.memory_adapter import LabMemoryAdapter
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from memory.user_memory import UserMemoryCore


class TextAdapter(ProviderAdapter):
    """Unit-only deterministic adapter; it is not runtime/provider evidence."""
    controlled_text_only = True

    def __init__(self, name):
        self.id = self.label = name
        self.calls = []

    def probe(self):
        return ProviderInfo(self.id, self.label, 'test', Availability.AVAILABLE, models=['test'])

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps({'mission': 'Document', 'plan_version': 1, 'tasks': [
            {'id': 'document', 'title': 'Document', 'instruction': 'Create the requested short document',
             'role': 'BUILDER', 'capability': 'artifact.text', 'path': 'result.md',
             'risk': 'LOW', 'repair_budget': 1, 'depends_on': [],
             'acceptance': {'method': 'constraints', 'min_chars': 10, 'max_chars': 100,
                            'required_sections': []}}]})
        if 'Implement only' in kwargs.get('system', ''):
            text = 'ZARA_AUTOPILOT_OK'
        return ProviderResult(True, text=text, availability=Availability.AVAILABLE,
                              model_reported=kwargs['model'],
                              input_tokens=10, output_tokens=20, duration_ms=1,
                              provider_session_id='fake-request')


class Files:
    def __init__(self, sandbox):
        self.sandbox = sandbox

    def execute(self, request, deadline):
        Path(request.path).write_bytes(request.content.encode('utf-8'))
        return {'success': True, 'data': {'executor': 'test'}}


@pytest.fixture
def lab(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    registry = ProviderRegistry(tmp_path / 'health.json')
    for name in ('primary', 'fallback'):
        registry.register(TextAdapter(name))
        registry.record_result(name, 'test', ProviderResult(True, availability=Availability.AVAILABLE))
    memory = UserMemoryCore(db_path=tmp_path / 'user_memory.db')
    runtime = LabRuntime(store, registry, LabMemoryAdapter(store, memory))
    store.save_team(Team('team', 'Phase 1 Proof'))
    # Mission A is planned by primary/test; Mission B by fallback/mini: a
    # different agent instance AND a different model must recover the discovery.
    for name, provider, model, role in (
            ('lead', 'primary', 'test', RoleName.CEO),
            ('worker', 'fallback', 'test', RoleName.BUILDER),
            ('relief', 'fallback', 'mini', RoleName.BUILDER)):
        store.save_agent(AgentProfile(name, name, provider, model, role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership('member:' + name, 'team', name))
    policy = WorkforcePolicy({'mission_entry_enabled': True, 'background_enabled': True,
        'authorized_providers': ['primary', 'fallback'],
        'resource_classes': {'primary/*': 'OWNER_REPORTED_FREE', 'fallback/*': 'OWNER_REPORTED_FREE'},
        'authorized_models': ['primary/*', 'fallback/*'],
        'authorized_roles': ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER']})

    def build():
        return Autopilot(LabRuntime(store, registry, LabMemoryAdapter(store, memory)),
                         root=tmp_path / 'missions', executor_factory=Files, policy=policy)

    return {'store': store, 'memory': memory, 'registry': registry, 'build': build}


def test_completed_mission_promotes_verified_outcome_to_central_memory_idempotently(lab):
    engine = lab['build']()
    sid = engine.start('Central memory promotion proof')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'

    facts = [f for f in lab['memory'].list() if f.get('source') == 'zara_lab']
    assert len(facts) == 1
    assert 'Central memory promotion proof' in facts[0]['fact']
    assert facts[0]['ref'].startswith(f'lab:{sid}:')

    lessons = lab['store'].list_lessons()
    assert len(lessons) == 1
    assert lessons[0].source_session_id == sid
    assert facts[0]['fact'] == lessons[0].statement

    event_types = {e.type for e in lab['store'].list_events(sid, limit=500)}
    assert EventType.LESSON_MARKED_VERIFIED in event_types
    assert EventType.LESSON_PROMOTED in event_types

    # Crash/replay after completion must not duplicate the fact or the lesson.
    restarted = lab['build']()
    assert restarted.run(sid)['state'] == 'COMPLETED'
    assert len([f for f in lab['memory'].list() if f.get('source') == 'zara_lab']) == 1
    assert len(lab['store'].list_lessons()) == 1
    assert engine.metrics(sid).get('central_memory_promoted') is True


def test_new_instance_new_agent_new_model_recovers_mission_a_discovery_with_source(lab):
    engine_a = lab['build']()
    sid_a = engine_a.start('Discovery recovery evidence for the archive')['session_id']
    assert engine_a.run(sid_a)['state'] == 'COMPLETED'
    statement = lab['store'].list_lessons()[0].statement

    engine_b = lab['build']()
    sid_b = engine_b.start('Archive discovery recovery must survive instance changes')['session_id']
    assert sid_b != sid_a
    assert engine_b.run(sid_b)['state'] == 'COMPLETED'

    # The relief worker (fallback provider, 'mini' model — a different agent
    # instance and model from Mission A's worker) received Mission A's verified
    # discovery with its durable source reference.
    worker_prompts = [c['prompt'] for c in lab['registry'].get('fallback').calls]
    assert any(statement in prompt for prompt in worker_prompts)
    assert any(f'[evidencia: lab:{sid_a}:' in prompt for prompt in worker_prompts)

    resumed = AgentContinuity(lab['store'], lab['memory']).resume(sid_b, 'relief')
    recovered = [exp for exp in resumed.relevant_experiences if exp.source == 'user_memory']
    assert any(exp.statement == statement and exp.source_session_id == sid_a
               and exp.evidence_ref.startswith(f'lab:{sid_a}:') for exp in recovered)


def test_handoff_checkpoint_is_persisted_by_verified_steps_and_injected_after_failover(lab):
    engine = lab['build']()
    sid = engine.start('Handoff failover proof')['session_id']
    assert engine.run(sid)['state'] == 'COMPLETED'

    continuity = AgentContinuity(lab['store'], lab['memory'])
    lead_handoff = continuity.load_handoff_checkpoint(sid, 'lead')
    worker_handoff = continuity.load_handoff_checkpoint(sid, 'worker')
    assert lead_handoff is not None and lead_handoff.stage == 'STRATEGIST'
    assert lead_handoff.artifact_ref.startswith('response:')
    assert lead_handoff.provenance['session'] == sid
    assert worker_handoff is not None and worker_handoff.stage == 'REVIEWER'
    assert worker_handoff.evidence_refs

    # Failover: a new engine instance resumes the SAME mission; the staged
    # baton is injected back into the model context by the production port.
    resumed = AgentContinuity(lab['store'], lab['memory']).resume(sid, 'lead')
    assert resumed.handoff == lead_handoff

    failover_sid = engine.start('Handoff injection proof')['session_id']
    prior = continuity.save_checkpoint(
        failover_sid, 'lead', cursor='owner-intake', summary='Prior baton from a lost instance.',
        state={'handoff': {
            'stage': 'STRATEGIST', 'artifact_ref': 'response:lost-attempt',
            'evidence_refs': ['event:lost-evidence'],
            'provenance': {'session': failover_sid, 'agent': 'lead', 'step': 'plan'}}})
    assert prior.state['handoff']['stage'] == 'STRATEGIST'
    lead_calls_before = len(lab['registry'].get('primary').calls)
    assert engine.run(failover_sid)['state'] == 'COMPLETED'
    first_prompt = lab['registry'].get('primary').calls[lead_calls_before]['prompt']
    assert 'Handoff [STRATEGIST] artefato response:lost-attempt' in first_prompt
    assert 'event:lost-evidence' in first_prompt
