"""
Tool Router — Deterministic routing of tool requests to execution.

Flow: REQUEST → VALIDATE → LOOKUP → PERMISSION CHECK → EXECUTE → NORMALIZE → VERIFY → RESULT

NO LLM, deterministic only.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from core.tool_definition import ToolState
from core.tool_error_model import ErrorCategory, tool_error
from core.tool_registry import get_tool_registry
from core.tool_result import ToolResult, ToolVerificationResult
from core.tool_verifier import verify_result

logger = logging.getLogger(__name__)

__all__ = ["ToolRouter", "ToolRequest", "get_tool_router"]


class ToolRequest:
    """Incoming request to execute a tool."""

    def __init__(self, tool_name: str, parameters: dict = None, **kwargs):
        self.tool_name = tool_name
        self.parameters = parameters or {}
        self.kwargs = kwargs
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "timestamp": self.timestamp,
        }


class ToolRouter:
    """Deterministic tool execution router."""

    def __init__(self, tool_registry=None, action_registry=None):
        self.registry = tool_registry or get_tool_registry()
        self.action_registry = action_registry  # Optional fallback to ActionRegistry
        self._audit_hook = None
        self._permission_checker = None
        self._verifier_hooks = {}

    def set_audit_hook(self, hook: Callable[[dict], None]) -> None:
        """Set hook for audit logging."""
        self._audit_hook = hook

    def set_permission_checker(self, checker: Callable[[str, dict], bool]) -> None:
        """Set hook for permission checking."""
        self._permission_checker = checker

    def set_verifier(self, tool_name: str, verifier: Callable) -> None:
        """Set custom verifier for a tool."""
        self._verifier_hooks[tool_name] = verifier

    def route(self, request: ToolRequest) -> ToolResult:
        """Execute tool request through routing pipeline.

        Pipeline:
        1. VALIDATE — Validate request format
        2. LOOKUP — Find tool in registry
        3. PERMISSION_CHECK — Check permissions
        4. EXECUTE — Run tool executor
        5. NORMALIZE — Standardize result
        6. VERIFY — Verify execution actually happened
        7. RESULT — Return structured result
        """
        start_time = time.time()

        # STEP 1: VALIDATE
        try:
            self._validate_request(request)
        except ValueError as e:
            return ToolResult(
                success=False,
                error=str(e),
                error_code=ErrorCategory.VALIDATION_ERROR,
                duration_ms=self._elapsed_ms(start_time),
            )

        # STEP 2: LOOKUP
        tool = self.registry.get(request.tool_name)
        if not tool:
            if self.action_registry:
                return self._fallback_to_action_registry(request, start_time)
            return ToolResult(
                success=False,
                error=f"Tool '{request.tool_name}' not found",
                error_code=ErrorCategory.NOT_FOUND,
                duration_ms=self._elapsed_ms(start_time),
            )

        # STEP 2b: SCHEMA VALIDATION
        schema_ok, schema_msg = self.registry.validate_schema(
            request.tool_name, request.parameters
        )
        if not schema_ok:
            return ToolResult(
                success=False,
                error=schema_msg,
                error_code=ErrorCategory.VALIDATION_ERROR,
                duration_ms=self._elapsed_ms(start_time),
            )

        # STEP 3: PERMISSION_CHECK
        if self._permission_checker:
            try:
                if not self._permission_checker(request.tool_name, request.parameters):
                    return ToolResult(
                        success=False,
                        error=f"Permission denied for '{request.tool_name}'",
                        error_code=ErrorCategory.PERMISSION_DENIED,
                        duration_ms=self._elapsed_ms(start_time),
                    )
            except Exception as e:
                logger.exception(
                    "[ToolRouter] Permission check raised for '%s'", request.tool_name
                )
                return ToolResult(
                    success=False,
                    error=f"Permission check failed: {e}",
                    error_code=ErrorCategory.EXECUTION_FAILED,
                    duration_ms=self._elapsed_ms(start_time),
                )

        # STEP 4: EXECUTE
        exec_start = time.time()
        try:
            if not tool.executor:
                return ToolResult(
                    success=False,
                    error=f"No executor for '{request.tool_name}'",
                    error_code=ErrorCategory.UNAVAILABLE,
                    duration_ms=self._elapsed_ms(start_time),
                )

            result_data = tool.executor(**request.parameters)
            exec_time_ms = self._elapsed_ms(exec_start)

        except TimeoutError:
            return ToolResult(
                success=False,
                error=f"Tool execution timed out (>{tool.timeout_ms}ms)",
                error_code=ErrorCategory.TIMEOUT,
                duration_ms=self._elapsed_ms(start_time),
                retryable=True,
            )
        except Exception as e:
            logger.exception(
                "[ToolRouter] Executor raised for '%s'", request.tool_name
            )
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {e}",
                error_code=ErrorCategory.EXECUTION_FAILED,
                duration_ms=self._elapsed_ms(start_time),
            )

        # STEP 5: NORMALIZE
        result = self._normalize_result(request.tool_name, result_data, exec_time_ms)

        # STEP 6: VERIFY
        if tool.verifier or request.tool_name in self._verifier_hooks:
            verifier = self._verifier_hooks.get(request.tool_name) or tool.verifier
            try:
                verification = verify_result(verifier, request.parameters, result_data)
                result.verification = verification
                result.verificado = verification.is_verified()
            except Exception as e:
                result.verification = ToolVerificationResult(
                    state="FAILED",
                    error=str(e),
                    confidence=0.0,
                )
                result.verificado = False

        # STEP 7: AUDIT
        if self._audit_hook:
            try:
                self._audit_hook({
                    "tool": request.tool_name,
                    "success": result.success,
                    "duration_ms": result.duration_ms,
                    "error_code": result.error_code,
                })
            except Exception:
                logger.exception("[ToolRouter] Audit hook failed for '%s'", request.tool_name)

        result.duration_ms = self._elapsed_ms(start_time)
        return result

    def _validate_request(self, request: ToolRequest) -> None:
        """Validate request format."""
        if not request.tool_name:
            raise ValueError("tool_name is required")
        if not isinstance(request.parameters, dict):
            raise ValueError("parameters must be a dict")

    def _normalize_result(
        self, tool_name: str, result_data: Any, exec_time_ms: float
    ) -> ToolResult:
        """Normalize executor result to ToolResult."""
        if isinstance(result_data, ToolResult):
            result_data.duration_ms = exec_time_ms
            return result_data

        if isinstance(result_data, dict):
            return ToolResult(
                success=result_data.get("success", True),
                data=result_data.get("data"),
                output=result_data.get("output", ""),
                error=result_data.get("error", ""),
                message=result_data.get("message", ""),
                duration_ms=exec_time_ms,
                verificado=result_data.get("verificado", True),
            )

        if isinstance(result_data, bool):
            return ToolResult(
                success=result_data,
                output="OK" if result_data else "Failed",
                duration_ms=exec_time_ms,
            )

        if isinstance(result_data, str):
            return ToolResult(
                success=True,
                output=result_data,
                data=result_data,
                duration_ms=exec_time_ms,
            )

        return ToolResult(
            success=True,
            data=result_data,
            output=str(result_data),
            duration_ms=exec_time_ms,
        )

    def _fallback_to_action_registry(
        self, request: ToolRequest, start_time: float
    ) -> ToolResult:
        """Fallback to ActionRegistry if tool not in ToolRegistry."""
        try:
            action_result = self.action_registry.execute(
                request.tool_name, **request.parameters
            )
            return ToolResult.from_action_result(action_result)
        except Exception as e:
            logger.exception(
                "[ToolRouter] ActionRegistry fallback raised for '%s'", request.tool_name
            )
            return ToolResult(
                success=False,
                error=f"ActionRegistry fallback failed: {e}",
                error_code=ErrorCategory.EXECUTION_FAILED,
                duration_ms=self._elapsed_ms(start_time),
            )

    def _elapsed_ms(self, start_time: float) -> float:
        """Calculate elapsed time in milliseconds."""
        return (time.time() - start_time) * 1000


# Global singleton instance
_router_instance = None


def get_tool_router(
    tool_registry=None, action_registry=None
) -> ToolRouter:
    """Get or create global ToolRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = ToolRouter(tool_registry, action_registry)
    return _router_instance
