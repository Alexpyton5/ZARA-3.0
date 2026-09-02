"""
Tool Result — Standardized result structure for tool execution.

Preserves backward compatibility with ActionResult while adding
structured error, verification, and metadata fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["ToolResult", "ToolVerificationResult"]


@dataclass
class ToolVerificationResult:
    """Result of tool verification (was the action actually executed?)."""

    state: str  # VERIFIED | FAILED | UNKNOWN | NOT_APPLICABLE
    proof: Any = None  # Evidence of verification (e.g., file stat, readback value)
    error: str | None = None  # Verification failure reason
    confidence: float = 1.0  # Confidence level (0.0 to 1.0)

    def is_verified(self) -> bool:
        """Whether action was proven to execute."""
        return self.state == "VERIFIED"

    def is_uncertain(self) -> bool:
        """Whether action result is uncertain (not verified)."""
        return self.state in ("UNKNOWN", "NOT_APPLICABLE")

    def is_failed(self) -> bool:
        """Whether verification detected failure."""
        return self.state == "FAILED"


@dataclass
class ToolResult:
    """Result of tool execution.

    - success: Whether execution succeeded (requested action completed)
    - data: Result data (tool-specific structure)
    - error: Error message if failed
    - error_code: Standardized error code (VALIDATION_ERROR, TIMEOUT, etc.)
    - duration_ms: Execution time in milliseconds
    - metadata: Extended result metadata
    - verification: Verification state (action actually executed?)
    - retryable: Whether action can be retried

    ZARA-NAO-VERIFICADO-001: Honesty about verification state:
    - success=True, verificado=True → action confirmed executed
    - success=True, verificado=False → action dispatched but not confirmed
    - success=False → action failed to execute

    "Dispatched but not confirmed" is NOT success; it's honest uncertainty.
    """

    success: bool = False
    data: Any = None
    output: str = ""  # Backward compat with ActionResult
    error: str = ""
    error_code: str | None = None
    message: str = ""
    duration_ms: float = 0.0

    # Verification: was the action actually executed?
    # True = observed postcondition (file exists, volume changed, etc.)
    # False = action dispatched but could not verify execution
    verificado: bool = False

    # Extended metadata
    metadata: dict = field(default_factory=dict)
    verification: ToolVerificationResult | None = None
    retryable: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def incerto(self) -> bool:
        """Executed but unverified (honest uncertainty)."""
        return self.success and not self.verificado

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "output": self.output,
            "error": self.error,
            "error_code": self.error_code,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "verificado": self.verificado,
            "incerto": self.incerto(),
            "metadata": self.metadata,
            "verification": (
                {
                    "state": self.verification.state,
                    "confidence": self.verification.confidence,
                    "error": self.verification.error,
                }
                if self.verification
                else None
            ),
            "retryable": self.retryable,
        }

    @classmethod
    def from_action_result(cls, action_result) -> ToolResult:
        """Convert ActionResult to ToolResult (adapter pattern)."""
        return cls(
            success=action_result.success,
            data=action_result.data,
            output=action_result.output,
            error=action_result.error,
            duration_ms=action_result.duration_ms,
            verificado=action_result.verificado,
        )

    def __bool__(self) -> bool:
        """Truthy if success AND verified."""
        return self.success and self.verificado

    def __str__(self) -> str:
        if self.success and not self.verificado:
            return f"INCERTO: {self.output or self.message or 'Executed but unverified'}"
        return self.output or self.error or self.message or ("OK" if self.success else "FAILED")
