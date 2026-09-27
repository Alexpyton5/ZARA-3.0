"""Storage utilities — atomic writes, safe user paths."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path | str, data: Any, indent: int = 2) -> None:
    """Write JSON atomically (write to temp, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(data, tmp, indent=indent, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    """Write text atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding=encoding, dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def safe_user_path(*parts: str) -> Path:
    """
    Resolve a path under the user's data directory (LOCALAPPDATA on Windows),
    creating parent directories. Never follows symlinks outside the base.
    """
    base = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share"))
    base = base / "ZARA3"
    target = base.joinpath(*parts).resolve()
    # Ensure we stay within base
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"Path traversal attempt: {parts}") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def resource_dir() -> Path:
    """Directory where packaged resources live (works in PyInstaller onefile)."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """User-writable data directory."""
    return safe_user_path("data")
