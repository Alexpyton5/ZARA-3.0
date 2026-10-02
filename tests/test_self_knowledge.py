from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage
from core.self_knowledge import detect_self_knowledge_topic, is_self_knowledge_followup


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
        ("O sistema novo de voz da ZARA já foi implementado ou ainda usa Gemini?", "voice"),
        ("Você já está com o novo motor de voz ativado ou ainda usa Gemini Live?", "voice"),
        ("O ZARA Lab já está totalmente funcional?", "lab_status"),
    ],
)
def test_detects_only_supported_self_knowledge_questions(question, topic):
    assert detect_self_knowledge_topic(question) == topic


def test_does_not_capture_unrelated_general_questions():
    assert detect_self_knowledge_topic("O que é Python?") is None
    assert detect_self_knowledge_topic("Quem é Ada Lovelace?") is None


def test_detects_only_explicit_verification_followup():
    assert is_self_knowledge_followup("Você consegue checar isto para mim?") is True
    assert is_self_knowledge_followup("Consegue confirmar isso?") is True
    assert is_self_knowledge_followup("Cheque o preço disso para mim") is False


def test_live_voice_routes_status_and_verification_through_local_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())

    assert handler._voice_turn_needs_executor(
        "o sistema novo de voz já foi implementado ou ainda usa Gemini Live?"
    ) is True
    assert handler._voice_turn_needs_executor("você consegue checar isto para mim?") is True
    assert handler._voice_turn_needs_executor("o ZARA Lab já está totalmente funcional?") is True


@pytest.mark.asyncio
async def test_voice_and_lab_status_are_runtime_backed_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())
    handler.voice_active = True
    handler.voice_mode = "gemini_live"
    handler.voice_pipeline = object()
    handler.gemini_live_voice = object()
    handler.tts_manager = object()
    handler.lab = object()

    voice_reply = await handler._try_self_knowledge(
        "O sistema novo de voz da ZARA já foi implementado ou ainda usa Gemini?"
    )
    lab_reply = await handler._try_self_knowledge("O ZARA Lab já está totalmente funcional?")

    assert "Gemini Live" in voice_reply
    assert "cérebro selecionado" in voice_reply
    assert "Vosk + Kokoro permanece pendente" not in voice_reply
    assert "Estado observado agora" in lab_reply
    assert "não prova que todo o Lab esteja totalmente funcional" in lab_reply
    assert "falta aplicar o patch" not in lab_reply


@pytest.mark.asyncio
async def test_verification_followup_rechecks_previous_self_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())
    handler.voice_pipeline = object()
    handler.conversation_history.append(
        "user", "Você ainda usa o sistema antigo de voz com Gemini?", engine="luna"
    )
    handler.conversation_history.append(
        "assistant", "resposta antiga inventada", engine="luna"
    )
    handler.conversation_history.append(
        "user", "Você consegue checar isto para mim?", engine="luna"
    )

    reply = await handler._try_self_knowledge("Você consegue checar isto para mim?")

    assert "Estado observado agora" in reply
    assert "pipeline local" in reply
    assert "não está confirmado" not in reply


@pytest.mark.asyncio
async def test_verification_followup_without_previous_topic_does_not_claim_check(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_self_knowledge("Você consegue checar isto para mim?")

    assert "não encontrei o assunto" in reply.casefold()


@pytest.mark.asyncio
async def test_verification_followup_never_reopens_older_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    handler = IPCHandler(AsyncMock())
    handler.conversation_history.append(
        "user", "Você ainda usa o sistema antigo de voz com Gemini?", engine="luna"
    )
    handler.conversation_history.append(
        "assistant", "resposta sobre voz", engine="self_knowledge"
    )
    handler.conversation_history.append(
        "user", "Qual é a previsão do tempo?", engine="luna"
    )
    handler.conversation_history.append(
        "assistant", "resposta sobre clima", engine="luna"
    )
    handler.conversation_history.append(
        "user", "Você consegue checar isto para mim?", engine="luna"
    )

    reply = await handler._try_self_knowledge("Você consegue checar isto para mim?")

    assert "não encontrei o assunto" in reply.casefold()
    assert "pipeline local" not in reply


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

    assert "motor do TROPA DEV" in model_reply
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
    handler._try_self_knowledge = AsyncMock(return_value="Eu sou o motor do TROPA DEV, a ZARA.")
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
