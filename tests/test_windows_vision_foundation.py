from __future__ import annotations

import importlib

import pytest

from core.action_registry import get_registry


@pytest.fixture
def vision():
    module = importlib.import_module("core.actions.windows_vision_foundation")
    module.clear_windows_ocr_provider()
    return module


def test_vision_action_is_read_only_and_registered(vision):
    registry = get_registry()
    assert "windows_vision_read" in registry.list_actions("windows")
    assert registry.get_spec("windows_vision_read").capability == "READ_ONLY"
    result = registry.execute("windows_vision_read", mode="simulate", simulated_text="janela teste")
    assert result.success is True
    assert result.verificado is True
    assert result.data["status"] == "SIMULATED"


def test_native_ocr_fails_closed_on_non_windows(vision, monkeypatch):
    monkeypatch.setattr(vision.platform, "system", lambda: "Linux")
    result = vision.windows_vision_read(mode="native")
    assert result.success is False
    assert result.verificado is False
    assert result.data["status"] == "UNSUPPORTED_PLATFORM"


def test_native_provider_is_explicit_and_read_only(vision, monkeypatch):
    monkeypatch.setattr(vision.platform, "system", lambda: "Windows")
    calls = []
    vision.register_windows_ocr_provider(lambda request: calls.append(request) or {"text": "texto lido"})
    result = vision.windows_vision_read(mode="native", source="foreground")
    assert result.success is True
    assert result.verificado is True
    assert result.data["text"] == "texto lido"
    assert calls == [{"source": "foreground"}]


def test_simulation_rejects_control_characters(vision):
    result = vision.windows_vision_read(mode="simulate", simulated_text="ok\x00")
    assert result.success is False
    assert result.data["status"] == "INVALID_SIMULATION"
