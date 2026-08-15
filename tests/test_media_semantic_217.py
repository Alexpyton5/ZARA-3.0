"""217/219 — media semantic readback adapter: verdade honesta, sem falso PASS."""
from __future__ import annotations

import pytest

from core.actions import os_ops


@pytest.fixture(autouse=True)
def _windows(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_send_windows_media_command", lambda name: True)


def test_no_readback_backend_is_not_proven(monkeypatch):
    monkeypatch.setattr(os_ops, "_media_semantic_state", lambda: None)
    res = os_ops._media_action("media_play_pause", "ok")
    assert res.success is False
    assert res.error == "MEDIA_COMMAND_SENT_NOT_PROVEN"
    assert res.data["readback"] == "UNAVAILABLE"
    assert res.data["state_verified"] is False


def test_readback_without_change_is_not_proven(monkeypatch):
    state = {"backend": "pycaw_session_state", "active_render_sessions": ["x.exe"]}
    monkeypatch.setattr(os_ops, "_media_semantic_state", lambda: dict(state))
    res = os_ops._media_action("media_next", "ok")
    assert res.success is False
    assert res.error == "MEDIA_COMMAND_SENT_NOT_PROVEN"
    assert res.data["readback"] == "NO_SEMANTIC_CHANGE"


def test_semantic_change_is_the_only_success_path(monkeypatch):
    seq = iter([
        {"backend": "pycaw_session_state", "active_render_sessions": ["player.exe"]},
        {"backend": "pycaw_session_state", "active_render_sessions": []},
    ])
    monkeypatch.setattr(os_ops, "_media_semantic_state", lambda: next(seq))
    res = os_ops._media_action("media_play_pause", "ok")
    assert res.success is True
    assert res.data["state_verified"] is True
    assert res.data["readback"] == "SEMANTIC_CHANGE_CONFIRMED"
    assert res.data["before"] != res.data["after"]


def test_transport_failure_is_error(monkeypatch):
    def _boom(_name):
        raise OSError("no transport")
    monkeypatch.setattr(os_ops, "_send_windows_media_command", _boom)
    monkeypatch.setattr(os_ops, "_media_semantic_state", lambda: None)
    res = os_ops._media_action("media_previous", "ok")
    assert res.success is False
    assert "Falha no controle de mídia" in res.error


def test_semantic_state_never_raises():
    """The readback probe must degrade to None, never explode."""
    out = os_ops._media_semantic_state()
    assert out is None or set(out) == {"backend", "active_render_sessions"}
