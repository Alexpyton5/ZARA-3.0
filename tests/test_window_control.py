from unittest.mock import AsyncMock

import pytest

from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "action"),
    [
        ("minimize a janela", "window_minimize"),
        ("minimize esta janela", "window_minimize"),
        ("agora minimize ele", "window_minimize"),
        ("maximize", "window_maximize"),
        ("maximize esta janela", "window_maximize"),
        ("restaure a janela", "window_restore"),
        ("volte a janela ao normal", "window_restore"),
        ("traz o Chrome pra frente", "window_focus_named"),
        ("volta pra ZARA", "window_focus_named"),
        ("troca para o VS Code", "window_focus_named"),
        ("mostra o projeto", "window_focus_named"),
    ],
)
def test_window_aliases(phrase, action):
    result = PcVoiceIntentDetector(
        window_context_available=phrase == "agora minimize ele",
    ).detect(phrase)
    assert result.action == action
    assert result.blocked is False


@pytest.mark.parametrize(
    ("phrase", "target"),
    [
        ("Zara, traz o Chrome pra frente", "chrome"),
        ("Zara, volta pra ZARA", "zara"),
        ("Zara, troca para o VS Code", "vscode"),
        ("Zara, mostra o projeto", "project"),
    ],
)
def test_named_window_alias_keeps_target_distinct_from_wake_word(phrase, target):
    result = PcVoiceIntentDetector().detect(phrase)
    assert result.action == "window_focus_named"
    assert result.param == target


@pytest.mark.parametrize("phrase", ["troque de janela", "vá para a próxima janela"])
def test_blind_window_switch_requires_named_target(phrase):
    result = PcVoiceIntentDetector().detect(phrase)
    assert result.action == "window_switch_next"
    assert result.blocked is True
    assert "não alterno às cegas" in result.reply


def test_window_target_guard_rejects_missing_active_window(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_foreground_window", lambda: None)
    assert os_ops.window_minimize_action().success is False


def test_named_window_focus_requires_one_candidate_and_postcondition(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_windows", lambda: [11])
    monkeypatch.setattr(os_ops, "_window_matches_named_target", lambda hwnd, target: hwnd == 11 and target == "vscode")
    monkeypatch.setattr(os_ops, "_foreground_window", lambda: 11)
    monkeypatch.setattr(os_ops, "_window_pid", lambda hwnd: 22)
    monkeypatch.setattr(os_ops, "_window_process_name", lambda hwnd: "code.exe")
    monkeypatch.setattr(os_ops, "_window_text", lambda hwnd: "ZARA - Visual Studio Code")

    result = os_ops.window_focus_named_action("vscode")

    assert result.success is True
    assert result.data["status"] == "FOREGROUND_CONFIRMED"
    assert result.data["hwnd"] == 11


def test_named_window_focus_never_guesses_between_candidates(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_windows", lambda: [11, 12])
    monkeypatch.setattr(os_ops, "_window_matches_named_target", lambda hwnd, target: True)
    monkeypatch.setattr(os_ops, "_foreground_window", lambda: 99)

    result = os_ops.window_focus_named_action("chrome")

    assert result.success is False
    assert result.data["status"] == "AMBIGUOUS"


def test_explicit_context_hwnd_is_reused_after_minimize(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_window", lambda hwnd: hwnd == 123)
    states = iter(("minimized", "restored"))
    monkeypatch.setattr(os_ops, "_window_state", lambda hwnd: next(states))
    monkeypatch.setattr(os_ops, "_window_process_name", lambda hwnd: "notepad.exe")
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)
    result = os_ops.window_restore_action(hwnd=123)
    assert result.success is True
    assert result.data["hwnd"] == 123


def test_restore_accepts_prior_maximized_state(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_window", lambda hwnd: hwnd == 123)
    states = iter(("minimized", "maximized"))
    monkeypatch.setattr(os_ops, "_window_state", lambda hwnd: next(states))
    monkeypatch.setattr(os_ops, "_window_process_name", lambda hwnd: "systemsettings.exe")
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)

    result = os_ops.window_restore_action(hwnd=123)

    assert result.success is True
    assert result.data["after"] == "maximized"


def test_window_state_action_requires_verified_state(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_foreground_window", lambda: 123)
    monkeypatch.setattr(os_ops, "_window_state", lambda hwnd: "restored")
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)
    result = os_ops.window_minimize_action()
    assert result.success is False


@pytest.mark.asyncio
async def test_local_window_command_executes_directly(monkeypatch):
    execute = AsyncMock(return_value=type(
        "Result", (), {
            "success": True,
            "error": "",
            "output": "Janela minimizada e verificada.",
            "data": {"hwnd": 123, "pid": 456, "after": "minimized"},
        }
    )())
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    reply = await handler._try_pc_intent("minimize a janela")
    assert reply == "Janela minimizada e verificada."
    execute.assert_awaited_once_with("window_minimize")


@pytest.mark.parametrize("phrase", ["alt+f4", "mate o processo", "minimize && powershell"])
def test_destructive_or_arbitrary_window_text_is_not_mapped(phrase):
    result = PcVoiceIntentDetector().detect(phrase)
    assert not result.action.startswith("window_")


@pytest.mark.parametrize(
    ("phrase", "action", "param"),
    [
        ("coloca essa janela do lado direito", "window_move", "right"),
        ("move isso pro lado esquerdo", "window_move", "left"),
        ("deixa essa janela maior", "window_resize_larger", ""),
        ("fecha essa janela", "window_close", ""),
    ],
)
def test_contextual_geometry_requires_exact_recent_window(phrase, action, param):
    missing = PcVoiceIntentDetector().detect(phrase)
    assert missing.action == action
    assert missing.blocked is True
    available = PcVoiceIntentDetector(window_context_available=True).detect(phrase)
    assert available.action == action
    assert available.param == param
    assert available.blocked is False


def test_window_geometry_verifies_observed_rectangle(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_window", lambda hwnd: hwnd == 123)
    monkeypatch.setattr(os_ops, "_window_work_area", lambda hwnd: (0, 0, 1920, 1040))
    rectangles = iter(((100, 100, 900, 700), (960, 0, 1920, 1040)))
    monkeypatch.setattr(os_ops, "_window_rect", lambda hwnd: next(rectangles))
    monkeypatch.setattr(os_ops, "_window_pid", lambda hwnd: 456)
    monkeypatch.setattr(os_ops, "_set_window_rect", lambda hwnd, target: True)
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)

    result = os_ops.window_move_action("right", hwnd=123)

    assert result.success is True
    assert result.data["after"] == (960, 0, 1920, 1040)


def test_window_close_refuses_room(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_window", lambda hwnd: True)
    monkeypatch.setattr(os_ops, "_window_text", lambda hwnd: "ZARA Room - ChatGPT")
    monkeypatch.setattr(os_ops, "_window_process_name", lambda hwnd: "chrome.exe")

    result = os_ops.window_close_action(hwnd=123)

    assert result.success is False
    assert result.data["status"] == "PROTECTED"
