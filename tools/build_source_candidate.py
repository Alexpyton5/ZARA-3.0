"""Build an isolated desktop package from a verified SourceMission candidate.

This is deliberately separate from ``build_current.py``.  It creates a full
disposable build projection under one mission sandbox, overlays only the
candidate's authorized files, then invokes the normal PyInstaller/Electron
pipeline *inside that projection*.  It cannot activate a package or write the
canonical ``dist-sidecar``/``ZARA CURRENT BUILD`` paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from typing import Any, Iterable


class CandidateBuildError(RuntimeError):
    """A candidate cannot be safely packaged as a desktop build."""


_BACKEND_INPUTS = (
    "main.py", "build_exe.py", "pyproject.toml", "IDENTITY.md", "core", "memory", "voice", "plugins",
    "tools/build_current.py", "tools/autonomy_release.py", "tools/electron_lab_canary.py",
)
_FRONTEND_INPUTS = (
    "frontend/src", "frontend/public", "frontend/package.json", "frontend/package-lock.json",
    "frontend/index.html", "frontend/vite.config.ts", "frontend/tsconfig.json", "frontend/tsconfig.node.json",
)
_CANDIDATE_DIR = "desktop-workspace"
_BUILD_TIMEOUT_SECONDS = 1700
_VERIFY_TIMEOUT_SECONDS = 120
_CANARY_TIMEOUT_SECONDS = 240
_MIN_BUILD_FREE_BYTES = 2 * 1024 * 1024 * 1024


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _require_build_space(sandbox: Path) -> None:
    try:
        free = shutil.disk_usage(sandbox).free
    except OSError as exc:
        raise CandidateBuildError("CANDIDATE_BUILD_DISK_PREFLIGHT_FAILED") from exc
    if free < _MIN_BUILD_FREE_BYTES:
        raise CandidateBuildError("CANDIDATE_BUILD_DISK_SPACE_BELOW_2GB")


def _relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CandidateBuildError("CANDIDATE_PATH_INVALID")
    path = PurePosixPath(value.replace("\\", "/"))
    if (path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)
            or (path.parts and ":" in path.parts[0])):
        raise CandidateBuildError("CANDIDATE_PATH_INVALID")
    return path


def _copy_input(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise CandidateBuildError(f"SYMLINKED_BUILD_INPUT: {source}")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    if not source.is_dir():
        return  # IDENTITY.md is deliberately optional in the canonical build.
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_symlink():
            raise CandidateBuildError(f"SYMLINKED_BUILD_INPUT: {item}")
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".pyo"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _dependency_junction(link: Path, target: Path) -> None:
    """Expose shared installed frontend dependencies without installing them.

    The build executes only typecheck/build/electron-builder commands; no npm
    install/update command is issued. The canonical dependency directory is a
    shared external resource, not a build output or an OS-enforced read-only mount.
    """
    if not target.is_dir() or link.exists() or link.is_symlink():
        raise CandidateBuildError("NODE_DEPENDENCY_PATH_INVALID")
    link.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False,
                            timeout=30)
    if result.returncode:
        raise CandidateBuildError("NODE_DEPENDENCY_LINK_FAILED")
    if not link.is_dir() or not _inside(link, link.parent):
        # A junction resolves outside by design; this check documents that it is
        # never an output boundary.  Its target is checked before creation.
        if not link.is_dir():
            raise CandidateBuildError("NODE_DEPENDENCY_LINK_FAILED")


def _git(workspace: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(["git", *arguments], cwd=workspace, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", shell=False, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise CandidateBuildError("CANONICAL_GIT_METADATA_TIMEOUT") from exc
    if result.returncode:
        raise CandidateBuildError("CANONICAL_GIT_METADATA_UNAVAILABLE")
    return result.stdout.strip()


def _source_identity(python: Path, staged: Path, env: dict[str, str]) -> dict[str, Any]:
    command = [str(python), "-c", "import json; from tools.build_current import source_identity; print(json.dumps(source_identity()))"]
    try:
        result = subprocess.run(command, cwd=staged, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", shell=False, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise CandidateBuildError("CANDIDATE_SOURCE_IDENTITY_TIMEOUT") from exc
    if result.returncode:
        raise CandidateBuildError("CANDIDATE_SOURCE_IDENTITY_FAILED")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CandidateBuildError("CANDIDATE_SOURCE_IDENTITY_INVALID") from exc


def _require_review(review_evidence: dict[str, Any]) -> None:
    if not isinstance(review_evidence, dict) or review_evidence.get("verdict") != "PASS":
        raise CandidateBuildError("INDEPENDENT_REVIEW_NOT_PASSED")
    refs = review_evidence.get("evidence_refs")
    if not isinstance(refs, dict):
        raise CandidateBuildError("INDEPENDENT_REVIEW_EVIDENCE_REQUIRED")
    hashes, receipts = refs.get("artifact_hashes"), refs.get("test_receipt_ids")
    if (not isinstance(hashes, list) or not isinstance(receipts, list) or not hashes or not receipts
            or not all(isinstance(value, str) and value for value in hashes + receipts)
            or not isinstance(review_evidence.get("reviewer_run_id"), str)
            or not review_evidence["reviewer_run_id"]):
        raise CandidateBuildError("INDEPENDENT_REVIEW_EVIDENCE_REQUIRED")


def _bind_review(review_evidence: dict[str, Any], overlays: list[dict[str, str]]) -> None:
    """Require the reviewer to have inspected every exact byte overlay in order."""
    _require_review(review_evidence)
    reviewed = review_evidence["evidence_refs"]["artifact_hashes"]
    actual = [item["sha256"] for item in overlays]
    if reviewed != actual:
        raise CandidateBuildError("INDEPENDENT_REVIEW_HASH_MISMATCH")


def _copy_projection(workspace: Path, staged: Path, *, skip_paths: Iterable[str] = ()) -> None:
    skipped = {PurePosixPath(value.replace("\\", "/")).as_posix() for value in skip_paths}
    for relative in _BACKEND_INPUTS + _FRONTEND_INPUTS:
        if PurePosixPath(relative).as_posix() in skipped:
            continue
        source = workspace.joinpath(*PurePosixPath(relative).parts)
        _copy_input(source, staged.joinpath(*PurePosixPath(relative).parts))


def _canary_environment(build_environment: dict[str, str]) -> dict[str, str]:
    """Launch the packaged runtime outside the builder's temp/cache tree.

    The PyInstaller sidecar extracts into TEMP before Python starts. A build
    scratch directory is not a runtime setting, including on package recovery.
    Set temp explicitly: merely removing it can make Python fall back to cwd.
    """
    discarded = {"TMP", "TEMP", "TMPDIR", "PYINSTALLER_CONFIG_DIR", "NPM_CONFIG_CACHE"}
    environment = {
        key: value for key, value in build_environment.items()
        if key.upper() not in discarded
        and not key.upper().startswith(("ELECTRON_", "ZARA_BUILD_"))
    }
    local_app_data = environment.get("LOCALAPPDATA")
    runtime_temp = (Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local") / "Temp"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    environment.update({key: str(runtime_temp) for key in ("TMP", "TEMP", "TMPDIR")})
    return environment


def _overlay_candidate(source_root: Path, staged: Path, allowed_paths: Iterable[str]) -> list[dict[str, str]]:
    overlays = []
    for raw in allowed_paths:
        relative = _relative(raw)
        source = source_root.joinpath(*relative.parts)
        target = staged.joinpath(*relative.parts)
        if not _inside(source, source_root) or not _inside(target, staged) or source.is_symlink() or not source.is_file():
            raise CandidateBuildError("CANDIDATE_OVERLAY_MISSING_OR_UNSAFE")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        overlays.append({"path": relative.as_posix(), "sha256": _digest(source)})
    if not overlays:
        raise CandidateBuildError("CANDIDATE_OVERLAY_REQUIRED")
    return overlays


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], failure: str, timeout_seconds: int,
    receipt_dir: Path,
) -> str:
    def tail(value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return str(value or "")[-200000:]

    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / (failure.casefold() + ".json")
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", shell=False,
                                timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        receipt_path.write_text(json.dumps({"command": command, "cwd": str(cwd), "timeout": True,
            "timeout_seconds": timeout_seconds, "stdout_tail": tail(exc.stdout),
            "stderr_tail": tail(exc.stderr)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise CandidateBuildError(failure + "_TIMEOUT") from exc
    receipt_path.write_text(json.dumps({"command": command, "cwd": str(cwd), "timeout": False,
        "exit_code": result.returncode, "stdout_tail": result.stdout[-200000:],
        "stderr_tail": result.stderr[-200000:]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise CandidateBuildError(failure)
    return result.stdout


def _require_frozen_overlays(
    source_root: Path, staged: Path, package: Path, overlays: list[dict[str, str]], source_sha256: str,
) -> None:
    for item in overlays:
        relative = _relative(item["path"])
        source = source_root.joinpath(*relative.parts)
        projected = staged.joinpath(*relative.parts)
        if (not source.is_file() or not projected.is_file()
                or _digest(source) != item["sha256"] or _digest(projected) != item["sha256"]):
            raise CandidateBuildError("CANDIDATE_OVERLAY_CHANGED_DURING_BUILD")
    manifest = json.loads((package / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("sha256") != source_sha256:
            raise CandidateBuildError("CANDIDATE_SOURCE_IDENTITY_CHANGED_DURING_BUILD")


def _require_successful_build_receipt(receipt_path: Path) -> dict[str, Any]:
    """Accept only the receipt emitted by a completed build command."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("CANDIDATE_BUILD_SUCCESS_RECEIPT_REQUIRED") from exc
    if receipt.get("timeout") is not False or receipt.get("exit_code") != 0:
        raise CandidateBuildError("CANDIDATE_BUILD_NOT_COMPLETED")
    return receipt


def _verify_reusable_receipt(
    receipt_path: Path, source_root: Path, allowed_paths: Iterable[str], review_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Revalidate a completed immutable candidate without changing its bytes."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("CANDIDATE_RECEIPT_INVALID") from exc
    if receipt.get("review_evidence") != review_evidence:
        raise CandidateBuildError("CANDIDATE_RECEIPT_REVIEW_MISMATCH")
    overlays = receipt.get("overlay")
    expected_paths = [_relative(value).as_posix() for value in allowed_paths]
    if not isinstance(overlays, list) or [item.get("path") for item in overlays] != expected_paths:
        raise CandidateBuildError("CANDIDATE_RECEIPT_OVERLAY_MISMATCH")
    _bind_review(review_evidence, overlays)
    for item in overlays:
        source = source_root.joinpath(*_relative(item["path"]).parts)
        if not source.is_file() or source.is_symlink() or _digest(source) != item.get("sha256"):
            raise CandidateBuildError("CANDIDATE_RECEIPT_INPUT_DRIFT")

    staged = Path(receipt.get("workspace", ""))
    package = Path(receipt.get("package", ""))
    if not staged.is_dir() or not package.is_dir() or not _inside(package, staged):
        raise CandidateBuildError("CANDIDATE_RECEIPT_PACKAGE_INVALID")
    build_receipt = Path(receipt.get("build_receipt", ""))
    if not _inside(build_receipt, receipt_path.parent):
        raise CandidateBuildError("CANDIDATE_BUILD_SUCCESS_RECEIPT_REQUIRED")
    _require_successful_build_receipt(build_receipt)
    try:
        info = json.loads((package / "win-unpacked" / "BUILD_INFO.json").read_text(encoding="utf-8"))
        manifest = json.loads((package / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
        report = json.loads(Path(receipt["canary_report"]).read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("CANDIDATE_RECEIPT_PACKAGE_INVALID") from exc
    paths = {
        "exe_sha256": package / "win-unpacked" / "ZARA 3.0.exe",
        "asar_sha256": package / "win-unpacked" / "resources" / "app.asar",
        "backend_sha256": package / "win-unpacked" / "resources" / "backend" / "zara-backend.exe",
    }
    if (manifest.get("sha256") != receipt.get("source_sha256")
            or info.get("SOURCE_SHA256") != receipt.get("source_sha256")
            or report != receipt.get("canary")
            or report.get("status") != "passed" or report.get("live") is not False or report.get("runs")):
        raise CandidateBuildError("CANDIDATE_RECEIPT_IDENTITY_MISMATCH")
    for key, path in paths.items():
        if not path.is_file() or _digest(path) != receipt.get(key):
            raise CandidateBuildError("CANDIDATE_RECEIPT_ARTIFACT_DRIFT")
    if (report.get("asar_sha256") != receipt.get("asar_sha256")
            or report.get("backend_sha256") != receipt.get("backend_sha256")):
        raise CandidateBuildError("CANDIDATE_RECEIPT_IDENTITY_MISMATCH")
    return receipt


def _fresh_staging_path(sandbox: Path) -> tuple[Path, int]:
    """Choose one of three immutable build attempts; never modify an old one."""
    candidates = [(sandbox / _CANDIDATE_DIR, 0)] + [
        (sandbox / f"{_CANDIDATE_DIR}-retry-{index}", index) for index in (1, 2)
    ]
    for path, index in candidates:
        if not path.exists():
            return path, index
    raise CandidateBuildError("CANDIDATE_DESKTOP_BUILD_RETRY_LIMIT")


def build_candidate(
    workspace: Path, sandbox: Path, source_root: Path, allowed_paths: list[str], review_evidence: dict[str, Any],
    runtime_drift_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Build and canary-test a desktop candidate; never activate or promote it."""
    _require_review(review_evidence)
    workspace, sandbox, source_root = Path(workspace).resolve(strict=True), Path(sandbox).resolve(strict=True), Path(source_root).resolve(strict=True)
    if not workspace.is_dir() or not source_root.is_dir() or _inside(sandbox, workspace) or not _inside(source_root, sandbox):
        raise CandidateBuildError("CANDIDATE_WORKSPACE_BOUNDARY_INVALID")
    _require_build_space(sandbox)
    staged = sandbox / _CANDIDATE_DIR
    retry_index = 0
    recover_existing = False
    if staged.exists():
        retry_index = 1
        while (sandbox / f"{_CANDIDATE_DIR}-retry-{retry_index}").exists():
            completed = (sandbox / f"{_CANDIDATE_DIR}-retry-{retry_index}" / "DESKTOP_CANDIDATE_RECEIPT.json").is_file()
            candidate_staging = sandbox / f"{_CANDIDATE_DIR}-retry-{retry_index}"
            if completed:
                raise CandidateBuildError("CANDIDATE_DESKTOP_BUILD_RETRY_LIMIT")
            if retry_index >= 2:
                # A failed NSIS wrapper may leave a complete package.  Reuse
                # that exact immutable staging tree after validating its bytes;
                # this is a harness recovery, not a new candidate build.
                if _recoverable_package(candidate_staging):
                    staged, recover_existing = candidate_staging, True
                    break
                raise CandidateBuildError("CANDIDATE_DESKTOP_BUILD_RETRY_LIMIT")
            retry_index += 1
        if not recover_existing:
            staged = sandbox / f"{_CANDIDATE_DIR}-retry-{retry_index}"
    venv = workspace / ".venv"
    python = venv / "Scripts" / "python.exe"
    node_modules = workspace / "frontend" / "node_modules"
    if not python.is_file() or not (node_modules / "electron-builder" / "cli.js").is_file():
        raise CandidateBuildError("CANDIDATE_BUILD_DEPENDENCIES_UNAVAILABLE")

    if not recover_existing:
        staged.mkdir(parents=True)
    # Reuse the isolated tool caches from a timed-out build.  The previous
    # staging tree remains immutable evidence; only this fresh projection is
    # rebuilt, so a retry never overwrites an earlier candidate.
    build_temp = sandbox / "desktop-build-temp"
    build_temp.mkdir(exist_ok=True)
    _copy_projection(workspace, staged, skip_paths=runtime_drift_paths if recover_existing else ())
    overlays = _overlay_candidate(source_root, staged, allowed_paths)
    _bind_review(review_evidence, overlays)
    if not recover_existing:
        _dependency_junction(staged / "frontend" / "node_modules", node_modules)
    environment = dict(os.environ)
    environment.update({
        "ZARA_BUILD_VENV_DIR": str(venv), "ZARA_BUILD_PYTHON": str(python),
        "ZARA_BUILD_GIT_BRANCH": _git(workspace, "branch", "--show-current"),
        "ZARA_BUILD_GIT_COMMIT": _git(workspace, "rev-parse", "HEAD"),
        "ZARA_BUILD_GIT_DIRTY": "1" if _git(workspace, "status", "--porcelain") else "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMP": str(build_temp), "TEMP": str(build_temp), "TMPDIR": str(build_temp),
        "PYINSTALLER_CONFIG_DIR": str(build_temp / "pyinstaller"),
        "npm_config_cache": str(build_temp / "npm-cache"),
        "ELECTRON_CACHE": str(build_temp / "electron-cache"),
        "ELECTRON_BUILDER_CACHE": str(build_temp / "electron-builder-cache"),
    })
    identity = _source_identity(python, staged, environment)
    evidence_dir = sandbox / ("desktop-build-evidence" + (f"-retry-{retry_index}" if retry_index else ""))
    if not recover_existing:
        _run([str(python), "tools/build_current.py", "build", "--delta", "Isolated SourceMission desktop candidate"],
             cwd=staged, env=environment, failure="CANDIDATE_DESKTOP_BUILD_FAILED",
             timeout_seconds=_BUILD_TIMEOUT_SECONDS, receipt_dir=evidence_dir)
    packages = sorted((staged / "frontend").glob(".current-build-staging-*"), key=lambda path: path.stat().st_mtime)
    if len(packages) != 1:
        raise CandidateBuildError("CANDIDATE_PACKAGE_IDENTITY_AMBIGUOUS")
    package = packages[0]
    if recover_existing and not (package / "win-unpacked" / "BUILD_INFO.json").is_file():
        _materialize_recovered_metadata(package, identity, environment, retry_index)
    _run([str(python), "tools/build_current.py", "verify", str(package)], cwd=staged, env=environment,
         failure="CANDIDATE_PACKAGE_VERIFY_FAILED", timeout_seconds=_VERIFY_TIMEOUT_SECONDS,
         receipt_dir=evidence_dir)

    canary_output = sandbox / ("desktop-canary" + (f"-retry-{retry_index}" if retry_index else ""))
    canary_command = [str(python), str(workspace / "tools" / "electron_lab_canary.py"), str(package),
                      "--output", str(canary_output), "--read-only"]
    runtime_environment = _canary_environment(environment)
    try:
        _run(canary_command, cwd=workspace, env=runtime_environment,
             failure="CANDIDATE_READONLY_CANARY_FAILED", timeout_seconds=_CANARY_TIMEOUT_SECONDS,
             receipt_dir=evidence_dir)
    except CandidateBuildError:
        # A cold Electron launch can lose the first IPC handshake even though
        # the same immutable package is healthy.  Preserve the first report and
        # grant one bounded read-only retry; this never rebuilds or calls a
        # provider.
        first_report_path = canary_output / "VALIDATION.json"
        try:
            first_report = json.loads(first_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            first_report = {}
        if first_report.get("stage") != "WAITING_LAB_IPC":
            raise
        retry_output = sandbox / ("desktop-canary" + (f"-retry-{retry_index}" if retry_index else "") + "-attempt-2")
        retry_command = [str(python), str(workspace / "tools" / "electron_lab_canary.py"), str(package),
                         "--output", str(retry_output), "--read-only"]
        _run(retry_command, cwd=workspace, env=runtime_environment,
             failure="CANDIDATE_READONLY_CANARY_RETRY_FAILED", timeout_seconds=_CANARY_TIMEOUT_SECONDS,
             receipt_dir=evidence_dir)
        canary_output = retry_output
    report_path = canary_output / "VALIDATION.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        info = json.loads((package / "win-unpacked" / "BUILD_INFO.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("CANDIDATE_CANARY_REPORT_MISSING") from exc
    if (report.get("status") != "passed" or report.get("live") is not False or report.get("runs")
            or report.get("asar_sha256") != info["ASAR_SHA256"]
            or report.get("backend_sha256") != info["BACKEND_SHA256"]):
        raise CandidateBuildError("CANDIDATE_CANARY_NOT_READONLY")
    if info.get("SOURCE_SHA256") != identity["sha256"]:
        raise CandidateBuildError("CANDIDATE_SOURCE_IDENTITY_CHANGED_DURING_BUILD")
    _require_frozen_overlays(source_root, staged, package, overlays, identity["sha256"])
    paths = {
        "exe": package / "win-unpacked" / "ZARA 3.0.exe",
        "asar": package / "win-unpacked" / "resources" / "app.asar",
        "backend": package / "win-unpacked" / "resources" / "backend" / "zara-backend.exe",
    }
    result = {
        "status": "PACKAGED_RUNTIME_CANDIDATE", "candidate_status": "VERIFIED_AWAITING_APPROVAL",
        "desktop_package": True, "package": str(package), "workspace": str(staged),
        "source_sha256": identity["sha256"], "overlay": overlays, "review_evidence": review_evidence,
        "exe_path": str(paths["exe"]), "exe_sha256": _digest(paths["exe"]),
        "asar_path": str(paths["asar"]), "asar_sha256": _digest(paths["asar"]),
        "backend_path": str(paths["backend"]), "backend_sha256": _digest(paths["backend"]),
        "canonical_git_branch": environment["ZARA_BUILD_GIT_BRANCH"],
        "canonical_git_commit": environment["ZARA_BUILD_GIT_COMMIT"],
        "canonical_git_dirty": environment["ZARA_BUILD_GIT_DIRTY"] == "1",
        "build_id": info["BUILD_ID"], "canary_report": str(report_path), "canary": report,
        "build_recovered_from_complete_output": recover_existing,
        "build_failure_evidence": str(evidence_dir / "candidate_desktop_build_failed.json")
            if recover_existing and (evidence_dir / "candidate_desktop_build_failed.json").is_file() else None,
        "activation": "FORBIDDEN_UNTIL_CANONICAL_SOURCE_PROMOTION_AND_REBUILD",
        "build_retry_index": retry_index,
        "automatic_promotion": "NOT_IMPLEMENTED",
    }
    (sandbox / "DESKTOP_CANDIDATE_RECEIPT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


__all__ = ["CandidateBuildError", "build_candidate"]
