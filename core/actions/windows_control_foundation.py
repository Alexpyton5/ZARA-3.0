"""Safe Windows control foundations for ZARA.

This module deliberately provides only a small, deterministic surface:
allow-listed app launch/close, unique-window focus, and read-only window
state.  It never shells out to a user-supplied command and never uses Linux
window-control utilities.  Mutating operations return failure when their
post-condition cannot be observed.

The actions are registered in the existing :class:`ActionRegistry` through
``@action``.  ToolRouter integration remains the existing ActionRegistry
fallback/adaptation path; this module does not create another router.
"""
from __future__ import annotations

import csv
import io
import platform
import subprocess
import time
import unicodedata
from typing import Any

from core.action_registry import ActionResult, action


# A deliberately small, fixed allow-list.  Values are executable names, not
# user-provided command strings.  No shell is ever used to launch them.
_SAFE_APPS: dict[str, dict[str, Any]] = {
    "notepad": {
        "executable": "notepad.exe",
        "process_names": {"notepad.exe"},
        "title_aliases": {"notepad", "bloco de notas"},
    },
    "calculator": {
        "executable": "calc.exe",
        "process_names": {"calculatorapp.exe", "calc.exe"},
        "title_aliases": {"calculator", "calculadora"},
    },
    "paint": {
        "executable": "mspaint.exe",
        "process_names": {"mspaint.exe"},
        "title_aliases": {"paint"},
    },
    "task_manager": {
        "executable": "taskmgr.exe",
        "process_names": {"taskmgr.exe"},
        "title_aliases": {"task manager", "gerenciador de tarefas"},
    },
    "chrome": {
        "executable": "chrome.exe",
        "process_names": {"chrome.exe"},
        "title_aliases": set(),
    },
    "edge": {
        "executable": "msedge.exe",
        "process_names": {"msedge.exe"},
        "title_aliases": set(),
    },
}

_APP_ALIASES = {
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "calculator": "calculator",
    "calculadora": "calculator",
    "calc": "calculator",
    "paint": "paint",
    "mspaint": "paint",
    "task manager": "task_manager",
    "taskmanager": "task_manager",
    "gerenciador de tarefas": "task_manager",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
}

_OPEN_TIMEOUT_SECONDS = 4.0
_CLOSE_TIMEOUT_SECONDS = 4.0
_POLL_INTERVAL_SECONDS = 0.10
_WM_CLOSE = 0x0010
_SW_RESTORE = 9


class _WindowsUnavailable(RuntimeError):
    """Raised when a native Windows observation/control API is unavailable."""


def _is_windows() -> bool:
    """Return whether native Windows APIs are available for this process."""
    return platform.system().casefold() == "windows"


def _unsupported(operation: str) -> ActionResult:
    return ActionResult(
        success=False,
        error=f"{operation} indisponível: esta fundação requer Windows.",
        data={"status": "UNSUPPORTED_PLATFORM", "platform": platform.system()},
        verificado=False,
    )


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.casefold().strip().split())


def _resolve_app(app: str) -> tuple[str | None, dict[str, Any] | None]:
    key = _fold(app)
    app_id = _APP_ALIASES.get(key)
    if app_id is None:
        return None, None
    return app_id, _SAFE_APPS[app_id]


def _process_name(pid: int) -> str:
    """Read a process image basename through Windows APIs, best-effort."""
    if not pid or not _is_windows():
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process = kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
        if not process:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            length = wintypes.DWORD(len(buffer))
            ok = kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length))
            if not ok:
                return ""
            return buffer.value.rsplit("\\", 1)[-1].casefold()
        finally:
            kernel32.CloseHandle(process)
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def _window_snapshot() -> list[dict[str, Any]]:
    """Enumerate visible top-level windows using user32, never Linux tools."""
    if not _is_windows():
        raise _WindowsUnavailable("Windows APIs are unavailable")

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        foreground = int(user32.GetForegroundWindow() or 0)
        rows: list[dict[str, Any]] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = int(user32.GetWindowTextLengthW(hwnd))
            title_buffer = ctypes.create_unicode_buffer(max(length + 1, 1))
            user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rows.append(
                {
                    "hwnd": int(hwnd),
                    "title": title_buffer.value,
                    "pid": int(pid.value),
                    "process_name": _process_name(int(pid.value)),
                    "visible": True,
                    "is_foreground": int(hwnd) == foreground,
                }
            )
            return True

        callback_ref = callback_type(callback)
        if not user32.EnumWindows(callback_ref, 0):
            raise _WindowsUnavailable("EnumWindows failed")
        return rows
    except _WindowsUnavailable:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise _WindowsUnavailable(f"window enumeration failed: {exc}") from exc


def _running_process_names() -> set[str]:
    """Read process names with the native Windows tasklist utility.

    ``tasklist.exe`` is a Windows component and is used only after the
    platform guard.  A failure returns an empty set; callers still require a
    separately observed window before claiming an app operation succeeded.
    """
    if not _is_windows():
        raise _WindowsUnavailable("Windows APIs are unavailable")
    try:
        completed = subprocess.run(
            ["tasklist.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _WindowsUnavailable(f"tasklist failed: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise _WindowsUnavailable(f"tasklist returned {completed.returncode}")
    names: set[str] = set()
    try:
        for row in csv.reader(io.StringIO(completed.stdout)):
            if row and row[0].strip() and row[0].strip() != "INFO:":
                names.add(row[0].strip().casefold())
    except (csv.Error, TypeError) as exc:
        raise _WindowsUnavailable("tasklist returned invalid CSV") from exc
    if not names and completed.stdout.strip():
        raise _WindowsUnavailable("tasklist returned no process names")
    return names


def _observe_app(app_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Observe an allow-listed app using process and visible-window state."""
    windows = _window_snapshot()
    process_error = ""
    try:
        process_names = _running_process_names()
    except _WindowsUnavailable as exc:
        process_names = set()
        process_error = str(exc)
    expected_processes = {str(name).casefold() for name in spec["process_names"]}
    expected_titles = {_fold(name) for name in spec["title_aliases"]}
    matching_windows = []
    for window in windows:
        process_name = str(window.get("process_name") or "").casefold()
        title = _fold(str(window.get("title") or ""))
        if process_name in expected_processes or any(alias and alias in title for alias in expected_titles):
            matching_windows.append(window)
    if process_error and not matching_windows:
        raise _WindowsUnavailable(process_error)
    matching_processes = sorted(expected_processes & process_names)
    state = {
        "app": app_id,
        "present": bool(matching_windows or matching_processes),
        "processes": matching_processes,
        "windows": matching_windows,
        "window_count": len(matching_windows),
    }
    if process_error:
        state["process_observation_error"] = process_error
    return state


def _wait_for_app(app_id: str, spec: dict[str, Any], expected: bool, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, float(timeout))
    last: dict[str, Any] = {"app": app_id, "present": None, "processes": [], "windows": [], "window_count": 0}
    while True:
        try:
            last = _observe_app(app_id, spec)
        except _WindowsUnavailable:
            return {**last, "present": None, "observation_error": "WINDOW_OR_PROCESS_API_UNAVAILABLE"}
        if last.get("present") is expected:
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(_POLL_INTERVAL_SECONDS)


def _launch_app(spec: dict[str, Any]) -> None:
    executable = str(spec["executable"])
    subprocess.Popen(
        [executable],
        shell=False,
        close_fds=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _window_matches(window: dict[str, Any], title: str, app_spec: dict[str, Any] | None) -> bool:
    wanted_title = _fold(title)
    observed_title = _fold(str(window.get("title") or ""))
    if not wanted_title or wanted_title not in observed_title:
        return False
    if app_spec is None:
        return True
    process_name = str(window.get("process_name") or "").casefold()
    expected = {str(name).casefold() for name in app_spec["process_names"]}
    return not process_name or process_name in expected


def _send_close(hwnd: int) -> bool:
    if not _is_windows():
        raise _WindowsUnavailable("Windows APIs are unavailable")
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        return bool(user32.PostMessageW(int(hwnd), _WM_CLOSE, 0, 0))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _focus_window(hwnd: int) -> bool:
    if not _is_windows():
        raise _WindowsUnavailable("Windows APIs are unavailable")
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.ShowWindow(int(hwnd), _SW_RESTORE)
        return bool(user32.SetForegroundWindow(int(hwnd)))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _foreground_hwnd() -> int:
    if not _is_windows():
        raise _WindowsUnavailable("Windows APIs are unavailable")
    try:
        import ctypes

        return int(ctypes.WinDLL("user32", use_last_error=True).GetForegroundWindow() or 0)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


@action(
    name="windows_app_open",
    category="windows",
    description="Open one fixed allow-listed Windows application and verify its observed state",
    parameters={
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Allow-listed app id or alias"},
            "confirm": {"type": "boolean", "default": False},
        },
        "required": ["app"],
    },
    requires_confirmation=True,
    risk="MEDIUM",
    capability="LOCAL_PC_CONTROL",
    tags=["windows", "allow-list", "verified"],
)
def windows_app_open(app: str) -> ActionResult:
    if not _is_windows():
        return _unsupported("Abertura de aplicativo")
    app_id, spec = _resolve_app(app)
    if app_id is None or spec is None:
        return ActionResult(
            success=False,
            error="Aplicativo não permitido; use um id da allow-list.",
            data={"status": "APP_NOT_ALLOWED", "requested_app": str(app)},
            verificado=False,
        )
    try:
        before = _observe_app(app_id, spec)
        _launch_app(spec)
        observed = _wait_for_app(app_id, spec, True, _OPEN_TIMEOUT_SECONDS)
    except (OSError, _WindowsUnavailable) as exc:
        return ActionResult(
            success=False,
            error=f"Não foi possível abrir {app_id}: {type(exc).__name__}.",
            data={"status": "LAUNCH_FAILED", "app": app_id, "detail": str(exc)},
            verificado=False,
        )
    # Um processo pode existir em background sem a aplicação ter aberto uma
    # janela utilizável. Para esta ação, a pós-condição é processo + janela
    # visível observados; presença de processo sozinha não prova a abertura.
    verified = bool(observed.get("present") and observed.get("windows"))
    if not verified:
        return ActionResult(
            success=False,
            error=f"A abertura de {app_id} foi enviada, mas processo e janela não foram confirmados.",
            data={"status": "POSTCONDITION_NOT_VERIFIED", "app": app_id, "before": before, "observed": observed},
            verificado=False,
        )
    return ActionResult(
        success=True,
        output=f"{app_id} aberto; estado observado no Windows.",
        data={"status": "OPEN", "app": app_id, "before": before, "observed": observed},
        verificado=True,
    )


@action(
    name="windows_app_close",
    category="windows",
    description="Close an allow-listed Windows application with WM_CLOSE and verify it is gone",
    parameters={
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Allow-listed app id or alias"},
            "confirm": {"type": "boolean", "default": False},
        },
        "required": ["app"],
    },
    requires_confirmation=True,
    risk="MEDIUM",
    capability="LOCAL_PC_CONTROL",
    tags=["windows", "allow-list", "verified", "non-destructive-close"],
)
def windows_app_close(app: str) -> ActionResult:
    if not _is_windows():
        return _unsupported("Fechamento de aplicativo")
    app_id, spec = _resolve_app(app)
    if app_id is None or spec is None:
        return ActionResult(
            success=False,
            error="Aplicativo não permitido; use um id da allow-list.",
            data={"status": "APP_NOT_ALLOWED", "requested_app": str(app)},
            verificado=False,
        )
    try:
        before = _observe_app(app_id, spec)
    except _WindowsUnavailable as exc:
        return ActionResult(
            success=False,
            error=f"Não foi possível ler o estado de {app_id}.",
            data={"status": "STATE_UNAVAILABLE", "app": app_id, "detail": str(exc)},
            verificado=False,
        )
    if not before.get("present"):
        return ActionResult(
            success=True,
            output=f"{app_id} já estava fechado; estado confirmado.",
            data={"status": "ALREADY_CLOSED", "app": app_id, "observed": before},
            verificado=True,
        )

    windows = list(before.get("windows") or [])
    if not windows:
        return ActionResult(
            success=False,
            error=f"{app_id} está em execução, mas não há janela segura para fechar.",
            data={"status": "NO_WINDOW_TO_CLOSE", "app": app_id, "observed": before},
            verificado=False,
        )
    close_results = [{"hwnd": int(window["hwnd"]), "sent": _send_close(int(window["hwnd"]))} for window in windows]
    if not all(item["sent"] for item in close_results):
        return ActionResult(
            success=False,
            error=f"O Windows não aceitou fechar todas as janelas de {app_id}.",
            data={"status": "CLOSE_DISPATCH_FAILED", "app": app_id, "close_results": close_results},
            verificado=False,
        )
    observed = _wait_for_app(app_id, spec, False, _CLOSE_TIMEOUT_SECONDS)
    verified = observed.get("present") is False
    if not verified:
        return ActionResult(
            success=False,
            error=f"O fechamento de {app_id} não foi confirmado; nenhuma finalização forçada foi executada.",
            data={"status": "POSTCONDITION_NOT_VERIFIED", "app": app_id, "before": before, "observed": observed, "close_results": close_results},
            verificado=False,
        )
    return ActionResult(
        success=True,
        output=f"{app_id} fechado; estado observado no Windows.",
        data={"status": "CLOSED", "app": app_id, "before": before, "observed": observed, "close_results": close_results},
        verificado=True,
    )


@action(
    name="windows_window_focus",
    category="windows",
    description="Focus one uniquely identified visible Windows window and verify the foreground hwnd",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Case-insensitive visible window title fragment"},
            "app": {"type": "string", "description": "Optional allow-listed app id or alias"},
            "confirm": {"type": "boolean", "default": False},
        },
        "required": ["title"],
    },
    requires_confirmation=True,
    risk="MEDIUM",
    capability="LOCAL_PC_CONTROL",
    tags=["windows", "window", "verified"],
)
def windows_window_focus(title: str, app: str | None = None) -> ActionResult:
    if not _is_windows():
        return _unsupported("Foco de janela")
    wanted_title = str(title or "").strip()
    if not wanted_title or len(wanted_title) > 200 or any(ord(char) < 32 for char in wanted_title):
        return ActionResult(success=False, error="Título de janela inválido.", data={"status": "INVALID_TITLE"}, verificado=False)
    app_id = None
    app_spec = None
    if app is not None:
        app_id, app_spec = _resolve_app(app)
        if app_id is None or app_spec is None:
            return ActionResult(success=False, error="Aplicativo não permitido; use um id da allow-list.", data={"status": "APP_NOT_ALLOWED"}, verificado=False)
    try:
        windows = [window for window in _window_snapshot() if _window_matches(window, wanted_title, app_spec)]
    except _WindowsUnavailable as exc:
        return ActionResult(success=False, error="Não foi possível ler as janelas do Windows.", data={"status": "STATE_UNAVAILABLE", "detail": str(exc)}, verificado=False)
    if not windows:
        return ActionResult(success=False, error=f"Janela não encontrada: {wanted_title}.", data={"status": "WINDOW_NOT_FOUND", "title": wanted_title}, verificado=False)
    if len(windows) != 1:
        return ActionResult(success=False, error=f"Mais de uma janela corresponde a: {wanted_title}.", data={"status": "AMBIGUOUS_WINDOW", "title": wanted_title, "matches": windows}, verificado=False)
    target = windows[0]
    hwnd = int(target["hwnd"])
    if not _focus_window(hwnd):
        return ActionResult(success=False, error="O Windows não aceitou o foco solicitado.", data={"status": "FOCUS_DISPATCH_FAILED", "window": target}, verificado=False)
    foreground = _foreground_hwnd()
    verified = foreground == hwnd
    if not verified:
        return ActionResult(success=False, error="Foco enviado, mas a janela em primeiro plano não foi confirmada.", data={"status": "POSTCONDITION_NOT_VERIFIED", "window": target, "foreground_hwnd": foreground}, verificado=False)
    return ActionResult(success=True, output=f"Janela focada: {target.get('title') or wanted_title}.", data={"status": "FOCUSED", "window": target, "foreground_hwnd": foreground}, verificado=True)


@action(
    name="windows_state",
    category="windows",
    description="Read visible Windows window state and foreground window without mutating the system",
    parameters={"type": "object", "properties": {}},
    risk="LOW",
    capability="READ_ONLY",
    tags=["windows", "read-only", "state"],
)
def windows_state() -> ActionResult:
    if not _is_windows():
        return _unsupported("Leitura do estado de janelas")
    try:
        windows = _window_snapshot()
        foreground = _foreground_hwnd()
        processes = sorted(_running_process_names())
    except _WindowsUnavailable as exc:
        return ActionResult(
            success=False,
            error="Não foi possível ler o estado nativo do Windows.",
            data={"status": "STATE_UNAVAILABLE", "detail": str(exc)},
            verificado=False,
        )
    state = {"status": "STATE_READ", "foreground_hwnd": foreground, "windows": windows, "processes": processes}
    return ActionResult(success=True, output=f"Estado lido: {len(windows)} janelas visíveis.", data=state, verificado=True)


__all__ = [
    "windows_app_open",
    "windows_app_close",
    "windows_window_focus",
    "windows_state",
]
