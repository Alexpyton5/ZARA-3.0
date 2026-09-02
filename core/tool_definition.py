"""
Tool Definition — Lightweight abstraction for tool/action metadata.

Provides unified interface for all tool types (actions, adapters, external tools).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["ToolState", "ToolDefinition"]


class ToolState:
    """Tool execution state constants."""
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"


@dataclass
class ToolDefinition:
    """Definition of a tool (action, adapter, or external capability).

    Provides unified metadata for tool contract, risk classification,
    permission requirements, execution settings, and verification.
    """

    # Identity
    name: str
    description: str
    category: str  # system, audio, files, apps, windows, browser, clipboard, screenshot, vision, terminal, etc.

    # Schema & Interface
    input_schema: dict = field(default_factory=dict)  # JSON Schema for tool input
    output_schema: dict = field(default_factory=dict)  # JSON Schema for tool output
    parameters: dict = field(default_factory=dict)  # Backward compat; prefer input_schema

    # Execution
    executor: Callable | None = None  # Function that executes the tool
    verifier: Callable | None = None  # Function that verifies tool executed correctly
    timeout_ms: int = 30000  # Default timeout in milliseconds
    async_execution: bool = False  # Whether executor is async

    # Risk & Permissions
    risk_level: str = "LOW"  # LOW | MEDIUM | HIGH
    capability: str = "READ_ONLY"  # READ_ONLY | LOCAL_PC_CONTROL | PC_CONTROL | REMOTE_PC_CONTROL | AGENTIC_PC_CONTROL | FILES_MUTATE | CODE_EXECUTION | SYSTEM_POWER
    requires_confirmation: bool = False  # Whether action needs human approval
    requires_superbrain: bool = False  # Whether Supercérebro/PC_CONTROL gate required

    # Metadata
    tags: list[str] = field(default_factory=list)  # e.g., ["voice-enabled", "local", "deterministic"]
    hidden: bool = False  # Hide from public API
    deprecated: bool = False  # Mark as deprecated
    experimental: bool = False  # Mark as experimental
    aliases: list[str] = field(default_factory=list)  # Alternative names
    metadata: dict = field(default_factory=dict)  # Extended metadata

    # Status
    available: bool = True  # Whether tool is currently available
    state: str = field(default_factory=lambda: ToolState.AVAILABLE)
    last_error: str | None = None  # Last error message if unavailable

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "timeout_ms": self.timeout_ms,
            "async_execution": self.async_execution,
            "risk_level": self.risk_level,
            "capability": self.capability,
            "requires_confirmation": self.requires_confirmation,
            "requires_superbrain": self.requires_superbrain,
            "tags": self.tags,
            "hidden": self.hidden,
            "deprecated": self.deprecated,
            "experimental": self.experimental,
            "aliases": self.aliases,
            "available": self.available,
            "state": self.state,
        }

    @classmethod
    def from_action_spec(cls, spec) -> ToolDefinition:
        """Convert ActionSpec to ToolDefinition (adapter pattern)."""
        return cls(
            name=spec.name,
            description=spec.description,
            category=spec.category,
            input_schema=spec.parameters or {},
            output_schema={},
            risk_level=spec.risk,
            capability=spec.capability,
            requires_confirmation=spec.requires_confirmation,
            async_execution=spec.async_execution,
            tags=spec.tags or [],
        )
