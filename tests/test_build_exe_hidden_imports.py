"""The frozen sidecar must explicitly pack decorator modules imported at runtime."""

import build_exe
from core.action_registry import ADVANCED_ACTION_MODULES


def test_pyinstaller_hidden_imports_include_runtime_only_modules():
    assert set(ADVANCED_ACTION_MODULES).issubset(set(build_exe.HIDDEN_IMPORTS))
    assert "certifi" in build_exe.HIDDEN_IMPORTS


def test_pyinstaller_collects_certifi_ca_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(build_exe, "BUILD_DIR", tmp_path)
    spec_path = build_exe.create_pyinstaller_spec()

    assert "cacert.pem" in spec_path.read_text(encoding="utf-8")


def test_pyinstaller_no_longer_bundles_omnivoice_worker(monkeypatch, tmp_path):
    # OmniVoice removido (02/10, decisao do Alex): nem o worker vai pro pacote.
    monkeypatch.setattr(build_exe, "BUILD_DIR", tmp_path)
    spec_path = build_exe.create_pyinstaller_spec()
    spec = spec_path.read_text(encoding="utf-8")

    assert "omnivoice_worker.py" not in spec
    assert "OmniVoice.from_pretrained" not in spec


def test_offline_whisper_is_packaged_without_unaudited_vad_weights(monkeypatch, tmp_path):
    monkeypatch.setattr(build_exe, "BUILD_DIR", tmp_path)
    spec = build_exe.create_pyinstaller_spec().read_text(encoding='utf-8')
    assert 'core.whisper_local' in spec
    assert 'ctranslate2.dll' in spec
    assert 'faster_whisper' in spec
    assert 'silero_vad' not in spec
