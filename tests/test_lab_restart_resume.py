"""A real Lab process is killed mid-mission and a new process resumes it.

The first process is a genuine child interpreter: it starts a real source
mission, runs real subprocess tests and is destroyed with ``os._exit`` at a
chosen point, leaving its lease held and its step DISPATCHED. The parent then
builds a brand new store/controller/autopilot over the same database — that is
the restart — and must find the same mission, reconcile it from durable
evidence only, and never start a second one.

Everything lives in tmp_path. No production workspace, package or pointer is
referenced.
"""
import json
import subprocess
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
from core.lab_v1.mission_controller import owner_is_alive, process_identity
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from tests.test_lab_source_mission import UnitReasoningFixture

REPOSITORY = str(Path(__file__).resolve().parents[1])
INTENT = 'Corrija a ZARA core/example.py: twice deve duplicar também negativos.'


def make_workspace(root: Path) -> Path:
    """Fake workspace with a fake CURRENT build, identical in both processes."""
    workspace = root / 'workspace'
    if workspace.exists():
        return workspace
    (workspace / 'core').mkdir(parents=True)
    (workspace / 'memory').mkdir()
    (workspace / 'core/__init__.py').touch()
    (workspace / 'core/example.py').write_text('def twice(n):\n    return n + 2\n')
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


def unit_desktop_builder(workspace, sandbox, source_root, allowed_paths, review_evidence, **kwargs):
    import hashlib
    package = Path(sandbox) / 'unit-desktop-package'
    resources = package / 'win-unpacked' / 'resources'
    resources.mkdir(parents=True, exist_ok=True)
    exe, asar = package / 'win-unpacked' / 'ZARA 3.0.exe', resources / 'app.asar'
    backend = resources / 'backend' / 'zara-backend.exe'
    backend.parent.mkdir(exist_ok=True)
    for path, body in ((exe, b'unit-exe'), (asar, b'unit-asar'), (backend, b'unit-backend')):
        path.write_bytes(body)
    canary_path = Path(sandbox) / 'desktop-canary' / 'VALIDATION.json'
    canary_path.parent.mkdir(exist_ok=True)
    canary = {'status': 'passed', 'live': False, 'runs': [], 'fixture': 'UNIT_ONLY'}
    canary_path.write_text(json.dumps(canary))

    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    return {
        'status': 'PACKAGED_RUNTIME_CANDIDATE', 'package': str(package),
        'candidate_status': 'VERIFIED_AWAITING_APPROVAL', 'desktop_package': True,
        'workspace': str(Path(sandbox) / 'desktop-workspace'), 'source_sha256': '0' * 64,
        'overlay': [{'path': path, 'sha256': digest(Path(source_root) / path)} for path in allowed_paths],
        'review_evidence': review_evidence,
        'exe_path': str(exe), 'exe_sha256': digest(exe),
        'asar_path': str(asar), 'asar_sha256': digest(asar),
        'backend_path': str(backend), 'backend_sha256': digest(backend), 'build_id': 'UNIT-ONLY',
        'canary_report': str(canary_path), 'canary': canary,
        'activation': 'FORBIDDEN_UNTIL_CANONICAL_SOURCE_PROMOTION_AND_REBUILD',
        'evidence_level': 'TEST_ONLY',
    }


def install_seams(patch=None):
    """Same deterministic seams in both processes: unit models, no real build."""
    import tools.build_source_candidate as builder
    from core.lab_v1.candidate_source import CandidateSource
    original = CandidateSource.__init__

    def with_python(self, *args, **kwargs):
        kwargs['python_executable'] = Path(sys.executable)
        original(self, *args, **kwargs)

    if patch is None:
        CandidateSource.__init__ = with_python
        builder.build_candidate = unit_desktop_builder
    else:
        patch.setattr(CandidateSource, '__init__', with_python)
        patch.setattr(builder, 'build_candidate', unit_desktop_builder)


def build_engine(root: Path, patch=None) -> Autopilot:
    """Construct a complete Lab over root/lab.db — this is one 'process boot'."""
    workspace = make_workspace(root)
    install_seams(patch)
    registry = ProviderRegistry(root / 'health.json')
    registry.register(UnitReasoningFixture())
    store = LabStore(root / 'lab.db')
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Unit only'))
    for model, role in (('planner', RoleName.CEO), ('builder', RoleName.BUILDER),
                        ('reviewer', RoleName.REVIEWER)):
        registry.record_result('unit-only', model, ProviderResult(True, availability=Availability.AVAILABLE))
        store.save_agent(AgentProfile(model, model, 'unit-only', model, role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership(model, 'team', model))
    policy = WorkforcePolicy({'workspace': str(workspace), 'authorized_models': ['unit-only/*'],
                              'resource_classes': {'unit-only/*': 'OWNER_REPORTED_FREE'}})
    return Autopilot(runtime, root=root / 'missions', policy=policy)


CHILD = '''
import json, os, sys
sys.path.insert(0, {repository!r})
from pathlib import Path
root = Path(sys.argv[1])
kill_at = sys.argv[2]
from tests.test_lab_restart_resume import build_engine, INTENT
from core.lab_v1.candidate_source import CandidateSource
from core.lab_v1.store import LabStore

if kill_at == 'AFTER_DURABLE_RECEIPT':
    original = LabStore.save_artifact
    def kill_after_artifact(self, artifact):
        result = original(self, artifact)
        if artifact.kind == 'SOURCE_DIFF':
            (root / 'killed.json').write_text(json.dumps({{'pid': os.getpid(), 'at': kill_at}}))
            os._exit(9)
        return result
    LabStore.save_artifact = kill_after_artifact
else:
    original = CandidateSource.apply_edits
    def kill_before_artifact(self, edits):
        result = original(self, edits)
        (root / 'killed.json').write_text(json.dumps({{'pid': os.getpid(), 'at': kill_at}}))
        os._exit(9)
    CandidateSource.apply_edits = kill_before_artifact

engine = build_engine(root)
session = engine.start(INTENT)
(root / 'session.json').write_text(json.dumps(session))
engine.run(session['session_id'])
(root / 'never.json').write_text('the child was supposed to die')
'''


def crash_a_real_lab_process(root: Path, kill_at: str) -> dict:
    script = root / 'child_lab.py'
    script.write_text(CHILD.format(repository=REPOSITORY), encoding='utf-8')
    completed = subprocess.run([sys.executable, str(script), str(root), kill_at],
                               capture_output=True, text=True, timeout=300)
    assert completed.returncode == 9, (completed.returncode, completed.stdout[-3000:], completed.stderr[-3000:])
    assert not (root / 'never.json').exists()
    return {'session': json.loads((root / 'session.json').read_text()),
            'killed': json.loads((root / 'killed.json').read_text())}


def mission_row(engine, sid):
    with engine.store._connect() as conn:
        row = conn.execute('SELECT lease_token, lease_until, lease_owner FROM mission_controls '
                           'WHERE session_id=?', (sid,)).fetchone()
    return {'token': row[0], 'until': row[1],
            'owner': json.loads(row[2]) if row[2] else None}


@pytest.fixture
def restarted(tmp_path, monkeypatch, request):
    """Kill a real Lab process, then boot a completely new one on its database."""
    crashed = crash_a_real_lab_process(tmp_path, request.param)
    sid = crashed['session']['session_id']
    engine = build_engine(tmp_path, monkeypatch)  # <- the restart
    return {'engine': engine, 'sid': sid, 'crashed': crashed, 'root': tmp_path}


@pytest.mark.parametrize('restarted', ['AFTER_DURABLE_RECEIPT'], indirect=True)
def test_restart_resumes_the_same_mission_from_its_durable_receipt(restarted):
    engine, sid = restarted['engine'], restarted['sid']
    before = engine.controller.snapshot(sid)
    held = mission_row(engine, sid)
    step = next(item for item in before['steps'] if item['capability'] == 'source.apply')
    change_evidence = engine.metrics(sid)['source_work']['change_evidence']
    runs_before = [(run.id, run.state.value) for run in engine.store.list_runs(sid)]
    artifacts_before = [item.id for item in engine.store.list_artifacts(sid)]

    # The dead process still holds a valid lease, and the step is mid-flight.
    assert step['status'] == 'DISPATCHED' and step['receipt'] is None
    assert held['token'] is not None and held['until'] > engine.controller.clock()
    assert held['owner']['pid'] == restarted['crashed']['killed']['pid']
    assert owner_is_alive(held['owner']) is False
    assert owner_is_alive(process_identity()) is True

    result = engine.run(sid)

    assert result['state'] == 'COMPLETED'
    after = engine.controller.snapshot(sid)
    resumed = next(item for item in after['steps'] if item['capability'] == 'source.apply')
    # Recovered from the receipt the dead process had already persisted; the
    # file effect was never replayed.
    assert resumed['reconciliation'] == {
        'verdict': 'APPLIED',
        'evidence_ref': 'source-recovery:SOURCE_DIFF:' + step['attempt_id']}
    assert resumed['receipt']['artifact_ref'] == 'SOURCE_DIFF:' + step['attempt_id']
    assert engine.metrics(sid)['source_work']['change_evidence'] == change_evidence
    # Same mission: no second session, no new plan, no lost history.
    assert [row.id for row in engine.store.list_sessions()] == [sid]
    assert after['session_id'] == before['session_id']
    assert after['plan_version'] == before['plan_version']
    assert after['deadline'] == before['deadline']
    assert [item['id'] for item in after['steps']] == [item['id'] for item in before['steps']]
    assert after['restarts'][0]['reclaimed_lease_owner'] == held['owner']
    assert after['restarts'][0]['reclaimed_by']['pid'] == process_identity()['pid']
    assert engine.metrics(sid)['source_work']['repair_count'] == 0
    assert engine.metrics(sid)['source_work']['counterexamples'] == []
    # Evidence from the dead process is preserved, never rewritten.
    runs_after = [(run.id, run.state.value) for run in engine.store.list_runs(sid)]
    assert runs_after[:len(runs_before)] == runs_before
    assert [item.id for item in engine.store.list_artifacts(sid)][:len(artifacts_before)] == artifacts_before


@pytest.mark.parametrize('restarted', ['BEFORE_DURABLE_RECEIPT'], indirect=True)
def test_restart_refuses_to_replay_an_effect_it_cannot_prove(restarted):
    engine, sid = restarted['engine'], restarted['sid']
    before = engine.controller.snapshot(sid)
    step = next(item for item in before['steps'] if item['capability'] == 'source.apply')
    sandbox = Path(engine.metrics(sid)['source_work']['sandbox'])
    edited = (sandbox / 'source' / 'core' / 'example.py').read_text()

    result = engine.run(sid)

    # The edit happened on disk but no receipt was ever bound to the attempt:
    # the mission stops on UNCERTAIN_EFFECT instead of running it again.
    assert edited.endswith('return n * 2\n')
    assert result['state'] == 'BLOCKED'
    assert engine.controller.snapshot(sid)['blocker'] == 'UNCERTAIN_EFFECT'
    stopped = next(item for item in engine.controller.snapshot(sid)['steps']
                   if item['capability'] == 'source.apply')
    assert stopped['status'] == 'RECONCILE'
    assert stopped['reconciliation']['verdict'] == 'UNKNOWN'
    assert stopped['receipt'] is None
    assert 'no-durable-bound-receipt' in stopped['reconciliation']['evidence_ref']
    assert [row.id for row in engine.store.list_sessions()] == [sid]
    assert 'change_evidence' not in engine.metrics(sid)['source_work']
    assert not any(artifact.id == 'SOURCE_DIFF:' + step['attempt_id']
                   for artifact in engine.store.list_artifacts(sid))


def test_a_live_owner_never_loses_its_lease(tmp_path, monkeypatch):
    engine = build_engine(tmp_path, monkeypatch)
    session = engine.start(INTENT)
    sid = session['session_id']
    token = engine.controller._claim(sid)
    assert token is not None

    assert engine.controller.release_dead_leases() == []

    held = mission_row(engine, sid)
    assert held['token'] == token
    assert held['owner'] == process_identity()
    # An owner on another host, or one we cannot inspect, is also left alone.
    assert owner_is_alive({'host': 'another-machine', 'pid': 1, 'started_at': 1.0}) is True
    assert owner_is_alive(None) is True
    assert owner_is_alive({'host': process_identity()['host']}) is True
