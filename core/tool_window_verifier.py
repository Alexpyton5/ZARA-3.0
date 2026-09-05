"""
Window Verifier — Verify window operations.
"""
from typing import Any

from core.tool_verifier import ToolVerifier, ToolVerificationResult, VerificationState

__all__ = ["WindowVisibleVerifier"]


class WindowVisibleVerifier(ToolVerifier):
    """Verify that a window is visible/focused."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        window_name = parameters.get("name") or parameters.get("title")
        if not window_name:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No window name in parameters",
            )

        try:
            import pygetwindow

            # Find window by partial name match
            windows = pygetwindow.getWindowsWithTitle(window_name)
            if windows:
                window = windows[0]
                if window.isVisible:
                    return ToolVerificationResult(
                        state=VerificationState.VERIFIED,
                        proof={
                            "window_title": window.title,
                            "is_active": window.isActive,
                            "is_visible": window.isVisible,
                        },
                        confidence=0.95,
                    )
                else:
                    return ToolVerificationResult(
                        state=VerificationState.FAILED,
                        error=f"Window found but not visible: {window.title}",
                    )
            else:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"Window not found: {window_name}",
                )
        except ImportError:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="pygetwindow not available",
            )
        except Exception as e:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error=f"Window verification error: {e}",
            )
