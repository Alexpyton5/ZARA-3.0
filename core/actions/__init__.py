"""Core Actions Package — Auto-registers all actions on import."""
from __future__ import annotations

# Re-export registry
from core.action_registry import ActionResult, action, get_registry, registry

# Import all action modules to register them (trigger @action decorators)
from core.actions import (  # noqa: F401
    browser,
    code,
    files,
    os_ops,
    scheduler,
    system,
    terminal,
    vision,
    web,
)

__all__ = [
    "registry",
    "get_registry",
    "ActionResult",
    "action",
]
