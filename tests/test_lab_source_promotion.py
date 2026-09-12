"""Isolated proof of transactional source promotion and automatic rollback.

Every path here lives in tmp_path; the owner's real CURRENT build, pointers and
source tree are never referenced.
"""
import hashlib
import json
from pathlib import Path

import pytest

from core.lab_v1 import release as release_module
from core.lab_v1.release import ReleaseQueue, SourcePromotion, known_good, promotion_readiness
from core.lab_v1.store import LabStore
from tools import build_current as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_package(folder, tag, source_sha):
    paths = build.packaged_paths(folder)
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tag + '-' + key)
    for name in ('ffmpeg.dll', 'icudtl.dat', 'resources.pak', 'v8_context_snapshot.bin', 'locales/en-US.pak'):
        path = folder / 'win-unpacked' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (folder / 'setup.exe').write_text(tag)
    info = {'BUILD_ID': tag, 'SOURCE_SHA256': source_sha, 'INSTALLER_NAME': 'setup.exe',
            'INSTALLER_SHA256': build.digest(folder / 'setup.exe'),
            **{key: build.digest(path) for key, path in paths.items()}}
    build.write_json(folder / 'win-unpacked/BUILD_INFO.json', info)
    build.write_json(folder / 'SOURCE_MANIFEST.json', {'sha256': source_sha})
    return info


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """known-good A active; candidate B built from a changed sandbox source."""
    root = tmp_path / 'workspace'
    frontend = root / 'frontend'
    frontend.mkdir(parents=True)
    current = frontend / 'ZARA CURRENT BUILD'
    (root / 'core').mkdir()
    (root / 'core' / 'example.py').write_text('def twice(n):\n    return n + 2\n')
    (root / 'tests').mkdir()
    sidecar = root / 'dist-sidecar' / 'zara-backend.exe'
    sidecar.parent.mkdir()
    sidecar.write_text('A-BACKEND_SHA256')

    monkeypatch.setattr(build, 'ROOT', root)
    monkeypatch.setattr(build, 'FRONTEND', frontend)
    monkeypatch.setattr(build, 'CURRENT', current)

    # Deterministic stand-in for the real workspace source identity.
    def source_identity(backend_only=False):
        files = sorted(p for folder in ('core', 'tests') for p in (root / folder).rglob('*.py'))
        payload = json.dumps([[p.relative_to(root).as_posix(), sha(p)] for p in files]).encode()
        return {'sha256': hashlib.sha256(payload).hexdigest(), 'files': []}
    monkeypatch.setattr(build, 'source_identity', source_identity)

    source_a = source_identity()['sha256']
    make_package(current, 'A', source_a)
    build.write_json(root / 'ZARA_ACTIVE_BUILD.json', {'BUILD_ID': 'A'})
    (root / 'ZARA_ACTIVE_BUILD.txt').write_text('A-pointer\n')

    # Candidate B: isolated staged projection with the changed source.
    staged = tmp_path / 'sandbox' / 'desktop-workspace'
    (staged / 'core').mkdir(parents=True)
    (staged / 'tests').mkdir()
    (staged / 'core' / 'example.py').write_text('def twice(n):\n    return n * 2\n')
    (staged / 'tests' / 'test_regression.py').write_text('def test_x():\n    assert True\n')
    overlay = [{'path': p, 'sha256': sha(staged / p)}
               for p in ('core/example.py', 'tests/test_regression.py')]

    # Source identity B = workspace A with the candidate overlay applied.
    saved = {p: (root / p).read_text() if (root / p).is_file() else None for p in ('core/example.py', 'tests/test_regression.py')}
    for item in overlay:
        target = root.joinpath(*Path(item['path']).parts)
        target.write_text((staged / item['path']).read_text())
    source_b = source_identity()['sha256']
    for path, value in saved.items():
        target = root / path
        if value is None:
            target.unlink()
        else:
            target.write_text(value)
    assert source_identity()['sha256'] == source_a

    package = tmp_path / 'sandbox' / 'candidate-package'
    package_info = make_package(package, 'B', source_b)
    (package / 'win-unpacked' / 'resources' / 'backend' / 'zara-backend.exe').write_text('B-BACKEND_SHA256')
    canary_path = tmp_path / 'sandbox' / 'desktop-canary' / 'VALIDATION.json'
    canary_path.parent.mkdir(parents=True)
    canary = {'status': 'passed', 'live': False, 'runs': [],
              'asar_sha256': package_info['ASAR_SHA256'], 'backend_sha256': package_info['BACKEND_SHA256']}
    build.write_json(canary_path, canary)
    paths = build.packaged_paths(package)
    receipt = {
        'status': 'PACKAGED_RUNTIME_CANDIDATE', 'candidate_status': 'VERIFIED_AWAITING_APPROVAL',
        'desktop_package': True, 'risk': 'LOW', 'package': str(package), 'workspace': str(staged),
        'source_sha256': source_b, 'overlay': overlay, 'build_id': 'B',
        'review_evidence': {'verdict': 'PASS', 'rationale': 'isolated fixture',
                            'evidence_refs': {'artifact_hashes': [i['sha256'] for i in overlay],
                                              'test_receipt_ids': ['r1']},
                            'reviewer_run_id': 'run-1'},
        'exe_path': str(paths['EXE_SHA256']), 'exe_sha256': build.digest(paths['EXE_SHA256']),
        'asar_path': str(paths['ASAR_SHA256']), 'asar_sha256': build.digest(paths['ASAR_SHA256']),
        'backend_path': str(paths['BACKEND_SHA256']), 'backend_sha256': build.digest(paths['BACKEND_SHA256']),
        'canary_report': str(canary_path), 'canary': canary,
    }
    return {'root': root, 'current': current, 'receipt': receipt, 'canary': canary_path,
            'source_a': source_a, 'source_b': source_b, 'sidecar': sidecar,
            'store': LabStore(tmp_path / 'lab.db')}


def queued(lab, sid='s1'):
    queue = ReleaseQueue(lab['store'])
    queue.schedule_source_candidate(sid, lab['receipt'], lab['root'])
    receipt = lab['receipt']
    queue.package_ready(sid, receipt['package'], {
        'BUILD_ID': receipt['build_id'], 'SOURCE_SHA256': receipt['source_sha256'],
        'ASAR_SHA256': receipt['asar_sha256'], 'BACKEND_SHA256': receipt['backend_sha256']})
    queue.accept_canary(sid, lab['canary'])
    return queue


def test_readiness_refuses_unverified_or_unreviewed_candidates(lab):
    assert promotion_readiness(lab['receipt'], lab['root'])['eligible'] is True
    for change, reason in (({'candidate_status': 'DRAFT'}, 'CANDIDATE_NOT_VERIFIED'),
                           ({'review_evidence': {'verdict': 'FAIL'}}, 'INDEPENDENT_REVIEW_NOT_PASSED'),
                           ({'risk': 'MEDIUM'}, 'CANDIDATE_RISK_NOT_LOW'),
                           ({'canary': {'status': 'failed', 'live': False, 'runs': []}}, 'PACKAGED_CANARY_NOT_PASSED')):
        assert promotion_readiness(dict(lab['receipt'], **change), lab['root'])['reason'] == reason


def test_readiness_refuses_when_candidate_bytes_drifted(lab):
    Path(lab['receipt']['asar_path']).write_text('tampered')
    assert promotion_readiness(lab['receipt'], lab['root'])['reason'] == 'CANDIDATE_ARTIFACT_DRIFT'


def test_scenario_a_promotion_is_transactional_and_healthy(lab):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    before = known_good()
    assert before['build_id'] == 'A'

    doc = queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                        rollback=promotion.rollback, commit=promotion.commit)

    assert doc['state'] == 'ACTIVE' and doc['build_id'] == 'B'
    # Runtime pointers, package, source and sidecar are all B.
    assert build.verify_package(lab['current'])['BUILD_ID'] == 'B'
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'B'
    assert (lab['root'] / 'core/example.py').read_text() == 'def twice(n):\n    return n * 2\n'
    assert (lab['root'] / 'tests/test_regression.py').is_file()
    assert build.source_identity()['sha256'] == lab['source_b']
    assert sha(lab['sidecar']) == lab['receipt']['backend_sha256']
    # The known-good A package was retained, not deleted.
    journal = json.loads(Path(promotion.journal_path).read_text())
    assert journal['state'] == 'COMMITTED'
    assert journal['before_source_sha256'] == lab['source_a']
    assert Path(json.loads(Path(journal['build_journal']).read_text())['backup']).is_dir()


def test_scenario_b_failed_health_rolls_back_to_known_good(lab):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    observed = {}

    def failing_health(info):
        observed['during'] = {'build_id': known_good()['build_id'],
                              'source': build.source_identity()['sha256']}
        return False

    doc = queue.promote('s1', activate=promotion.activate, monitor=failing_health,
                        rollback=promotion.rollback)

    assert observed['during'] == {'build_id': 'B', 'source': lab['source_b']}
    assert doc['state'] == 'ROLLED_BACK' and doc['error'] == 'POST_ACTIVATION_MONITOR_FAILED'
    # Everything is A again, from the same known-good: source, sidecar, package, pointers.
    assert build.source_identity()['sha256'] == lab['source_a']
    assert (lab['root'] / 'core/example.py').read_text() == 'def twice(n):\n    return n + 2\n'
    assert not (lab['root'] / 'tests/test_regression.py').exists()
    assert sha(lab['sidecar']) == hashlib.sha256(b'A-BACKEND_SHA256').hexdigest()
    assert build.verify_package(lab['current'])['BUILD_ID'] == 'A'
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'A'
    assert (lab['root'] / 'ZARA_ACTIVE_BUILD.txt').read_text() == 'A-pointer\n'
    assert json.loads(Path(promotion.journal_path).read_text())['state'] == 'ROLLED_BACK'


def test_pointer_failure_during_activation_restores_source_and_package(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    original = build.write_json

    def fail_pointer(path, data):
        if Path(path) == lab['root'] / 'ZARA_ACTIVE_BUILD.json':
            raise OSError('disk failure')
        original(path, data)
    monkeypatch.setattr(build, 'write_json', fail_pointer)

    with pytest.raises(OSError):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)

    assert queue.snapshot('s1')['state'] == 'BLOCKED'
    assert build.source_identity()['sha256'] == lab['source_a']
    assert sha(lab['sidecar']) == hashlib.sha256(b'A-BACKEND_SHA256').hexdigest()
    assert build.verify_package(lab['current'])['BUILD_ID'] == 'A'
    assert json.loads((lab['root'] / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'A'


def test_source_drift_blocks_activation_before_any_pointer_moves(lab, monkeypatch):
    queue = queued(lab)
    promotion = SourcePromotion(lab['root'], lab['receipt'])
    # A new build is required when the workspace no longer matches the candidate.
    (lab['root'] / 'core' / 'other.py').write_text('# drift after packaging\n')

    with pytest.raises(ValueError, match='PROMOTED_SOURCE_DOES_NOT_MATCH_CANDIDATE'):
        queue.promote('s1', activate=promotion.activate, monitor=promotion.health,
                      rollback=promotion.rollback)

    assert build.verify_package(lab['current'], check_source=False)['BUILD_ID'] == 'A'
    assert (lab['root'] / 'core/example.py').read_text() == 'def twice(n):\n    return n + 2\n'
    assert json.loads(Path(promotion.journal_path).read_text())['state'] == 'ACTIVATION_FAILED_RESTORED'


def test_release_module_never_hardcodes_the_owner_current_build():
    text = Path(release_module.__file__).read_text(encoding='utf-8')
    assert 'ZARA CURRENT BUILD' not in text
