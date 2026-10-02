"""Update sidecar SHA256 manifests relative to the current project root."""
from __future__ import annotations

import hashlib
from pathlib import Path


def main() -> None:
    root = Path.cwd()
    exe = root / "dist-sidecar" / "zara-backend.exe"
    if not exe.is_file():
        raise SystemExit(f"zara-backend.exe not found: {exe}")
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    rel = exe.relative_to(root).as_posix()
    content = f"{digest}  {rel}\n"
    for path, value in (
        (root / "CLEAN_BUILD_ID.txt", digest[:8] + "\n"),
        (root / "SHA256_MANIFEST.txt", content),
        (root / "PATCH_SHA256_MANIFEST.txt", content),
    ):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)


if __name__ == "__main__":
    main()
