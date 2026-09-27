"""Focused tests for the safe Windows control foundation.

All tests use fakes for native Windows APIs.  They are intentionally
platform-neutral: Linux is only a negative case and no Linux window utility
is invoked or required.
"""
from __future__ import annotations

import importlib

import pytest

from core.action_registry import get_registry
from core.tool_router import ToolRequest, ToolRouter


@pytest.fixture
def foundation():
    return importlib.import_module("core.actions.windows_control_foundation")


@pytest.fixture
def registry(foundation):
    return get_registry()


def test_actions_register_in_existing_action_registry_and_route_without_new_router(foundation, registry, monkeypatch):
    expected = {
        "windows_app_open",
        "windows_app_close",
        "windows_window_focus",
        "windows_state",
    }
    assert expected.issubset(set(registry.list_actions("windows")))
    assert registry.get_spec("windows_state").risk == "LOW"
    assert registry.get_spec("windows_app_open").risk == "MEDIUM"
    assert registry.get_spec("windows_app_open").capability == "LOCAL_PC_CONTROL"

    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(foundation, "_window_snapshot", lambda: [])
    monkeypatch.setattr(foundation, "_foreground_hwnd", lambda: 0)
    monkeypatch.setattr(foundation, "_running_process_names", lambda: set())

    # ToolRouter uses the existing ActionRegistry fallback; the foundation
    # itself does not construct or own a second router.
    router = ToolRouter(action_registry=registry)
    result = router.route(ToolRequest("windows_state"))
    assert result.success is True
    assert result.verificado is True
    assert result.data["status"] == "STATE_READ"


def test_mutating_action_requires_confirmation_before_native_call(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    called = []
    monkeypatch.setattr(foundation, "_launch_app", lambda _spec: called.append(True))

    result = registry.execute("windows_app_open", app="notepad")

    assert result.success is False
    assert "confirmação" in result.error.lower()
    assert called == []


def test_linux_guard_fails_closed_without_subprocess(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation.platform, "system", lambda: "Linux")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("native launch must not be attempted on Linux")

    monkeypatch.setattr(foundation.subprocess, "Popen", fail_if_called)
    result = registry.execute("windows_app_open", app="notepad", confirm=True)

    assert result.success is False
    assert result.verificado is False
    assert result.data["status"] == "UNSUPPORTED_PLATFORM"


def test_unknown_app_is_rejected_even_on_windows(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(
        foundation,
        "_launch_app",
        lambda _spec: pytest.fail("unknown app must not be launched"),
    )

    result = registry.execute("windows_app_open", app="powershell", confirm=True)

    assert result.success is False
    assert result.data["status"] == "APP_NOT_ALLOWED"
    assert result.verificado is False


def test_open_reports_verified_only_after_observed_postcondition(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    observations = [
        {"app": "notepad", "present": False, "processes": [], "windows": [], "window_count": 0},
        {
            "app": "notepad",
            "present": True,
            "processes": ["notepad.exe"],
            "windows": [{"hwnd": 10, "title": "Notepad", "pid": 20}],
            "window_count": 1,
        },
    ]
    launched = []
    monkeypatch.setattr(foundation, "_observe_app", lambda *_args: observations.pop(0))
    monkeypatch.setattr(foundation, "_launch_app", lambda _spec: launched.append(True))

    result = registry.execute("windows_app_open", app="Bloco de Notas", confirm=True)

    assert launched == [True]
    assert result.success is True
    assert result.verificado is True
    assert result.data["status"] == "OPEN"
    assert result.data["observed"]["present"] is True


def test_open_does_not_invent_success_when_state_is_not_observed(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(foundation, "_OPEN_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setattr(
        foundation,
        "_observe_app",
        lambda *_args: {"app": "notepad", "present": False, "processes": [], "windows": [], "window_count": 0},
    )
    launched = []
    monkeypatch.setattr(foundation, "_launch_app", lambda _spec: launched.append(True))

    result = registry.execute("windows_app_open", app="notepad", confirm=True)

    assert launched == [True]
    assert result.success is False
    assert result.verificado is False
    assert result.data["status"] == "POSTCONDITION_NOT_VERIFIED"


def test_close_uses_wm_close_and_requires_absence_readback(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(foundation, "_CLOSE_TIMEOUT_SECONDS", 0.0)
    observations = [
        {
            "app": "notepad",
            "present": True,
            "processes": ["notepad.exe"],
            "windows": [{"hwnd": 12, "title": "Notepad", "pid": 30}],
            "window_count": 1,
        },
        {"app": "notepad", "present": False, "processes": [], "windows": [], "window_count": 0},
    ]
    sent = []
    monkeypatch.setattr(foundation, "_observe_app", lambda *_args: observations.pop(0))
    monkeypatch.setattr(foundation, "_send_close", lambda hwnd: sent.append(hwnd) or True)

    result = registry.execute("windows_app_close", app="notepad", confirm=True)

    assert sent == [12]
    assert result.success is True
    assert result.verificado is True
    assert result.data["status"] == "CLOSED"


def test_close_never_force_kills_when_postcondition_is_unknown(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(foundation, "_CLOSE_TIMEOUT_SECONDS", 0.0)
    present = {
        "app": "notepad",
        "present": True,
        "processes": ["notepad.exe"],
        "windows": [{"hwnd": 12, "title": "Notepad", "pid": 30}],
        "window_count": 1,
    }
    sent = []
    monkeypatch.setattr(foundation, "_observe_app", lambda *_args: present)
    monkeypatch.setattr(foundation, "_send_close", lambda hwnd: sent.append(hwnd) or True)

    result = registry.execute("windows_app_close", app="notepad", confirm=True)

    assert sent == [12]
    assert result.success is False
    assert result.verificado is False
    assert result.data["status"] == "POSTCONDITION_NOT_VERIFIED"


def test_focus_requires_unique_match_and_confirms_foreground_hwnd(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    target = {"hwnd": 99, "title": "Notepad", "pid": 44, "process_name": "notepad.exe", "visible": True}
    focused = []
    monkeypatch.setattr(foundation, "_window_snapshot", lambda: [target])
    monkeypatch.setattr(foundation, "_focus_window", lambda hwnd: focused.append(hwnd) or True)
    monkeypatch.setattr(foundation, "_foreground_hwnd", lambda: 99)

    result = registry.execute("windows_window_focus", title="note", app="notepad", confirm=True)

    assert focused == [99]
    assert result.success is True
    assert result.verificado is True
    assert result.data["status"] == "FOCUSED"


def test_focus_fails_closed_on_ambiguous_title_without_focusing(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    windows = [
        {"hwnd": 1, "title": "Notepad - one", "pid": 1, "process_name": "notepad.exe", "visible": True},
        {"hwnd": 2, "title": "Notepad - two", "pid": 2, "process_name": "notepad.exe", "visible": True},
    ]
    monkeypatch.setattr(foundation, "_window_snapshot", lambda: windows)
    monkeypatch.setattr(foundation, "_focus_window", lambda _hwnd: pytest.fail("ambiguous target must not focus"))

    result = registry.execute("windows_window_focus", title="Notepad", app="notepad", confirm=True)

    assert result.success is False
    assert result.verificado is False
    assert result.data["status"] == "AMBIGUOUS_WINDOW"


def test_state_is_read_only_and_verified_from_native_observation(foundation, registry, monkeypatch):
    monkeypatch.setattr(foundation, "_is_windows", lambda: True)
    monkeypatch.setattr(foundation, "_window_snapshot", lambda: [{"hwnd": 7, "title": "Desktop", "visible": True}])
    monkeypatch.setattr(foundation, "_foreground_hwnd", lambda: 7)
    monkeypatch.setattr(foundation, "_running_process_names", lambda: {"explorer.exe"})

    result = registry.execute("windows_state")

    assert result.success is True
    assert result.verificado is True
    assert result.data == {
        "status": "STATE_READ",
        "foreground_hwnd": 7,
        "windows": [{"hwnd": 7, "title": "Desktop", "visible": True}],
        "processes": ["explorer.exe"],
    }
