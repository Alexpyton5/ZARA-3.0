"""AUDITORIA_2026-08-28 (Alex): "abra o chrome no perfil Trabalho" tem que
abrir direto nesse perfil, sem passar pela tela de escolha de perfil."""
from __future__ import annotations

import json
from unittest.mock import Mock

from core.actions import os_ops
from core.pc_voice_intent import PcVoiceIntentDetector


def _fake_local_state(tmp_path, profiles: dict[str, str]):
    chrome_dir = tmp_path / "Google" / "Chrome" / "User Data"
    chrome_dir.mkdir(parents=True, exist_ok=True)
    local_state = chrome_dir / "Local State"
    local_state.write_text(
        json.dumps({"profile": {"info_cache": {key: {"name": name} for name, key in profiles.items()}}}),
        encoding="utf-8",
    )
    return local_state


def test_resolve_chrome_profile_reads_real_local_state(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Trabalho": "Profile 4", "alex": "Profile 2"})
    monkeypatch.setattr(os_ops.os, "environ", {**os_ops.os.environ, "LOCALAPPDATA": str(tmp_path)})

    assert os_ops.resolve_chrome_profile("Trabalho") == "Profile 4"
    assert os_ops.resolve_chrome_profile("TRABALHO") == "Profile 4"
    assert os_ops.resolve_chrome_profile("nao existe") is None


def test_chrome_open_profile_action_launches_with_profile_flag(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Trabalho": "Profile 4"})
    monkeypatch.setattr(os_ops.os, "environ", {**os_ops.os.environ, "LOCALAPPDATA": str(tmp_path)})
    monkeypatch.setattr(os_ops, "_resolve_windows_app_command", lambda app: ["C:/chrome.exe"])
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: {123})
    popen = Mock()
    monkeypatch.setattr(os_ops.subprocess, "Popen", popen)

    result = os_ops.chrome_open_profile_action("Trabalho")

    assert result.success is True
    popen.assert_called_once_with(["C:/chrome.exe", "--profile-directory=Profile 4"])


def test_chrome_open_profile_action_fails_honestly_for_unknown_profile(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Trabalho": "Profile 4"})
    monkeypatch.setattr(os_ops.os, "environ", {**os_ops.os.environ, "LOCALAPPDATA": str(tmp_path)})

    result = os_ops.chrome_open_profile_action("Perfil Fantasma")

    assert result.success is False
    assert "Trabalho" in result.error


def test_voice_detects_open_chrome_with_profile():
    detector = PcVoiceIntentDetector()

    result = detector.detect("abra o chrome no perfil trabalho")

    assert result.action == "chrome_open_profile"
    assert result.param == "trabalho"
    assert result.blocked is False
