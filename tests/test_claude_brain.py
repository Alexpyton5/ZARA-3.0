"""Testes offline para core/claude_brain.py -- NUNCA invocam o `claude` CLI
de verdade (seria recursivo/caro/lento). `asyncio.create_subprocess_exec` é
sempre mockado."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

import pytest

from core.claude_brain import ask_claude, claude_cli_available


def test_claude_cli_available_reflects_which(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/claude")
    assert claude_cli_available() is True

    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    assert claude_cli_available() is False


@pytest.mark.asyncio
async def test_ask_claude_empty_prompt_returns_none():
    assert await ask_claude("") is None
    assert await ask_claude("   ") is None


@pytest.mark.asyncio
async def test_ask_claude_cli_missing_returns_none(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: False)

    assert await ask_claude("oi") is None


class _FakeProcess:
    def __init__(self, stdout: bytes, returncode: int = 0, *, hang: bool = False):
        self._stdout = stdout
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(10)
        return self._stdout, b""

    def kill(self):
        self.killed = True


@pytest.mark.asyncio
async def test_ask_claude_success_returns_stdout(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)

    captured_args = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_args["args"] = args
        return _FakeProcess(b"Resposta do Claude aqui.\n")

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await ask_claude("qual a capital da Franca?")

    assert result == "Resposta do Claude aqui."
    assert captured_args["args"] == ("claude", "-p", "qual a capital da Franca?", "-c")


@pytest.mark.asyncio
async def test_ask_claude_without_continue_conversation_omits_flag(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    captured_args = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured_args["args"] = args
        return _FakeProcess(b"ok")

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await ask_claude("oi", continue_conversation=False)

    assert captured_args["args"] == ("claude", "-p", "oi")


@pytest.mark.asyncio
async def test_ask_claude_nonzero_exit_returns_none(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProcess(b"", returncode=1)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert await ask_claude("oi") is None


@pytest.mark.asyncio
async def test_ask_claude_empty_stdout_returns_none(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProcess(b"   \n")

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert await ask_claude("oi") is None


@pytest.mark.asyncio
async def test_ask_claude_timeout_kills_process_and_returns_none(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)
    fake_process = _FakeProcess(b"nunca chega", hang=True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await ask_claude("oi", timeout_s=0.05)

    assert result is None
    assert fake_process.killed is True


@pytest.mark.asyncio
async def test_ask_claude_spawn_failure_returns_none(monkeypatch):
    import core.claude_brain as module

    monkeypatch.setattr(module, "claude_cli_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        raise OSError("não achei o executável")

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert await ask_claude("oi") is None
