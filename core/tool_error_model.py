"""
Tool Error Model — Standardized error categories and handling.

Provides unified error classification for tools without masking
underlying exceptions or logging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["ToolError", "ErrorCategory", "tool_error"]


class ErrorCategory:
    """Standard error categories."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class ToolError:
    """Structured tool error."""

    category: str = ErrorCategory.UNKNOWN
    message: str = ""
    details: dict[str, Any] | None = None
    retryable: bool = False
    original_exception: Exception | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category,
            "message": self.message,
            "details": self.details or {},
            "retryable": self.retryable,
        }

    def __str__(self) -> str:
        return f"{self.category}: {self.message}"


def tool_error(
    category: str = ErrorCategory.EXECUTION_FAILED,
    message: str = "",
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    original_exception: Exception | None = None,
) -> ToolError:
    """Create a structured tool error."""
    return ToolError(
        category=category,
        message=message,
        details=details,
        retryable=retryable,
        original_exception=original_exception,
    )


# Error mapping for common exception types
EXCEPTION_TO_ERROR_CATEGORY = {
    ValueError: ErrorCategory.VALIDATION_ERROR,
    TypeError: ErrorCategory.VALIDATION_ERROR,
    KeyError: ErrorCategory.NOT_FOUND,
    FileNotFoundError: ErrorCategory.NOT_FOUND,
    PermissionError: ErrorCategory.PERMISSION_DENIED,
    TimeoutError: ErrorCategory.TIMEOUT,
    ConnectionError: ErrorCategory.DEPENDENCY_ERROR,
    RuntimeError: ErrorCategory.EXECUTION_FAILED,
}


def categorize_exception(exc: Exception) -> str:
    """Map exception type to error category."""
    exc_type = type(exc)
    return EXCEPTION_TO_ERROR_CATEGORY.get(exc_type, ErrorCategory.UNKNOWN)
