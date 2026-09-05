"""
Tool Registry — Unified registry for tools with adapter for ActionRegistry.

Provides unified interface to register, lookup, list, and filter tools
while maintaining backward compatibility with ActionRegistry.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from core.tool_definition import ToolDefinition
from core.tool_risk_model import get_risk_profile

logger = logging.getLogger(__name__)

__all__ = ["ToolRegistry", "get_tool_registry"]


class ToolRegistry:
    """Unified registry for all tools (actions, adapters, external)."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._tools: dict[str, ToolDefinition] = {}
        self._by_category: dict[str, list[str]] = {}
        self._aliases: dict[str, str] = {}  # alias -> canonical name
        self._action_registry = None
        self._mutation_lock = threading.Lock()

    def register(self, tool: ToolDefinition) -> bool:
        """Register a tool.

        Returns True if this was a new registration, False if an existing
        tool with the same name was overwritten (caller can detect this).
        """
        with self._mutation_lock:
            overwritten = tool.name in self._tools
            if overwritten:
                logger.warning("[ToolRegistry] Overwriting tool '%s'", tool.name)

            self._tools[tool.name] = tool

            # Register aliases (skip any that collide with a real tool name
            # or an existing alias so lookups can't be silently redirected)
            for alias in tool.aliases:
                if alias in self._tools and alias != tool.name:
                    logger.warning(
                        "[ToolRegistry] Alias '%s' for tool '%s' collides with an "
                        "existing tool name; skipping alias",
                        alias, tool.name,
                    )
                    continue
                existing_target = self._aliases.get(alias)
                if existing_target is not None and existing_target != tool.name:
                    logger.warning(
                        "[ToolRegistry] Alias '%s' already points to '%s'; "
                        "not redirecting to '%s'",
                        alias, existing_target, tool.name,
                    )
                    continue
                self._aliases[alias] = tool.name

            # Register by category
            if tool.category not in self._by_category:
                self._by_category[tool.category] = []
            if tool.name not in self._by_category[tool.category]:
                self._by_category[tool.category].append(tool.name)

        return not overwritten

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        with self._mutation_lock:
            if name in self._tools:
                tool = self._tools.pop(name)
                # Remove from category
                if tool.category in self._by_category:
                    self._by_category[tool.category] = [
                        t for t in self._by_category[tool.category] if t != name
                    ]
                # Remove aliases
                for alias in tool.aliases:
                    self._aliases.pop(alias, None)

    def get(self, name: str) -> ToolDefinition | None:
        """Get tool by name or alias."""
        # Resolve alias first
        canonical_name = self._aliases.get(name, name)
        return self._tools.get(canonical_name)

    def list_tools(self, category: str = None) -> list[str]:
        """List all tools, optionally filtered by category."""
        if category:
            return self._by_category.get(category, []).copy()
        return list(self._tools.keys())

    def list_categories(self) -> list[str]:
        """List all categories."""
        return list(self._by_category.keys())

    def filter_by_risk(self, risk_level: str) -> list[str]:
        """List tools by risk level."""
        return [
            name for name, tool in self._tools.items()
            if tool.risk_level == risk_level
        ]

    def filter_by_capability(self, capability: str) -> list[str]:
        """List tools by capability."""
        return [
            name for name, tool in self._tools.items()
            if tool.capability == capability
        ]

    def filter_available(self) -> list[str]:
        """List only available tools."""
        return [
            name for name, tool in self._tools.items()
            if tool.available
        ]

    def find_duplicates(self) -> dict[str, list[str]]:
        """Find tools that may be duplicates (same category + description)."""
        by_desc = {}
        for name, tool in self._tools.items():
            key = (tool.category, tool.description)
            if key not in by_desc:
                by_desc[key] = []
            by_desc[key].append(name)

        return {k: v for k, v in by_desc.items() if len(v) > 1}

    def validate_schema(self, name: str, input_data: dict) -> tuple[bool, str]:
        """Validate input against tool's input schema (basic)."""
        tool = self.get(name)
        if not tool:
            return False, f"Tool '{name}' not found"

        if not tool.input_schema:
            return True, "No schema defined"

        # Basic JSON Schema validation
        required = tool.input_schema.get("required", [])
        for field in required:
            if field not in input_data:
                return False, f"Required field missing: {field}"

        return True, "Valid"

    def set_availability(self, name: str, available: bool, error: str = None) -> None:
        """Set tool availability."""
        with self._mutation_lock:
            tool = self.get(name)
            if tool:
                tool.available = available
                tool.state = "AVAILABLE" if available else "UNAVAILABLE"
                if error:
                    tool.last_error = error

    @staticmethod
    def _make_action_registry_executor(action_registry, action_name: str) -> Callable:
        """Closure que delega para `ActionRegistry.execute(action_name, **kwargs)`.

        `action_name` é capturado por argumento (não por variável de loop) de
        propósito — closure sobre variável de loop é o bug clássico de
        late-binding em Python (todas as closures acabariam apontando para o
        último `action_name` iterado).
        """

        def _executor(**kwargs):
            return action_registry.execute(action_name, **kwargs)

        return _executor

    def adapt_from_action_registry(self, action_registry) -> int:
        """Adapt all actions from ActionRegistry to ToolRegistry.

        Returns number of tools registered.
        """
        self._action_registry = action_registry
        count = 0
        failed: list[str] = []

        try:
            action_specs = action_registry.get_all_specs()
        except Exception:
            logger.exception("[ToolRegistry] Failed to read specs from ActionRegistry")
            return count

        for action_name, action_spec in action_specs.items():
            try:
                tool = ToolDefinition.from_action_spec(action_spec)

                # Enrich with risk profile if available
                risk_prof = get_risk_profile(action_name)
                if risk_prof:
                    tool.risk_level = risk_prof.risk_level
                    tool.requires_confirmation = risk_prof.requires_confirmation
                    tool.requires_superbrain = risk_prof.requires_superbrain

                # BUGFIX_2026-09-02: from_action_spec() nunca ligava
                # `tool.executor` a nada, então ToolRouter.route() sempre
                # retornava "No executor for '<name>'" para qualquer tool
                # adaptada daqui — nenhum caminho de produção chamava
                # get_tool_router() antes do Planner (ver
                # core/planner/execution.py), então isso nunca foi notado.
                # Delegar para ActionRegistry.execute() completa o "adapter
                # pattern" que o docstring de from_action_spec já dizia
                # implementar: ActionRegistry.execute() já aplica os gates
                # de capability/risk/permission de qualquer forma, então
                # nenhuma checagem é pulada ao rotear por aqui.
                tool.executor = self._make_action_registry_executor(action_registry, action_name)
                tool.async_execution = bool(action_spec.async_execution)

                self.register(tool)
                count += 1
            except Exception:
                failed.append(action_name)
                logger.exception(
                    "[ToolRegistry] Error adapting action '%s' from ActionRegistry",
                    action_name,
                )

        if failed:
            logger.warning(
                "[ToolRegistry] %d/%d actions failed to adapt: %s",
                len(failed), len(action_specs), failed,
            )

        return count

    def get_all_specs(self) -> dict[str, dict]:
        """Get all tool specs as dict (for serialization)."""
        return {name: tool.to_dict() for name, tool in self._tools.items()}

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={len(self._tools)} categories={len(self._by_category)}>"


# Global singleton instance
_registry_instance = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global ToolRegistry instance."""
    return _registry_instance
