from __future__ import annotations

from pathlib import Path

import pytest

from tools.build_source_candidate import CandidateBuildError, build_candidate


def test_checkout_evidence_sandbox_passes_boundary_and_stops_at_disk_preflight(tmp_path, monkeypatch):
    workspace = tmp_path / "checkout"
    sandbox = workspace / ".unlazy" / "run" / "profile" / "mission"
    source = sandbox / "source"
    source.mkdir(parents=True)
    import tools.build_source_candidate as builder

    def preflight_reached(_sandbox):
        raise CandidateBuildError("PREFLIGHT_REACHED")

    monkeypatch.setattr(builder, "_require_build_space", preflight_reached)
    review = {"verdict": "PASS", "reviewer_run_id": "review-1",
              "evidence_refs": {"artifact_hashes": ["a"], "test_receipt_ids": ["t"]}}
    with pytest.raises(CandidateBuildError, match="PREFLIGHT_REACHED"):
        build_candidate(workspace, sandbox, source, [], review)


def test_checkout_source_tree_cannot_be_candidate_sandbox(tmp_path):
    workspace = tmp_path / "checkout"
    sandbox = workspace / "core" / "mission"
    source = sandbox / "source"
    source.mkdir(parents=True)
    review = {"verdict": "PASS", "reviewer_run_id": "review-1",
              "evidence_refs": {"artifact_hashes": ["a"], "test_receipt_ids": ["t"]}}
    with pytest.raises(CandidateBuildError, match="CANDIDATE_WORKSPACE_BOUNDARY_INVALID"):
        build_candidate(workspace, sandbox, source, [], review)

import pytest

from tools.build_source_candidate import (
    CandidateBuildError,
    _bind_review,
    _overlay_candidate,
    _relative,
    _require_build_space,
    _require_frozen_overlays,
    _require_review,
)


def test_overlay_uses_only_authorized_candidate_bytes(tmp_path: Path):
    source = tmp_path / "sandbox" / "source"; staged = tmp_path / "sandbox" / "desktop-workspace"
    (source / "core").mkdir(parents=True); staged.mkdir(parents=True)
    (source / "core" / "safe.py").write_text("answer = 2\n", encoding="utf-8")
    (staged / "core").mkdir(); (staged / "core" / "safe.py").write_text("answer = 1\n", encoding="utf-8")
    receipt = _overlay_candidate(source, staged, ["core/safe.py"])
    assert receipt[0]["path"] == "core/safe.py"
    assert (staged / "core" / "safe.py").read_text(encoding="utf-8") == "answer = 2\n"


@pytest.mark.parametrize("path", ["../core/x.py", "C:/core/x.py", "", "core/../../x.py"])
def test_overlay_path_cannot_escape_candidate(path):
    with pytest.raises(CandidateBuildError):
        _relative(path)


def test_overlay_requires_a_real_candidate_file(tmp_path: Path):
    source = tmp_path / "source"; staged = tmp_path / "staged"
    source.mkdir(); staged.mkdir()
    with pytest.raises(CandidateBuildError):
        _overlay_candidate(source, staged, ["core/missing.py"])


def test_builder_requires_a_passing_independent_review_with_evidence():
    with pytest.raises(CandidateBuildError):
        _require_review({"verdict": "PASS"})
    review = {"verdict": "PASS", "reviewer_run_id": "real-review-run",
              "evidence_refs": {"artifact_hashes": ["hash"], "test_receipt_ids": ["receipt"]}}
    _require_review(review)


def test_builder_binds_every_overlay_byte_to_the_independent_review():
    review = {"verdict": "PASS", "reviewer_run_id": "real-review-run",
              "evidence_refs": {"artifact_hashes": ["one", "two"], "test_receipt_ids": ["receipt"]}}
    overlays = [{"path": "core/a.py", "sha256": "one"}, {"path": "tests/test_a.py", "sha256": "two"}]
    _bind_review(review, overlays)
    with pytest.raises(CandidateBuildError, match="INDEPENDENT_REVIEW_HASH_MISMATCH"):
        _bind_review(review, list(reversed(overlays)))


def test_source_manifest_requires_runtime_overlay_but_not_regression_test_overlay(tmp_path: Path):
    source = tmp_path / "source"; staged = tmp_path / "staged"; package = tmp_path / "package"
    for root in (source, staged, package):
        (root / "core").mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(parents=True, exist_ok=True)
    runtime = b"answer = 2\n"; regression = b"def test_answer(): assert True\n"
    for root in (source, staged):
        (root / "core" / "safe.py").write_bytes(runtime)
        (root / "tests" / "test_safe.py").write_bytes(regression)
    import hashlib, json
    runtime_sha = hashlib.sha256(runtime).hexdigest()
    regression_sha = hashlib.sha256(regression).hexdigest()
    (package / "SOURCE_MANIFEST.json").write_text(json.dumps({
        "sha256": "source-id",
        "files": [{"path": "core/safe.py", "sha256": runtime_sha}],
    }), encoding="utf-8")

    _require_frozen_overlays(source, staged, package, [
        {"path": "core/safe.py", "sha256": runtime_sha},
        {"path": "tests/test_safe.py", "sha256": regression_sha},
    ], "source-id")

    (package / "SOURCE_MANIFEST.json").write_text(json.dumps({
        "sha256": "source-id", "files": []}), encoding="utf-8")
    with pytest.raises(CandidateBuildError, match="CANDIDATE_OVERLAY_NOT_IN_SOURCE_MANIFEST"):
        _require_frozen_overlays(source, staged, package, [
            {"path": "core/safe.py", "sha256": runtime_sha}
        ], "source-id")


def test_sidecar_spec_does_not_embed_external_hermes_runtime_files():
    build_script = (Path(__file__).parents[1] / "build_exe.py").read_text(encoding="utf-8")
    assert "hermes_runner.py" not in build_script
    assert "hermes_pin.json" not in build_script


def test_builder_refuses_target_with_less_than_two_gib_free(tmp_path: Path, monkeypatch):
    disk_usage = type("DiskUsage", (), {"free": 2 * 1024 * 1024 * 1024 - 1})()
    monkeypatch.setattr("tools.build_source_candidate.shutil.disk_usage", lambda _path: disk_usage)
    with pytest.raises(CandidateBuildError, match="CANDIDATE_BUILD_DISK_SPACE_BELOW_2GB"):
        _require_build_space(tmp_path)
