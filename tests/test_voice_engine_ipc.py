from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage, parse_ipc_message


@pytest.mark.asyncio
async def test_voice_engine_set_maps_legacy_omnivoice_to_kore(tmp_path, monkeypatch):
    # OmniVoice removido (02/10, decisao do Alex): o nome antigo mapeia pra
    # "kore" em vez de quebrar clientes antigos.
    from core import voice_preferences

    preference_file = tmp_path / "config" / "voice_preferences.json"
    monkeypatch.setattr(voice_preferences, "voice_preferences_path", lambda: preference_file)
    handler = IPCHandler.__new__(IPCHandler)
    handler.send = AsyncMock()
    handler._voice_output_engine = "kore"
    handler.tts_manager = SimpleNamespace(config=SimpleNamespace(output_engine="kore"))
    request = IPCMessage(type="voice-engine-set", request_id="set-engine", payload={"engine": "omnivoice"})

    await handler.handle_voice_engine_set(request)

    assert preference_file.read_text(encoding="utf-8") == '{"output_engine": "kore"}'
    assert handler._voice_output_engine == "kore"
    assert handler.tts_manager.config.output_engine == "kore"


@pytest.mark.asyncio
async def test_voice_engine_set_rejects_invalid_engine_without_changing_preference(tmp_path, monkeypatch):
    from core import voice_preferences

    preference_file = tmp_path / "config" / "voice_preferences.json"
    monkeypatch.setattr(voice_preferences, "voice_preferences_path", lambda: preference_file)
    handler = IPCHandler.__new__(IPCHandler)
    handler.send = AsyncMock()
    handler._voice_output_engine = "kore"
    request = IPCMessage(type="voice-engine-set", request_id="set-engine", payload={"engine": "sapi"})

    await handler.handle_voice_engine_set(request)

    assert not preference_file.exists()
    assert handler._voice_output_engine == "kore"
    handler.send.assert_awaited_once()
    assert "inválido" in (handler.send.await_args.args[0].error or "")


def test_voice_engine_requests_are_allowlisted_and_require_object_payload():
    assert parse_ipc_message({"type": "voice-engine-get", "request_id": "voice-engine-get"}).type == "voice-engine-get"
    assert parse_ipc_message({"type": "voice-engine-set", "payload": {"engine": "kore"}}).payload == {"engine": "kore"}
    with pytest.raises(ValueError, match="payload must be an object"):
        parse_ipc_message({"type": "voice-engine-set", "payload": "omnivoice"})
