"""Testes do adaptador Gmail real da Conselheira (sem rede: IMAP/SMTP falsos)."""
import json

import pytest

from core.ceo_gmail_adapter import (
    GmailImapSmtpAdapter,
    GmailNotConfiguredError,
    build_gmail_adapter,
    load_gmail_config,
)


def _write_config(tmp_path, data):
    p = tmp_path / "ceo_gmail.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_config_ausente_levanta(tmp_path):
    with pytest.raises(GmailNotConfiguredError):
        load_gmail_config(tmp_path / "nao-existe.json")


def test_config_json_quebrado_levanta(tmp_path):
    p = tmp_path / "ceo_gmail.json"
    p.write_text("{quebrado", encoding="utf-8")
    with pytest.raises(GmailNotConfiguredError):
        load_gmail_config(p)


def test_config_incompleta_levanta(tmp_path):
    p = _write_config(tmp_path, {"email": "zoeeproject@gmail.com"})
    with pytest.raises(GmailNotConfiguredError):
        load_gmail_config(p)


def test_build_ok(tmp_path):
    p = _write_config(tmp_path, {
        "email": "zoeeproject@gmail.com",
        "app_password": "abcd efgh ijkl mnop",
    })
    adapter = build_gmail_adapter(p)
    assert adapter.is_real is True
    assert adapter.email_address == "zoeeproject@gmail.com"
    assert adapter.app_password == "abcdefghijklmnop"  # espaços removidos


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.sent = []
        self.logged_in = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def test_send(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    mid = adapter.send("zoeeproject@gmail.com", "[ZARA-CHAT] CHAT-1 oi", "corpo")
    assert mid.startswith("<") and mid.endswith(">")
    fake = _FakeSMTP.instances[-1]
    assert fake.logged_in == ("zoeeproject@gmail.com", "segredo")
    assert len(fake.sent) == 1
    assert fake.sent[0]["Subject"] == "[ZARA-CHAT] CHAT-1 oi"
    assert fake.sent[0]["To"] == "zoeeproject@gmail.com"


def test_send_falha_rede_levanta(monkeypatch):
    class _Boom(_FakeSMTP):
        def login(self, user, password):
            raise OSError("rede caiu")

    monkeypatch.setattr("smtplib.SMTP", _Boom)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    with pytest.raises(OSError):
        adapter.send("a@b.c", "s", "corpo")  # fail-closed: sem sucesso falso


RAW_1 = (
    b"From: zoe@teste\r\n"
    b"Subject: [ZARA-CHAT] CHAT-AAA primeira\r\n"
    b"Date: Mon, 28 Sep 2026 21:00:00 -0300\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"resposta um"
)
RAW_2 = (
    b"From: zoe@teste\r\n"
    b"Subject: [ZARA-CHAT] CHAT-BBB segunda\r\n"
    b"Date: Mon, 28 Sep 2026 22:00:00 -0300\r\n"
    b"Content-Type: multipart/alternative; boundary=XYZ\r\n"
    b"\r\n"
    b"--XYZ\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"resposta dois em texto puro\r\n"
    b"--XYZ\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<p>resposta dois em html</p>\r\n"
    b"--XYZ--\r\n"
)


class _FakeIMAP:
    instances = []
    fail_gm_raw = False
    fail_store = False

    def __init__(self, host, port, timeout=None):
        self.searches = []
        self.stores = []
        _FakeIMAP.instances.append(self)

    def login(self, user, password):
        pass

    def select(self, box):
        return ("OK", [b"2"])

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            self.searches.append(args)
            if args[1] == "X-GM-RAW" and _FakeIMAP.fail_gm_raw:
                import imaplib
                raise imaplib.IMAP4.error("desconhecido")
            return ("OK", [b"1 2"])
        if cmd == "FETCH":
            uid = args[0]
            raw = RAW_1 if uid == b"1" else RAW_2
            return ("OK", [(b"1 (RFC822 {123}", raw)])
        if cmd == "STORE":
            if _FakeIMAP.fail_store:
                raise OSError("falhou")
            self.stores.append(args)
            return ("OK", [b""])
        raise AssertionError(cmd)

    def logout(self):
        pass


def test_search_mais_novas_primeiro_e_limite(monkeypatch):
    _FakeIMAP.instances.clear()
    _FakeIMAP.fail_gm_raw = False
    monkeypatch.setattr("imaplib.IMAP4_SSL", _FakeIMAP)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    msgs = adapter.search("[ZARA-CHAT]", max_results=1)
    assert len(msgs) == 1
    assert msgs[0]["subject"] == "[ZARA-CHAT] CHAT-BBB segunda"  # uid 2 = mais nova
    assert "resposta dois em texto puro" in msgs[0]["body"]
    assert "<p>" not in msgs[0]["body"]  # prefere text/plain
    assert msgs[0]["date"] > 0


def test_search_texto_puro_simples(monkeypatch):
    _FakeIMAP.instances.clear()
    monkeypatch.setattr("imaplib.IMAP4_SSL", _FakeIMAP)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    msgs = adapter.search("[ZARA-CHAT]", max_results=10)
    assert len(msgs) == 2
    assert msgs[1]["body"] == "resposta um"


def test_search_fallback_subject(monkeypatch):
    _FakeIMAP.instances.clear()
    _FakeIMAP.fail_gm_raw = True
    monkeypatch.setattr("imaplib.IMAP4_SSL", _FakeIMAP)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    msgs = adapter.search("[ZARA-CHAT]")
    assert len(msgs) == 2
    crits = [s[1] for s in _FakeIMAP.instances[-1].searches]
    assert "X-GM-RAW" in crits and "SUBJECT" in crits
    _FakeIMAP.fail_gm_raw = False


def test_mark_read_best_effort(monkeypatch):
    _FakeIMAP.instances.clear()
    _FakeIMAP.fail_store = True
    monkeypatch.setattr("imaplib.IMAP4_SSL", _FakeIMAP)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    adapter.mark_read("2")  # não levanta mesmo falhando
    _FakeIMAP.fail_store = False


def test_search_vazia(monkeypatch):
    class _Vazia(_FakeIMAP):
        def uid(self, cmd, *args):
            if cmd == "SEARCH":
                return ("OK", [b""])
            return super().uid(cmd, *args)

    monkeypatch.setattr("imaplib.IMAP4_SSL", _Vazia)
    adapter = GmailImapSmtpAdapter("zoeeproject@gmail.com", "segredo")
    assert adapter.search("[ZARA-CEO]") == []


def test_parse_chat_reply_ignora_template_proprio():
    """O e-mail de SAÍDA contém o bloco template; não é resposta da zoe."""
    from core.lab_ceo_gmail_bridge import build_chat_email, parse_chat_reply
    payload = build_chat_email("oi, conselheira?")
    assert parse_chat_reply(payload["body"]) is None


def test_parse_chat_reply_valida():
    from core.lab_ceo_gmail_bridge import parse_chat_reply
    body = (
        "Claro!\n\n[ZARA-CHAT-REPLY]\n"
        "chat_id: CHAT-123-ABC\n"
        "reply: Tudo certo por aqui.\n"
        "[/ZARA-CHAT-REPLY]\n"
    )
    r = parse_chat_reply(body)
    assert r is not None
    assert r.chat_id == "CHAT-123-ABC"
    assert r.reply == "Tudo certo por aqui."
