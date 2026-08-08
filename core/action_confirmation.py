"""Ephemeral, one-shot confirmations for HIGH-risk actions.

The broker stores only opaque fingerprints and monotonic deadlines. Raw action
parameters are never persisted or logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_HIGH_CONFIRMATION_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "files_delete": (("path", "Excluir"),),
    "os_power": (("action_type", "Ação de energia"),),
    "system_kill": (("pid", "Encerrar processo PID"),),
    "terminal": (("command", "Executar comando"),),
    "terminal_bg": (("command", "Executar comando em segundo plano"),),
    "browser_eval": (("script", "Executar JavaScript"),),
}


def build_confirmation_summary(action: str, params: Mapping[str, Any]) -> str | None:
    """Build an allowlisted, bounded summary for informed HIGH-risk consent."""
    fields = _HIGH_CONFIRMATION_FIELDS.get(action)
    if not fields:
        return None

    parts: list[str] = []
    for field_name, label in fields:
        value = params.get(field_name)
        if value is None and action == "os_power" and field_name == "action_type":
            # Accept the public IPC spelling while binding whichever spelling
            # was actually supplied in the full fingerprint.
            value = params.get("action")
        if value is None or isinstance(value, (dict, list, tuple, set)):
            return None
        rendered = " ".join(str(value).split())[:180]
        if not rendered:
            return None
        parts.append(f"{label}: {rendered}")
    return " | ".join(parts)


class ConfirmationCapacityError(RuntimeError):
    """Raised when the bounded in-memory challenge store is full."""


class ConfirmationSerializationError(ValueError):
    """Raised when action data cannot be represented canonically."""


@dataclass(frozen=True)
class ConfirmationProof:
    confirmation_id: str
    action_fingerprint: str


@dataclass(frozen=True)
class ConfirmationChallenge:
    confirmation_id: str
    action_fingerprint: str
    expires_at: str
    action: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "confirmation_id": self.confirmation_id,
            "action_fingerprint": self.action_fingerprint,
            "expires_at": self.expires_at,
            "action": self.action,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class _PendingConfirmation:
    action_fingerprint: str
    deadline: float


class ConfirmationBroker:
    """Issues and atomically consumes short-lived confirmation challenges."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        max_pending: int = 32,
        clock: Callable[[], float] | None = None,
        wall_clock: Callable[[], float] | None = None,
        secret_key: bytes | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")

        self.ttl_seconds = float(ttl_seconds)
        self.max_pending = int(max_pending)
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or time.time
        self._secret_key = secret_key or secrets.token_bytes(32)
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._pending: dict[str, _PendingConfirmation] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _token_key(confirmation_id: str) -> str:
        return hashlib.sha256(confirmation_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_payload(
        action: str,
        metadata: Mapping[str, Any],
        params: Mapping[str, Any],
    ) -> bytes:
        payload = {
            "action": action,
            "metadata": dict(metadata),
            "params": dict(params),
        }
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ConfirmationSerializationError(
                "Action parameters cannot be fingerprinted safely"
            ) from exc
        return encoded.encode("utf-8")

    def _fingerprint(
        self,
        action: str,
        metadata: Mapping[str, Any],
        params: Mapping[str, Any],
    ) -> str:
        canonical = self._canonical_payload(action, metadata, params)
        digest = hmac.new(self._secret_key, canonical, hashlib.sha256).hexdigest()
        return f"hmac-sha256:{digest}"

    def _purge_expired_locked(self, now: float) -> None:
        expired = [key for key, pending in self._pending.items() if pending.deadline <= now]
        for key in expired:
            self._pending.pop(key, None)

    def issue(
        self,
        *,
        action: str,
        metadata: Mapping[str, Any],
        params: Mapping[str, Any],
        summary: str,
    ) -> ConfirmationChallenge:
        fingerprint = self._fingerprint(action, metadata, params)
        confirmation_id = self._token_factory()
        if not isinstance(confirmation_id, str) or len(confirmation_id) < 16:
            raise RuntimeError("Confirmation token factory returned an invalid token")

        now = self._clock()
        deadline = now + self.ttl_seconds
        with self._lock:
            self._purge_expired_locked(now)
            if len(self._pending) >= self.max_pending:
                raise ConfirmationCapacityError("Confirmation store is full")
            token_key = self._token_key(confirmation_id)
            if token_key in self._pending:
                raise RuntimeError("Confirmation token collision")
            self._pending[token_key] = _PendingConfirmation(
                action_fingerprint=fingerprint,
                deadline=deadline,
            )

        expires_at = datetime.fromtimestamp(
            self._wall_clock() + self.ttl_seconds,
            tz=UTC,
        ).isoformat().replace("+00:00", "Z")
        safe_summary = " ".join(str(summary).split())[:240]
        return ConfirmationChallenge(
            confirmation_id=confirmation_id,
            action_fingerprint=fingerprint,
            expires_at=expires_at,
            action=action,
            summary=safe_summary,
        )

    def consume(
        self,
        proof: ConfirmationProof,
        *,
        action: str,
        metadata: Mapping[str, Any],
        params: Mapping[str, Any],
    ) -> tuple[bool, str]:
        """Consume a proof once and validate it against the current request."""
        if (
            not isinstance(proof.confirmation_id, str)
            or not isinstance(proof.action_fingerprint, str)
            or len(proof.confirmation_id) < 16
        ):
            return False, "CONFIRMATION_INVALID"

        token_key = self._token_key(proof.confirmation_id)
        now = self._clock()
        with self._lock:
            # Pop first: mismatch, races and validation failures are all one-shot.
            pending = self._pending.pop(token_key, None)
            self._purge_expired_locked(now)

        if pending is None:
            return False, "CONFIRMATION_INVALID"
        if pending.deadline <= now:
            return False, "CONFIRMATION_EXPIRED"

        try:
            current_fingerprint = self._fingerprint(action, metadata, params)
        except ConfirmationSerializationError:
            return False, "CONFIRMATION_MISMATCH"

        if not hmac.compare_digest(proof.action_fingerprint, pending.action_fingerprint):
            return False, "CONFIRMATION_MISMATCH"
        if not hmac.compare_digest(current_fingerprint, pending.action_fingerprint):
            return False, "CONFIRMATION_MISMATCH"
        return True, "CONFIRMATION_ACCEPTED"

    def cancel(self, confirmation_id: str) -> bool:
        if not isinstance(confirmation_id, str) or len(confirmation_id) < 16:
            return False
        with self._lock:
            return self._pending.pop(self._token_key(confirmation_id), None) is not None
