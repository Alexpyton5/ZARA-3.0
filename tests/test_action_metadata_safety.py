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
