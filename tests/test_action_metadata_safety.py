"""Static safety metadata for built-in actions with real side effects."""

import core.actions  # noqa: F401 - imports register action metadata only
from core.action_registry import get_registry


def test_side_effecting_actions_are_not_registered_as_read_only():
    registry = get_registry()
    expected = {
        "web_download": ("MEDIUM", "FILES_MUTATE"),
        "code_format": ("MEDIUM", "FILES_MUTATE"),
        "code_test": ("MEDIUM", "CODE_EXECUTION"),
        "vision_click_template": ("MEDIUM", "PC_CONTROL"),
    }

    actual = {
        name: (registry.get_spec(name).risk, registry.get_spec(name).capability)
        for name in expected
    }

    assert actual == expected


def test_closed_windows_reflexes_are_local_but_open_ended_actions_are_not():
    registry = get_registry()
    local = {
        "os_volume", "audio_mute", "audio_unmute", "os_brightness_absolute",
        "os_night_light_on", "os_app", "os_open", "window_minimize",
        "window_switch", "media_play_pause", "os_wifi_on", "os_bluetooth_on",
        "os_clipboard",
    }

    assert {registry.get_spec(name).capability for name in local} == {"LOCAL_PC_CONTROL"}
    assert registry.get_spec("browser_open_url").capability == "PC_CONTROL"
    assert registry.get_spec("browser_search").capability == "PC_CONTROL"
    assert registry.get_spec("terminal").capability == "CODE_EXECUTION"
    assert registry.get_spec("os_power").capability == "SYSTEM_POWER"
