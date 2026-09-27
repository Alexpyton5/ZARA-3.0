from core.action_registry import get_registry


def test_windows_vision_is_registered_by_core_actions_import():
    registry = get_registry()
    assert "windows_vision_read" in registry.list_actions("windows")
    result = registry.execute("windows_vision_read", mode="simulate", simulated_text="runtime")
    assert result.success is True
    assert result.data["status"] == "SIMULATED"
