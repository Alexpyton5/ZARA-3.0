"""ZARA Lab — Ponte CEO Remoto via Gmail (ZARA-CEO-RELAY-001)

Contrato entre o ZARA Lab local e a zoe (assistente Muse) atuando como CEO
remoto, com o Gmail como transporte.

Direção das mensagens:
  ZARA -> e-mail "[ZARA-CEO]" -> zoe lê, decide e responde no formato da ponte
  zoe -> resposta "[ZARA-CEO-DECISION]" -> ZARA importa a decisão para o Lab

Este módulo NÃO usa API paga, NÃO usa a Model API da Meta e NÃO finge que um
modelo local é a zoe. O transporte é o Gmail que a ZARA já conecta no painel
Comunicações, através de um adaptador injetável (ver CeoMailAdapter).

Fila local (padrão do mentor_relay):
%LOCALAPPDATA%/ZARA3/data/ceo-relay/
  outbox/   pedidos de decisão ainda não enviados
  sent/     pedidos enviados, aguardando resposta
  archive/  pedidos respondidos / mensagens inválidas
  chat/     conversa contínua da Conselheira (outbox/sent/archive/thread.jsonl)

Padrões decididos com o Alex (2026-09-26):
  - a ponte é checada a cada 5 minutos (CHAT_CHECK_INTERVAL_SECONDS)
  - o e-mail da ponte é zoeeproject@gmail.com (CEO_MAILBOX_DEFAULT),
    a caixa que a zoe verifica
  - a zoe tem AUTONOMIA TOTAL: decide tudo sem gate de confirmação;
    pedidos e decisões ficam registrados na fila local (auditável)
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

SUBJECT_TAG = "[ZARA-CEO]"
REQUEST_ID_PREFIX = "CEO-"
DECISION_OPEN = "[ZARA-CEO-DECISION]"
DECISION_CLOSE = "[/ZARA-CEO-DECISION]"

# Conselheira — conversa contínua (ZARA-CHAT-001).
# Padrões decididos com o Alex (2026-09-26):
CHAT_SUBJECT_TAG = "[ZARA-CHAT]"
CHAT_ID_PREFIX = "CHAT-"
CHAT_REPLY_OPEN = "[ZARA-CHAT-REPLY]"
CHAT_REPLY_CLOSE = "[/ZARA-CHAT-REPLY]"
CHAT_CHECK_INTERVAL_SECONDS = 5 * 60  # a ponte é checada a cada 5 minutos
CEO_MAILBOX_DEFAULT = "zoeeproject@gmail.com"  # caixa que a zoe verifica

VALID_DECISIONS = {"APPROVE", "REJECT", "DEFER", "ANSWER"}


class CeoMailAdapter(Protocol):
    """Contrato que o código de Comunicações da ZARA deve implementar.

    A implementação real usa a conexão Gmail do painel Comunicações.
    Para testes, usar LoggingStubAdapter.
    """

    def send(self, to: str, subject: str, body: str) -> str:
        """Envia o e-mail; retorna um id de mensagem."""
        ...

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Busca mensagens; cada item tem message_id, subject, body, date."""
        ...

    def mark_read(self, message_id: str) -> None:
        """Marca a mensagem como lida (best-effort)."""
        ...


class LoggingStubAdapter:
    """Adaptador em memória: registra envios e simula a caixa de entrada."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: list[dict[str, Any]] = []
        self.read: list[str] = []

    def send(self, to: str, subject: str, body: str) -> str:
        mid = f"stub-{len(self.sent) + 1}"
        self.sent.append({"message_id": mid, "to": to, "subject": subject, "body": body})
        return mid

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        return [m for m in self.inbox if query in m.get("subject", "")][:max_results]

    def mark_read(self, message_id: str) -> None:
        self.read.append(message_id)

    def inject_reply(self, subject: str, body: str) -> None:
        self.inbox.append({
            "message_id": f"stub-in-{len(self.inbox) + 1}",
            "subject": subject,
            "body": body,
            "date": time.time(),
        })


@dataclass
class CeoDecision:
    request_id: str
    decision: str  # APPROVE | REJECT | DEFER | ANSWER
    summary: str = ""
    rationale: str = ""
    decided_at: float = field(default_factory=time.time)
    matched: bool = True  # False quando não há pedido correspondente


def new_request_id() -> str:
    return f"{REQUEST_ID_PREFIX}{int(time.time())}-{uuid.uuid4().hex[:8].upper()}"


def build_request(kind: str, title: str, context: str, question: str,
                  options: list[str] | None = None,
                  request_id: str | None = None) -> dict[str, Any]:
    """Monta o pedido de decisão do CEO no formato da ponte."""
    rid = request_id or new_request_id()
    if not rid.startswith(REQUEST_ID_PREFIX):
        raise ValueError("request_id fora do padrão CEO-")
    title = (title or "").strip()[:80]
    if not title:
        raise ValueError("title obrigatório")
    opts = [o.strip() for o in (options or []) if o and o.strip()]
    lines = [
        f"{SUBJECT_TAG} Pedido de decisão do Lab",
        "",
        f"request_id: {rid}",
        f"kind: {(kind or 'decision').strip().lower()}",
        "",
        "## Contexto",
        (context or "").strip() or "(sem contexto)",
        "",
        "## Pergunta para a CEO",
        (question or "").strip() or "(sem pergunta)",
    ]
    if opts:
        lines += ["", "## Opções em consideração"]
        lines += [f"{i + 1}. {o}" for i, o in enumerate(opts)]
    lines += [
        "",
        "---",
        "Responda a este e-mail mantendo o assunto e incluindo o bloco:",
        DECISION_OPEN,
        f"request_id: {rid}",
        "decision: APPROVE | REJECT | DEFER | ANSWER",
        "summary: <uma frase>",
        "rationale: <motivo em 2-3 linhas>",
        DECISION_CLOSE,
    ]
    body = "\n".join(lines)
    return {
        "schema": 1,
        "request_id": rid,
        "kind": (kind or "decision").strip().lower(),
        "title": title,
        "subject": f"{SUBJECT_TAG} {rid} {title}",
        "body": body,
        "options": opts,
        "created_at": time.time(),
        "status": "PENDING",
    }


_DECISION_RE = re.compile(
    r"\[ZARA-CEO-DECISION\]\s*(.*?)\s*\[/ZARA-CEO-DECISION\]",
    re.IGNORECASE | re.DOTALL,
)


def _parse_block(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if key in {"request_id", "decision", "summary", "rationale"}:
            fields[key] = value.strip()
    return fields


def parse_reply(body: str) -> CeoDecision | None:
    """Extrai a decisão da resposta da CEO; None se o bloco for inválido."""
    match = _DECISION_RE.search(body or "")
    if not match:
        return None
    fields = _parse_block(match.group(1))
    rid = fields.get("request_id", "")
    decision = fields.get("decision", "").upper()
    if not rid.startswith(REQUEST_ID_PREFIX) or decision not in VALID_DECISIONS:
        return None
    return CeoDecision(
        request_id=rid,
        decision=decision,
        summary=fields.get("summary", ""),
        rationale=fields.get("rationale", ""),
    )


class CeoRelay:
    """Fila local + envio/busca via adaptador de e-mail."""

    def __init__(self, root: str | Path | None = None,
                 adapter: CeoMailAdapter | None = None,
                 mailbox: str = CEO_MAILBOX_DEFAULT) -> None:
        if root is None:
            local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            root = local / "ZARA3" / "data" / "ceo-relay"
        self.root = Path(root)
        self.outbox = self.root / "outbox"
        self.sent_dir = self.root / "sent"
        self.archive = self.root / "archive"
        for p in (self.outbox, self.sent_dir, self.archive):
            p.mkdir(parents=True, exist_ok=True)
        self.adapter: CeoMailAdapter = adapter or LoggingStubAdapter()
        self.mailbox = mailbox
        self.seen_path = self.root / "seen.json"
        self._seen: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        try:
            data = json.loads(self.seen_path.read_text(encoding="utf-8"))
            return {str(x) for x in data} if isinstance(data, list) else set()
        except Exception:
            return set()

    def _mark_seen(self, message_id: str) -> None:
        if not message_id or message_id in self._seen:
            return
        self._seen.add(message_id)
        try:
            self._atomic_json(self.seen_path, sorted(self._seen)[-5000:])
        except Exception:
            pass

    @staticmethod
    def _atomic_json(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # -- pedidos ---------------------------------------------------------
    def request_decision(self, kind: str, title: str, context: str, question: str,
                         options: list[str] | None = None) -> dict[str, Any]:
        payload = build_request(kind, title, context, question, options)
        self._atomic_json(self.outbox / f"{payload['request_id']}.json", payload)
        return payload

    def pending_count(self) -> int:
        return sum(1 for p in self.outbox.glob(f"{REQUEST_ID_PREFIX}*.json") if p.is_file())

    def awaiting_count(self) -> int:
        return sum(1 for p in self.sent_dir.glob(f"{REQUEST_ID_PREFIX}*.json") if p.is_file())

    def sync_outbox(self) -> list[str]:
        """Envia pedidos pendentes; retorna os request_ids enviados."""
        sent: list[str] = []
        for path in sorted(self.outbox.glob(f"{REQUEST_ID_PREFIX}*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rid = str(payload.get("request_id", ""))
                if not rid.startswith(REQUEST_ID_PREFIX):
                    raise ValueError("request_id inválido")
                self.adapter.send(self.mailbox, str(payload["subject"]), str(payload["body"]))
                payload["status"] = "SENT"
                payload["sent_at"] = time.time()
                self._atomic_json(self.sent_dir / path.name, payload)
                path.unlink()
                sent.append(rid)
            except Exception:
                bad = self.archive / f"{path.stem}.invalid-{int(time.time())}.json"
                try:
                    os.replace(path, bad)
                except Exception:
                    pass
        return sent

    # -- respostas --------------------------------------------------------
    def _load_sent(self, request_id: str) -> dict[str, Any] | None:
        path = self.sent_dir / f"{request_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def sync_inbox(self, limit: int = 20) -> list[CeoDecision]:
        """Busca respostas, valida o bloco de decisão e arquiva. Idempotente."""
        decisions: list[CeoDecision] = []
        try:
            messages = self.adapter.search(SUBJECT_TAG, max_results=limit)
        except Exception:
            return decisions
        for msg in messages:
            mid = str(msg.get("message_id", ""))
            if not mid or mid in self._seen:
                continue
            self._mark_seen(mid)
            body = str(msg.get("body", ""))
            parsed = parse_reply(body)
            if parsed is None:
                continue  # sem bloco válido: ignora sem arquivar pedido algum
            original = self._load_sent(parsed.request_id)
            if original is None:
                # Resposta sem pedido correspondente: registra como não-casada.
                parsed.matched = False
                decisions.append(parsed)
            else:
                archive_path = self.archive / f"{parsed.request_id}.decision.json"
                self._atomic_json(archive_path, {
                    "schema": 1,
                    "request": original,
                    "decision": asdict(parsed),
                    "imported_at": time.time(),
                })
                (self.sent_dir / f"{parsed.request_id}.json").unlink(missing_ok=True)
                decisions.append(parsed)
            try:
                self.adapter.mark_read(mid)
            except Exception:
                pass
        return decisions

    def snapshot(self) -> dict[str, Any]:
        return {
            "pending": self.pending_count(),
            "awaiting_reply": self.awaiting_count(),
            "transport": "gmail",
            "tag": SUBJECT_TAG,
        }


# ---------------------------------------------------------------------------
# Conselheira — conversa contínua com a zoe dentro da ZARA (ZARA-CHAT-001)
#
# É a visão "Jarvis" do Alex: um chat dentro do app onde a zoe atua como
# conselheira/CEO. Cada mensagem do Alex viaja por e-mail com um snapshot do
# estado da ZARA anexado; a zoe responde no formato da ponte e a ZARA importa
# a resposta para o painel.
#
# Como a zoe tem autonomia total (decisão do Alex), nada aqui exige
# confirmação: tudo é apenas registrado na fila local, de forma auditável.
# ---------------------------------------------------------------------------


def new_chat_id() -> str:
    return f"{CHAT_ID_PREFIX}{int(time.time())}-{uuid.uuid4().hex[:8].upper()}"


def build_context_snapshot(extra: str = "") -> str:
    """Monta o contexto da ZARA anexado a cada mensagem (só stdlib)."""
    import platform
    lines = [
        f"Data/hora: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Sistema: {platform.system()} {platform.release()}",
        "ZARA: app desktop v3.0 (Electron + Python)",
    ]
    extra = (extra or "").strip()
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def build_chat_email(text: str, context: str = "",
                     chat_id: str | None = None) -> dict[str, Any]:
    """Monta a mensagem de chat da Conselheira no formato da ponte."""
    cid = chat_id or new_chat_id()
    if not cid.startswith(CHAT_ID_PREFIX):
        raise ValueError("chat_id fora do padrão CHAT-")
    text = (text or "").strip()
    if not text:
        raise ValueError("text obrigatório")
    excerpt = text.replace("\n", " ")[:48]
    body = "\n".join([
        f"{CHAT_SUBJECT_TAG} Conversa com a Conselheira (zoe)",
        "",
        f"chat_id: {cid}",
        "",
        "## Contexto da ZARA",
        (context or "").strip() or "(sem contexto)",
        "",
        "## Mensagem do Alex",
        text,
        "",
        "---",
        "Responda a este e-mail mantendo o assunto e incluindo o bloco:",
        CHAT_REPLY_OPEN,
        f"chat_id: {cid}",
        "reply: <sua resposta para o Alex>",
        CHAT_REPLY_CLOSE,
    ])
    return {
        "schema": 1,
        "chat_id": cid,
        "role": "alex",
        "text": text,
        "context": (context or "").strip(),
        "subject": f"{CHAT_SUBJECT_TAG} {cid} {excerpt}",
        "body": body,
        "created_at": time.time(),
        "status": "PENDING",
    }


_CHAT_REPLY_RE = re.compile(
    r"\[ZARA-CHAT-REPLY\]\s*(.*?)\s*\[/ZARA-CHAT-REPLY\]",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class ChatReply:
    chat_id: str
    reply: str
    received_at: float = field(default_factory=time.time)
    matched: bool = True  # False quando não há mensagem correspondente


def parse_chat_reply(body: str) -> ChatReply | None:
    """Extrai a resposta da zoe; None se o bloco for inválido."""
    match = _CHAT_REPLY_RE.search(body or "")
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if key in {"chat_id", "reply"}:
            fields[key] = value.strip()
    cid = fields.get("chat_id", "")
    reply = fields.get("reply", "")
    if not cid.startswith(CHAT_ID_PREFIX) or not reply:
        return None
    return ChatReply(chat_id=cid, reply=reply)


def _load_seen_file(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in data} if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_seen_file(path: Path, seen: set[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(sorted(seen)[-5000:], ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


class ChatRelay:
    """Fila local do chat da Conselheira + envio/busca via adaptador de e-mail.

    Segue o mesmo padrão do CeoRelay: fila outbox/sent/archive, adaptador
    injetável (ver CeoMailAdapter) e idempotência via seen.json.
    """

    def __init__(self, root: str | Path | None = None,
                 adapter: CeoMailAdapter | None = None,
                 mailbox: str = CEO_MAILBOX_DEFAULT,
                 check_interval: int = CHAT_CHECK_INTERVAL_SECONDS) -> None:
        if root is None:
            local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            root = local / "ZARA3" / "data" / "ceo-relay"
        self.root = Path(root)
        self.chat_dir = self.root / "chat"
        self.outbox = self.chat_dir / "outbox"
        self.sent_dir = self.chat_dir / "sent"
        self.archive = self.chat_dir / "archive"
        for p in (self.outbox, self.sent_dir, self.archive):
            p.mkdir(parents=True, exist_ok=True)
        self.thread_path = self.chat_dir / "thread.jsonl"
        self.last_sync_path = self.chat_dir / "last_sync.json"
        self.adapter: CeoMailAdapter = adapter or LoggingStubAdapter()
        self.mailbox = mailbox
        self.check_interval = check_interval
        self.seen_path = self.root / "seen.json"
        self._seen: set[str] = _load_seen_file(self.seen_path)

    def _mark_seen(self, message_id: str) -> None:
        if not message_id or message_id in self._seen:
            return
        self._seen.add(message_id)
        try:
            _save_seen_file(self.seen_path, self._seen)
        except Exception:
            pass

    @staticmethod
    def _atomic_json(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _append_thread(self, chat_id: str, role: str, text: str,
                       created_at: float | None = None) -> None:
        entry = {
            "chat_id": chat_id,
            "role": role,
            "text": text,
            "created_at": created_at if created_at is not None else time.time(),
        }
        with self.thread_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- envio -----------------------------------------------------------
    def send_message(self, text: str, context: str = "") -> dict[str, Any]:
        """Registra a mensagem do Alex na outbox e no histórico do painel."""
        payload = build_chat_email(text, context)
        self._atomic_json(self.outbox / f"{payload['chat_id']}.json", payload)
        self._append_thread(payload["chat_id"], "alex", payload["text"],
                            payload["created_at"])
        return payload

    def pending_count(self) -> int:
        return sum(1 for p in self.outbox.glob(f"{CHAT_ID_PREFIX}*.json") if p.is_file())

    def awaiting_count(self) -> int:
        return sum(1 for p in self.sent_dir.glob(f"{CHAT_ID_PREFIX}*.json") if p.is_file())

    def sync_outbox(self) -> list[str]:
        """Envia mensagens pendentes; retorna os chat_ids enviados."""
        sent: list[str] = []
        for path in sorted(self.outbox.glob(f"{CHAT_ID_PREFIX}*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                cid = str(payload.get("chat_id", ""))
                if not cid.startswith(CHAT_ID_PREFIX):
                    raise ValueError("chat_id inválido")
                self.adapter.send(self.mailbox, str(payload["subject"]), str(payload["body"]))
                payload["status"] = "SENT"
                payload["sent_at"] = time.time()
                self._atomic_json(self.sent_dir / path.name, payload)
                path.unlink()
                sent.append(cid)
            except Exception:
                bad = self.archive / f"{path.stem}.invalid-{int(time.time())}.json"
                try:
                    os.replace(path, bad)
                except Exception:
                    pass
        return sent

    # -- respostas --------------------------------------------------------
    def _load_sent(self, chat_id: str) -> dict[str, Any] | None:
        path = self.sent_dir / f"{chat_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def sync_inbox(self, limit: int = 20) -> list[ChatReply]:
        """Busca respostas da zoe, valida o bloco e arquiva. Idempotente."""
        replies: list[ChatReply] = []
        try:
            messages = self.adapter.search(CHAT_SUBJECT_TAG, max_results=limit)
        except Exception:
            return replies
        for msg in messages:
            mid = str(msg.get("message_id", ""))
            if not mid or mid in self._seen:
                continue
            self._mark_seen(mid)
            parsed = parse_chat_reply(str(msg.get("body", "")))
            if parsed is None:
                continue  # sem bloco válido: ignora
            original = self._load_sent(parsed.chat_id)
            if original is None:
                parsed.matched = False
            else:
                self._atomic_json(self.archive / f"{parsed.chat_id}.reply.json", {
                    "schema": 1,
                    "message": original,
                    "reply": asdict(parsed),
                    "imported_at": time.time(),
                })
                (self.sent_dir / f"{parsed.chat_id}.json").unlink(missing_ok=True)
            self._append_thread(parsed.chat_id, "zoe", parsed.reply, parsed.received_at)
            replies.append(parsed)
            try:
                self.adapter.mark_read(mid)
            except Exception:
                pass
        return replies

    def sync(self) -> dict[str, Any]:
        """Uma passada completa: envia pendentes e importa respostas."""
        sent = self.sync_outbox()
        replies = self.sync_inbox()
        stamp = {"last_sync_at": time.time(), "sent": len(sent),
                 "replies": len(replies)}
        self._atomic_json(self.last_sync_path, stamp)
        return {
            "sent": sent,
            "replies": [asdict(r) for r in replies],
            "last_sync_at": stamp["last_sync_at"],
        }

    # -- leitura ----------------------------------------------------------
    def get_thread(self, limit: int = 200) -> list[dict[str, Any]]:
        """Histórico da conversa para o painel (mais antigas primeiro)."""
        entries: list[dict[str, Any]] = []
        try:
            with self.thread_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
        except FileNotFoundError:
            pass
        return entries[-limit:] if limit else entries

    def last_sync_at(self) -> float | None:
        try:
            data = json.loads(self.last_sync_path.read_text(encoding="utf-8"))
            ts = float(data.get("last_sync_at") or 0)
            return ts if ts > 0 else None
        except Exception:
            return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "pending": self.pending_count(),
            "awaiting_reply": self.awaiting_count(),
            "mailbox": self.mailbox,
            "transport": "gmail",
            "tag": CHAT_SUBJECT_TAG,
            "check_interval_seconds": self.check_interval,
            "last_sync_at": self.last_sync_at(),
        }
