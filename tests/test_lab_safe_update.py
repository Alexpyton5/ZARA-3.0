import json
from pathlib import Path
import pytest

from core.lab_v1.evolution import WORKFLOW
from core.lab_v1.evolution_repairs import REPAIR_ID, digest
from core.lab_v1.release import ReleaseQueue
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


@pytest.fixture
def release_world(tmp_path):
    workspace = tmp_path / 'workspace'; source = workspace / 'memory/user_memory.py'
    source.parent.mkdir(parents=True); source.write_text('old', encoding='utf-8')
    root = tmp_path / 'state'; candidate = root / 'candidate/user_memory.py'
    baseline = root / 'baseline/user_memory.py'
    candidate.parent.mkdir(parents=True); baseline.parent.mkdir(parents=True)
    candidate.write_text('new', encoding='utf-8'); baseline.write_text('old', encoding='utf-8')
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    store.mission_snapshot = lambda sid: {'session_id': sid, 'state': 'COMPLETED'}
    queue = ReleaseQueue(store, policy=WorkforcePolicy(WorkforcePolicy.default_document()))
    evolution = {'session_id': 'session', 'workflow': WORKFLOW, 'repair_id': REPAIR_ID,
        'state': 'CANDIDATE_VERIFIED', 'build_state': 'PACKAGE_PENDING',
        'source': str(source), 'candidate': str(candidate), 'baseline': str(baseline),
        'before_sha256': digest('old'), 'after_sha256': digest('new')}
    return queue, evolution, workspace, source, tmp_path


def _package(queue, evolution, workspace, tmp_path):
    assert queue.schedule(evolution, workspace)['state'] == 'PACKAGE_PENDING'
    package = tmp_path / 'package'; package.mkdir()
    info = {'BUILD_ID': 'candidate-build', 'SOURCE_SHA256': 'tree-sha',
            'ASAR_SHA256': 'asar', 'BACKEND_SHA256': 'backend'}
    assert queue.package_ready('session', package, info)['state'] == 'CANARY_PENDING'
    validation = tmp_path / 'validation.json'
    validation.write_text(json.dumps({'status': 'passed', 'asar_sha256': 'asar',
                                      'backend_sha256': 'backend'}), encoding='utf-8')
    assert queue.accept_canary('session', validation)['state'] == 'READY_TO_ACTIVATE'
    return package, validation


def test_full_safe_cycle_promotes_only_after_bound_canary(release_world):
    queue, evolution, workspace, source, tmp_path = release_world
    package, validation = _package(queue, evolution, workspace, tmp_path)
    calls = []
    journal = tmp_path / 'rollback.json'; journal.write_text('{}')
    def activate(actual_package, actual_validation):
        calls.append(('activate', actual_package, actual_validation))
        return {'BUILD_ID': 'candidate-build', 'ROLLBACK_JOURNAL': str(journal)}
    result = queue.promote('session', activate=activate,
                           monitor=lambda info: calls.append(('monitor', info['BUILD_ID'])) or True,
                           rollback=lambda path: calls.append(('rollback', path)))
    assert result['state'] == 'ACTIVE' and result['monitored'] is True
    assert calls == [('activate', package.resolve(), validation.resolve()),
                     ('monitor', 'candidate-build')]
    assert source.read_text() == 'old'


def test_monitor_failure_rolls_back_known_good(release_world):
    queue, evolution, workspace, source, tmp_path = release_world
    _package(queue, evolution, workspace, tmp_path)
    journal = tmp_path / 'rollback.json'; journal.write_text('{}')
    rolled_back = []
    result = queue.promote('session',
        activate=lambda *_: {'BUILD_ID': 'candidate-build', 'ROLLBACK_JOURNAL': str(journal)},
        monitor=lambda _: False, rollback=lambda path: rolled_back.append(path))
    assert result['state'] == 'ROLLED_BACK'
    assert rolled_back == [journal]
    assert source.read_text() == 'old'


def test_wrong_canary_or_changed_baseline_never_activates(release_world):
    queue, evolution, workspace, source, tmp_path = release_world
    source.write_text('independent edit', encoding='utf-8')
    with pytest.raises(ValueError, match='baseline changed'):
        queue.schedule(evolution, workspace)

    source.write_text('old', encoding='utf-8')
    queue, evolution, workspace, source, tmp_path = release_world
    assert queue.schedule(evolution, workspace)['state'] == 'PACKAGE_PENDING'
    package = tmp_path / 'package'; package.mkdir()
    queue.package_ready('session', package, {'BUILD_ID': 'b', 'SOURCE_SHA256': 's',
        'ASAR_SHA256': 'asar', 'BACKEND_SHA256': 'backend'})
    bad = tmp_path / 'bad.json'; bad.write_text(json.dumps({'status': 'passed',
        'asar_sha256': 'other', 'backend_sha256': 'backend'}))
    with pytest.raises(ValueError, match='does not identify'):
        queue.accept_canary('session', bad)
    assert queue.snapshot('session')['state'] == 'CANARY_PENDING'
