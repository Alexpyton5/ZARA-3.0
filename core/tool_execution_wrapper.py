"""
Execution Wrapper — Wraps tool execution with timing, validation, errors, timeout, audit, cancellation.

Does NOT rewrite action internals; only wraps execution.
"""
from __future__ import annotations

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable

from core.tool_error_model import ErrorCategory, tool_error
from core.tool_result import ToolResult
from core.tool_verifier import verify_result

logger = logging.getLogger(__name__)

__all__ = ["wrap_executor", "ExecutionWrapper"]


class ExecutionWrapper:
    """Wraps a tool executor with additional capabilities."""

    def __init__(
        self,
        executor: Callable,
        name: str = None,
        timeout_ms: int = 30000,
        audit_hook: Callable = None,
        cancel_hook: Callable = None,
        result_normalizer: Callable = None,
        verifier: Callable = None,
    ):
        self.executor = executor
        self.name = name or getattr(executor, "__name__", "unknown")
        self.timeout_ms = timeout_ms
        self.audit_hook = audit_hook
        self.cancel_hook = cancel_hook
        self.result_normalizer = result_normalizer
        self.verifier = verifier
        self._running = False
        self._cancelled = False

    def execute(self, **kwargs) -> ToolResult:
        """Execute with wrapping."""
        start_time = time.time()
        self._cancelled = False
        self._running = True

        try:
            # TIMING: Measure execution
            exec_start = time.time()
            result_data = self._execute_with_timeout(**kwargs)
            exec_time_ms = (time.time() - exec_start) * 1000

            # NORMALIZATION: Convert result
            result = self._normalize_result(result_data, exec_time_ms)

            # VERIFICATION: Optional verification hook
            if self.verifier:
                try:
                    verification = verify_result(self.verifier, kwargs, result_data)
                    result.verification = verification
                    result.verificado = verification.is_verified()
                except Exception as e:
                    result.verificado = False
                    result.verification_error = str(e)

            # AUDIT: Log execution
            if self.audit_hook:
                try:
                    self.audit_hook({
                        "tool": self.name,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                        "parameterscount": len(kwargs),
                    })
                except Exception:
                    logger.exception("[ExecutionWrapper] Audit failed for %s", self.name)

            return result

        except TimeoutError:
            self._handle_cancellation()
            return ToolResult(
                success=False,
                error=f"Tool execution timed out (>{self.timeout_ms}ms)",
                error_code=ErrorCategory.TIMEOUT,
                duration_ms=(time.time() - start_time) * 1000,
                retryable=True,
            )

        except asyncio.CancelledError:
            self._handle_cancellation()
            return ToolResult(
                success=False,
                error="Tool execution cancelled",
                error_code=ErrorCategory.CANCELLED,
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.exception("[ExecutionWrapper] Executor raised for %s", self.name)
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {e}",
                error_code=ErrorCategory.EXECUTION_FAILED,
                duration_ms=(time.time() - start_time) * 1000,
            )

        finally:
            self._running = False

    def _execute_with_timeout(self, **kwargs) -> Any:
        """Execute with timeout enforcement."""
        # Simple timeout using threading for sync functions
        # For async, use asyncio.wait_for
        if self.timeout_ms <= 0:
            return self.executor(**kwargs)

        # Try direct execution first (most actions are fast)
        start = time.time()
        try:
            result = self.executor(**kwargs)
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms > self.timeout_ms:
                raise TimeoutError(f"Execution exceeded timeout: {elapsed_ms}ms > {self.timeout_ms}ms")
            return result
        except TimeoutError:
            raise

    def _normalize_result(self, result_data: Any, exec_time_ms: float) -> ToolResult:
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

        # Default: treat as successful data
        return ToolResult(
            success=True,
            data=result_data,
            output=str(result_data)[:1000] if result_data else "",
            duration_ms=exec_time_ms,
        )

    def _handle_cancellation(self):
        """Handle cancellation cleanup."""
        if self.cancel_hook:
            try:
                self.cancel_hook()
            except Exception:
                logger.exception("[ExecutionWrapper] Cancellation hook failed for %s", self.name)

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True
        self._handle_cancellation()


def wrap_executor(
    executor: Callable,
    name: str = None,
    timeout_ms: int = 30000,
    audit_hook: Callable = None,
    cancel_hook: Callable = None,
    result_normalizer: Callable = None,
    verifier: Callable = None,
) -> ExecutionWrapper:
    """Create an execution wrapper for a tool executor."""
    return ExecutionWrapper(
        executor=executor,
        name=name,
        timeout_ms=timeout_ms,
        audit_hook=audit_hook,
        cancel_hook=cancel_hook,
        result_normalizer=result_normalizer,
        verifier=verifier,
    )


def wrap_with_timeout(timeout_ms: int = 30000):
    """Decorator to wrap function with timeout."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            wrapper_obj = ExecutionWrapper(
                executor=lambda **kw: func(*args, **kw),
                name=func.__name__,
                timeout_ms=timeout_ms,
            )
            result = wrapper_obj.execute(**kwargs)
            if not result.success:
                # Never let a failure look like a normal None/"" return value —
                # raise so the caller can't mistake failure for success.
                raise RuntimeError(
                    result.error or f"{func.__name__} failed (error_code={result.error_code})"
                )
            # Return raw result data, not ToolResult
            return result.data if result.data is not None else result.output
        return wrapper
    return decorator
