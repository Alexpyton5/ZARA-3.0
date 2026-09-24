import json
import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import build_current as build
from core.lab_v1.canary import allowed


def _candidate_receipt(sandbox, build, *, relative='core/lab_v1/agent.py',
                       payload=b'after', source_sha='candidate-source'):
    """A package whose receipt, builder, artifacts, manifest and canary agree."""
    staged = sandbox / 'desktop-workspace'
    overlay = staged / relative
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_bytes(payload)
    builder = staged / 'tools' / 'build_candidate.py'
    builder.parent.mkdir(parents=True, exist_ok=True)
    builder.write_text('official builder bytes')
    builder_sha = hashlib.sha256(builder.read_bytes()).hexdigest().upper()
    package = staged / 'frontend' / 'candidate-build'
    paths = build.packaged_paths(package)
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key.encode())
    info = {'BUILD_ID': 'candidate-build', 'EXE_PATH': str(paths['EXE_SHA256']),
            'SOURCE_SHA256': source_sha, 'BUILD_TOOL_SHA256': builder_sha,
            **{key: hashlib.sha256(path.read_bytes()).hexdigest().upper()
               for key, path in paths.items()}}
    build.write_json(package / 'win-unpacked' / 'BUILD_INFO.json', info)
    build.write_json(package / 'SOURCE_MANIFEST.json', {
        'sha256': source_sha,
        'files': [{'path': relative, 'sha256': hashlib.sha256(payload).hexdigest()}],
        'build_tool': {'path': 'tools/build_candidate.py', 'sha256': builder_sha},
    })
    build_receipt = sandbox / 'desktop-build-evidence' / 'official_candidate_build_failed.json'
    build.write_json(build_receipt, {'timeout': False, 'exit_code': 0})
    canary = {'status': 'passed', 'live': False, 'runs': [],
              'asar_sha256': info['ASAR_SHA256'].lower(),
              'backend_sha256': info['BACKEND_SHA256'].lower()}
    canary_path = sandbox / 'desktop-canary' / 'VALIDATION.json'
    build.write_json(canary_path, canary)
    return {
        'status': 'PACKAGED_RUNTIME_CANDIDATE',
        'candidate_status': 'VERIFIED_AWAITING_APPROVAL', 'desktop_package': True,
        'review_evidence': {'verdict': 'PASS'}, 'risk': 'LOW',
        'canary': canary, 'canary_report': str(canary_path),
        'source_sha256': source_sha, 'workspace': str(staged),
        'package': str(package), 'build_id': info['BUILD_ID'],
        'build_tool_sha256': builder_sha, 'build_receipt': str(build_receipt),
        'overlay': [{'path': relative, 'sha256': hashlib.sha256(payload).hexdigest()}],
        **{key.lower().replace('_sha256', '_path'): str(path) for key, path in paths.items()},
        **{key.lower(): hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
    }


@pytest.fixture
def packages(tmp_path, monkeypatch):
    frontend = tmp_path / 'frontend'; frontend.mkdir()
    current = frontend / 'ZARA CURRENT BUILD'
    candidate = frontend / '.current-build-staging-test'
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    monkeypatch.setattr(build, 'FRONTEND', frontend)
    monkeypatch.setattr(build, 'CURRENT', current)
    monkeypatch.setattr(build, 'source_identity', lambda **_: {'sha256': 'source'})
    for folder, tag in ((current, 'old'), (candidate, 'new')):
        paths = build.packaged_paths(folder)
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(tag)
        for name in ('ffmpeg.dll', 'icudtl.dat', 'resources.pak', 'v8_context_snapshot.bin', 'locales/en-US.pak'):
            path = folder / 'win-unpacked' / name; path.parent.mkdir(exist_ok=True); path.touch()
        (folder / 'setup.exe').write_text(tag)
        info = {'BUILD_ID': tag, 'SOURCE_SHA256': 'source', 'INSTALLER_NAME': 'setup.exe',
            'INSTALLER_SHA256': build.digest(folder / 'setup.exe'), **{k: build.digest(p) for k, p in paths.items()}}
        build.write_json(folder / 'win-unpacked/BUILD_INFO.json', info)
        build.write_json(folder / 'SOURCE_MANIFEST.json', {'sha256': 'source'})
    sidecar = tmp_path / 'dist-sidecar/zara-backend.exe'; sidecar.parent.mkdir(); sidecar.write_text('new')
    build.write_json(tmp_path / 'ZARA_ACTIVE_BUILD.json', {'BUILD_ID': 'old'})
    (tmp_path / 'ZARA_ACTIVE_BUILD.txt').write_text('old-pointer')
    validation = tmp_path / 'canary.json'
    build.write_json(validation, {'status': 'passed', 'asar_sha256': build.digest(build.packaged_paths(candidate)['ASAR_SHA256']),
        'backend_sha256': build.digest(build.packaged_paths(candidate)['BACKEND_SHA256'])})
    return tmp_path, current, candidate, validation


def test_activation_and_rollback_preserve_exact_baseline(packages):
    root, current, candidate, validation = packages
    info = build.activate_package(candidate, validation)
    assert build.verify_package(current, check_source=False)['BUILD_ID'] == 'new'
    old = build.rollback_package(Path(info['ROLLBACK_JOURNAL']))
    assert old['BUILD_ID'] == 'old'
    assert build.verify_package(current, check_source=False)['BUILD_ID'] == 'old'
    assert (root / 'ZARA_ACTIVE_BUILD.txt').read_text() == 'old-pointer'
    assert Path(json.loads(Path(info['ROLLBACK_JOURNAL']).read_text())['failed_package']).is_dir()


def test_pointer_failure_restores_old_package(packages, monkeypatch):
    root, current, candidate, validation = packages
    original = build.write_json
    def fail_pointer(path, data):
        if path == root / 'ZARA_ACTIVE_BUILD.json': raise OSError('disk failure')
        original(path, data)
    monkeypatch.setattr(build, 'write_json', fail_pointer)
    with pytest.raises(OSError): build.activate_package(candidate, validation)
    assert build.packaged_paths(current)['ASAR_SHA256'].read_text() == 'old'
    assert candidate.is_dir()
    assert json.loads((root / 'ZARA_ACTIVE_BUILD.json').read_text())['BUILD_ID'] == 'old'


def test_mismatched_canary_never_moves_packages(packages):
    root, current, candidate, validation = packages
    build.write_json(validation, {'status': 'passed', 'asar_sha256': 'wrong', 'backend_sha256': 'wrong'})
    with pytest.raises(ValueError): build.activate_package(candidate, validation)
    assert current.exists() and candidate.exists()


def test_lab_live_canary_requires_isolation_marker(tmp_path, monkeypatch):
    import core.lab_v1.canary as canary
    monkeypatch.setattr(canary.tempfile, 'gettempdir', lambda: str(tmp_path))
    home = tmp_path / 'zara-lab-canaries/one'; home.mkdir(parents=True)
    monkeypatch.setenv('ZARA_LAB_LIVE_CANARY', '1')
    monkeypatch.setenv('ZARA3_HOME', str(home))
    assert allowed('lab-v1-snapshot') and not allowed('lab-v1-autopilot')
    (home / 'CANARY_ONLY').touch()
    assert allowed('lab-v1-autopilot')
    assert not allowed('action-execute') and not allowed('lab-v1-submit') and not allowed('lab-v1-autonomy-configure')
    monkeypatch.setenv('ZARA3_HOME', str(tmp_path))
    assert not allowed('lab-v1-autopilot')


def test_known_good_uses_the_exact_active_build_pointer(packages):
    import core.lab_v1.release as release
    root, current, _, _ = packages
    info_path = current / 'win-unpacked' / 'BUILD_INFO.json'
    info = json.loads(info_path.read_text())
    info['EXE_PATH'] = str(current / 'win-unpacked' / 'ZARA 3.0.exe')
    for key in ('EXE_SHA256', 'ASAR_SHA256', 'BACKEND_SHA256'):
        info[key] = info[key].upper()
    info_path.write_text(json.dumps(info))
    build.write_json(root / 'ZARA_ACTIVE_BUILD.json', info)
    baseline = release.known_good(build)
    assert baseline['available'] is True
    assert baseline['build_id'] == 'old'
    assert Path(baseline['path']) == current


def test_candidate_builder_resolves_official_uppercase_active_hashes(packages):
    from tools.build_source_candidate import _active_build_package

    root, current, _, _ = packages
    info_path = current / 'win-unpacked' / 'BUILD_INFO.json'
    info = json.loads(info_path.read_text())
    info['EXE_PATH'] = str(current / 'win-unpacked' / 'ZARA 3.0.exe')
    for key in ('EXE_SHA256', 'ASAR_SHA256', 'BACKEND_SHA256'):
        info[key] = info[key].upper()
    build.write_json(info_path, info)
    build.write_json(root / 'ZARA_ACTIVE_BUILD.json', info)
    assert _active_build_package(root) == current


def test_candidate_builder_reuses_completed_receipt_without_new_build(packages, monkeypatch, tmp_path):
    from tools import build_source_candidate as candidate_builder

    root, _, _, _ = packages
    sandbox = tmp_path.parent / (tmp_path.name + '-sandbox')
    source_root = sandbox / 'source-root'
    receipt = _candidate_receipt(sandbox, build)
    overlay = receipt['overlay'][0]
    source_file = source_root / overlay['path']
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes((Path(receipt['workspace']) / overlay['path']).read_bytes())
    review = {'verdict': 'PASS', 'reviewer_run_id': 'review-1',
              'evidence_refs': {'artifact_hashes': [overlay['sha256']], 'test_receipt_ids': ['test-1']}}
    receipt['review_evidence'] = review
    (sandbox / 'DESKTOP_CANDIDATE_RECEIPT.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(candidate_builder, '_run', lambda *_args, **_kwargs: pytest.fail('build reran'))
    assert candidate_builder.build_candidate(root, sandbox, source_root,
                                             [overlay['path']], review) == receipt
    assert not (sandbox / 'desktop-workspace-retry-1').exists()


def test_source_promotion_lock_refuses_a_second_writer(tmp_path):
    import core.lab_v1.release as release

    local_build = SimpleNamespace(ROOT=tmp_path)
    with release._promotion_lock(local_build):
        with pytest.raises(ValueError, match='SOURCE_PROMOTION_ALREADY_IN_PROGRESS'):
            with release._promotion_lock(local_build):
                pass


def test_source_promotion_readiness_rejects_out_of_scope_and_traversal(packages, monkeypatch, tmp_path):
    import core.lab_v1.release as release

    root, _, _, _ = packages
    monkeypatch.setattr(release, 'known_good', lambda _build: {'available': True, 'build_id': 'old'})
    monkeypatch.setattr(release, 'pending_promotions', lambda _build: [])
    receipt = _candidate_receipt(tmp_path.parent / (tmp_path.name + '-sandbox'), build)
    receipt['overlay'][0]['path'] = 'core/ipc_handlers.py'
    outside = release.promotion_readiness(receipt, root, build)
    receipt['overlay'][0]['path'] = 'core/lab_v1/../../ZARA_ACTIVE_BUILD.json'
    traversal = release.promotion_readiness(receipt, root, build)
    assert outside['eligible'] is False
    assert outside['reason'] == 'CANDIDATE_OUTSIDE_LAB_SCOPE'
    assert traversal['eligible'] is False
    assert traversal['reason'] == 'CANDIDATE_OVERLAY_PATH_INVALID'


def test_source_promotion_readiness_accepts_only_matching_lab_overlay(packages, monkeypatch, tmp_path):
    import core.lab_v1.release as release

    root, _, _, _ = packages
    monkeypatch.setattr(release, 'known_good', lambda _build: {'available': True, 'build_id': 'old'})
    monkeypatch.setattr(release, 'pending_promotions', lambda _build: [])
    receipt = _candidate_receipt(tmp_path.parent / (tmp_path.name + '-sandbox'), build,
                                 relative='core/lab_v1/improvement.py', payload=b'candidate change')
    readiness = release.promotion_readiness(receipt, root, build)
    assert readiness['eligible'] is True
    assert readiness['known_good']['build_id'] == 'old'


@pytest.mark.parametrize('forgery,reason', [
    ('artifact_path', 'CANDIDATE_ARTIFACT_PATH_MISMATCH'),
    ('build_info', 'CANDIDATE_PACKAGE_IDENTITY_MISMATCH'),
    ('manifest', 'CANDIDATE_PACKAGE_IDENTITY_MISMATCH'),
    ('canary', 'CANDIDATE_CANARY_PACKAGE_MISMATCH'),
    ('builder', 'CANDIDATE_BUILD_TOOL_IDENTITY_MISMATCH'),
])
def test_source_promotion_rejects_forged_package_links(packages, monkeypatch, tmp_path, forgery, reason):
    import core.lab_v1.release as release

    root, _, _, _ = packages
    monkeypatch.setattr(release, 'known_good', lambda _build: {'available': True, 'build_id': 'old'})
    monkeypatch.setattr(release, 'pending_promotions', lambda _build: [])
    sandbox = tmp_path.parent / (tmp_path.name + '-sandbox')
    receipt = _candidate_receipt(sandbox, build)
    package = Path(receipt['package'])
    info_path = package / 'win-unpacked' / 'BUILD_INFO.json'
    info = json.loads(info_path.read_text())
    if forgery == 'artifact_path':
        copied = sandbox / 'same-exe.exe'
        copied.write_bytes(Path(receipt['exe_path']).read_bytes())
        receipt['exe_path'] = str(copied)
    elif forgery == 'build_info':
        info['BUILD_ID'] = 'other-build'
        build.write_json(info_path, info)
    elif forgery == 'manifest':
        manifest_path = package / 'SOURCE_MANIFEST.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['sha256'] = 'other-source'
        build.write_json(manifest_path, manifest)
    elif forgery == 'canary':
        receipt['canary']['asar_sha256'] = '0' * 64
        build.write_json(Path(receipt['canary_report']), receipt['canary'])
    elif forgery == 'builder':
        (Path(receipt['workspace']) / 'tools' / 'build_candidate.py').write_text('changed')
    readiness = release.promotion_readiness(receipt, root, build)
    assert readiness['eligible'] is False
    assert readiness['reason'] == reason


@pytest.mark.parametrize('monitor_behavior', [
    'healthy', 'failed', 'source-drift', 'sidecar-drift', 'sidecar-backup-missing',
    'commit-failed', 'crash-activating',
])
def test_source_promotion_commits_or_fully_rolls_back_active_pointer(tmp_path, monitor_behavior):
    import core.lab_v1.release as release

    root = tmp_path / 'canonical'
    frontend = root / 'frontend'
    source_file = root / 'core' / 'lab_v1' / 'agent.py'
    source_file.parent.mkdir(parents=True)
    source_file.write_text('before')

    def packaged_paths(folder):
        unpacked = Path(folder) / 'win-unpacked'
        return {
            'EXE_SHA256': unpacked / 'ZARA 3.0.exe',
            'ASAR_SHA256': unpacked / 'resources' / 'app.asar',
            'BACKEND_SHA256': unpacked / 'resources' / 'backend' / 'zara-backend.exe',
        }

    def write_json(path, document):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2))

    build = SimpleNamespace(
        ROOT=root, FRONTEND=frontend, packaged_paths=packaged_paths, write_json=write_json,
        source_identity=lambda: {'sha256': hashlib.sha256(source_file.read_bytes()).hexdigest()},
    )

    def make_package(folder, build_id, payload):
        folder = Path(folder)
        paths = packaged_paths(folder)
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        exe = paths['EXE_SHA256']
        info = {'BUILD_ID': build_id, 'EXE_PATH': str(exe),
                **{key: hashlib.sha256(path.read_bytes()).hexdigest()
                   for key, path in paths.items()}}
        info['SOURCE_SHA256'] = build.source_identity()['sha256']
        write_json(exe.parent / 'BUILD_INFO.json', info)
        return info

    old_folder = frontend / 'known-good-build'
    old_info = make_package(old_folder, 'known-good-build', b'old-package')
    write_json(root / 'ZARA_ACTIVE_BUILD.json', old_info)
    (root / 'ZARA_ACTIVE_BUILD.txt').write_text(old_info['EXE_PATH'])
    sidecar = root / 'dist-sidecar' / 'zara-backend.exe'
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b'old-package')

    candidate_source_sha = hashlib.sha256(b'after').hexdigest()
    receipt = _candidate_receipt(tmp_path / 'isolated', build, source_sha=candidate_source_sha)
    candidate_folder = Path(receipt['package'])
    candidate_info = json.loads((candidate_folder / 'win-unpacked' / 'BUILD_INFO.json').read_text())
    canary_path = Path(receipt['canary_report'])

    class Store:
        def __init__(self, path):
            self.path = path

        def _connect(self):
            return sqlite3.connect(self.path)

    queue = release.ReleaseQueue(Store(tmp_path / 'isolated' / 'lab.sqlite'), build=build)
    sid = 'mission-release-test'
    queue.schedule_source_candidate(sid, receipt, root)
    queue.package_ready(sid, candidate_folder, {
        'BUILD_ID': candidate_info['BUILD_ID'], 'SOURCE_SHA256': candidate_info['SOURCE_SHA256'],
        'ASAR_SHA256': candidate_info['ASAR_SHA256'],
        'BACKEND_SHA256': candidate_info['BACKEND_SHA256'],
    })
    queue.accept_canary(sid, canary_path)
    source_promotion = release.SourcePromotion(root, receipt, build=build)
    if monitor_behavior == 'crash-activating':
        source_promotion.activate(candidate_folder, canary_path)
        queue.update(sid, state='ACTIVATING')
        outcome = queue.reconcile_interrupted(sid)
        assert queue.reconcile_interrupted(sid) == outcome
    else:
        def monitor(info):
            if monitor_behavior in {'healthy', 'commit-failed'}:
                return source_promotion.health(info)
            if monitor_behavior == 'source-drift':
                source_file.write_text('user edit after promotion')
            elif monitor_behavior == 'sidecar-drift':
                sidecar.write_text('user edit after promotion')
            elif monitor_behavior == 'sidecar-backup-missing':
                Path(source_promotion.journal['sidecar']['backup']).unlink()
            return False

        def commit(info):
            if monitor_behavior == 'commit-failed':
                raise OSError('simulated journal write failure')
            return source_promotion.commit(info)

        if monitor_behavior in {'source-drift', 'sidecar-drift', 'sidecar-backup-missing', 'commit-failed'}:
            with pytest.raises((ValueError, OSError)):
                queue.promote(sid, activate=source_promotion.activate, monitor=monitor,
                              rollback=source_promotion.rollback, commit=commit)
            if monitor_behavior == 'commit-failed':
                assert queue.snapshot(sid)['state'] == 'COMMIT_PENDING'
                outcome = queue.reconcile_interrupted(sid)
                assert queue.reconcile_interrupted(sid) == outcome
            else:
                assert queue.snapshot(sid)['state'] == 'BLOCKED'
                assert json.loads(source_promotion.journal_path.read_text())['state'] == 'ROLLING_BACK'
                if monitor_behavior == 'source-drift':
                    assert source_file.read_text() == 'user edit after promotion'
                if monitor_behavior == 'sidecar-drift':
                    assert sidecar.read_text() == 'user edit after promotion'
                if monitor_behavior == 'sidecar-backup-missing':
                    assert source_file.read_text() == 'after'
                return
        else:
            outcome = queue.promote(sid, activate=source_promotion.activate, monitor=monitor,
                                    rollback=source_promotion.rollback, commit=commit)

    active = release.known_good(build)
    if monitor_behavior in {'healthy', 'commit-failed'}:
        assert outcome['state'] == 'ACTIVE'
        assert active['build_id'] == 'candidate-build'
        assert source_file.read_text() == 'after'
        journal = json.loads(Path(outcome['rollback_journal']).read_text())
        assert journal['state'] in {'COMMITTED', 'RECONCILED_COMMITTED'}
    else:
        assert outcome['state'] == 'ROLLED_BACK'
        assert active['build_id'] == 'known-good-build'
        assert source_file.read_text() == 'before'
        journal = json.loads(Path(outcome['rollback_journal']).read_text())
        assert journal['state'] in {'ROLLED_BACK', 'RECONCILED_KNOWN_GOOD'}
        quarantine_record = journal.get('candidate_quarantine') or journal['reconciliations'][-1]['candidate_quarantine']
        quarantine = Path(quarantine_record['quarantine_path'])
        assert (quarantine / 'QUARANTINE_MANIFEST.json').is_file()
