from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUARANTINE = ROOT / "_quarentena"
MANIFEST = QUARANTINE / "MANIFEST_P0.1_20260923.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    if MANIFEST.exists():
        raise FileExistsError(f"Refusing to overwrite existing manifest: {MANIFEST}")

    files: list[dict[str, object]] = []
    skipped_symlinks: list[dict[str, str]] = []
    by_directory: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})

    for current, dirnames, filenames in os.walk(QUARANTINE, followlinks=False):
        current_path = Path(current)
        safe_dirnames = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                skipped_symlinks.append({
                    "path": candidate.relative_to(QUARANTINE).as_posix(),
                    "link_target": os.readlink(candidate),
                })
            else:
                safe_dirnames.append(dirname)
        dirnames[:] = safe_dirnames

        for filename in sorted(filenames):
            path = current_path / filename
            relative = path.relative_to(QUARANTINE).as_posix()
            if relative == MANIFEST.name:
                continue
            if path.is_symlink():
                skipped_symlinks.append({
                    "path": relative,
                    "link_target": os.readlink(path),
                })
                continue
            size = path.stat().st_size
            top = Path(relative).parts[0]
            files.append({
                "path": relative,
                "size_bytes": size,
                "sha256": sha256(path),
                "classification": "preserved_pending_original_purpose_review",
            })
            by_directory[top]["files"] += 1
            by_directory[top]["bytes"] += size

    files.sort(key=lambda item: str(item["path"]).casefold())
    payload = {
        "status": "INVENTORIED_AND_PRESERVED; NO_FILES_DELETED_OR_RECLASSIFIED",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip(),
        "source_worktree": str(ROOT),
        "scope": "Every regular file currently under _quarentena; symlinks are listed, never followed.",
        "freed_disk_bytes": 0,
        "total_file_count": len(files),
        "total_file_bytes": sum(int(item["size_bytes"]) for item in files),
        "directories": dict(sorted(by_directory.items())),
        "skipped_symlinks": skipped_symlinks,
        "files": files,
        "unresolved_candidates": [
            {
                "candidate": "The aggregate '35 stubs/dead memories' set",
                "status": "NOT_ENUMERATED; NOT MOVED; NOT CALLED DISPOSABLE",
                "reason": "No authoritative file list reconciles the claimed count; source references and runtime purpose are not proven dead.",
            },
            {
                "candidate": "Memory-related source and data outside the inventoried quarantine",
                "status": "PRESERVED; REVIEW REQUIRED",
                "reason": "Active memory modules and user data remain protected without item-specific proof they are obsolete.",
            },
        ],
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FILES={payload['total_file_count']}")
    print(f"BYTES={payload['total_file_bytes']}")
    print(f"MANIFEST={MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
