"""Remote Approval Bridge — Single-use approval flow for risky actions.

Security contract:
- One approval per action, consumed once
- Token verification via injected verifier callable
- Thread-safe with bounded terminal history
- No check-then-act or execution APIs exposed
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class _ApprovalRecord:
    action_description: str
    status: str  # pending, approved, rejected, expired, consumed
    created_at: float
    expires_at: float
    token: Optional[str] = None
    decided_at: Optional[float] = None


class RemoteApprovalBridge:
    """Thread-safe, single-use approval bridge.

    Args:
        verifier: Callable that takes a token string and returns True if valid.
                  Can be None (all verifications fail closed).
        clock: Optional callable returning current time (for testing).
        max_terminal_records: Max number of terminal (non-pending) records to keep.
    """

    _TERMINAL = {"approved", "rejected", "expired", "consumed"}

    def __init__(
        self,
        verifier: Optional[Callable[[str], bool]] = None,
        clock: Optional[Callable[[], float]] = None,
        max_terminal_records: int = 100,
    ):
        self._verifier = verifier
        self._clock = clock or time.time
        self._max_terminal = max_terminal_records
        self._pending: dict[str, _ApprovalRecord] = {}
        self._lock = threading.Lock()

    def submit_action(self, description: str, timeout_seconds: float = 6 * 3600) -> str:
        """Submit a new action for remote approval.

        Args:
            description: Human-readable description of the action.
            timeout_seconds: Seconds until the approval expires (default 6h).

        Returns:
            Approval ID (short hex string).

        Raises:
            ValueError: If description is empty or timeout invalid.
        """
        if not description or not description.strip():
            raise ValueError("Action description cannot be empty")
        if timeout_seconds <= 0 or timeout_seconds != timeout_seconds:  # catches inf, nan
            raise ValueError("Timeout must be positive finite number")

        approval_id = uuid.uuid4().hex[:8]
        now = self._clock()

        with self._lock:
            self._pending[approval_id] = _ApprovalRecord(
                action_description=description.strip(),
                status="pending",
                created_at=now,
                expires_at=now + timeout_seconds,
            )
            self._prune_terminal_locked()

        return approval_id

    def get_status(self, approval_id: str) -> Optional[str]:
        """Get current status of an approval."""
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None:
                return None

            # Check expiry
            if record.status == "pending" and self._clock() >= record.expires_at:
                record.status = "expired"
                record.decided_at = self._clock()
            return record.status

    def approve_action(self, approval_id: str, token: str) -> bool:
        """Approve a pending action with a token.

        Returns True only if:
        - approval_id exists and is pending
        - token is valid (verifier returns True)
        - not expired
        - first decision on this approval_id
        """
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None or record.status != "pending":
                return False
            if self._clock() >= record.expires_at:
                record.status = "expired"
                record.decided_at = self._clock()
                return False
            if self._verifier is None or not self._verifier(token):
                return False

            record.status = "approved"
            record.token = token
            record.decided_at = self._clock()
            return True

    def reject_action(self, approval_id: str, token: str) -> bool:
        """Reject a pending action with a token.

        Returns True only if:
        - approval_id exists and is pending
        - token is valid (verifier returns True)
        - not expired
        - first decision on this approval_id
        """
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None or record.status != "pending":
                return False
            if self._clock() >= record.expires_at:
                record.status = "expired"
                record.decided_at = self._clock()
                return False
            if self._verifier is None or not self._verifier(token):
                return False

            record.status = "rejected"
            record.token = token
            record.decided_at = self._clock()
            return True

    def consume_approval(self, approval_id: str) -> bool:
        """Consume an approved approval (single-use).

        Returns True only if:
        - approval_id exists
        - status is 'approved'
        - not already consumed
        """
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None or record.status != "approved":
                return False

            record.status = "consumed"
            record.decided_at = self._clock()
            return True

    def _prune_terminal_locked(self) -> None:
        """Remove oldest terminal records beyond max_terminal_records."""
        terminal_ids = [
            aid for aid, rec in self._pending.items()
            if rec.status in self._TERMINAL
        ]
        # Sort by decided_at (oldest first)
        terminal_ids.sort(key=lambda aid: self._pending[aid].decided_at or 0)
        while len(terminal_ids) > self._max_terminal:
            oldest = terminal_ids.pop(0)
            self._pending.pop(oldest, None)