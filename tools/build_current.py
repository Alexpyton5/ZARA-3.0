"""Build, verify and activate the current Electron + Python package.

The previous active package is preserved until an explicitly verified package is
activated. No dependency installation, process termination or baseline overwrite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
CURRENT = FRONTEND / "ZARA CURRENT BUILD"
PYTHON = Path(os.environ.get("ZARA_BUILD_PYTHON", str(ROOT / ".venv" / "Scripts" / "python.exe"))).resolve()
BACKEND_INPUTS = ("main.py", "build_exe.py", "pyproject.toml", "IDENTITY.md", "core", "memory", "voice", "plugins", "tools/build_current.py", "tools/autonomy_release.py", "tools/electron_lab_canary.py")
FRONTEND_INPUTS = ("frontend/src", "frontend/public", "frontend/package.json", "frontend/package-lock.json", "frontend/index.html", "frontend/vite.config.ts", "frontend/tsconfig.json", "frontend/tsconfig.node.json")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def source_identity(backend_only: bool = False) -> dict:
    paths = []
    for name in BACKEND_INPUTS + (() if backend_only else FRONTEND_INPUTS):
        path = ROOT / name
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"})
    entries = [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in sorted(set(paths))]
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(payload).hexdigest(), "files": entries}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run(command: list[str], cwd: Path = ROOT) -> str:
    print("[BUILD] " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, flush=True)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command[0]}")
    return result.stdout.strip()


def git_value(command: list[str], override: str) -> str:
    """Use a recorded canonical revision for a disposable candidate workspace."""
    value = os.environ.get(override)
    return value.strip() if value and value.strip() else run(["git", *command])


def toolchain() -> dict:
    node = shutil.which("node.exe") or shutil.which("node")
    if not node or not PYTHON.is_file():
        raise RuntimeError("Node or project .venv Python is missing")
    npm_cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not npm_cli.is_file():
        raise RuntimeError(f"npm CLI was not found beside Node: {npm_cli}")
    return {"python": str(PYTHON), "python_version": run([str(PYTHON), "--version"]), "node": node,
            "node_version": run([node, "--version"]), "npm_cli": str(npm_cli),
            "npm_version": run([node, str(npm_cli), "--version"])}


def confined_package(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent != FRONTEND.resolve() or not (resolved.name.startswith(".current-build-staging-") or resolved == CURRENT.resolve()):
        raise ValueError("package must be a current-build staging directory or ZARA CURRENT BUILD inside frontend")
    return resolved


def packaged_paths(package: Path) -> dict[str, Path]:
    unpacked = package / "win-unpacked"
    return {"EXE_SHA256": unpacked / "ZARA 3.0.exe", "ASAR_SHA256": unpacked / "resources" / "app.asar",
            "BACKEND_SHA256": unpacked / "resources" / "backend" / "zara-backend.exe"}


def verify_package(package: Path, check_source: bool = True) -> dict:
    package = confined_package(package)
    info = json.loads((package / "win-unpacked" / "BUILD_INFO.json").read_text(encoding="utf-8"))
    for key, path in packaged_paths(package).items():
        if not path.is_file() or digest(path) != info[key]:
            raise ValueError(f"packaged artifact missing or changed: {path.name}")
    installer = package / info["INSTALLER_NAME"]
    if not installer.is_file() or digest(installer) != info["INSTALLER_SHA256"]:
        raise ValueError("installer missing or changed")
    source_manifest = json.loads((package / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if source_manifest["sha256"] != info["SOURCE_SHA256"]:
        raise ValueError("source manifest does not match build identity")
    if check_source and source_identity()["sha256"] != info["SOURCE_SHA256"]:
        raise ValueError("source changed after packaging; rebuild before activation")
    if check_source and digest(ROOT / "dist-sidecar" / "zara-backend.exe") != info["BACKEND_SHA256"]:
        raise ValueError("packaged backend differs from dist-sidecar")
    for essential in ("ffmpeg.dll", "icudtl.dat", "resources.pak", "v8_context_snapshot.bin", "locales/en-US.pak"):
        if not (package / "win-unpacked" / essential).is_file():
            raise ValueError(f"Electron runtime is incomplete: {essential}")
    return info


def build_package(delta: str, reuse_sidecar: bool = False) -> Path:
    chain = toolchain()
    if not (FRONTEND / "node_modules" / "electron-builder" / "cli.js").is_file():
        raise RuntimeError("frontend dependencies are missing; run npm ci in frontend")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    package = confined_package(FRONTEND / f".current-build-staging-{stamp}")
    if package.exists():
        raise FileExistsError(package)
    before = source_identity()
    if reuse_sidecar:
        receipt = json.loads((ROOT / "dist-sidecar" / "BUILD_INFO.json").read_text(encoding="utf-8"))
        if receipt.get("SOURCE_SHA256") != source_identity(backend_only=True)["sha256"]:
            raise ValueError("sidecar source receipt is stale; rebuild the sidecar")
        if receipt.get("SIDECAR_SHA256") != digest(ROOT / "dist-sidecar" / "zara-backend.exe"):
            raise ValueError("sidecar receipt does not match binary")
    else:
        run([str(PYTHON), "build_exe.py"])
    npm = [chain["node"], chain["npm_cli"]]
    run(npm + ["run", "typecheck"], FRONTEND)
    run(npm + ["run", "build"], FRONTEND)
    run(npm + ["run", "build:electron"], FRONTEND)
    run([chain["node"], str(FRONTEND / "node_modules" / "electron-builder" / "cli.js"), "--win", "nsis", f"--config.directories.output={package}"], FRONTEND)
    if before != source_identity():
        raise RuntimeError("source changed while building; package was not activated")
    hashes = {key: digest(path) for key, path in packaged_paths(package).items()}
    if hashes["BACKEND_SHA256"] != digest(ROOT / "dist-sidecar" / "zara-backend.exe"):
        raise RuntimeError("packaged backend does not match the new sidecar")
    installers = list(package.glob("ZARA 3.0 Setup *.exe"))
    if len(installers) != 1:
        raise RuntimeError("expected exactly one newly built installer")
    info = {"BUILD_ID": f"zara-current-{stamp}", "BUILD_TIMESTAMP": datetime.now().astimezone().isoformat(),
            "BUILD_LABEL": "ZARA CURRENT BUILD", "BUILD_METHOD": "PyInstaller + TypeScript + Vite + electron-builder NSIS",
            "GIT_BRANCH": git_value(["branch", "--show-current"], "ZARA_BUILD_GIT_BRANCH"),
            "GIT_COMMIT": git_value(["rev-parse", "HEAD"], "ZARA_BUILD_GIT_COMMIT"),
            "GIT_DIRTY": git_value(["status", "--porcelain"], "ZARA_BUILD_GIT_DIRTY") in {"1", "true", "TRUE"},
            "SOURCE_SHA256": before["sha256"],
            "EXE_PATH": str(packaged_paths(package)["EXE_SHA256"]), **hashes, "TOOLCHAIN": chain,
            "INSTALLER_NAME": installers[0].name, "INSTALLER_SHA256": digest(installers[0]), "DELTA": delta,
            "STATUS": "packaged-awaiting-runtime-validation"}
    write_json(package / "SOURCE_MANIFEST.json", before)
    write_json(package / "win-unpacked" / "BUILD_INFO.json", info)
    verify_package(package)
    print(f"\nPACKAGED_BUILD={package}\nActivate only after validating this exact package.")
    return package


def activate_package(package: Path, validation: Path, shortcuts: bool = False) -> dict:
    package = confined_package(package)
    info = verify_package(package)
    validation = validation.resolve(strict=True)
    report = json.loads(validation.read_text(encoding="utf-8"))
    if report.get("status") != "passed" or report.get("asar_sha256") != info["ASAR_SHA256"] or report.get("backend_sha256") != info["BACKEND_SHA256"]:
        raise ValueError("validation must pass and identify this exact ASAR and backend")
    if package == CURRENT.resolve():
        raise ValueError("Current package is already active; use verification")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = FRONTEND / ".build-backups" / stamp
    journal_path = ROOT / "artifacts/releases" / (stamp + ".json")
    pointer_files = (ROOT / "ZARA_ACTIVE_BUILD.json", ROOT / "ZARA_ACTIVE_BUILD.txt")
    previous = {p.name: p.read_text(encoding="utf-8") if p.exists() else None for p in pointer_files}
    old_info = json.loads((CURRENT / "win-unpacked/BUILD_INFO.json").read_text(encoding="utf-8")) if CURRENT.exists() else None
    if old_info:
        for key, path in packaged_paths(CURRENT).items():
            if digest(path) != old_info[key]: raise ValueError("Current baseline changed before activation")
    journal = {"state": "PREPARED", "candidate": str(package), "backup": str(backup),
               "previous_pointers": previous, "previous_info": old_info}
    write_json(journal_path, journal)
    moved_old = moved_new = False
    try:
        backup.parent.mkdir(exist_ok=True)
        if CURRENT.exists():
            CURRENT.rename(backup)
            moved_old = True
        package.rename(CURRENT)
        moved_new = True
        info.update({"EXE_PATH": str(packaged_paths(CURRENT)["EXE_SHA256"]), "STATUS": "active-validated",
                     "VALIDATION_REPORT": "VALIDATION.json", "VALIDATION_SHA256": digest(validation),
                     "ROLLBACK_JOURNAL": str(journal_path), "PREVIOUS_PACKAGE": str(backup) if moved_old else None})
        shutil.copy2(validation, CURRENT / "VALIDATION.json")
        write_json(CURRENT / "win-unpacked" / "BUILD_INFO.json", info)
        write_json(ROOT / "ZARA_ACTIVE_BUILD.json", info)
        temporary = ROOT / "ZARA_ACTIVE_BUILD.txt.tmp"
        temporary.write_text(info["EXE_PATH"] + "\n", encoding="utf-8")
        os.replace(temporary, ROOT / "ZARA_ACTIVE_BUILD.txt")
        journal.update(state="ACTIVATED", new_build_id=info['BUILD_ID'])
        write_json(journal_path, journal)
    except Exception:
        if moved_new: CURRENT.rename(package)
        if moved_old: backup.rename(CURRENT)
        for path in pointer_files:
            value = previous[path.name]
            if value is not None: path.write_text(value, encoding="utf-8")
            elif path.exists(): path.unlink()
        journal['state'] = 'ACTIVATION_FAILED_RESTORED'
        write_json(journal_path, journal)
        raise

    if shortcuts:
        run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "update_current_shortcuts.ps1")])
    print(f"ACTIVE_BUILD={info['EXE_PATH']}")
    return info


def rollback_package(journal_path: Path) -> dict:
    """Restore the exact retained baseline; no deletion of either package."""
    journal = json.loads(journal_path.read_text(encoding='utf-8'))
    if journal.get('state') != 'ACTIVATED': raise ValueError('No active release to roll back')
    backup = Path(journal['backup']).resolve()
    if backup.parent != (FRONTEND / '.build-backups').resolve(): raise ValueError('Invalid rollback path')
    old = journal['previous_info']
    for key, path in packaged_paths(backup).items():
        if digest(path) != old[key]: raise ValueError('Rollback baseline failed integrity check')
    failed = FRONTEND / ('.current-build-staging-rollback-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    CURRENT.rename(failed)
    try:
        backup.rename(CURRENT)
    except Exception:
        failed.rename(CURRENT)
        raise
    for name, value in journal['previous_pointers'].items():
        if value is not None: (ROOT / name).write_text(value, encoding='utf-8')
    journal.update(state='ROLLED_BACK', failed_package=str(failed))
    write_json(journal_path, journal)
    return old


def main() -> int:
    # Windows redirected output may default to a legacy code page; Vite emits
    # Unicode status glyphs. Keep the build log UTF-8 as well as subprocess output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--delta", required=True)
    build.add_argument("--reuse-sidecar", action="store_true", help="Only reuses a sidecar with matching source and binary receipts")
    verify = sub.add_parser("verify")
    verify.add_argument("package", type=Path)
    verify.add_argument("--artifacts-only", action="store_true")
    activate = sub.add_parser("activate")
    activate.add_argument("package", type=Path)
    activate.add_argument("--validation", required=True, type=Path)
    activate.add_argument("--shortcuts", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build_package(args.delta, args.reuse_sidecar)
        elif args.command == "verify":
            info = verify_package(args.package, check_source=not args.artifacts_only)
            print(json.dumps({"status": "passed", "build_id": info["BUILD_ID"]}))
        else:
            activate_package(args.package, args.validation, args.shortcuts)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"[FAILED] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
