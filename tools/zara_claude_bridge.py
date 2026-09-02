"""ZARA-CLAUDE-BRIDGE-001 (Alex, 2026-08-28). Peça isolada.

Transforma um pedido falado/digitado num prompt estruturado pronto pra
disparar no terminal do Claude Code -- reusa o mesmo canal que já existe
(core/ponte_claude.py, action claude_enviar) pra ENVIAR; este módulo só
FORMATA o texto, não envia nada sozinho.
"""
from __future__ import annotations

from datetime import datetime


def format_prompt_for_claude(intent_description: str, *, context: str | None = None) -> str:
    """Monta um prompt estruturado a partir de uma descrição solta de
    intenção. Não inventa contexto que não foi dado -- se `context` for
    None, o prompt não finge ter mais informação do que tem."""
    text = str(intent_description or "").strip()
    if not text:
        raise ValueError("intent_description não pode ser vazio.")

    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"[Pedido via ZARA, {timestamp}]",
        "",
        text,
    ]
    if context:
        lines += ["", f"Contexto adicional: {context}"]
    return "\n".join(lines)
