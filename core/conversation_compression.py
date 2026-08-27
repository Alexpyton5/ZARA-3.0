"""ZARA-CONVERSA-LONGA-2026-08-27: deixa a Zara aguentar conversar por horas.

O historico de conversa (lista de mensagens) vem do renderer a cada
mensagem nova e crescia sem limite nenhum -- cada turno reenviava a
conversa inteira desde o comeco. Numa conversa de horas isso ia estourar
o contexto do modelo e ficar cada vez mais caro e lento.

Ideia inspirada no Mark LI ("sliding-window context compression"),
implementada do zero aqui: mantem as mensagens mais recentes inteiras e
troca as mais antigas por um resumo curto de uma linha, em vez de cortar
tudo cru ou mandar tudo sem limite.
"""
from __future__ import annotations

DEFAULT_MAX_MESSAGES = 40
DEFAULT_MAX_CHARS = 16_000


def _message_chars(msg: dict) -> int:
    return len(str(msg.get("content", "")))


def compress_history(
    history: list[dict] | None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """Return history unchanged if it fits; otherwise keep the most recent
    messages and replace the older ones with one short summary marker.

    Never raises: entrada invalida (None, tipos errados) volta como lista
    vazia em vez de derrubar a conversa.
    """
    if not history:
        return []
    try:
        messages = [m for m in history if isinstance(m, dict)]
    except TypeError:
        return []

    if len(messages) <= max_messages and sum(_message_chars(m) for m in messages) <= max_chars:
        return messages

    kept: list[dict] = []
    total_chars = 0
    for msg in reversed(messages):
        chars = _message_chars(msg)
        if len(kept) >= max_messages or total_chars + chars > max_chars:
            break
        kept.append(msg)
        total_chars += chars
    kept.reverse()

    omitted_count = len(messages) - len(kept)
    if omitted_count <= 0:
        return kept

    summary_marker = {
        "role": "system",
        "content": (
            f"[Conversa longa: {omitted_count} mensagem(ns) mais antiga(s) "
            "foram resumidas fora daqui para caber no contexto. Continue a "
            "conversa a partir das mensagens recentes abaixo.]"
        ),
    }
    return [summary_marker] + kept
