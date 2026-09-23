from __future__ import annotations

import hashlib
import json
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
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for record in payload["files"]:
        relative = record["path"]
        assert relative not in seen, f"duplicate inventory path: {relative}"
        seen.add(relative)
        path = QUARANTINE / Path(relative)
        assert path.is_file() and not path.is_symlink(), f"missing or linked file: {relative}"
        assert path.stat().st_size == record["size_bytes"], f"size changed: {relative}"
        assert sha256(path) == record["sha256"], f"SHA-256 changed: {relative}"
    assert len(seen) == payload["total_file_count"]
    assert sum(item["size_bytes"] for item in payload["files"]) == payload["total_file_bytes"]
    print(f"QUARANTINE_MANIFEST_PASS files={len(seen)} bytes={payload['total_file_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
