from __future__ import annotations

import hashlib
import json
import os
import runpy
from pathlib import Path

import pytest

from tools.build_manifest import ManifestError, generate_manifest, main, verify_manifest


def test_manifest_is_deterministic_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "zara.exe").write_bytes(b"binary")
    (tmp_path / "README.md").write_text("ZARA", encoding="utf-8")

    first = generate_manifest(tmp_path, ["dist/zara.exe", "README.md"])
    second = generate_manifest(tmp_path, ["README.md", "dist\\zara.exe"])

    assert first == second
    assert [item["path"] for item in first["artifacts"]] == ["dist/zara.exe", "README.md"]


@pytest.mark.parametrize(
    "path",
    ["../secret.txt", "C:/ordinary.txt", "/secret.txt", "snapshots/zara.zip", ".pytest_cache/x", ".env"],
)
def test_forbidden_or_escaping_paths_are_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(ManifestError):
        generate_manifest(tmp_path, [path])


def test_probable_secret_content_is_rejected_without_leaking_value(tmp_path: Path) -> None:
    secret_value = "ultra-private-value-123456"
    (tmp_path / "settings.json").write_text(
        json.dumps({"api_key": secret_value}), encoding="utf-8"
    )

    with pytest.raises(ManifestError) as exc_info:
        generate_manifest(tmp_path, ["settings.json"])
    assert secret_value not in str(exc_info.value)


def test_placeholder_config_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "settings.json").write_text(
        json.dumps({"api_key": "${ZARA_API_KEY}"}), encoding="utf-8"
    )
    assert generate_manifest(tmp_path, ["settings.json"])["artifacts"][0]["path"] == "settings.json"


def test_verify_detects_changed_file(tmp_path: Path) -> None:
    artifact = tmp_path / "zara.exe"
    artifact.write_bytes(b"version-one")
    manifest = generate_manifest(tmp_path, ["zara.exe"])
    artifact.write_bytes(b"version-two")

    report = verify_manifest(tmp_path, manifest)

    assert report == {"verdict": "failed", "missing": [], "changed": ["zara.exe"], "checked": 1}


def test_verify_reports_all_missing_and_changed_files(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"a")
    (tmp_path / "b.bin").write_bytes(b"b")
    manifest = generate_manifest(tmp_path, ["a.bin", "b.bin"])
    (tmp_path / "a.bin").unlink()
    (tmp_path / "b.bin").write_bytes(b"changed")

    report = verify_manifest(tmp_path, manifest)

    assert report["missing"] == ["a.bin"]
    assert report["changed"] == ["b.bin"]


def test_verify_rejects_tampered_manifest_shape(tmp_path: Path) -> None:
    (tmp_path / "file.bin").write_bytes(b"x")
    manifest = generate_manifest(tmp_path, ["file.bin"])
    manifest["artifacts"][0]["extra"] = "untrusted"
    with pytest.raises(ManifestError, match="entrada"):
        verify_manifest(tmp_path, manifest)


def test_symlink_is_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = tmp_path / "link.bin"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink sem privilegio neste Windows")
    with pytest.raises(ManifestError, match="simbolico"):
        generate_manifest(tmp_path, ["link.bin"])


def test_cli_create_and_verify(tmp_path: Path, capsys) -> None:
    (tmp_path / "zara.bin").write_bytes(b"release")
    output = tmp_path / "manifest.json"
    assert main(["create", "--root", str(tmp_path), "--allow", "zara.bin", "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "created"

    assert main(["verify", "--root", str(tmp_path), "--manifest", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "ok"


def test_sidecar_build_manifests_use_path_relative_to_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import build_exe

    sidecar = tmp_path / "dist-sidecar" / "zara-backend.exe"
    sidecar.parent.mkdir()
    payload = b"sidecar-release"
    sidecar.write_bytes(payload)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", tmp_path)

    build_exe.update_sidecar_manifests(sidecar)

    expected = f"{hashlib.sha256(payload).hexdigest()}  dist-sidecar/zara-backend.exe\n"
    assert (tmp_path / "SHA256_MANIFEST.txt").read_bytes() == expected.encode()
    assert (tmp_path / "PATCH_SHA256_MANIFEST.txt").read_bytes() == expected.encode()


def test_update_manifest_script_uses_path_relative_to_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = tmp_path / "dist-sidecar" / "zara-backend.exe"
    sidecar.parent.mkdir()
    payload = b"sidecar-release"
    sidecar.write_bytes(payload)
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(Path(__file__).parents[1] / "update_manifest.py"), run_name="__main__")

    expected = f"{hashlib.sha256(payload).hexdigest()}  dist-sidecar/zara-backend.exe\n"
    assert (tmp_path / "SHA256_MANIFEST.txt").read_bytes() == expected.encode()
    assert (tmp_path / "PATCH_SHA256_MANIFEST.txt").read_bytes() == expected.encode()
