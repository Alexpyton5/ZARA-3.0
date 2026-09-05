from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage
from core.self_knowledge import detect_self_knowledge_topic


@pytest.mark.parametrize(
    ("question", "topic"),
    [
        ("Quem é você?", "identity"),
        ("Qual modelo está usando?", "model"),
        ("Quais providers estão disponíveis?", "providers"),
        ("O que é Codex?", "codex"),
        ("O que é Mentor?", "mentor"),
        ("O que é LAB?", "lab"),
        ("Onde você está instalada?", "runtime"),
        ("O que você consegue fazer?", "capabilities"),
        ("Por que a última ação falhou?", "failure"),
    ],
)
def test_detects_only_supported_self_knowledge_questions(question, topic):
    assert detect_self_knowledge_topic(question) == topic


def test_does_not_capture_unrelated_general_questions():
    assert detect_self_knowledge_topic("O que é Python?") is None
    assert detect_self_knowledge_topic("Quem é Ada Lovelace?") is None


@pytest.mark.asyncio
async def test_model_and_provider_answers_use_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())
    handler.orchestrator = SimpleNamespace(last_engine_used="groq_gpt_oss_120b")
    handler.model_router = SimpleNamespace(
        configured_model_status=lambda include_paid=False: [
            {
                "id": "groq_gpt_oss_120b",
                "provider": "groq",
                "health": {"state": "AVAILABLE"},
            }
        ]
    )

    model_reply = await handler._try_self_knowledge("Qual modelo está usando?")
    provider_reply = await handler._try_self_knowledge("Quais providers estão disponíveis?")

    assert "Eu sou ZARA" in model_reply
    assert "GPT-OSS 120B (Groq)" in model_reply
    assert "groq" in model_reply
    assert "groq: AVAILABLE" in provider_reply


@pytest.mark.asyncio
async def test_capability_catalog_reflects_gate_and_hardware(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    import core.actions  # noqa: F401
    import core.ipc_handlers as ipc_handlers
    from core.action_registry import get_registry

    registry = get_registry()
    required_actions = {
        "os_volume", "audio_mute", "audio_unmute", "os_app", "os_open",
        "files_write", "files_copy", "files_move", "files_search",
        "window_minimize", "window_maximize", "window_restore", "window_switch",
        "browser_open_url", "browser_search", "media_play_pause", "media_next",
        "media_previous", "os_brightness_absolute", "os_night_light_on",
        "os_night_light_off",
    }
    for name in required_actions:
        if registry.get_spec(name) is None:
            registry.register(name, lambda: None, capability="PC_CONTROL")
    monkeypatch.setattr(ipc_handlers, "_read_windows_brightness_level", lambda: None)
    handler = IPCHandler(AsyncMock())
    handler.reminder_engine = object()
    handler.user_memory = object()
    handler.project_memory = object()

    blocked = await handler._try_self_knowledge("O que você consegue fazer?")
    assert "VOLUME/MUTE: AVAILABLE" in blocked
    assert "BRILHO: UNSUPPORTED" in blocked
    assert "LEMBRETES: AVAILABLE" in blocked

    available = await handler._try_self_knowledge("O que você consegue fazer?")
    assert "VOLUME/MUTE: AVAILABLE" in available


@pytest.mark.asyncio
async def test_text_and_voice_share_self_knowledge_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    sent = []

    async def capture(message):
        sent.append(message)

    handler = IPCHandler(capture)
    handler.conversation_history = None
    handler._try_self_knowledge = AsyncMock(return_value="Eu sou ZARA.")
    handler._speak_response = AsyncMock()

    await handler.handle_send_message(
        IPCMessage(type="send-message", request_id="text-1", payload={"text": "Quem é você?"})
    )
    await handler._process_voice_message("Quem é você?")

    assert handler._try_self_knowledge.await_count == 2
    text_response = next(item for item in sent if item.type == "response")
    voice_response = next(item for item in sent if item.type == "message")
    assert text_response.response["engine"] == "self_knowledge"
    assert voice_response.message["engine"] == "self_knowledge"
    assert text_response.response["response"] == voice_response.message["content"]


@pytest.mark.asyncio
async def test_last_action_failure_is_explained_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())
    handler._remember_action_failure("os_app", "executor", "token=abc123 C:\\secret\\path")

    reply = await handler._try_self_knowledge("Por que a última ação falhou?")

    assert "os_app" in reply
    assert "executor" in reply
    assert "abc123" not in reply
    assert "C:\\secret\\path" not in reply
