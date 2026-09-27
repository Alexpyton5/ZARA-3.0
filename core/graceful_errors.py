from __future__ import annotations

import atexit
import functools
import logging
import signal
import sys
import traceback
from typing import Any, Callable, Optional, TypeVar

log = logging.getLogger("graceful_errors")

T = TypeVar("T", bound=Callable)


def safe(
    func: T,
    fallback: Optional[Callable[..., Any]] = None,
    *,
    log_errors: bool = True,
    silent: bool = False,
) -> T:
    """Decorator / wrapper que captura exceções e opcionalmente executa fallback."""
    if not callable(func):
        raise TypeError("safe() espera um callable")

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            log.warning("Interrompido pelo usuário")
            raise
        except Exception as exc:
            if log_errors:
                log.error("Capturado %s: %s", type(exc).__name__, exc,
                          exc_info=not silent)
            if fallback is not None:
                try:
                    return fallback(*args, **kwargs)
                except Exception:
                    log.exception("Fallback também falhou")
            if not silent:
                raise

    return wrapper  # type: ignore[return-value]


class GracefulErrorHandler:
    """Handler central para shutdown gracioso e resiliência a erros."""

    def __init__(self, *, app_name: str = "zara") -> None:
        self.app_name = app_name
        self.errors: list[tuple[str, str]] = []
        self.running = True
        self._bound: list[tuple[signal.Signals, Callable[..., None]]] = []

    def bind_signals(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
                self._bound.append((sig, sig))
            except (ValueError, OSError):
                pass

    def _handle_signal(self, signum: int = None, frame=None) -> None:
        log.info("Recebido sinal %s, encerrando graciosamente", signum)
        self.running = False

    def catch(
        self,
        func: T,
        fallback: Optional[Callable[..., Any]] = None,
        **opts,
    ) -> Any:
        return safe(func, fallback, **opts)()

    def register_error(self, context: str, error: Exception) -> None:
        self.errors.append((context, repr(error)))

    def report(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "errors": self.errors,
            "running": self.running,
        }


_handler: Optional[GracefulErrorHandler] = None


def get_handler() -> GracefulErrorHandler:
    global _handler
    if _handler is None:
        _handler = GracefulErrorHandler()
    return _handler


def install() -> None:
    handler = get_handler()
    handler.bind_signals()
    atexit.register(handler.report)


if __name__ == "__main__":
    install()
    handler = get_handler()

    @safe
    def boom():
        raise RuntimeError("controlled explosion")

    try:
        boom()
    except RuntimeError:
        handler.register_error("test_boom", RuntimeError("seeded"))

    print(handler.report())
