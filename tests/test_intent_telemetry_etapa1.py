"""ETAPA 1 do plano de raciocinio livre — log puro, zero mudanca de rota.

docs/audits/PROPOSTA_RACIOCINIO_LIVRE_2026-08-28.md, secao (d), "Etapa 1".

O que a etapa promete: so um log (sem decisao nova) nos dois pontos onde a
cadeia deterministica hoje falha —

1. `_looks_like_unhandled_local_action` decide recusar (RESPOSTA_NAO_SEI).
2. a frase escapa dos filtros e vai para `orchestrator.process_message`,
   mas so quando contem "sinal amplo de linguagem de acao" (heuristica de
   telemetria, nao um intent novo).

Estes testes travam a promessa da etapa: a RESPOSTA dada ao Alex (recusa ou
conversa livre) tem de ser byte a byte a mesma com ou sem a instrumentacao, e
comandos que ja funcionavam (via regex, o caminho RAPIDO) continuam batendo
sem passar perto do log ou do orquestrador.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from core.action_registry import ActionResult
from core.ipc_handlers import IPCHandler, IPCMessage
from core.pc_voice_intent import RESPOSTA_NAO_SEI
from core import ipc_handlers as ipc_handlers_module


def create_handler() -> IPCHandler:
    """Mesmo helper de tests/test_comandos_voz_e2e.py, para nao inventar
    setup novo para uma cadeia que ja tem harness comprovado."""
    handler = IPCHandler(AsyncMock())
    handler._initialized = True
    handler._tts_initialized = False
    handler.gemini_live_voice = None
    handler.voice_mode = "off"
    handler.voice_pipeline = None
    handler.tts_manager = None
    handler.memory = None
    handler.orchestrator = None
    handler.model_router = None
    handler.hermes = None
    handler.conversation_history = None
    handler.reminder_engine = None
    handler.user_memory = None
    handler.project_memory = None
    handler.lab = None
    handler._event_loop = asyncio.get_event_loop()
    handler.supercerebro_active = True
    handler._last_window_hwnd = 12345
    handler._last_volume_level = 50
    handler._operational_context_updated_at = time.monotonic()
    handler._operational_context_turns = 3
    handler._operational_context = {
        "action_type": "window",
        "canonical_target": "some_window",
        "pid": 1234,
        "hwnd": 12345,
        "verified_value": "some_value",
        "timestamp": handler._operational_context_updated_at,
        "created_by_zara": False,
    }
    return handler


class FakeOrchestrator:
    """Substitui o LLM real. Devolve uma resposta fixa e previsivel para que
    o teste possa comparar a resposta final byte a byte."""

    def __init__(self, reply: str = "conversa livre, nada de comando aqui"):
        self.reply = reply
        self.last_engine_used = "fake_llm"
        self.calls: list[str] = []

    async def process_message(self, text, engine=None, history=None):
        self.calls.append(text)
        return self.reply


# ---------------------------------------------------------------------------
# Unidade: a heuristica de telemetria e o logger, isolados.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase",
    [
        "meu bluetooth sumiu",       # substantivo de acao, sem verbo no inicio
        "o wifi caiu de novo",       # idem
        "a janela ficou estranha",   # substantivo "janela"
        "esqueci de trocar o brilho ontem",  # verbo no meio da frase
    ],
)
def test_broad_signal_catches_phrases_the_strict_guard_misses(phrase):
    from core.ipc_handlers import _has_broad_action_language_signal, _looks_like_unhandled_local_action

    # Se a heuristica ampla nao pegasse nada que a regex estrita ja pega,
    # ela nao acrescentaria dado nenhum a Etapa 1.
    assert _has_broad_action_language_signal(phrase) is True
    # E o guarda estrito (ancorado no inicio) continua sem bater nelas —
    # senao a frase teria sido recusada antes de chegar perto do LLM.
    assert _looks_like_unhandled_local_action(phrase) is False


@pytest.mark.parametrize(
    "phrase",
    [
        "oi, tudo bem?",
        "obrigado por ajudar ontem",
        "qual e a capital da frança",
    ],
)
def test_broad_signal_stays_quiet_for_plain_conversation(phrase):
    from core.ipc_handlers import _has_broad_action_language_signal

    assert _has_broad_action_language_signal(phrase) is False


def test_log_intent_telemetry_prints_one_grepable_line(capsys):
    from core.ipc_handlers import _log_intent_telemetry

    _log_intent_telemetry("refused_local_action", "voice", "abaixa o som")

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY]" in out
    assert "event=refused_local_action" in out
    assert "path=voice" in out
    assert "abaixa o som" in out


# ---------------------------------------------------------------------------
# Integracao: o log aparece nos dois pontos certos, na voz E no texto, e a
# RESPOSTA dada ao Alex nao muda em nenhum dos dois casos.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_refusal_logs_and_keeps_the_same_honest_reply(capsys):
    handler = create_handler()
    handler.orchestrator = FakeOrchestrator()

    await handler._process_voice_message("abaixa o som")

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY] event=refused_local_action path=voice" in out
    assert "abaixa o som" in out
    # Zero chamada ao orquestrador: continua sendo a recusa honesta, nao a IA.
    assert handler.orchestrator.calls == []

    sent_messages = [
        call.args[0] for call in handler.send.call_args_list
        if getattr(call.args[0], "type", None) == "message"
    ]
    assert sent_messages, "esperava um evento 'message' com a recusa"
    last = sent_messages[-1]
    assert last.message["content"] == RESPOSTA_NAO_SEI
    assert last.message["engine"] == "local_action_guard"


@pytest.mark.asyncio
async def test_text_refusal_logs_and_keeps_the_same_honest_reply(capsys):
    handler = create_handler()
    handler.orchestrator = FakeOrchestrator()

    await handler.handle_send_message(
        IPCMessage(type="send-message", request_id="1", payload={"text": "abaixa o som"})
    )

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY] event=refused_local_action path=text" in out
    assert "abaixa o som" in out
    assert handler.orchestrator.calls == []

    response_calls = [
        call.args[0] for call in handler.send.call_args_list
        if getattr(call.args[0], "response", None) is not None
    ]
    assert response_calls, "esperava um send_response com a recusa"
    last = response_calls[-1]
    assert last.response["response"] == RESPOSTA_NAO_SEI
    assert last.response["engine"] == "local_action_guard"


@pytest.mark.asyncio
async def test_voice_escape_with_broad_signal_logs_and_keeps_llm_reply(capsys):
    handler = create_handler()
    fake = FakeOrchestrator(reply="acho que seu bluetooth só precisa ser reativado no Windows")
    handler.orchestrator = fake

    await handler._process_voice_message("meu bluetooth sumiu, o que eu faço")

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY] event=escaped_to_orchestrator path=voice" in out
    assert "meu bluetooth sumiu" in out
    # A frase que chegou no orquestrador e a mesma frase original (a versao
    # ENRIQUECIDA com memoria pode diferir, mas o log de telemetria usa a
    # frase crua do Alex, nunca o texto com contexto colado).
    assert fake.calls, "esperava que o orquestrador tivesse sido chamado"

    sent_messages = [
        call.args[0] for call in handler.send.call_args_list
        if getattr(call.args[0], "type", None) == "message"
    ]
    last = sent_messages[-1]
    assert last.message["content"] == fake.reply


@pytest.mark.asyncio
async def test_text_escape_with_broad_signal_logs_and_keeps_llm_reply(capsys):
    handler = create_handler()
    fake = FakeOrchestrator(reply="posso te ajudar a religar o bluetooth")
    handler.orchestrator = fake

    await handler.handle_send_message(
        IPCMessage(
            type="send-message",
            request_id="1",
            payload={"text": "meu bluetooth sumiu, o que eu faço"},
        )
    )

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY] event=escaped_to_orchestrator path=text" in out
    assert "meu bluetooth sumiu" in out
    assert fake.calls

    response_calls = [
        call.args[0] for call in handler.send.call_args_list
        if getattr(call.args[0], "response", None) is not None
    ]
    last = response_calls[-1]
    assert last.response["response"] == fake.reply


@pytest.mark.asyncio
async def test_escape_without_broad_signal_stays_silent(capsys):
    """Conversa comum, sem cheiro nenhum de comando de PC: a Etapa 1 promete
    logar SO quando ha sinal amplo de acao. Sem sinal, sem linha."""
    handler = create_handler()
    fake = FakeOrchestrator(reply="tudo bem sim, e você?")
    handler.orchestrator = fake

    await handler._process_voice_message("oi, tudo bem?")

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY]" not in out
    assert fake.calls  # ainda foi para o orquestrador, so nao logou


# ---------------------------------------------------------------------------
# Regressao: comandos que ja funcionavam pelo caminho RAPIDO (regex) continuam
# batendo exatamente como antes, sem passar perto do guarda ou do LLM.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_abra_o_wordpad_still_takes_the_fast_regex_path(capsys):
    handler = create_handler()
    handler.orchestrator = FakeOrchestrator()

    with patch("core.action_registry.execute_action") as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Abri o WordPad.")

        await handler._process_voice_message("abra o wordpad")

    mock_execute.assert_called_once()
    args, _kwargs = mock_execute.call_args
    assert args[0] == "os_app"

    out = capsys.readouterr().out
    # Nunca chegou perto do guarda nem do log de telemetria: resolveu no
    # intent determinístico, que e o caminho rapido e principal.
    assert "[INTENT_TELEMETRY]" not in out
    assert handler.orchestrator.calls == []


@pytest.mark.asyncio
async def test_que_horas_sao_still_answers_without_touching_the_llm_or_the_log(capsys):
    handler = create_handler()
    handler.orchestrator = FakeOrchestrator()

    await handler._process_voice_message("Zara, que horas são?")

    out = capsys.readouterr().out
    assert "[INTENT_TELEMETRY]" not in out
    # "Que horas são" e resolvido antes do LLM (auto-conhecimento ou intent de
    # PC determinístico) — nunca deveria precisar do fallback de IA.
    assert handler.orchestrator.calls == []
