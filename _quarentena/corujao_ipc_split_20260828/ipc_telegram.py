# core/ipc_telegram.py
"""
IPC Telegram - Telegram bridge, remote approval, mobile commands.
Extracted from IPCHandler (God Class decomposition).
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from core.ipc_protocol import IPCMessage


class IPCTelegram:
    """Handles Telegram bridge, remote approval queue, and mobile commands."""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._handler: "IPCHandler" = None
        self._telegram_grupo = None
        self._vigia_task: asyncio.Task = None

    def bind_handler(self, handler: "IPCHandler") -> None:
        self._handler = handler

    async def _ligar_telegram(self) -> None:
        """Start Telegram bridge."""
        # ... moved from IPCHandler
        pass

    async def _cuidar_das_pontes(self) -> None:
        """Maintain Telegram bridges."""
        # ... moved from IPCHandler
        pass

    async def _executar_do_celular(self, destino: str, texto: str) -> str:
        """Execute command from mobile."""
        # ... moved from IPCHandler
        return ""

    async def _responder_ao_celular(self, destino: str, texto: str, execute_action) -> str:
        """Respond to mobile message."""
        # ... moved from IPCHandler
        return ""

    def _fila_de_aprovacao(self):
        """Get approval queue."""
        # ... moved from IPCHandler
        return None

    async def pedir_autorizacao_ao_alex(self, o_que: str, quem: str = "O Claude") -> str | None:
        """Request approval from Alex via Telegram."""
        # ... moved from IPCHandler
        return None

    def foi_aprovado(self, id_do_pedido: str) -> bool:
        """Check if approval was granted."""
        # ... moved from IPCHandler
        return False

    async def _ligar_vigia_das_respostas(self) -> None:
        """Start approval watchdog."""
        # ... moved from IPCHandler
        pass

    def _marcar_canal(self, canal: str) -> None:
        """Mark channel for response routing."""
        # ... moved from IPCHandler
        pass

    def _alex_esta_longe(self) -> bool:
        """Check if Alex is away from computer."""
        # ... moved from IPCHandler
        return False

    async def handle_send_message(self, msg: IPCMessage) -> None:
        """Handle send_message IPC (Telegram/bridge)."""
        # ... moved from IPCHandler
        pass