"""ZARA — Adaptador Gmail REAL da ponte da Conselheira (ZARA-CHAT-001).

Liga o CeoMailAdapter ao Gmail de verdade: IMAP para ler a caixa da
zoe (zoeeproject@gmail.com) e SMTP para enviar. Só usa a biblioteca
padrão do Python — sem API paga, sem dependência nova, sem chave de
terceiro.

Credencial (senha de app do Gmail — passo manual do Alex, uma única vez):
  %LOCALAPPDATA%\\ZARA3\\config\\ceo_gmail.json
  {"email": "zoeeproject@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"}

Fail-closed: sem esse arquivo (ou com ele inválido), build_gmail_adapter()
levanta GmailNotConfiguredError e NADA finge que foi enviado/recebido.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import imaplib
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
DEFAULT_TIMEOUT = 30


class GmailNotConfiguredError(Exception):
    """Sem credencial do Gmail real: a ponte NÃO opera (fail-closed)."""


def default_config_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return local / "ZARA3" / "config" / "ceo_gmail.json"


def load_gmail_config(path: str | Path | None = None) -> tuple[str, str]:
    """Lê (email, app_password) do arquivo de config; levanta se ausente."""
    cfg_path = Path(path) if path else default_config_path()
    hint = (
        "Crie %s com "
        '{"email": "zoeeproject@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"} '
        "(senha de app gerada na Conta Google da zoe)."
    ) % cfg_path
    try:
        raw = cfg_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GmailNotConfiguredError(f"Gmail real não configurado. {hint}")
    except OSError as e:
        raise GmailNotConfiguredError(f"Gmail real não configurado ({e}). {hint}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise GmailNotConfiguredError(f"Arquivo de config inválido (JSON quebrado): {cfg_path}")
    if not isinstance(data, dict):
        raise GmailNotConfiguredError(f"Arquivo de config inválido (precisa ser objeto JSON): {cfg_path}")
    address = str(data.get("email") or "").strip()
    secret = str(data.get("app_password") or "").strip().replace(" ", "")
    if not address or "@" not in address or not secret:
        raise GmailNotConfiguredError(
            f"Arquivo de config incompleto (falta email/app_password): {cfg_path}"
        )
    return address, secret


def _extract_text(msg: email.message.Message) -> str:
    """Extrai o melhor texto legível da mensagem (prefere text/plain)."""
    if msg.is_multipart():
        plain: list[str] = []
        fallback: list[str] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                plain.append(text)
            elif ctype == "text/html":
                fallback.append(text)
        texts = plain or fallback
        return "\n".join(t.strip() for t in texts if t.strip())
    payload = msg.get_payload(decode=True)
    if payload is None:
        raw = msg.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _parse_date(msg: email.message.Message) -> float:
    try:
        dt = email.utils.parsedate_to_datetime(str(msg.get("Date") or ""))
        if dt is not None:
            return dt.timestamp()
    except Exception:
        pass
    return 0.0


class GmailImapSmtpAdapter:
    """CeoMailAdapter de verdade: Gmail via IMAP (ler) + SMTP (enviar).

    Cada operação abre e fecha a própria conexão (a ponte checa a cada
    5 min): simples, sem conexão pendurada. Erro de rede/autenticação
    levanta exceção — nunca retorna sucesso falso (fail-closed).
    """

    is_real = True

    def __init__(self, email_address: str, app_password: str,
                 imap_host: str = IMAP_HOST, imap_port: int = IMAP_PORT,
                 smtp_host: str = SMTP_HOST, smtp_port: int = SMTP_PORT,
                 timeout: int = DEFAULT_TIMEOUT) -> None:
        if not email_address or "@" not in email_address:
            raise ValueError("email_address inválido")
        if not app_password:
            raise ValueError("app_password obrigatório")
        self.email_address = email_address
        self.app_password = app_password
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.timeout = timeout

    # -- SMTP (envio) ----------------------------------------------------
    def send(self, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["From"] = self.email_address
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=self.email_address.split("@")[-1])
        msg.set_content(body or "")
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as smtp:
            smtp.starttls()
            smtp.login(self.email_address, self.app_password)
            smtp.send_message(msg)
        return str(msg["Message-ID"])

    # -- IMAP (leitura) --------------------------------------------------
    def _imap(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=self.timeout)
        imap.login(self.email_address, self.app_password)
        typ, _ = imap.select("INBOX")
        if typ != "OK":
            try:
                imap.logout()
            except Exception:
                pass
            raise ConnectionError("IMAP: não foi possível abrir a INBOX")
        return imap

    def _search_uids(self, imap: imaplib.IMAP4_SSL, query: str) -> list[bytes]:
        # X-GM-RAW entende a sintaxe de busca do Gmail; cai para SUBJECT
        # padrão se o servidor não suportar.
        clean = query.strip().strip("[]")
        for criteria in (
            ("X-GM-RAW", f'subject:"{clean}"'),
            ("SUBJECT", query),
        ):
            try:
                typ, data = imap.uid("SEARCH", None, *criteria)
            except imaplib.IMAP4.error:
                continue
            if typ == "OK" and data:
                return data[0].split()
        return []

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        imap = self._imap()
        try:
            uids = self._search_uids(imap, query)
            # UID crescente = mais antiga primeiro; inverte: mais novas primeiro.
            uids = uids[::-1][:max_results]
            out: list[dict[str, Any]] = []
            for uid in uids:
                typ, data = imap.uid("FETCH", uid, "(RFC822)")
                if typ != "OK" or not data:
                    continue
                raw = data[0][1] if isinstance(data[0], tuple) else None
                if not raw:
                    continue
                parsed = email.message_from_bytes(raw, policy=email.policy.default)
                out.append({
                    "message_id": uid.decode("ascii", errors="replace"),
                    "subject": str(parsed.get("Subject") or ""),
                    "body": _extract_text(parsed),
                    "date": _parse_date(parsed),
                })
            return out
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def mark_read(self, message_id: str) -> None:
        """Marca como lida; best-effort (nunca levanta)."""
        try:
            imap = self._imap()
            try:
                imap.uid("STORE", message_id, "+FLAGS", r"\Seen")
            finally:
                try:
                    imap.logout()
                except Exception:
                    pass
        except Exception:
            pass


def build_gmail_adapter(config_path: str | Path | None = None) -> GmailImapSmtpAdapter:
    """Constrói o adaptador real; levanta GmailNotConfiguredError sem credencial."""
    address, secret = load_gmail_config(config_path)
    return GmailImapSmtpAdapter(address, secret)
