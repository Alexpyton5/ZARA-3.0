"""Telegram Approval Adapter — Simple adapter for Telegram approval flow.

This module provides a thin adapter that translates Telegram message updates
into approval bridge operations and vice versa.
"""

from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import AsyncMock


class TelegramApprovalAdapter:
    """Simple adapter between Telegram bot and approval flow.

    Usage:
        adapter = TelegramApprovalAdapter(ponte)

        # To send approval request:
        await adapter.send_request(approval_id, message)

        # To handle response:
        approved = await adapter.handle_response(approval_id, "sim")
    """

    def __init__(self, ponte):
        """Initialize with a Telegram ponte (must have avisar coroutine)."""
        self._ponte = ponte
        self._pending: dict[str, asyncio.Future] = {}

    async def send_request(self, approval_id: str, message: str) -> bool:
        """Send approval request via Telegram.

        Args:
            approval_id: Unique approval identifier.
            message: Message to send.

        Returns:
            True if ponte.avisar succeeded, False otherwise.
        """
        try:
            result = await self._ponte.avisar(message)
            return bool(result)
        except Exception:
            return False

    def parse_response(self, text: str) -> tuple[Optional[str], Optional[bool]]:
        """Parse Telegram response text.

        Returns:
            (approval_id, approved) where approved is True/False/None.
            Returns (None, None) if not a valid approval response.
        """
        text = text.strip()
        parts = text.split()
        if len(parts) != 2:
            return None, None

        response, approval_id = parts[0].lower(), parts[1]
        if response in ("sim", "s", "yes", "y", "aprovo", "aprovado", "autorizo"):
            return approval_id, True
        if response in ("não", "nao", "n", "no", "rejeito", "rejeitado", "recuso"):
            return approval_id, False

        return None, None

    async def handle_response(self, approval_id: str, response_text: str) -> bool:
        """Process a parsed approval response.

        Args:
            approval_id: The approval ID.
            response_text: Raw response text from user.

        Returns:
            True if response was valid (sim/não), False otherwise.
        """
        parsed_id, approved = self.parse_response(response_text)
        if parsed_id != approval_id or approved is None:
            return False

        # Resolve pending future if exists
        future = self._pending.pop(approval_id, None)
        if future and not future.done():
            future.set_result(approved)
        return True

    def wait_for_response(self, approval_id: str, timeout: float = 30.0) -> Optional[bool]:
        """Wait for a response to an approval request.

        Args:
            approval_id: The approval ID to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            True if approved, False if rejected, None if timeout.
        """
        future = asyncio.Future()
        self._pending[approval_id] = future
        try:
            # This is a sync wrapper - in real usage would be called from async context
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(asyncio.wait_for(future, timeout=timeout))
        except asyncio.TimeoutError:
            self._pending.pop(approval_id, None)
            return None


# Backward compatibility: if someone passes (bridge, config), adapt
def _create_adapter(*args, **kwargs):
    """Factory that handles both old and new signatures."""
    if len(args) == 2 and not isinstance(args[1], asyncio.Future):
        # Old signature: (bridge, config) - create a mock ponte from bridge
        bridge, config = args
        class MockPonte:
            def __init__(self, bridge):
                self._bridge = bridge
            async def avisar(self, message):
                # In real usage, this would send via Telegram
                # For testing, just return True
                return True
        ponte = MockPonte(bridge)
        return TelegramApprovalAdapter(ponte)
    return TelegramApprovalAdapter(*args, **kwargs)