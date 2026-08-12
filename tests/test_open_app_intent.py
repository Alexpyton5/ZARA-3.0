from unittest.mock import AsyncMock, Mock

import pytest

from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "expected_app"),
    [
        ("abra a calculadora", "calculator"),
        ("inicie a calculadora", "calculator"),
        ("abre o bloco de notas", "notepad"),
        ("quero abrir o bloco de notas", "notepad"),
        ("abrir Chrome", "chrome"),
        ("abra o Google Chrome", "chrome"),
        ("abre calc", "calculator"),
        ("abrir notepad", "notepad"),
        ("executa calc", "calculator"),
        ("execute o bloco de notas", "notepad"),
        ("executar Chrome", "chrome"),
        ("abra o gerenciador de tarefas", "task_manager"),
        ("execute task manager", "task_manager"),
        ("abra as configurações", "settings"),
        ("abra o paint", "paint"),
        ("abra a ferramenta de captura", "snipping_tool"),
        ("abra o Microsoft Edge", "edge"),
        ("abra o Spotify", "spotify"),
    ],
)
def test_safe_app_phrases_normalize_to_allowlisted_ids(phrase, expected_app):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_app"
    assert result.param == expected_app
    assert result.blocked is False


@pytest.mark.parametrize(
    "phrase",
    [
        "abra powershell",
        "abra o regedit",
        "abra cmd /c calc",
        "abra calc && powershell",
        "execute powershell",
    ],
)
def test_unknown_or_injected_app_request_is_blocked_without_execution(phrase):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == "os_app"
    assert result.blocked is True
    assert result.physical_effect == 0
    assert "não está autorizado" in result.reply


def test_os_app_action_rejects_unknown_app_before_launch(monkeypatch):
    startfile = Mock()
    monkeypatch.setattr(os_ops.os, "startfile", startfile)

    result = os_ops.os_app_action("powershell -enc arbitrary")

    assert result.success is False
    assert result.data == {"app": "powershell -enc arbitrary", "allowlisted": False}
    startfile.assert_not_called()


def test_os_app_action_verifies_created_notepad_process(monkeypatch):
    observed = iter(({111}, {111, 222}))
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_resolve_windows_app_command", lambda app: ["notepad.exe"])
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: next(observed))
    monkeypatch.setattr(os_ops, "_window_for_pids", lambda pids: 444)
    startfile = Mock()
    monkeypatch.setattr(os_ops.os, "startfile", startfile)

    result = os_ops.os_app_action("notepad")

    assert result.success is True
    assert result.output == "Bloco de Notas aberto e verificado."
    assert result.data["preexisting_pids"] == [111]
    assert result.data["created_pids"] == [222]
    assert result.data["verified"] is True
    startfile.assert_called_once_with("notepad.exe")


def test_os_app_action_uses_grammatical_calculator_reply(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_resolve_windows_app_command", lambda app: ["calc.exe"])
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: {333})
    monkeypatch.setattr(os_ops, "_window_for_pids", lambda pids: 555)
    monkeypatch.setattr(os_ops.os, "startfile", Mock())

    result = os_ops.os_app_action("calculator")

    assert result.success is True
    assert result.output == "Calculadora aberta e verificada."


@pytest.mark.asyncio
async def test_ipc_routes_allowlisted_app_and_returns_verified_reply(monkeypatch):
    calls = []

    async def fake_execute_action(action, **params):
        calls.append((action, params))
        return type(
            "Result",
            (),
            {"success": True, "error": "", "output": "Calculadora aberta e verificada."},
        )()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)

    reply = await handler._try_pc_intent("abra a calculadora")

    assert calls == [("os_app", {"app": "calculator"})]
    assert reply == "Calculadora aberta e verificada."


@pytest.mark.asyncio
async def test_ipc_never_executes_unknown_app(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("abra powershell")

    assert "não está autorizado" in reply
    execute.assert_not_awaited()
