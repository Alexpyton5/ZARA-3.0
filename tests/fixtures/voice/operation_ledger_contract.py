"""Test-only voice-to-ledger boundary retained from the archived fixture.

This records admission only; provider dispatch and spoken responses stay out
of this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VoiceOperationRequest:
    request_id: str
    command: str
    transcript: str
    session_id: str | None = None


class DurableAdmissionAck(Protocol):
    request_id: str
    operation_id: str
    command: str
    accepted: bool
    newly_admitted: bool


class LedgerAdmitter(Protocol):
    def admit(
        self, request_id: str, command: str, payload: dict[str, Any]
    ) -> DurableAdmissionAck: ...


class WakeupEvent(Protocol):
    def set(self) -> None: ...


def admit_voice_operation(
    ledger: LedgerAdmitter,
    request: VoiceOperationRequest,
    *,
    wakeup: WakeupEvent | None = None,
) -> DurableAdmissionAck:
    """Persist admission before waking the existing consumer."""
    admit = getattr(ledger, "admit", None)
    if not callable(admit):
        raise TypeError("ledger must provide an admit method")
    signal = None if wakeup is None else getattr(wakeup, "set", None)
    if wakeup is not None and not callable(signal):
        raise TypeError("wakeup must provide a set method")

    request_id = _required(request.request_id, "request_id")
    command = _required(request.command, "command")
    transcript = _required(request.transcript, "transcript")
    payload = _dispatch_payload(command, transcript, request.session_id)
    ack = admit(request_id, command, payload)
    _validate_ack(ack, request_id=request_id, command=command)
    if signal is not None:
        signal()
    return ack


def _dispatch_payload(
    command: str, transcript: str, session_id: str | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"source": "voice", "transcript": transcript}
    if command == "lab.v1.submit":
        payload["objective"] = transcript
        if session_id is not None:
            payload["session_id"] = _required(session_id, "session_id")
        return payload
    if command == "lab.v1.message":
        payload["session_id"] = _required(session_id, "session_id")
        payload["content"] = transcript
        return payload
    if command in {"lab.v1.cancel", "lab.v1.resume"}:
        payload["session_id"] = _required(session_id, "session_id")
        return payload
    raise ValueError(f"unsupported voice command: {command}")


def _validate_ack(
    ack: DurableAdmissionAck, *, request_id: str, command: str
) -> None:
    if ack is None:
        raise TypeError("ledger ack is required")
    if getattr(ack, "accepted", None) is not True:
        raise ValueError("ledger ack was not accepted")
    if not isinstance(getattr(ack, "newly_admitted", None), bool):
        raise TypeError("ledger ack newly_admitted must be boolean")
    operation_id = getattr(ack, "operation_id", None)
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError("ledger ack operation_id is required")
    if getattr(ack, "request_id", None) != request_id:
        raise ValueError("ledger ack request_id mismatch")
    if getattr(ack, "command", None) != command:
        raise ValueError("ledger ack command mismatch")


def _required(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()
