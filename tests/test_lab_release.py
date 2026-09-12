import json
from pathlib import Path
import pytest
from tools import build_current as build
from core.lab_v1.canary import allowed


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
