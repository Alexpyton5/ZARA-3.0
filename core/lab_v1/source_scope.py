"""Bounded source-file selection for SourceMission entry."""
from __future__ import annotations

from pathlib import Path
import re


_PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:core|memory|frontend/src|tools|tests)(?:/[A-Za-z0-9_.-]+)+")


def select_source_scope(workspace: Path, intent: str) -> list[str]:
    workspace = Path(workspace).resolve(strict=True)
    candidates = []
    for raw in _PATH_PATTERN.findall(intent):
        relative = raw.replace("\\", "/").rstrip(".,;:!?")
        target = workspace.joinpath(*relative.split("/"))
        if target.is_file() and relative not in candidates:
            candidates.append(relative)
    return candidates