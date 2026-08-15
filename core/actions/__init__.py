"""Core Actions Package — Auto-registers all actions on import."""
from __future__ import annotations

# Re-export registry
from core.action_registry import ActionResult, action, get_registry, registry

# Import all action modules to register them (trigger @action decorators)
from core.actions import (  # noqa: F401
    aprendizado_acoes,
    browser,
    code,
    files,
    media_apps,
    os_ops,
    ponte_claude,
    scheduler,
    system,
    terminal,
    vision,
    web,
    windows_radios,
)

__all__ = [
    "registry",
    "get_registry",
    "ActionResult",
    "action",
]
