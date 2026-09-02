"""
Tool Verifier — Framework for proving tool/action execution actually happened.

Never invent success; always have proof.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from core.tool_result import ToolVerificationResult

__all__ = ["ToolVerifier", "VerificationState", "verify_result"]


class VerificationState:
    """Verification result states."""
    VERIFIED = "VERIFIED"  # Action execution confirmed
    FAILED = "FAILED"  # Action execution detected as failed
    UNKNOWN = "UNKNOWN"  # Cannot determine if action executed
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Verification not applicable for this tool


class ToolVerifier(ABC):
    """Base class for tool verifiers."""

    @abstractmethod
    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        """Verify that tool execution actually happened.

        Args:
            parameters: Input parameters to the tool
            result_data: Raw result data from executor

        Returns:
            ToolVerificationResult with state, proof, and confidence
        """
        pass


class AlwaysVerified(ToolVerifier):
    """Trivial verifier that always returns VERIFIED."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        return ToolVerificationResult(
            state=VerificationState.VERIFIED,
            confidence=1.0,
        )


class FileExistsVerifier(ToolVerifier):
    """Verify that a file was created/modified."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        path = parameters.get("path") or parameters.get("file")
        if not path:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No file path in parameters",
            )

        try:
            p = Path(path)
            if p.exists():
                return ToolVerificationResult(
                    state=VerificationState.VERIFIED,
                    proof={"exists": True, "size": p.stat().st_size},
                    confidence=1.0,
                )
            else:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"File not found: {path}",
                )
        except Exception as e:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error=str(e),
            )


class FileDeletedVerifier(ToolVerifier):
    """Verify that a file was deleted."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        path = parameters.get("path") or parameters.get("file")
        if not path:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No file path in parameters",
            )

        try:
            p = Path(path)
            if not p.exists():
                return ToolVerificationResult(
                    state=VerificationState.VERIFIED,
                    proof={"deleted": True},
                    confidence=1.0,
                )
            else:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"File still exists: {path}",
                )
        except Exception as e:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error=str(e),
            )


class VolumeChangeVerifier(ToolVerifier):
    """Verify that system volume changed."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        # TODO: Implement actual volume readback
        return ToolVerificationResult(
            state=VerificationState.UNKNOWN,
            error="Volume verifier not yet implemented",
        )


class ProcessExistsVerifier(ToolVerifier):
    """Verify that a process was launched."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        process_name = parameters.get("name") or parameters.get("app")
        if not process_name:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No process name in parameters",
            )

        # TODO: Check if process is running
        return ToolVerificationResult(
            state=VerificationState.UNKNOWN,
            error="Process verifier not yet implemented",
        )


def verify_result(
    verifier: ToolVerifier | Callable,
    parameters: dict[str, Any],
    result_data: Any,
) -> ToolVerificationResult:
    """Verify tool execution.

    Args:
        verifier: ToolVerifier instance or callable that returns ToolVerificationResult
        parameters: Input parameters to the tool
        result_data: Raw result data from executor

    Returns:
        ToolVerificationResult
    """
    try:
        if isinstance(verifier, ToolVerifier):
            return verifier.verify(parameters, result_data)
        elif callable(verifier):
            result = verifier(parameters, result_data)
            if isinstance(result, ToolVerificationResult):
                return result
            else:
                # Assume callable returns bool or truthy value
                if result:
                    return ToolVerificationResult(
                        state=VerificationState.VERIFIED,
                        confidence=1.0,
                    )
                else:
                    return ToolVerificationResult(
                        state=VerificationState.FAILED,
                        error="Verification returned False",
                    )
        else:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error=f"Invalid verifier type: {type(verifier)}",
            )
    except Exception as e:
        return ToolVerificationResult(
            state=VerificationState.UNKNOWN,
            error=f"Verification error: {e}",
        )
