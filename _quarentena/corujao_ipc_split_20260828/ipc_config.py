# core/ipc_config.py
"""
IPC Config - Configuration get/set, engine preferences, runtime prefs.
Extracted from IPCHandler (God Class decomposition).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.ipc_protocol import IPCMessage


class IPCConfig:
    """Handles configuration IPC: get, set, engine list, preferences."""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._handler: "IPCHandler" = None

    def bind_handler(self, handler: "IPCHandler") -> None:
        self._handler = handler

    def _load_runtime_preferences(self) -> None:
        """Load runtime preferences from disk."""
        # ... moved from IPCHandler
        pass

    def _persist_engine_preference(self, engine: str) -> None:
        """Persist engine preference."""
        # ... moved from IPCHandler
        pass

    async def handle_config_get(self, msg: IPCMessage) -> None:
        """Handle config_get request."""
        # ... moved from IPCHandler
        pass

    async def handle_config_set(self, msg: IPCMessage) -> None:
        """Handle config_set request."""
        # ... moved from IPCHandler
        pass

    async def handle_engine_list(self, msg: IPCMessage) -> None:
        """List available engines."""
        # ... moved from IPCHandler
        pass

    async def handle_engine_change(self, msg: IPCMessage) -> None:
        """Handle engine change request."""
        # ... moved from IPCHandler
        pass

    async def handle_supercerebro_status(self, msg: IPCMessage) -> None:
        """Report supercerebro status."""
        # ... moved from IPCHandler
        pass

    async def handle_self_status(self, msg: IPCMessage) -> None:
        """Report self status."""
        # ... moved from IPCHandler
        pass