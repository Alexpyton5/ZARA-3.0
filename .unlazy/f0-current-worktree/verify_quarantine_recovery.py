from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "_quarentena" / "organizacao-2026-09-23" / "recovered-fast-forward-20260923-184256" / "MANIFEST.json"


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    for item in data["files"]:
        path = MANIFEST.parent / item["original_path"]
        assert path.is_file(), f"quarantined artifact missing: {path}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert path.stat().st_size == item["size_bytes"], f"size mismatch: {path.name}"
        assert digest == item["sha256"].upper(), f"hash mismatch: {path.name}"
    assert data["status"] == "PRESERVED_NOT_CLASSIFIED_AS_DISPOSABLE"
    print(f"RECOVERED_FILES={len(data['files'])}")
    print("QUARANTINE_RECOVERY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
