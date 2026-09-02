"""
Clipboard Verifier — Verify clipboard operations.
"""
from typing import Any

from core.tool_verifier import ToolVerifier, ToolVerificationResult, VerificationState

__all__ = ["ClipboardWriteVerifier", "ClipboardReadVerifier"]


class ClipboardWriteVerifier(ToolVerifier):
    """Verify that text was written to clipboard."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        expected_text = parameters.get("text")
        if not expected_text:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No text in parameters",
            )

        try:
            import pyperclip

            current_clipboard = pyperclip.paste()
            if current_clipboard == expected_text:
                return ToolVerificationResult(
                    state=VerificationState.VERIFIED,
                    proof={"text_length": len(expected_text)},
                    confidence=1.0,
                )
            else:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"Clipboard mismatch: expected {len(expected_text)} chars, got {len(current_clipboard)} chars",
                )
        except ImportError:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="pyperclip not available",
            )
        except Exception as e:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error=f"Clipboard verification error: {e}",
            )


class ClipboardReadVerifier(ToolVerifier):
    """Verify that clipboard was read."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        # Reading clipboard is inherently verifiable (got some text back)
        if result_data and isinstance(result_data, str) and len(result_data) > 0:
            return ToolVerificationResult(
                state=VerificationState.VERIFIED,
                proof={"text_length": len(result_data)},
                confidence=1.0,
            )
        else:
            return ToolVerificationResult(
                state=VerificationState.UNKNOWN,
                error="No text in result",
            )
