"""End-to-end proof of the capability-gap loop, with no stub Autopilot.

`tests/test_lab_evolution.py` proves the observer with a `StubAutopilot`: it
records that `start(...)` was called and stops there. Nothing proved that the
call reaches a real mission. This file removes the stub.

The loop under test, every leg real code:

  runtime action fails on a real ZARA turn (`IPCHandler._remember_action_failure`)
    -> `LabV1Service.capture_runtime_failure` persists a CapabilityGap
    -> `EvolutionEngine.observe_and_plan` turns it into RUNTIME_CAPABILITY_FAILURE evidence
    -> real `Autopilot.start(mission_kind='SELF_IMPROVEMENT')`
    -> real plan, real team, real sandbox edit, real pytest subprocess
    -> independent review by an agent that is not the builder
    -> candidate package, registered as candidate only
    -> nothing in production is touched.

What is a fixture and what is not
---------------------------------
The *model* is a deterministic fixture (`UnitReasoningFixture`): no provider is
called over the network, so the planner/builder/reviewer text is scripted. The
*pipeline* is not a fixture: plan validation, sandbox isolation, the file edit,
the pytest subprocesses, the review gate and the candidate receipt are the real
production code paths. This is unit/integration evidence, never proof of
autonomous authorship.

Everything lives in tmp_path. The owner's workspace, CURRENT build and Lab
database are never referenced.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import (
    AgentProfile,
    Availability,
    ProviderResult,
    RoleName,
    Team,
    TeamMembership,
)
from core.lab_v1.evolution import EvolutionEngine
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from tests.test_lab_restart_resume import unit_desktop_builder
from tests.test_lab_source_mission import UnitReasoningFixture
from tools import build_current

# The action whose executor is observed failing, and the module the real ZARA
# registry maps it to. Kept identical to production so the evidence is factual.
FAILING_ACTION = 'os_brightness_absolute'
EXECUTOR_PATH = 'core/actions/os_ops.py'
REGRESSION_TEST = 'tests/test_zara_mission_regression.py'

BASELINE_EXECUTOR = '''\
def brightness_target(current, direction):
    """Nivel de brilho pedido por voz. Passo grande ("muito") nao e tratado."""
    if direction == "down":
        return current - 10
    return current + 10
'''

CANDIDATE_EXECUTOR = '''\
def brightness_target(current, direction):
    """Nivel de brilho pedido por voz, incluindo o passo grande."""
    if direction == "down_muito":
        return current - 30
    if direction == "up_muito":
        return current + 30
    if direction == "down":
        return current - 10
    return current + 10
'''

CANDIDATE_REGRESSION = '''\
from core.actions.os_ops import brightness_target


def test_large_step_is_supported():
    assert brightness_target(50, "down_muito") == 20
    assert brightness_target(50, "up_muito") == 80


def test_existing_steps_are_preserved():
    assert brightness_target(50, "down") == 40
    assert brightness_target(50, "up") == 60
'''


class CapabilityFixture(UnitReasoningFixture):
    """Same scripted planner/reviewer; the builder implements THIS capability."""

    def __init__(self):
        self.prompts = []

    def complete(self, **kwargs):
        self.prompts.append((kwargs['model'],
                             kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message') or ''))
        if kwargs['model'] != 'builder':
            return super().complete(**kwargs)
        result = {'edits': [{'path': EXECUTOR_PATH, 'content': CANDIDATE_EXECUTOR},
                            {'path': REGRESSION_TEST, 'content': CANDIDATE_REGRESSION}],
                  'summary': 'Unit fixture implementation, not a real autonomous contribution.'}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
                              model_reported='builder', provider_session_id='unit-fixture',
                              input_tokens=1, output_tokens=1)


def make_workspace(root: Path) -> Path:
    workspace = root / 'workspace'
    (workspace / 'core/actions').mkdir(parents=True)
    (workspace / 'memory').mkdir()
    (workspace / 'core/__init__.py').touch()
    (workspace / 'core/actions/__init__.py').touch()
    (workspace / EXECUTOR_PATH).write_text(BASELINE_EXECUTOR, encoding='utf-8')
    current = workspace / 'frontend/ZARA CURRENT BUILD/win-unpacked'
    (current / 'resources/backend').mkdir(parents=True)
    (current / 'BUILD_INFO.json').write_text(json.dumps(
        {'BUILD_ID': 'unit-current', 'PREVIOUS_PACKAGE': None, 'ROLLBACK_JOURNAL': None}))
    (current / 'ZARA 3.0.exe').write_bytes(b'current-exe')
    (current / 'resources/app.asar').write_bytes(b'current-asar')
    (current / 'resources/backend/zara-backend.exe').write_bytes(b'current-backend')
    (workspace / 'ZARA_ACTIVE_BUILD.json').write_text(json.dumps({'BUILD_ID': 'unit-current'}))
    (workspace / 'ZARA_ACTIVE_BUILD.txt').write_text(str(current / 'ZARA 3.0.exe'))
    return workspace


@pytest.fixture
def loop(tmp_path, monkeypatch):
    """A whole Lab over one tmp database, plus the real LabV1Service facade."""
    workspace = make_workspace(tmp_path)
    import tools.build_source_candidate as builder_module
    from core.lab_v1 import service as service_module
    from core.lab_v1.candidate_source import CandidateSource

    original_init = CandidateSource.__init__

    def with_python(self, *args, **kwargs):
        kwargs['python_executable'] = Path(sys.executable)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(CandidateSource, '__init__', with_python)
    monkeypatch.setattr(builder_module, 'build_candidate', unit_desktop_builder)
    # No promotion path is exercised, but keep even the read-only build helpers
    # pointed at the sandbox: the real CURRENT must not be readable from here.
    monkeypatch.setattr(build_current, 'ROOT', workspace)
    monkeypatch.setattr(build_current, 'FRONTEND', workspace / 'frontend')
    monkeypatch.setattr(build_current, 'CURRENT', workspace / 'frontend/ZARA CURRENT BUILD')

    adapter = CapabilityFixture()
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(adapter)
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Unit only'))
    for model, role in (('planner', RoleName.CEO), ('builder', RoleName.BUILDER),
                        ('reviewer', RoleName.REVIEWER)):
        registry.record_result('unit-only', model, ProviderResult(True, availability=Availability.AVAILABLE))
        store.save_agent(AgentProfile(model, model, 'unit-only', model, role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership(model, 'team', model))
    policy = WorkforcePolicy({'workspace': str(workspace), 'authorized_models': ['unit-only/*'],
                              'resource_classes': {'unit-only/*': 'OWNER_REPORTED_FREE'}})
    autopilot = Autopilot(runtime, root=tmp_path / 'missions', policy=policy)

    # The product facade, on the same database — this is what IPC talks to.
    monkeypatch.setattr(service_module, 'LabStore', lambda *a, **k: LabStore(tmp_path / 'lab.db'))
    monkeypatch.setattr(service_module, 'default_registry', lambda: registry)
    service = service_module.LabV1Service()

    return {'workspace': workspace, 'store': store, 'runtime': runtime, 'adapter': adapter,
            'autopilot': autopilot, 'policy': policy, 'service': service, 'root': tmp_path}


def observe_the_failed_action(loop):
    """A real ZARA turn fails, through the real IPC seam that reports it."""
    from core.ipc_handlers import IPCHandler

    async def drive():
        handler = IPCHandler.__new__(IPCHandler)
        handler.lab_v1 = loop['service']
        handler._lab_v1_background_tasks = set()
        handler._active_voice_turn_id = 42          # spoken command, not typed
        handler._remember_action_failure(
            FAILING_ACTION, 'executor',
            'brilho continuou em 50 apos a acao: o monitor recusou o passo grande')
        for _ in range(4):
            await asyncio.sleep(0)
        return handler._last_action_failure

    return asyncio.run(drive())


def evolution_engine(loop):
    return EvolutionEngine(loop['runtime'], loop['workspace'], policy=loop['policy'],
                           autopilot=loop['autopilot'])


def test_a_failed_runtime_action_becomes_a_persisted_capability_gap(loop):
    observed = observe_the_failed_action(loop)

    assert observed['action'] == FAILING_ACTION and observed['stage'] == 'executor'
    (gap,) = loop['store'].list_capability_gaps()
    assert gap.required == 'runtime.action.' + FAILING_ACTION
    assert gap.available is False
    detail = json.loads(gap.detail)
    # The gap points at the real executor module, taken from the live registry.
    assert detail['source_path'] == EXECUTOR_PATH
    assert detail['status'] == 'EXECUTOR_FAILED'
    assert detail['channel'] == 'voice' and detail['run_id'] == 'voice:42'


def test_the_gap_starts_a_real_self_improvement_mission(loop):
    observe_the_failed_action(loop)
    engine = evolution_engine(loop)

    started = engine.observe_and_plan()

    assert started['success'] is True and started['state'] == 'QUEUED'
    sid = started['session_id']
    # A real mission exists in the real controller, not a stub receipt.
    mission = loop['autopilot'].controller.snapshot(sid)
    assert mission['state'] == 'QUEUED'
    metrics = loop['autopilot'].metrics(sid)
    assert metrics['mission_kind'] == 'SELF_IMPROVEMENT'
    assert metrics['evidence']['observation_kind'] == 'RUNTIME_CAPABILITY_FAILURE'
    assert metrics['evidence']['capability_gaps'][0]['required'] == 'runtime.action.' + FAILING_ACTION
    # The mission is bound to the observed executor, nothing wider.
    assert metrics['source_work']['source_paths'] == [EXECUTOR_PATH]
    assert metrics['source_work']['allowed_paths'] == [EXECUTOR_PATH, REGRESSION_TEST]
    assert engine.snapshot(sid)['production_activation'] == 'OWNER_APPROVAL_REQUIRED'
    assert engine.snapshot(sid)['source_path'] == EXECUTOR_PATH


def test_the_loop_closes_on_a_reviewed_candidate_and_promotes_nothing(loop):
    observe_the_failed_action(loop)
    engine = evolution_engine(loop)
    sid = engine.observe_and_plan()['session_id']
    baseline = (loop['workspace'] / EXECUTOR_PATH).read_text(encoding='utf-8')

    result = engine.run(sid)

    assert result['state'] == 'COMPLETED', [
        (a.kind, a.body[:400]) for a in loop['store'].list_artifacts(sid)
        if a.kind in ('SOURCE_VERIFICATION', 'REAL_TESTS')]
    meta = loop['autopilot'].metrics(sid)['source_work']
    # Real subprocesses: the capability was missing before the change and present after.
    assert meta['test_evidence']['baseline']['exit_code'] == 1
    assert meta['test_evidence']['candidate']['exit_code'] == 0
    assert meta['change_evidence']['source_files_changed'] == 1
    # Independent review: the reviewer is not the builder and not the planner.
    assert meta['builder_id'] == 'builder' and meta['reviewer_id'] == 'reviewer'
    assert meta['reviewer_id'] != meta['builder_id']
    assert loop['autopilot'].metrics(sid)['planner_id'] not in (meta['builder_id'], meta['reviewer_id'])
    assert loop['autopilot'].metrics(sid)['content_review'] == 'INDEPENDENT_REVIEW_PASSED'
    # The capability exists as a candidate only.
    candidate = Path(meta['sandbox']) / 'source' / EXECUTOR_PATH
    assert 'down_muito' in candidate.read_text(encoding='utf-8')
    assert (Path(meta['sandbox']) / 'source' / REGRESSION_TEST).is_file()
    assert meta['candidate_build']['status'] == 'PACKAGED_RUNTIME_CANDIDATE'
    assert meta['candidate_build']['candidate_status'] == 'VERIFIED_AWAITING_APPROVAL'
    assert meta['candidate_build']['evidence_level'] == 'TEST_ONLY'
    assert meta['candidate_build']['activation'].startswith('FORBIDDEN')
    # Production is byte-identical and no promotion was attempted.
    assert (loop['workspace'] / EXECUTOR_PATH).read_text(encoding='utf-8') == baseline
    assert not (loop['workspace'] / REGRESSION_TEST).exists()
    assert meta['preservation_evidence']['status'] == 'NO_PROMOTION'
    assert meta['preservation_evidence']['matches'] is True
    assert json.loads((loop['workspace'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'unit-current'
    from core.lab_v1.release import ReleaseQueue, pending_promotions
    assert ReleaseQueue(loop['store']).snapshot(sid) is None
    assert pending_promotions(build_current) == []


def test_the_observed_gap_reaches_the_workers_prompt(loop):
    observe_the_failed_action(loop)
    engine = evolution_engine(loop)
    sid = engine.observe_and_plan()['session_id']

    assert engine.run(sid)['state'] == 'COMPLETED'

    builder_prompts = [text for model, text in loop['adapter'].prompts if model == 'builder']
    assert builder_prompts, 'the builder was never asked to implement anything'
    evidence = json.loads(builder_prompts[0].split('OBSERVATION_EVIDENCE: ', 1)[1].splitlines()[0])
    assert evidence['observation_kind'] == 'RUNTIME_CAPABILITY_FAILURE'
    assert evidence['capability_gaps'][0]['detail']['action_id'] == FAILING_ACTION
    assert 'monitor recusou o passo grande' in evidence['capability_gaps'][0]['detail']['reason']


def test_the_same_gap_never_starts_a_second_mission(loop):
    observe_the_failed_action(loop)
    engine = evolution_engine(loop)
    first = engine.observe_and_plan()['session_id']
    assert engine.run(first)['state'] == 'COMPLETED'

    again = engine.observe_and_plan()

    assert again.get('session_id') != first
    assert engine.snapshot(again['session_id'])['observation']['kind'] != 'RUNTIME_CAPABILITY_FAILURE'
    assert [row.id for row in loop['store'].list_sessions()].count(first) == 1
