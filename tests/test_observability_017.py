from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler, _sanitize_observation


def test_sanitization_redacts_paths_tokens_and_bounds_message():
    clean = _sanitize_observation(r"failed C:\Users\alex\secret.txt api_key=TOPSECRET token=ABC " + "x" * 300)
    assert "secret.txt" not in clean and "TOPSECRET" not in clean and "ABC" not in clean
    assert len(clean) <= 180


@pytest.mark.asyncio
async def test_executor_exception_logs_safe_structured_event(monkeypatch, capsys):
    async def fail(action, **params):
        raise RuntimeError(r"boom C:\private\data.txt token=SECRET")

    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", fail)
    assert await handler._try_pc_intent("volume em 20%") is None
    logged = capsys.readouterr().err
    assert "action=os_volume" in logged and "stage=executor" in logged
    assert "exception_type=RuntimeError" in logged and "duration_ms=" in logged
    assert "SECRET" not in logged and "private" not in logged
