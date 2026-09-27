"""Windows-only, read-only vision foundation for ZARA.

This module never clicks, types, or changes the desktop. Real OCR is delegated
through an explicit Windows provider; tests and planning may use simulation.
"""
from __future__ import annotations

import platform
import re
from typing import Any, Callable

from core.action_registry import ActionResult, action

_OCR_PROVIDER: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_MAX_TEXT = 8000


def _is_windows() -> bool:
    return platform.system().casefold() == "windows"


def register_windows_ocr_provider(provider: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Register the native Windows OCR bridge; never import an OS-specific bridge here."""
    if not callable(provider):
        raise TypeError("OCR provider must be callable")
    global _OCR_PROVIDER
    _OCR_PROVIDER = provider


def clear_windows_ocr_provider() -> None:
    global _OCR_PROVIDER
    _OCR_PROVIDER = None


def _clean_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _MAX_TEXT:
        raise ValueError("texto OCR excede o limite permitido")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("texto OCR contém caracteres inválidos")
    return text


@action(
    name="windows_vision_read",
    category="windows",
    description="Read-only OCR request through an explicit Windows provider or safe simulation",
    parameters={
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["simulate", "native"]},
            "simulated_text": {"type": "string"},
            "source": {"type": "string", "description": "Opaque provider source identifier"},
        },
        "required": ["mode"],
    },
    risk="LOW",
    capability="READ_ONLY",
    tags=["windows", "vision", "ocr", "read-only", "simulation"],
)
def windows_vision_read(mode: str = "simulate", simulated_text: str = "", source: str = "") -> ActionResult:
    mode = str(mode or "").strip().casefold()
    if mode not in {"simulate", "native"}:
        return ActionResult(False, error="Modo de visão inválido.", data={"status": "INVALID_MODE"}, verificado=False)
    if mode == "simulate":
        try:
            text = _clean_text(simulated_text)
        except ValueError as exc:
            return ActionResult(False, error=str(exc), data={"status": "INVALID_SIMULATION"}, verificado=False)
        return ActionResult(
            True,
            output="Leitura simulada concluída; nenhuma tela foi acessada.",
            data={"status": "SIMULATED", "text": text, "source": "test-simulation"},
            verificado=True,
        )
    if not _is_windows():
        return ActionResult(False, error="OCR nativo requer Windows.", data={"status": "UNSUPPORTED_PLATFORM", "platform": platform.system()}, verificado=False)
    if _OCR_PROVIDER is None:
        return ActionResult(False, error="Ponte OCR Windows não configurada.", data={"status": "OCR_PROVIDER_UNAVAILABLE"}, verificado=False)
    if len(str(source or "")) > 200 or any(ord(char) < 32 for char in str(source or "")):
        return ActionResult(False, error="Origem de OCR inválida.", data={"status": "INVALID_SOURCE"}, verificado=False)
    try:
        result = _OCR_PROVIDER({"source": str(source or "")})
        if not isinstance(result, dict):
            raise ValueError("provider returned non-object")
        text = _clean_text(result.get("text"))
        return ActionResult(True, output="OCR Windows concluído; resultado somente leitura.", data={"status": "OCR_READ", "text": text, "source": str(source or "")}, verificado=True)
    except Exception as exc:
        return ActionResult(False, error="OCR Windows falhou sem executar ação no sistema.", data={"status": "OCR_FAILED", "error_type": type(exc).__name__}, verificado=False)


__all__ = ["clear_windows_ocr_provider", "register_windows_ocr_provider", "windows_vision_read"]
