"""Fail-closed lock/idle monitor for the local Supercerebro permission key."""

from __future__ import annotations

import asyncio
import ctypes
import math
import os
from collections.abc import Awaitable, Callable
from ctypes import wintypes


AUTO_OFF_IDLE_SECONDS = 10 * 60
MONITOR_POLL_SECONDS = 1.0
DESKTOP_READOBJECTS = 0x0001
UOI_NAME = 2


def windows_user_idle_seconds() -> float:
    """Return Windows' last-input age, using the same wrapping DWORD clock."""
    if os.name != "nt":
        return 0.0

    class LastInputInfo(ctypes.Structure):
        _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    user32.GetLastInputInfo.argtypes = (ctypes.POINTER(LastInputInfo),)
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount.argtypes = ()
    kernel32.GetTickCount.restype = wintypes.DWORD
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())

    elapsed_ms = (int(kernel32.GetTickCount()) - int(info.dwTime)) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def windows_session_locked() -> bool:
    """Treat any non-default or unreadable input desktop as locked."""
    if os.name != "nt":
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
    user32.CloseDesktop.restype = wintypes.BOOL

    desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        required = wintypes.DWORD()
        user32.GetUserObjectInformationW(
            desktop, UOI_NAME, None, 0, ctypes.byref(required)
        )
        if required.value <= 0:
            raise ctypes.WinError(ctypes.get_last_error())
        name = ctypes.create_unicode_buffer(
            max(1, required.value // ctypes.sizeof(ctypes.c_wchar))
        )
        if not user32.GetUserObjectInformationW(
            desktop, UOI_NAME, name, ctypes.sizeof(name), ctypes.byref(required)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return name.value.casefold() != "default"
    finally:
        user32.CloseDesktop(desktop)


class SupercerebroAutoOff:
    """Poll lock/idle state while enabled and trip OFF on risk or uncertainty."""

    def __init__(
        self,
        on_auto_off: Callable[[str], Awaitable[None]],
        *,
        is_locked: Callable[[], bool] = windows_session_locked,
        idle_seconds: Callable[[], float] = windows_user_idle_seconds,
        idle_limit_seconds: float = AUTO_OFF_IDLE_SECONDS,
        poll_interval_seconds: float = MONITOR_POLL_SECONDS,
    ) -> None:
        if idle_limit_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("monitor intervals must be positive")
        self._on_auto_off = on_auto_off
        self._is_locked = is_locked
        self._idle_seconds = idle_seconds
        self.idle_limit_seconds = float(idle_limit_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._tripped = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._tripped = False
        self._task = asyncio.get_running_loop().create_task(
            self._run(), name="zara-supercerebro-auto-off"
        )

    def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def check_once(self) -> bool:
        """Perform one check; return true when OFF was requested."""
        if self._tripped:
            return True

        reason: str | None = None
        try:
            locked = bool(self._is_locked())
            idle = float(self._idle_seconds())
            if not math.isfinite(idle) or idle < 0:
                raise ValueError("invalid Windows idle duration")
            if locked:
                reason = "windows-locked"
            elif idle >= self.idle_limit_seconds:
                reason = "idle-timeout"
        except Exception:
            reason = "monitor-unavailable"

        if reason is None:
            return False

        self._tripped = True
        await self._on_auto_off(reason)
        return True

    async def _run(self) -> None:
        current = asyncio.current_task()
        try:
            while True:
                await asyncio.sleep(self.poll_interval_seconds)
                if await self.check_once():
                    return
        finally:
            if self._task is current:
                self._task = None
