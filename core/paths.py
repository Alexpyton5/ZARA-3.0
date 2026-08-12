"""Paths — central path resolution for ZARA 3.0."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """Root of the source tree or of the frozen sidecar executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Writable per-user data directory (LOCALAPPDATA on Windows).

    Optional override: set ZARA3_HOME to isolate the whole data tree
    (tests / parallel runtimes). Default behaviour is unchanged.
    """
    override = os.environ.get("ZARA3_HOME")
    if override:
        base = Path(override)
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share"))
        base = base / "ZARA3"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    """Configuration directory.

    Source/dev keeps using project/config. Frozen builds use LOCALAPPDATA so an
    installed app never needs to write inside Program Files/resources.
    """
    if getattr(sys, "frozen", False):
        path = user_data_dir() / "config"
    else:
        path = project_root() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    return project_root() / "assets"


def logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_dir() -> Path:
    path = user_data_dir() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = user_data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def api_keys_path() -> Path:
    return config_dir() / "api_keys.json"
