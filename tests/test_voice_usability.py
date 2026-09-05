"""Usability contract tests for the current renderer IPC path.

These scenarios exercise the messages emitted to Electron.  The handler is an
event-driven API; it does not return the assistant text to its Python caller.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from core.ipc_handlers import RESPOSTA_NAO_SEI, IPCHandler, IPCMessage


@dataclass
class Harness:
    handler: IPCHandler
    sent: list[IPCMessage]

    def response(self) -> IPCMessage:
        return next(message for message in reversed(self.sent) if message.type == "response")


class FakeOrchestrator:
    last_engine_used = "fake_engine"

    def __init__(self, response: str = "Tudo certo, Alex.") -> None:
        self.response = response
        self.calls: list[tuple[str, str, list]] = []

    async def process_message(self, text: str, engine: str, history=None) -> str:
        self.calls.append((text, engine, history or []))
        return self.response


@pytest.fixture()
def harness() -> Harness:
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    handler = IPCHandler(send)
    handler.conversation_history = None
    handler.orchestrator = FakeOrchestrator()
    return Harness(handler, sent)


@contextmanager
def _neutral_routes(handler: IPCHandler) -> Iterator[dict[str, AsyncMock]]:
    mocks = {
        "_try_jarvis_multi_action": AsyncMock(return_value=None),
        "_try_reminder_intent": AsyncMock(return_value=None),
        "_try_operational_memory_intent": AsyncMock(return_value=None),
        "_try_self_knowledge": AsyncMock(return_value=None),
        "_try_file_intent": AsyncMock(return_value=None),
        "_try_compound_pc_intent": AsyncMock(return_value=None),
        "_try_pc_intent": AsyncMock(return_value=None),
    }
    with patch.multiple(
        handler,
        **mocks,
    ):
        yield mocks


@pytest.mark.asyncio
async def test_text_message_emits_renderer_response(harness: Harness) -> None:
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="one", payload={"message": "Olá"})
        )
    response = harness.response()
    assert response.response == {"response": "Tudo certo, Alex.", "engine": "fake_engine"}


@pytest.mark.asyncio
async def test_history_is_forwarded_in_order(harness: Harness) -> None:
    history = [{"role": "user", "content": "antes"}]
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(
                type="send-message",
                request_id="history",
                payload={"message": "agora", "history": history},
            )
        )
    assert harness.handler.orchestrator.calls[0][2] == history


@pytest.mark.asyncio
async def test_empty_message_returns_explicit_error(harness: Harness) -> None:
    await harness.handler.handle_send_message(
        IPCMessage(type="send-message", request_id="empty", payload={"message": "   "})
    )
    assert harness.response().error == "No text provided"


@pytest.mark.asyncio
async def test_missing_backend_returns_friendly_response(harness: Harness) -> None:
    harness.handler.orchestrator = None
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="offline", payload={"message": "Olá"})
        )
    assert "temporariamente indisponível" in harness.response().response["response"]


@pytest.mark.asyncio
async def test_pc_reply_uses_same_renderer_response_contract(harness: Harness) -> None:
    with _neutral_routes(harness.handler) as mocks:
        mocks["_try_pc_intent"].return_value = "Aplicativo aberto e verificado."
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="pc", payload={"message": "abra o bloco de notas"})
        )
    response = harness.response().response
    assert response["engine"] == "pc_control"
    assert "verificado" in response["response"]


@pytest.mark.asyncio
async def test_pc_router_exception_fails_closed_without_crashing(harness: Harness) -> None:
    with _neutral_routes(harness.handler) as mocks:
        mocks["_try_pc_intent"].side_effect = RuntimeError("private detail")
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="pc-error", payload={"message": "abra o app"})
        )
    response = harness.response().response
    assert response["engine"] == "local_action_error"
    assert response["response"] == "Não consegui executar essa ação com segurança."
    assert "private detail" not in response["response"]


@pytest.mark.asyncio
async def test_unhandled_local_action_never_falls_through_to_model(harness: Harness) -> None:
    orchestrator = harness.handler.orchestrator
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="guard", payload={"message": "ligar a luz"})
        )
    assert harness.response().response["response"] == RESPOSTA_NAO_SEI
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_unicode_message_reaches_model_intact(harness: Harness) -> None:
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="unicode", payload={"message": "olá 😊"})
        )
    assert harness.handler.orchestrator.calls[0][0] == "olá 😊"


@pytest.mark.asyncio
async def test_large_message_is_processed_without_recursion_or_crash(harness: Harness) -> None:
    message = "a" * 10_000
    with _neutral_routes(harness.handler):
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="large", payload={"message": message})
        )
    assert len(harness.handler.orchestrator.calls[0][0]) == 10_000
    assert harness.response().response["response"] == "Tudo certo, Alex."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "engine"),
    [
        ("_try_reminder_intent", "reminder"),
        ("_try_operational_memory_intent", "operational_memory"),
        ("_try_self_knowledge", "self_knowledge"),
        ("_try_file_intent", "file_control"),
    ],
)
async def test_deterministic_routes_short_circuit_model(
    harness: Harness, route: str, engine: str
) -> None:
    orchestrator = harness.handler.orchestrator
    with _neutral_routes(harness.handler) as mocks:
        mocks[route].return_value = "Resposta determinística"
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id=engine, payload={"message": "pedido"})
        )
    assert harness.response().response == {
        "response": "Resposta determinística",
        "engine": engine,
    }
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_jarvis_plan_has_highest_priority(harness: Harness) -> None:
    with _neutral_routes(harness.handler) as mocks:
        mocks["_try_jarvis_multi_action"].return_value = "Plano pronto"
        await harness.handler.handle_send_message(
            IPCMessage(type="send-message", request_id="jarvis", payload={"message": "faça tudo"})
        )
    assert harness.response().response == {"response": "Plano pronto", "engine": "jarvis_plan"}


@pytest.mark.asyncio
async def test_interrupt_stops_all_active_audio_paths(harness: Harness) -> None:
    class TTS:
        interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    class VoicePipeline:
        interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    class Gemini:
        active = True
        interrupted = False

        async def interrupt_speech(self) -> None:
            self.interrupted = True

    tts, pipeline, gemini = TTS(), VoicePipeline(), Gemini()
    harness.handler.tts_manager = tts
    harness.handler.voice_pipeline = pipeline
    harness.handler.gemini_live_voice = gemini

    await harness.handler.handle_interrupt(IPCMessage(type="interrupt", request_id="stop"))

    assert tts.interrupted and pipeline.interrupted and gemini.interrupted
    assert harness.response().response == {"success": True}
