"""Testes do chat da Conselheira (fluxo ZARA-CHAT) — sem rede nem credencial."""
import tempfile
from pathlib import Path

import pytest

from core.lab_ceo_gmail_bridge import (
    CEO_MAILBOX_DEFAULT,
    CHAT_CHECK_INTERVAL_SECONDS,
    ChatRelay,
    LoggingStubAdapter,
    build_chat_email,
    build_context_snapshot,
    new_chat_id,
    parse_chat_reply,
)


def _relay(**kwargs):
    tmp = Path(tempfile.mkdtemp())
    return ChatRelay(root=tmp, adapter=LoggingStubAdapter(), **kwargs)


def test_defaults_decididos_com_o_alex():
    relay = _relay()
    assert relay.mailbox == "zoeeproject@gmail.com"
    assert relay.mailbox == CEO_MAILBOX_DEFAULT
    assert relay.check_interval == 300
    assert relay.check_interval == CHAT_CHECK_INTERVAL_SECONDS
    snap = relay.snapshot()
    assert snap["mailbox"] == "zoeeproject@gmail.com"
    assert snap["check_interval_seconds"] == 300
    assert snap["transport"] == "gmail"


def test_build_chat_email_formato():
    p = build_chat_email("Como está o Lab?", context="ctx teste")
    assert p["chat_id"].startswith("CHAT-")
    assert p["subject"].startswith("[ZARA-CHAT] CHAT-")
    assert "Como está o Lab?" in p["subject"]  # trecho no assunto
    assert "## Contexto da ZARA" in p["body"]
    assert "ctx teste" in p["body"]
    assert "## Mensagem do Alex" in p["body"]
    assert "Como está o Lab?" in p["body"]
    assert "[ZARA-CHAT-REPLY]" in p["body"]
    assert f"chat_id: {p['chat_id']}" in p["body"]


def test_build_chat_email_rejeita_vazia():
    with pytest.raises(ValueError):
        build_chat_email("   ")


def test_new_chat_id_unico():
    assert new_chat_id() != new_chat_id()
    assert new_chat_id().startswith("CHAT-")


def test_context_snapshot_basico():
    snap = build_context_snapshot("extra aqui")
    assert "Data/hora:" in snap
    assert "extra aqui" in snap


def test_parse_chat_reply_valida():
    cid = new_chat_id()
    body = f"""Oi Alex, segue:

[ZARA-CHAT-REPLY]
chat_id: {cid}
reply: Pode seguir com o plano.
[/ZARA-CHAT-REPLY]
"""
    r = parse_chat_reply(body)
    assert r is not None
    assert r.chat_id == cid
    assert r.reply == "Pode seguir com o plano."
    assert r.matched is True


def test_parse_chat_reply_invalida():
    assert parse_chat_reply("texto qualquer") is None
    cid = new_chat_id()
    assert parse_chat_reply("[ZARA-CHAT-REPLY]\nchat_id: XPTO\nreply: oi\n[/ZARA-CHAT-REPLY]") is None
    assert parse_chat_reply(f"[ZARA-CHAT-REPLY]\nchat_id: {cid}\nreply:   \n[/ZARA-CHAT-REPLY]") is None


def test_roundtrip_chat_idempotente():
    relay = _relay()
    p = relay.send_message("Qual a prioridade hoje?", context="ctx")
    assert relay.pending_count() == 1
    # mensagem já aparece no histórico do painel
    thread = relay.get_thread()
    assert len(thread) == 1
    assert thread[0]["role"] == "alex"
    assert thread[0]["text"] == "Qual a prioridade hoje?"

    result = relay.sync()
    assert result["sent"] == [p["chat_id"]]
    assert relay.pending_count() == 0
    assert relay.awaiting_count() == 1

    adapter = relay.adapter
    assert isinstance(adapter, LoggingStubAdapter)
    assert adapter.sent[0]["to"] == "zoeeproject@gmail.com"
    adapter.inject_reply(
        f"Re: {p['subject']}",
        f"[ZARA-CHAT-REPLY]\nchat_id: {p['chat_id']}\nreply: Foca no Lab hoje.\n[/ZARA-CHAT-REPLY]",
    )
    replies = relay.sync_inbox()
    assert len(replies) == 1
    assert replies[0].reply == "Foca no Lab hoje."
    assert replies[0].matched is True
    assert relay.awaiting_count() == 0

    thread = relay.get_thread()
    assert [t["role"] for t in thread] == ["alex", "zoe"]
    assert thread[1]["text"] == "Foca no Lab hoje."

    # idempotência: segunda leitura não duplica
    assert relay.sync_inbox() == []
    assert len(relay.get_thread()) == 2
    assert result["last_sync_at"] is not None
    assert relay.snapshot()["last_sync_at"] == result["last_sync_at"]


def test_resposta_sem_mensagem_marcada_unmatched():
    relay = _relay()
    adapter = relay.adapter
    assert isinstance(adapter, LoggingStubAdapter)
    cid = new_chat_id()
    adapter.inject_reply(
        "[ZARA-CHAT] assunto",
        f"[ZARA-CHAT-REPLY]\nchat_id: {cid}\nreply: Olá!\n[/ZARA-CHAT-REPLY]",
    )
    replies = relay.sync_inbox()
    assert len(replies) == 1
    assert replies[0].matched is False
    # mesmo sem par, entra no histórico para o Alex ver
    assert relay.get_thread()[-1]["text"] == "Olá!"


def test_sync_envia_e_importa_de_uma_vez():
    relay = _relay()
    p = relay.send_message("Oi zoe")
    relay.sync_outbox()
    adapter = relay.adapter
    assert isinstance(adapter, LoggingStubAdapter)
    adapter.inject_reply(
        f"Re: {p['subject']}",
        f"[ZARA-CHAT-REPLY]\nchat_id: {p['chat_id']}\nreply: Oi Alex!\n[/ZARA-CHAT-REPLY]",
    )
    # simula que a mensagem já foi enviada antes (não está na outbox)
    result = relay.sync()
    assert result["sent"] == []
    assert len(result["replies"]) == 1
    assert result["replies"][0]["reply"] == "Oi Alex!"
