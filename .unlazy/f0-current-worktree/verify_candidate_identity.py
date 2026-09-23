from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    pointer_path = ROOT / "ZARA_ACTIVE_BUILD.json"
    pointer_txt_path = ROOT / "ZARA_ACTIVE_BUILD.txt"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    exe = Path(pointer["EXE_PATH"])
    info_path = exe.parent / "BUILD_INFO.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    backend = exe.parent / "resources" / "backend" / "zara-backend.exe"
    asar = exe.parent / "resources" / "app.asar"

    assert pointer["BUILD_ID"] == info["BUILD_ID"]
    assert Path(info["EXE_PATH"]).resolve() == exe.resolve()
    assert pointer_txt_path.read_text(encoding="utf-8").strip() == str(exe)
    for path, field in (
        (exe, "EXE_SHA256"),
        (backend, "BACKEND_SHA256"),
        (asar, "ASAR_SHA256"),
    ):
        assert path.is_file(), f"missing packaged artifact: {path}"
        actual = sha256(path)
        assert actual == str(pointer[field]).upper(), f"active pointer hash mismatch: {field}"
        assert actual == str(info[field]).upper(), f"packaged BUILD_INFO hash mismatch: {field}"

    report = {
        "status": "PASS",
        "build_id": pointer["BUILD_ID"],
        "exe_path": str(exe),
        "exe_sha256": sha256(exe),
        "backend_sha256": sha256(backend),
        "asar_sha256": sha256(asar),
        "git_commit": info["GIT_COMMIT"],
        "git_dirty": info["GIT_DIRTY"],
    }
    (ROOT / ".unlazy" / "f0-current-worktree" / "candidate-identity-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"BUILD_ID={pointer['BUILD_ID']}")
    print("CANDIDATE_IDENTITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
