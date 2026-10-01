"""MSS snapshot failures and stale grounding must prevent desktop input."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from core.actions import computer_use as pc


@pytest.fixture
def observed_desktop(monkeypatch):
    events = []
    window = {'hwnd': 7, 'title': 'Editor', 'rect': {'left': 0, 'top': 0, 'right': 100, 'bottom': 100}}
    foreground = Mock(side_effect=lambda: dict(window))
    monkeypatch.setattr(pc, '_foreground', foreground)
    class Capture:
        monitors = [{'left': 0, 'top': 0, 'width': 400, 'height': 400}]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, region):
            events.append('snapshot')
            return SimpleNamespace(raw=bytes(region['width'] * region['height'] * 4))
    capture = Capture()
    monkeypatch.setitem(sys.modules, 'mss', SimpleNamespace(mss=lambda: capture))
    gui = SimpleNamespace(FAILSAFE=True, failSafeCheck=Mock(),
        click=Mock(side_effect=lambda *a, **k: events.append('click')),
        scroll=Mock(side_effect=lambda *a, **k: events.append('scroll')),
        press=Mock(side_effect=lambda *a, **k: events.append('key')))
    monkeypatch.setitem(sys.modules, 'pyautogui', gui)
    return events, foreground, capture, gui, window


@pytest.mark.parametrize('kind', ['click', 'scroll', 'key'])
def test_snapshot_precedes_input_and_receipt_contains_no_pixels(observed_desktop, kind):
    events, _, _, _, _ = observed_desktop
    result = (pc.computer_click_action(20, 30, 7) if kind == 'click' else
              pc.computer_scroll_action(20, 30, 1, 7) if kind == 'scroll' else
              pc.computer_press_key_action('enter', 7))
    assert result.success and not result.verificado
    assert events == ['snapshot', kind]
    observation = result.data['observation']
    assert len(observation['frame_sha256']) == 64
    assert observation['observed_at'] and observation['hwnd'] == 7
    assert 'pixels' not in observation and 'text' not in observation


def test_failed_capture_aborts_without_input(observed_desktop, monkeypatch):
    events, _, capture, gui, _ = observed_desktop
    monkeypatch.setattr(capture, 'grab', Mock(side_effect=OSError('capture failed')))
    result = pc.computer_click_action(20, 30, 7)
    assert not result.success
    gui.click.assert_not_called()
    assert events == []


@pytest.mark.parametrize('change', ['hwnd', 'rect'])
def test_window_change_during_snapshot_aborts_input(observed_desktop, monkeypatch, change):
    events, _, capture, gui, window = observed_desktop
    original = capture.grab
    def grab(region):
        shot = original(region)
        if change == 'hwnd': window['hwnd'] = 8
        else: window['rect'] = {**window['rect'], 'left': 10}
        return shot
    monkeypatch.setattr(capture, 'grab', grab)
    result = pc.computer_click_action(20, 30, 7)
    assert not result.success
    gui.click.assert_not_called()
    assert events == ['snapshot']
