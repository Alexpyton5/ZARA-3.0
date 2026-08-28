# core/ipc_router.py
"""
IPC Router - Core message routing and dispatch.
Extracted from IPCHandler (God Class decomposition).
"""
from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from core.ipc_protocol import IPCMessage


class IPCRouter:
    """Routes incoming IPC messages to appropriate handlers."""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._handler: "IPCHandler" = None  # set by IPCHandler after init

    def bind_handler(self, handler: "IPCHandler") -> None:
        """Back-reference to main handler for cross-module calls."""
        self._handler = handler

    async def handle_message(self, msg: IPCMessage) -> None:
        """Main entry point: route message by type."""
        msg_type = getattr(msg, "type", None)
        if not msg_type:
            await self.send_error(msg, "Mensagem sem tipo")
            return

        # Map message types to handler methods
        handlers = {
            # Lab
            "lab_state": self._handler.handle_lab_state,
            "lab_send": self._handler.handle_lab_send,
            "lab_proposal_create": self._handler.handle_lab_proposal_create,
            "lab_proposal_decide": self._handler.handle_lab_proposal_decide,
            # Engine / Supercerebro
            "engine_change": self._handler.handle_engine_change,
            "supercerebro_toggle": self._handler.handle_supercerebro_toggle,
            "supercerebro_status": self._handler.handle_supercerebro_status,
            # Actions
            "action_execute": self._handler.handle_action_execute,
            "action_confirm": self._handler.handle_action_confirm,
            "action_confirm_cancel": self._handler.handle_action_confirm_cancel,
            "action_list": self._handler.handle_action_list,
            # Config
            "config_get": self._handler.handle_config_get,
            "config_set": self._handler.handle_config_set,
            "engine_list": self._handler.handle_engine_list,
            # System
            "system_metrics": self._handler.handle_system_metrics,
            "system_info": self._handler.handle_system_info,
            # Voice
            "voice_start": self._handler.handle_voice_start,
            "voice_stop": self._handler.handle_voice_stop,
            "voice_mute": self._handler.handle_voice_mute,
            "voice_status": self._handler.handle_voice_status,
            # Communication
            "send_message": self._handler.handle_send_message,
            "interrupt": self._handler.handle_interrupt,
            # Self status
            "self_status": self._handler.handle_self_status,
            # Reminder
            "reminder-create": self._handler.handle_reminder_create,
            "reminder-list": self._handler.handle_reminder_list,
            "reminder-cancel": self._handler.handle_reminder_cancel,
            # Memory
            "memory-user-add": self._handler.handle_memory_user_add,
            "memory-user-search": self._handler.handle_memory_user_search,
            "memory-user-list": self._handler.handle_memory_user_list,
            "memory-user-forget": self._handler.handle_memory_user_forget,
            # Project memory
            "project-memory-get": self._handler.handle_project_memory_get,
            "project-memory-list": self._handler.handle_project_memory_list,
            # Galaxy memory
            "memory-galaxy-list": self._handler.handle_memory_galaxy_list,
            # Conversation history
            "conversation-history-list": self._handler.handle_conversation_history_list,
            "conversation-history-clear": self._handler.handle_conversation_history_clear,
        }

        handler_method = handlers.get(msg_type)
        if handler_method:
            try:
                await handler_method(msg)
            except Exception as e:
                print(f"[IPC] Handler error for {msg_type}: {e}")
                traceback.print_exc()
                await self.send_error(msg, str(e))
        else:
            await self.send_error(msg, f"Tipo de mensagem desconhecido: {msg_type}")

    async def send_response(
        self, request_id: str, response: Any = None, error: str = None, result: Any = None
    ) -> None:
        """Send a response message."""
        from core.ipc_protocol import IPCMessage
        await self.send(IPCMessage(
            type="response",
            request_id=request_id,
            response=response,
            error=error,
            result=result,
        ))

    async def send_error(self, msg: IPCMessage, error: str) -> None:
        """Send an error response."""
        await self.send_response(getattr(msg, "request_id", "unknown"), error=error)

    async def send_event(self, event_type: str, data: Any) -> None:
        """Send an event notification."""
        from core.ipc_protocol import IPCMessage
        await self.send(IPCMessage(type="event", event=event_type, data=data))