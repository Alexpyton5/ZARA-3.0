# core/ipc_protocol.py
"""
IPC Protocol - Message types and serialization.
Shared by all IPC modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class IPCMessage:
    """Standard IPC message between Electron and Python."""
    type: str
    request_id: Optional[str] = None
    response: Any = None
    error: Optional[str] = None
    result: Any = None
    event: Optional[str] = None
    data: Any = None
    message: Any = None
    # Voice-specific
    audio: Optional[bytes] = None
    level: Optional[float] = None
    speaking: Optional[bool] = None
    state: Optional[str] = None
    partial: Optional[str] = None
    text: Optional[str] = None


def serialize_ipc_message(msg: IPCMessage) -> str:
    """Serialize IPCMessage to JSON string."""
    import json
    # Handle non-serializable fields
    data = {
        "type": msg.type,
        "request_id": msg.request_id,
        "response": msg.response,
        "error": msg.error,
        "result": msg.result,
        "event": msg.event,
        "data": msg.data,
        "message": msg.message,
        "level": msg.level,
        "speaking": msg.speaking,
        "state": msg.state,
        "partial": msg.partial,
        "text": msg.text,
    }
    # Remove None values
    return json.dumps({k: v for k, v in data.items() if v is not None})


def deserialize_ipc_message(text: str) -> IPCMessage:
    """Deserialize JSON string to IPCMessage."""
    import json
    data = json.loads(text)
    return IPCMessage(**data)