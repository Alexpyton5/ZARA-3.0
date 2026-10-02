"""
Network Verifier — Verify network operations.
"""
from typing import Any

from core.tool_verifier import ToolVerifier, ToolVerificationResult, VerificationState

__all__ = ["NetworkVerifier", "HTTPResponseVerifier"]


class NetworkVerifier(ToolVerifier):
    """Verify that a network operation succeeded (basic HTTP check)."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        # Network operations are hard to verify after-the-fact
        # Best we can do is check if result_data contains a response
        if result_data and isinstance(result_data, dict):
            status_code = result_data.get("status_code") or result_data.get("code")
            if status_code and 200 <= status_code < 400:
                return ToolVerificationResult(
                    state=VerificationState.VERIFIED,
                    proof={"status_code": status_code},
                    confidence=0.9,
                )
            elif status_code:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"HTTP error: {status_code}",
                )

        return ToolVerificationResult(
            state=VerificationState.UNKNOWN,
            error="No status code in result",
        )


class HTTPResponseVerifier(ToolVerifier):
    """Verify HTTP response code."""

    def verify(
        self, parameters: dict[str, Any], result_data: Any
    ) -> ToolVerificationResult:
        expected_codes = parameters.get("expected_codes") or [200, 301, 302]
        if isinstance(expected_codes, int):
            expected_codes = [expected_codes]

        if result_data and isinstance(result_data, dict):
            status_code = result_data.get("status_code") or result_data.get("code")
            if status_code in expected_codes:
                return ToolVerificationResult(
                    state=VerificationState.VERIFIED,
                    proof={"status_code": status_code},
                    confidence=1.0,
                )
            else:
                return ToolVerificationResult(
                    state=VerificationState.FAILED,
                    error=f"Unexpected status code: {status_code} (expected {expected_codes})",
                )

        return ToolVerificationResult(
            state=VerificationState.UNKNOWN,
            error="No status code in result",
        )
