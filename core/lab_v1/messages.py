"""Canonical helpers for persistent agent-to-agent messages.

The SQLite ``messages`` table remains the source of truth.  This module only
contains deterministic normalization and read-model helpers; it does not add
a second in-memory bus or a background worker.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from core.lab_v1.domain import Message
from core.lab_v1.mentions import (
    MentionResolutionError,
    active_member_ids,
    resolve_recipient_ids,
)

__all__ = [
    "MESSAGE_MAX_CHARS",
    "normalize_message_text",
    "new_correlation_id",
    "message_to_dict",
    "message_provenance",
    "pending_reply_ids",
    "MentionResolutionError",
    "active_member_ids",
    "resolve_recipient_ids",
]

MESSAGE_MAX_CHARS = 4000
_CORRELATION_PREFIX = "v1comm_"
_WHITESPACE = re.compile(r"\s+")


def normalize_message_text(text: Any, *, max_chars: int = MESSAGE_MAX_CHARS) -> str:
    """Return bounded, single-line communication text.

    Agent-to-agent traffic is intentionally concise.  Whitespace is folded so
    a persisted message has stable rendering and comparisons across restart;
    truncation is explicit rather than silently allowing an unbounded prompt.
    """
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    value = _WHITESPACE.sub(" ", str(text or "")).strip()
    if not value:
        raise ValueError("A message needs non-empty content")
    if len(value) > max_chars:
        raise ValueError(f"A message is limited to {max_chars} characters")
    return value


def new_correlation_id(prefix: str = _CORRELATION_PREFIX) -> str:
    # Import lazily to keep this helper dependency-free at module import time.
    from core.lab_v1.domain import new_id
    return new_id(prefix.rstrip("_"))


def message_to_dict(message: Message, *, pending: bool | None = None,
                    provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Serialize a canonical Message with additive read-model metadata."""
    result = message.to_dict()
    if pending is not None:
        result["pending_reply"] = bool(pending)
    if provenance is not None:
        result["provenance"] = dict(provenance)
    return result


def message_provenance(message: Message, *, task_id: str | None = None,
                       assigned_agent_id: str | None = None) -> dict[str, Any]:
    """Build provenance from persisted Message fields only.

    No display name or current role is treated as identity.  A consumer can
    follow ``run_id`` to the canonical Run row when it needs provider/model
    evidence.
    """
    return {
        "message_id": message.id,
        "session_id": message.session_id,
        "author_agent_id": message.author_agent_id,
        "to_agent_id": message.to_agent_id,
        "run_id": message.run_id,
        "correlation_id": message.correlation_id,
        "reply_to": message.reply_to,
        "task_id": task_id,
        "assigned_agent_id": assigned_agent_id,
    }


def pending_reply_ids(messages: Iterable[Message], *, for_agent_id: str | None = None) -> set[str]:
    """Return root addressed messages still awaiting their recipient reply.

    A reply is any later message whose ``reply_to`` references the root.  The
    result is reconstructed entirely from SQLite rows, so it survives process
    restart and does not depend on an in-memory pending flag.
    """
    rows = list(messages)
    replied = {message.reply_to for message in rows if message.reply_to}
    pending: set[str] = set()
    for message in rows:
        if message.reply_to is not None:
            continue
        if not message.to_agent_id or message.id in replied:
            continue
        if for_agent_id is not None and message.to_agent_id != for_agent_id:
            continue
        pending.add(message.id)
    return pending
