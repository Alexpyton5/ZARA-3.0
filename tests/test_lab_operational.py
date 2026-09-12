"""Production orchestration with local workers, independent postconditions and no UI pump."""
import asyncio
import json
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, Team, TeamMembership
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


def plan(tasks=2):
    return {'mission': 'Create useful functions', 'plan_version': 1, 'tasks': [
        {'id': f'feature{i}', 'title': f'Increment {i}', 'instruction': 'Implement increment(x), returning x + 1.',
         'role': 'BUILDER', 'capability': 'artifact.python', 'path': f'increment{i}.py',
         'depends_on': [] if i == 0 else ['feature0'], 'risk': 'LOW', 'repair_budget': 1,
         'acceptance': {'method': 'python_cases', 'cases': [
             {'function': 'increment', 'args': [1], 'expected': 2},
             {'function': 'increment', 'args': [-1], 'expected': 0}]}}
        for i in range(tasks)]}


class Worker(ProviderAdapter):
    controlled_text_only = True
    def __init__(self):
        self.id = self.label = 'local'; self.calls = []; self.bad_once = False; self.offline_once = False
        self.plan = plan(); self.fail_task = None
    def probe(self):
        return ProviderInfo(self.id, self.label, 'fixture', Availability.AVAILABLE, models=['planner', 'builder'])
    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['model'] == 'planner':
            text = json.dumps(self.plan)
        else:
            if self.offline_once:
                self.offline_once = False
                return ProviderResult(False, availability=Availability.RATE_LIMITED, error='temporary')
            text = 'def increment(x):\n    return x + 1\n'
            if self.bad_once:
                self.bad_once = False; text = 'def increment(x):\n    return 0\n'
        return ProviderResult(True, text=text, availability=Availability.AVAILABLE,
            model_reported=kwargs['model'], provider_session_id=f'local-{len(self.calls)}')


@pytest.fixture
def lab(tmp_path):
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    registry = ProviderRegistry(tmp_path / 'health.json'); adapter = Worker(); registry.register(adapter)
    store.save_team(Team('team', 'Internal Team'))
    for name, role in [('planner', RoleName.MEMBER), ('builder', RoleName.BUILDER)]:
        store.save_agent(AgentProfile(name, name, 'local', name, role, capabilities=['model.text']))
        store.save_membership(TeamMembership(name, 'team', name))
        registry.record_result('local', name, ProviderResult(True, availability=Availability.AVAILABLE))
    policy = WorkforcePolicy({'authorized_models': ['local/*'], 'authorized_providers': ['local'],
        'resource_classes': {'local/*': 'OWNER_REPORTED_FREE'}})
    engine = Autopilot(LabRuntime(store, registry), root=tmp_path / 'missions', policy=policy)
    return engine, adapter


def test_dynamic_plan_handoff_verified_artifacts_and_one_report(lab):
    engine, adapter = lab
    sid = engine.start('Create increment functions with tests')['session_id']
    result = engine.run(sid)
    assert result['state'] == 'COMPLETED', result
    doc = engine.controller.snapshot(sid)
    assert doc['plan_version'] >= 2 and len(doc['steps']) == 5
    assert Path(engine.metrics(sid)['sandbox'], 'increment1.py').is_file()
    assert len(engine.store.list_runs(sid)) == 3
    assert 'increment0.py' in adapter.calls[-1]['prompt']
    assert len(engine.store.list_handoffs(sid)) >= 1
    assert engine.metrics(sid)['owner_touches'] == 1
    assert engine.metrics(sid)['final_report_automatic'] is True
    engine.run(sid)
    assert len([m for m in engine.store.list_messages(sid) if m.id == 'autopilot-report:' + sid]) == 1


def test_wrong_valid_python_rejected_then_repaired_with_evidence(lab):
    engine, adapter = lab; adapter.bad_once = True
    sid = engine.start('Create increment functions')['session_id']
    result = engine.run(sid)
    assert result['state'] == 'COMPLETED', result
    builders = [c for c in adapter.calls if c['model'] == 'builder']
    assert len(builders) == 3 and 'expected' in builders[1]['prompt']
    assert engine.controller.snapshot(sid)['used']['retries'] == 1
    assert any('FAIL' in a.body for a in engine.store.list_artifacts(sid) if a.kind == 'VERIFICATION')


def test_resource_wait_persists_and_safe_retry_is_bounded(lab):
    engine, adapter = lab; adapter.offline_once = True; adapter.plan = plan(1)
    sid = engine.start('Create increment')['session_id']
    result = engine.run(sid)
    assert result['state'] == 'WAITING_RESOURCE', result
    count = len(adapter.calls)
    assert engine.run(sid)['state'] == 'WAITING_RESOURCE'
    assert len(adapter.calls) == count
    with engine.controller._transaction() as conn:
        doc, _ = engine.controller._load(conn, sid)
        for step in doc['steps']:
            if step['status'] == 'PROVIDER_FAILED': step['retry_at'] = 0
        engine.controller._save(conn, doc, 'test.clock_advanced')
    assert engine.run(sid)['state'] == 'COMPLETED'
    assert engine.metrics(sid)['owner_touches'] == 1


def test_restart_after_verified_planning_uses_same_session(lab):
    from core.lab_v1.autopilot import _AutopilotPorts
    engine, adapter = lab
    sid = engine.start('Create increment')['session_id']
    ports = _AutopilotPorts(engine, sid, engine.metrics(sid))
    engine.controller.tick(sid, ports)
    engine.controller.tick(sid, ports)
    resumed = Autopilot(LabRuntime(LabStore(engine.store.db_path), engine.runtime.registry),
                        root=engine.root, policy=engine.policy)
    assert resumed.run(sid)['state'] == 'COMPLETED'
    assert len([c for c in adapter.calls if c['model'] == 'planner']) == 1


def test_no_default_policy_bypass(lab):
    engine, _ = lab
    other = Autopilot(engine.runtime, root=engine.root)
    with pytest.raises(ValueError): other.start('Spend on unknown local model')
