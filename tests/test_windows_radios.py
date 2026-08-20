from __future__ import annotations

import json
import subprocess
from unittest.mock import AsyncMock

import pytest

from core.action_registry import ActionResult
from core.actions import windows_radios
from core.ipc_handlers import IPCHandler, IPCMessage
from core.pc_voice_intent import PcVoiceIntentDetector


def _completed(payload: dict, returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["powershell.exe"],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_radio_status_uses_hidden_static_powershell_and_parses_readback(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return _completed({
            "success": True,
            "status": "AVAILABLE",
            "kind": "WiFi",
            "before": "On",
            "after": "On",
            "changed": False,
        })

    monkeypatch.setattr(windows_radios.platform, "system", lambda: "Windows")
    monkeypatch.setattr(windows_radios.subprocess, "run", fake_run)

    result = windows_radios.os_wifi_status_action()

    assert result.success is True
    assert result.data["after"] == "On"
    assert observed["command"][:5] == [
        "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"
    ]
    assert observed["kwargs"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert observed["kwargs"]["timeout"] == 15


@pytest.mark.parametrize(
    ("action", "kind", "desired"),
    [
        (windows_radios.os_wifi_on_action, "wifi", True),
        (windows_radios.os_wifi_off_action, "wifi", False),
        (windows_radios.os_bluetooth_on_action, "bluetooth", True),
        (windows_radios.os_bluetooth_off_action, "bluetooth", False),
    ],
)
def test_radio_mutations_require_confirmed_postcondition(monkeypatch, action, kind, desired):
    monkeypatch.setattr(
        windows_radios,
        "_run_radio_command",
        lambda observed_kind, observed_desired: {
            "success": True,
            "status": "AVAILABLE",
            "kind": observed_kind,
            "before": "Off" if desired else "On",
            "after": "On" if desired else "Off",
            "changed": True,
        },
    )

    result = action()

    assert result.success is True
    assert result.data["kind"] == kind
    assert result.data["after"] == ("On" if desired else "Off")


def test_radio_mutation_never_claims_success_without_readback(monkeypatch):
    monkeypatch.setattr(
        windows_radios,
        "_run_radio_command",
        lambda *_: {"success": False, "status": "POSTCONDITION_FAILED", "after": "Off"},
    )

    result = windows_radios.os_bluetooth_on_action()

    assert result.success is False
    assert result.data["status"] == "POSTCONDITION_FAILED"


@pytest.mark.parametrize(
    ("phrase", "action"),
    [
        ("ligue o wi-fi", "os_wifi_on"),
        ("desligue o wifi", "os_wifi_off"),
        ("ative o bluetooth", "os_bluetooth_on"),
        ("desative o bluetooth", "os_bluetooth_off"),
    ],
)
def test_text_and_voice_radio_intents_use_registered_actions(phrase, action):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == action
    assert result.blocked is False


def test_radio_intent_remains_local_when_supercerebro_is_off():
    result = PcVoiceIntentDetector(pc_control_allowed=False).detect("ligue o bluetooth")

    assert result.is_pc_intent is True
    assert result.action == "os_bluetooth_on"
    assert result.blocked is False


@pytest.mark.asyncio
async def test_text_and_voice_execute_the_same_wifi_action(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    import core.action_registry as action_registry

    execute = AsyncMock(
        return_value=ActionResult(success=True, output="WiFi ficou ligado. Estado confirmado.")
    )
    monkeypatch.setattr(action_registry, "execute_action", execute)
    sent = []

    async def capture(message):
        sent.append(message)

    handler = IPCHandler(capture)
    handler.conversation_history = None
    handler._speak_response = AsyncMock()
    handler._set_supercerebro_state(True)

    await handler.handle_send_message(
        IPCMessage(type="send-message", request_id="text-wifi", payload={"text": "ligue o wi-fi"})
    )
    await handler._process_voice_message("ligue o wi-fi")

    assert execute.await_count == 2
    assert [call.args[0] for call in execute.await_args_list] == ["os_wifi_on", "os_wifi_on"]
    assert any(item.type == "response" and item.response["engine"] == "pc_control" for item in sent)
    assert any(item.type == "message" and item.message["engine"] == "pc_control" for item in sent)
