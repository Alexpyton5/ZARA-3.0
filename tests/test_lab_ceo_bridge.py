"""Testes da ponte CEO remoto via Gmail (não exigem rede nem credencial)."""
import tempfile
from pathlib import Path

import pytest

from core.lab_ceo_gmail_bridge import (
    CeoRelay,
    LoggingStubAdapter,
    build_request,
    new_request_id,
    parse_reply,
)


def _relay():
    tmp = Path(tempfile.mkdtemp())
    return CeoRelay(root=tmp, adapter=LoggingStubAdapter())


def test_build_request_formato():
    p = build_request("milestone", "Promover M010?", "ctx", "Aprova?", ["sim", "não"])
    assert p["request_id"].startswith("CEO-")
    assert p["subject"].startswith("[ZARA-CEO] CEO-")
    assert "request_id: " + p["request_id"] in p["body"]
    assert "[ZARA-CEO-DECISION]" in p["body"]


def test_build_request_rejeita_sem_titulo():
    with pytest.raises(ValueError):
        build_request("x", "   ", "ctx", "q")


def test_parse_reply_valida():
    rid = new_request_id()
    body = f"""Oi, segue decisão:

[ZARA-CEO-DECISION]
request_id: {rid}
decision: APPROVE
summary: Pode promover.
rationale: Evidências conferem.
[/ZARA-CEO-DECISION]
"""
    d = parse_reply(body)
    assert d is not None
    assert d.request_id == rid
    assert d.decision == "APPROVE"
    assert d.summary == "Pode promover."


def test_parse_reply_invalida_sem_bloco():
    assert parse_reply("só um texto qualquer") is None


def test_parse_reply_rejeita_decisao_desconhecida():
    rid = new_request_id()
    body = f"[ZARA-CEO-DECISION]\nrequest_id: {rid}\ndecision: TALVEZ\n[/ZARA-CEO-DECISION]"
    assert parse_reply(body) is None


def test_roundtrip_idempotente():
    relay = _relay()
    p = relay.request_decision("proposta", "Aceitar patch?", "ctx", "Aceita?")
    assert relay.pending_count() == 1
    sent = relay.sync_outbox()
    assert sent == [p["request_id"]]
    assert relay.pending_count() == 0
    assert relay.awaiting_count() == 1

    adapter = relay.adapter
    assert isinstance(adapter, LoggingStubAdapter)
    adapter.inject_reply(
        f"Re: {p['subject']}",
        f"[ZARA-CEO-DECISION]\nrequest_id: {p['request_id']}\n"
        "decision: DEFER\nsummary: Quero mais dados.\nrationale: Falta evidência.\n[/ZARA-CEO-DECISION]",
    )
    decisions = relay.sync_inbox()
    assert len(decisions) == 1
    assert decisions[0].decision == "DEFER"
    assert decisions[0].matched is True
    assert relay.awaiting_count() == 0
    # segunda leitura não duplica
    assert relay.sync_inbox() == []


def test_resposta_sem_pedido_marcada_unmatched():
    relay = _relay()
    adapter = relay.adapter
    assert isinstance(adapter, LoggingStubAdapter)
    rid = new_request_id()
    adapter.inject_reply(
        "[ZARA-CEO] assunto",
        f"[ZARA-CEO-DECISION]\nrequest_id: {rid}\ndecision: ANSWER\nsummary: ok.\n[/ZARA-CEO-DECISION]",
    )
    decisions = relay.sync_inbox()
    assert len(decisions) == 1
    assert decisions[0].matched is False
