import asyncio

from core.ipc_handlers import IPCHandler, IPCMessage
from memory.pilot_context import build_pilot_context


class _UnexpectedBrain:
    def query(self, *_args, **_kwargs):
        raise AssertionError("greetings must not query the shared brain")


def test_builder_skips_brain_for_context_free_greeting():
    result = build_pilot_context(_UnexpectedBrain(), "Oi, Zoe")

    assert result["success"] is True
    assert result["context"] == ""


def test_handler_does_not_construct_shared_brain_for_greeting():
    handler = object.__new__(IPCHandler)
    sent = []

    async def send(message):
        sent.append(message)

    def forbidden_brain_construction():
        raise AssertionError("greetings must not compose the shared brain")

    handler.send = send
    handler.get_second_brain = forbidden_brain_construction

    asyncio.run(handler.handle_pilot_context(
        IPCMessage(type="pilot-context", request_id="greeting-1", payload={"text": "Oi, Zoe"})
    ))

    assert len(sent) == 1
    assert sent[0].response["success"] is True
    assert sent[0].response["context"] == ""


def test_greeting_with_a_question_retains_context_and_queries_brain():
    calls = []

    class Brain:
        def query(self, text, **_kwargs):
            calls.append(text)
            return {"items": [{"text": "A entrega azul ainda esta pendente.",
                               "provenance": "aprendizados/entrega.md"}], "degraded": []}

    text = "Oi, Zoe! Qual o estado da entrega azul?"
    result = build_pilot_context(Brain(), text)

    assert calls == [text]
    assert result["success"] is True
    assert "entrega azul" in result["context"]


def test_greeting_with_a_question_does_not_bypass_unavailable_brain():
    result = build_pilot_context(None, "Oi, Zoe! O que falta no projeto?")

    assert result["success"] is False
    assert result["context"] == ""


def test_handler_still_composes_brain_for_a_question_after_greeting():
    handler = object.__new__(IPCHandler)
    sent = []
    compositions = []

    async def send(message):
        sent.append(message)

    def unavailable_brain():
        compositions.append(True)
        return None

    handler.send = send
    handler.get_second_brain = unavailable_brain
    asyncio.run(handler.handle_pilot_context(
        IPCMessage(type="pilot-context", request_id="context-1",
                   payload={"text": "Oi, Zoe! O que falta no projeto?"})
    ))

    assert compositions == [True]
    assert len(sent) == 1
    assert sent[0].response["success"] is False
