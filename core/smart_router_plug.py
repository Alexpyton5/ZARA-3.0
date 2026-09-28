# core/smart_router_plug.py — Ponte entre o classificador da zoe e o ModelRouter.
#
# Traduz CHAT/LEVE/PESADO -> TaskType e entrega como SUGESTÃO via context
# ("smart_router_hint"), que o ModelRouter honra em classify_intent().
#
# Atrás de flag: ZARA_SMART_ROUTER=1 liga. Desligado (padrão) = comportamento
# atual do app, zero mudança. Só sugere — ranking, health e fallback
# continuam 100% no ModelRouter.
from __future__ import annotations

import os

from core.model_router import TaskType
from core.smart_router import PESADO, classify

_FLAG_ENV = "ZARA_SMART_ROUTER"

# Sinais de que o pedido pesado é de código (vira CODING antes de REASONING)
_CODE_KEYWORDS = (
    "código", "codigo", "program", "script", "função", "funcao",
    "bug", "python", "javascript", "typescript", "debug",
)


def smart_router_enabled() -> bool:
    """Flag da integração. Padrão: desligado (preserva o comportamento atual)."""
    return os.environ.get(_FLAG_ENV, "").strip().lower() in {"1", "true", "on", "yes"}


def suggest_task_types(
    pedido: str,
    modo_chat: bool = False,
    motor_manual: str | None = None,
) -> list[TaskType]:
    """Sugere TaskTypes a partir do pedido, via classificador da zoe."""
    nivel = classify(pedido, modo_chat=modo_chat, motor_manual=motor_manual)
    if nivel == PESADO:
        t = (pedido or "").lower()
        if any(k in t for k in _CODE_KEYWORDS):
            return [TaskType.CODING, TaskType.REASONING]
        return [TaskType.REASONING]
    # CHAT, LEVE ou qualquer valor manual desconhecido: o seguro é GENERAL_CHAT
    return [TaskType.GENERAL_CHAT]
