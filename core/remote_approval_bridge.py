"""Remote Approval Bridge — Single-use approval flow for risky actions.

Security contract:
- One approval per action, consumed once
- Token verification via injected verifier callable
- Thread-safe with bounded terminal history
- No check-then-act or execution APIs exposed
"""

from __future__ import annotations

import math
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
        # ZARA-APROVACAO-TIMEOUT-INF-001: o comentario dizia "catches inf,
        # nan" mas so pegava nan (x != x). inf passava direto: <= 0 e falso,
        # inf != inf tambem e falso. Uma aprovacao com timeout infinito
        # nunca expira -- falha de seguranca real num bridge cujo proprio
        # contrato exige expiracao (fail-closed).
        if timeout_seconds <= 0 or math.isnan(timeout_seconds) or math.isinf(timeout_seconds):
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

    def _expire_if_due_locked(self, record: _ApprovalRecord) -> bool:
        """Flip pending/approved records past their deadline to 'expired'.

        ZARA-APROVACAO-EXPIRA-APROVADO-001: só 'pending' virava 'expired'
        aqui. Uma aprovação DECIDIDA a tempo mas nunca consumida ficava
        'approved' para sempre, mesmo muito depois do prazo -- executar uma
        decisão velha não é o mesmo que executar a decisão que alguém tomou
        agora. Precisa ser chamado com o lock já segurado.
        """
        if record.status in ("pending", "approved") and self._clock() >= record.expires_at:
            record.status = "expired"
            record.decided_at = self._clock()
            self._prune_terminal_locked()
            return True
        return False

    def get_status(self, approval_id: str) -> Optional[str]:
        """Get current status of an approval."""
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None:
                return None
            self._expire_if_due_locked(record)
            return record.status

    def approve_action(self, approval_id: str, token: str) -> bool:
        """Approve a pending action with a token.

        Returns True only if:
        - approval_id exists and is pending
        - token is valid (verifier returns True)
        - not expired before OR after verification
        - first decision on this approval_id
        """
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None or record.status != "pending":
                return False
            if self._expire_if_due_locked(record):
                return False
            # ZARA-APROVACAO-VERIFICADOR-FALHA-FECHADA-001: um verificador
            # que lança exceção (adapter fora do ar, etc.) tem que negar,
            # nunca propagar -- fail closed é o contrato desta classe.
            try:
                verified = self._verifier is not None and self._verifier(token)
            except Exception:
                verified = False
            if not verified:
                return False
            # ZARA-APROVACAO-EXPIRA-DURANTE-VERIFICACAO-001: o verificador
            # pode demorar (rede, etc.); reconferir o prazo com o relógio
            # ATUAL antes de aprovar — aprovar algo que já expirou enquanto
            # verificava é a mesma falha de fechamento tardio.
            if self._expire_if_due_locked(record):
                return False

            # ZARA-APROVACAO-TOKEN-NAO-GUARDADO-001: o token nunca era lido
            # de volta em nenhum outro lugar da classe (so escrito aqui e em
            # reject_action) -- pura permanencia de um segredo em memoria
            # sem uso funcional nenhum, visivel em repr(). Verificado, nao
            # precisa ficar guardado depois de decidir.
            record.status = "approved"
            record.decided_at = self._clock()
            self._prune_terminal_locked()
            return True

    def reject_action(self, approval_id: str, token: str) -> bool:
        """Reject a pending action with a token.

        Returns True only if:
        - approval_id exists and is pending
        - token is valid (verifier returns True)
        - not expired before OR after verification
        - first decision on this approval_id
        """
        with self._lock:
            record = self._pending.get(approval_id)
            if record is None or record.status != "pending":
                return False
            if self._expire_if_due_locked(record):
                return False
            try:
                verified = self._verifier is not None and self._verifier(token)
            except Exception:
                verified = False
            if not verified:
                return False
            if self._expire_if_due_locked(record):
                return False

            record.status = "rejected"
            record.decided_at = self._clock()
            self._prune_terminal_locked()
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
            # Nao depende de get_status ter sido chamado antes -- reconfere
            # o prazo aqui tambem.
            if self._expire_if_due_locked(record):
                return False

            record.status = "consumed"
            record.decided_at = self._clock()
            self._prune_terminal_locked()
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