from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import build_current as current

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_approved_candidate_builder_writes_build_identity() -> None:
    source = (PROJECT_ROOT / 'tools' / 'build_candidate.py').read_text(encoding='utf-8')
    assert '"--full", action="store_true"' in source
    assert '"BUILD_INFO.json"' in source
    assert '"ZARA_ACTIVE_BUILD.json"' in source
    assert '"ZARA_ACTIVE_BUILD.txt"' in source


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(current, "ROOT", tmp_path)
    monkeypatch.setattr(current, "FRONTEND", tmp_path / "frontend")
    monkeypatch.setattr(current, "CURRENT", tmp_path / "frontend" / "ZARA CURRENT BUILD")
    (tmp_path / "main.py").write_text("print('current')", encoding="utf-8")
    result = tmp_path / "frontend" / ".current-build-staging-test"
    paths = current.packaged_paths(result)
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    for essential in ("ffmpeg.dll", "icudtl.dat", "resources.pak", "v8_context_snapshot.bin", "locales/en-US.pak"):
        path = result / "win-unpacked" / essential
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime")
    sidecar = tmp_path / "dist-sidecar" / "zara-backend.exe"
    sidecar.parent.mkdir()
    sidecar.write_bytes(paths["BACKEND_SHA256"].read_bytes())
    installer = result / "ZARA 3.0 Setup 3.0.0.exe"
    installer.write_bytes(b"installer")
    source = current.source_identity()
    info = {"BUILD_ID": "test-build", "SOURCE_SHA256": source["sha256"],
            "INSTALLER_NAME": installer.name, "INSTALLER_SHA256": current.digest(installer),
            **{key: current.digest(path) for key, path in paths.items()}}
    current.write_json(result / "SOURCE_MANIFEST.json", source)
    current.write_json(result / "win-unpacked" / "BUILD_INFO.json", info)
    return result


def test_package_verifies_source_and_all_primary_artifacts(package: Path) -> None:
    assert current.verify_package(package)["BUILD_ID"] == "test-build"
    current.packaged_paths(package)["ASAR_SHA256"].write_bytes(b"old frontend")
    with pytest.raises(ValueError, match="artifact"):
        current.verify_package(package)


def test_changed_source_prevents_activation(package: Path) -> None:
    (current.ROOT / "main.py").write_text("print('newer')", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        current.activate_package(package, current.ROOT / "validation.json")
    assert package.exists()
    assert not (current.ROOT / "ZARA_ACTIVE_BUILD.json").exists()


def test_validation_of_different_binary_cannot_activate(package: Path) -> None:
    validation = current.ROOT / "validation.json"
    current.write_json(validation, {"status": "passed", "asar_sha256": "wrong", "backend_sha256": "wrong"})
    with pytest.raises(ValueError, match="validation"):
        current.activate_package(package, validation)
    assert package.exists()
    assert not current.CURRENT.exists()


def test_activation_preserves_previous_package_and_writes_agreeing_pointers(package: Path) -> None:
    info = current.verify_package(package)
    previous_paths = current.packaged_paths(current.CURRENT)
    for key, path in previous_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'previous-{key}'.encode())
    current.write_json(
        current.CURRENT / 'win-unpacked' / 'BUILD_INFO.json',
        {key: current.digest(path) for key, path in previous_paths.items()},
    )
    previous = current.CURRENT / "previous.txt"
    previous.write_text("previous package", encoding="utf-8")
    validation = current.ROOT / "validation.json"
    current.write_json(validation, {"status": "passed", "asar_sha256": info["ASAR_SHA256"], "backend_sha256": info["BACKEND_SHA256"]})
    activated = current.activate_package(package, validation)
    assert current.verify_package(current.CURRENT)["STATUS"] == "active-validated"
    assert list((current.FRONTEND / ".build-backups").glob("*/previous.txt"))
    assert not package.exists()
    assert json.loads((current.ROOT / "ZARA_ACTIVE_BUILD.json").read_text())["EXE_PATH"] == activated["EXE_PATH"]
    assert (current.ROOT / "ZARA_ACTIVE_BUILD.txt").read_text().strip() == activated["EXE_PATH"]
    assert current.digest(current.CURRENT / "VALIDATION.json") == activated["VALIDATION_SHA256"]


def test_paths_outside_build_area_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside frontend"):
        current.confined_package(tmp_path)


def test_run_streams_both_outputs_and_appends_incremental_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "build-current.log"
    monkeypatch.setattr(current, "ROOT", tmp_path)
    monkeypatch.setenv("ZARA_BUILD_LOG", str(log))
    result = current.run([__import__("sys").executable, "-c", "import sys; print('out', flush=True); print('err', file=sys.stderr, flush=True)"], cwd=tmp_path, timeout_seconds=5, heartbeat_seconds=0.1, stage="diagnostic-stream")
    assert set(result.splitlines()) == {"out", "err"}
    captured = capsys.readouterr().out
    logged = log.read_text(encoding="utf-8")
    assert "[HEARTBEAT] stage=diagnostic-stream status=started" in captured
    assert "[stdout] out" in logged and "[stderr] err" in logged
    assert "[DONE] stage=diagnostic-stream" in logged


def test_run_reports_observable_timeout_in_incremental_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "timeout.log"
    monkeypatch.setattr(current, "ROOT", tmp_path)
    monkeypatch.setenv("ZARA_BUILD_LOG", str(log))
    with pytest.raises(TimeoutError, match="timed out"):
        current.run([__import__("sys").executable, "-c", "import time; time.sleep(2)"], cwd=tmp_path, timeout_seconds=0.2, heartbeat_seconds=0.05, stage="diagnostic-timeout")
    logged = log.read_text(encoding="utf-8")
    assert "[HEARTBEAT] stage=diagnostic-timeout" in logged
    assert "[TIMEOUT] stage=diagnostic-timeout" in logged
