"""Core package exports for the Electron/Python sidecar architecture.

Keep package import lightweight: legacy Flet UI modules are intentionally not
imported here, so importing ``core.model_router`` or Hermes does not pull a GUI
framework into the sidecar.
"""
from __future__ import annotations

from core.paths import (
    api_keys_path,
    assets_dir,
    config_dir,
    data_dir,
    logs_dir,
    memory_dir,
    project_root,
    user_data_dir,
)
from core.storage import atomic_write_json, atomic_write_text, resource_dir, safe_user_path
from core.token_tracker import TokenTracker, tracker

__all__ = [
    "project_root",
    "config_dir",
    "assets_dir",
    "logs_dir",
    "memory_dir",
    "data_dir",
    "user_data_dir",
    "api_keys_path",
    "atomic_write_json",
    "atomic_write_text",
    "safe_user_path",
    "resource_dir",
    "tracker",
    "TokenTracker",
]
