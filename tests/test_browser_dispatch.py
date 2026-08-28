from unittest.mock import AsyncMock, Mock
import pytest
from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector
from core.action_registry import get_registry

# Set pc_control_allowed to True for these tests
registry = get_registry()
registry.pc_control_allowed = True

@pytest.mark.parametrize(
    ("phrase", "action", "param"),
    [
        ("abra google.com", "browser_open_url", "google.com"),
        ("acesse https://openai.com", "browser_open_url", "https://openai.com"),
        ("vá para github.com", "browser_open_url", "github.com"),
        ("abra o site da OpenAI", "browser_open_url", "https://openai.com/"),
        ("abra o YouTube", "youtube_open", "youtube"),
        ("pesquise clima em Salvador", "browser_search", "clima em salvador"),
        ("procure por Python asyncio", "browser_search", "python asyncio"),
    ],
)
def test_browser_intents(phrase, action, param):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)
    assert result.action == action
    assert result.param == param

def test_domain_normalization_and_dispatch(monkeypatch):
    startfile = Mock()
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: {10})
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(os_ops.os, "startfile", startfile)
    result = os_ops.browser_open_url_action("google.com")
    assert result.success is True
    assert result.data["url"] == "https://google.com/"
    assert result.data["dispatch"] == "DISPATCH_PROVEN"
    assert result.data["browser_process_present"] is True
    assert result.data["target_page_proven"] is False
    startfile.assert_called_once_with("https://google.com/")

def test_search_uses_encoding_not_shell(monkeypatch):
    startfile = Mock()
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_running_app_pids", lambda names: {10})
    monkeypatch.setattr(os_ops.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(os_ops.os, "startfile", startfile)
    result = os_ops.browser_search_action("café & asyncio")
    assert result.success is True
    assert result.data["search_url"].endswith("q=caf%C3%A9+%26+asyncio")
    startfile.assert_called_once_with(result.data["search_url"])

@pytest.mark.parametrize(
    "payload",
    ["file:///C:/Windows/", "javascript:alert(1)", "data:text/html,x", "shell:AppsFolder", r"\\server\share", "https://example.com/a.exe", "https://user:pass@example.com"],
)
def test_dangerous_schemes_and_payloads_are_blocked(monkeypatch, payload):
    startfile = Mock()
    monkeypatch.setattr(os_ops.os, "startfile", startfile)
    assert os_ops.browser_open_url_action(payload).success is False
    startfile.assert_not_called()

def test_ambiguous_phrase_is_not_browser_navigation():
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect("abra uma possibilidade")
    assert result.action not in {"browser_open_url", "browser_search"}

@pytest.mark.asyncio
async def test_capability_gate_blocks_browser_dispatch(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    reply = await handler._try_pc_intent("abra google.com")
    assert reply == "Para controlar o computador, ative o Supercérebro."
    execute.assert_not_awaited()