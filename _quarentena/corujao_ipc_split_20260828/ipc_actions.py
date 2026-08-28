# core/ipc_actions.py
"""
IPC Actions - Action execution, confirmation, listing, system metrics.
Extracted from IPCHandler (God Class decomposition).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.ipc_protocol import IPCMessage


class IPCActions:
    """Handles action-related IPC: execute, confirm, list, system metrics/info."""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._handler: "IPCHandler" = None

    def bind_handler(self, handler: "IPCHandler") -> None:
        self._handler = handler

    async def handle_action_execute(self, msg: IPCMessage) -> None:
        """Execute an action."""
        # ... moved from IPCHandler
        pass

    async def handle_action_confirm(self, msg: IPCMessage) -> None:
        """Confirm pending action."""
        # ... moved from IPCHandler
        pass

    async def handle_action_confirm_cancel(self, msg: IPCMessage) -> None:
        """Cancel pending action confirmation."""
        # ... moved from IPCHandler
        pass

    async def handle_action_list(self, msg: IPCMessage) -> None:
        """List available actions."""
        # ... moved from IPCHandler
        pass

    async def handle_system_metrics(self, msg: IPCMessage) -> None:
        """Report system metrics."""
        # ... moved from IPCHandler
        pass

    async def handle_system_info(self, msg: IPCMessage) -> None:
        """Report system info."""
        # ... moved from IPCHandler
        pass

    def _selo_do_ultimo_resultado(self) -> str:
        """Get seal of last result."""
        # ... moved from IPCHandler
        return ""

    async def _conversar(self, texto: str) -> str:
        """Conversational fallback."""
        # ... moved from IPCHandler
        return ""

    def _ocioso_ha_quantos_segundos(self) -> float:
        """Idle time."""
        # ... moved from IPCHandler
        return 0.0

    def _tela_bloqueada(self) -> bool:
        """Check if screen is locked."""
        # ... moved from IPCHandler
        return False

    def _parece_dirigido_a_ela(self, frase: str) -> bool:
        """Check if phrase is directed at ZARA."""
        # ... moved from IPCHandler
        return False

    def _arquivo_da_voz(self):
        """Voice data file."""
        # ... moved from IPCHandler
        return None

    def _carregar_silenciada(self) -> bool:
        """Load mute state."""
        # ... moved from IPCHandler
        return False

    def _gravar_silenciada(self, mudo: bool) -> None:
        """Save mute state."""
        # ... moved from IPCHandler
        pass

    # Learning / Memory (delegated)
    def _anotar_experiencia(self, pedido: str, acao: str, sucesso: bool,
                            resultado: object, origem: str) -> None:
        # ... moved from IPCHandler
        pass

    def _ouvir_reacao_do_alex(self, fala: str) -> None:
        # ... moved from IPCHandler
        pass

    def _anotar_o_que_alex_disse(self, texto: str, origem: str) -> None:
        # ... moved from IPCHandler
        pass

    async def _append_conversation_message(self, role: str, content: str) -> None:
        # ... moved from IPCHandler
        pass

    async def _try_reminder_intent(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    async def _try_pc_intent(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    async def _executar_intent_de_pc(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    async def _try_compound_pc_intent(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    def _jarvis_reply_status(self, reply: str | None) -> str:
        # ... moved from IPCHandler
        return ""

    async def _try_jarvis_multi_action(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    # Self-knowledge / Latency
    async def _build_self_knowledge_snapshot(self, *, probe_hardware: bool = False) -> dict[str, Any]:
        # ... moved from IPCHandler
        return {}

    async def _try_self_knowledge(self, text: str) -> str | None:
        # ... moved from IPCHandler
        return None

    def _confirmar_o_que_entendeu(self) -> str:
        # ... moved from IPCHandler
        return ""

    def _contar_a_latencia(self) -> str | None:
        # ... moved from IPCHandler
        return None