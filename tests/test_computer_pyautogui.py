"""Desktop inputs preserve foreground grounding and PyAutoGUI emergency stop."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from core.actions import computer_use as pc


@pytest.fixture
def desktop(monkeypatch):
    gui = SimpleNamespace(FAILSAFE=True, failSafeCheck=Mock(), click=Mock(), scroll=Mock(), press=Mock(), write=Mock())
    monkeypatch.setitem(sys.modules, 'pyautogui', gui)
    monkeypatch.setattr(pc, '_observe_before_input', lambda *a: {'frame_sha256': 'test-frame'})
    native = Mock()
    monkeypatch.setattr(pc.ctypes, 'windll', SimpleNamespace(user32=native))
    monkeypatch.setattr(pc, '_foreground', lambda: {'hwnd': 7, 'title': 'Editor', 'rect': {'left': 0, 'top': 0, 'right': 400, 'bottom': 400}})
    return gui, native


@pytest.mark.parametrize('operation', ['click', 'scroll', 'key'])
def test_observed_input_uses_pyautogui_and_still_needs_verification(desktop, operation):
    gui, native = desktop
    if operation == 'click':
        result = pc.computer_click_action(20, 30, 7)
        gui.click.assert_called_once_with(20, 30)
    elif operation == 'scroll':
        result = pc.computer_scroll_action(20, 30, 2, 7)
        gui.scroll.assert_called_once_with(2, x=20, y=30)
    else:
        result = pc.computer_press_key_action('enter', 7)
        gui.press.assert_called_once_with('enter')
    assert result.success and not result.verificado
    gui.failSafeCheck.assert_called()
    assert not native.mock_calls


@pytest.mark.parametrize('failure', ['disabled', 'corner'])
@pytest.mark.parametrize('operation', ['click', 'scroll', 'key'])
def test_emergency_stop_never_falls_back_to_native_input(desktop, failure, operation):
    gui, native = desktop
    if failure == 'disabled':
        gui.FAILSAFE = False
    else:
        gui.failSafeCheck.side_effect = RuntimeError('corner emergency stop')
    result = (pc.computer_click_action(20, 30, 7) if operation == 'click'
              else pc.computer_scroll_action(20, 30, 2, 7) if operation == 'scroll'
              else pc.computer_press_key_action('enter', 7))
    assert not result.success and not result.verificado
    gui.click.assert_not_called()
    gui.scroll.assert_not_called()
    gui.press.assert_not_called()
    assert not native.mock_calls


def test_changed_window_rejects_input_before_the_driver(desktop):
    gui, native = desktop
    result = pc.computer_click_action(20, 30, 8)
    assert not result.success
    gui.click.assert_not_called()
    assert not native.mock_calls


def test_ascii_typing_uses_driver_but_unicode_keeps_existing_safe_transport(desktop, monkeypatch):
    from core.actions import os_ops
    gui, _ = desktop
    unicode_writer = Mock(return_value=True)
    monkeypatch.setattr(os_ops, '_send_unicode_text', unicode_writer)
    assert pc._type_observed_text('hello')
    gui.write.assert_called_once_with('hello', interval=0)
    assert pc._type_observed_text('olá')
    unicode_writer.assert_called_once_with('olá')


@pytest.mark.parametrize('kind', ['text', 'template'])
def test_vision_clicks_share_the_emergency_stop(desktop, monkeypatch, kind):
    from core.action_registry import ActionResult
    from core.actions import vision, vision_actions
    gui, native = desktop
    gui.FAILSAFE = False
    monkeypatch.setattr(vision_actions, 'vision_find_text_action', Mock(return_value=ActionResult(True, data={'matches': [{'left': 20, 'top': 30, 'width': 10, 'height': 10}]})))
    monkeypatch.setattr(vision, 'vision_find_template_action', Mock(return_value=ActionResult(True, data={'matches': [{'x': 20, 'y': 30, 'width': 10, 'height': 10}]})))
    result = vision_actions.vision_click_text_action('button') if kind == 'text' else vision.vision_click_template_action('test.png')
    assert not result.success
    gui.click.assert_not_called()
    assert not native.mock_calls
