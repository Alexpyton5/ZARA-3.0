import json

from core.omnivoice_runtime import OmniVoiceWorkerTTS


def test_omnivoice_is_unavailable_until_its_runtime_and_model_marker_exist(tmp_path):
    runtime = tmp_path / "runtime"
    data = tmp_path / "data"
    python = runtime / "venv" / "Scripts" / "python.exe"
    worker = tmp_path / "omnivoice_worker.py"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"test stub")
    worker.write_text("# test worker", encoding="utf-8")
    engine = OmniVoiceWorkerTTS(runtime_root=runtime, data_root=data, worker_path=worker)

    assert engine.available is False
    marker = data / engine.READY_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"ready": True, "model": "k2-fsa/OmniVoice"}), encoding="utf-8")
    assert engine.available is True


def test_worker_environment_does_not_forward_api_keys_or_tokens(tmp_path):
    safe = OmniVoiceWorkerTTS._worker_environment(
        {
            "PATH": "C:/Windows/System32",
            "SYSTEMROOT": "C:/Windows",
            "GEMINI_API_KEY": "must-not-pass",
            "HF_TOKEN": "must-not-pass",
            "CUSTOM_SECRET": "must-not-pass",
        },
        tmp_path,
    )

    assert safe["PATH"] == "C:/Windows/System32"
    assert safe["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert "GEMINI_API_KEY" not in safe
    assert "HF_TOKEN" not in safe
    assert "CUSTOM_SECRET" not in safe
    assert "TOKENIZERS_PARALLELISM" in safe


def test_runtime_marker_must_match_the_supported_model(tmp_path):
    runtime = tmp_path / "runtime"
    data = tmp_path / "data"
    python = runtime / "venv" / "Scripts" / "python.exe"
    worker = tmp_path / "omnivoice_worker.py"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"test stub")
    worker.write_text("# test worker", encoding="utf-8")
    marker = data / OmniVoiceWorkerTTS.READY_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"ready": True, "model": "different/model"}), encoding="utf-8")

    engine = OmniVoiceWorkerTTS(runtime_root=runtime, data_root=data, worker_path=worker)

    assert engine.available is False
