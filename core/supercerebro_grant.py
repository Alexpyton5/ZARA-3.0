"""Autorizacao remota do Supercerebro via WhatsApp (ZARA-WHATSAPP-GRANT-001).

REGRA DURA - ler antes de mexer neste arquivo:
- A trava do Supercerebro continua FAIL-CLOSED. Este modulo NAO remove a trava,
  NAO cria bypass e NAO liga nada sozinho.
- O arquivo whatsapp_grant.json so pode ser escrito pela ZOE, e SOMENTE depois
  de autorizacao EXPLICITA do Alex no chat (ex.: "pode mexer por 30 minutos").
- O grant NUNCA e criado automaticamente: sem resposta dele, nada acontece.
- A checagem e por comparacao de timestamp (expires_at > agora) feita NA HORA
  de cada tentativa de acao PC_CONTROL. Nao ha thread nem agendamento em
  background: se o processo morrer, o grant simplesmente expira sozinho.
- Arquivo ausente, expirado ou malformado = NEGAR. Sempre.

Fluxo aprovado pelo Alex (2026-09-28):
  1) a zoe PEDE no WhatsApp ("preciso mexer no PC por ~30 min para [tarefa] - pode?");
  2) SOMENTE apos o "pode/sim" explicito dele no chat, a zoe escreve o grant pela ponte;
  3) sem resposta = nada acontece (fail-closed).

NUNCA reimplementar aqui: work_mode_active / work_mode_sentinel /
_watch_supercerebro_work_mode (quarentena - ver ~/AGENTS.md).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

GRANT_DIR_NAME = "supercerebro"
GRANT_FILE_NAME = "whatsapp_grant.json"
GRANT_VIA_EXPECTED = "whatsapp"
GRANT_SCOPE_EXPECTED = "use-computer"
# Teto de uma janela de autorizacao: grant com prazo maior que isso e recusado
# na escrita. A ideia e sempre "janela curta", nunca "liberacao permanente".
MAX_GRANT_MINUTES = 720  # 12h

_ENV_GRANT_PATH = "ZARA_WHATSAPP_GRANT_PATH"


def grant_file_path() -> Path:
    """Onde o grant mora. Override por env existe so para testes."""
    override = os.environ.get(_ENV_GRANT_PATH)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / GRANT_DIR_NAME / GRANT_FILE_NAME


def _parse_expiry(value: object) -> float | None:
    """Aceita epoch (numero ou string) ou ISO-8601. Qualquer outra coisa = None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            pass
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        if moment.tzinfo is None:
            # Sem timezone = assume UTC (documentado). Na duvida, negar e
            # pedir um grant novo e mais seguro do que adivinhar errado.
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    return None


def check_whatsapp_grant(
    now: float | None = None,
    path: Path | None = None,
) -> tuple[bool, str, dict]:
    """Diz se ha um grant via WhatsApp valido AGORA.

    Retorna (permitido, motivo, info). Fail-closed: qualquer problema no
    arquivo (ausente, ilegivel, malformado, expirado, via/scope errados)
    devolve (False, motivo, info).
    """
    grant_path = path or grant_file_path()
    info: dict = {}
    try:
        raw = grant_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "no-grant-file", info
    except OSError:
        return False, "grant-unreadable", info
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return False, "grant-malformed", info
    if not isinstance(data, dict):
        return False, "grant-malformed", info
    info = {
        key: data.get(key)
        for key in ("granted_at", "expires_at", "granted_via", "scope", "note")
    }
    if data.get("granted_via") != GRANT_VIA_EXPECTED:
        return False, "grant-via-mismatch", info
    if data.get("scope") != GRANT_SCOPE_EXPECTED:
        return False, "grant-scope-mismatch", info
    expires = _parse_expiry(data.get("expires_at"))
    if expires is None:
        return False, "grant-malformed-expiry", info
    granted_at = _parse_expiry(data.get("granted_at"))
    if granted_at is not None and granted_at > expires:
        return False, "grant-malformed-window", info
    moment = time.time() if now is None else float(now)
    if expires <= moment:
        return False, "grant-expired", info
    return True, "ok", info


def _audit_grant_event(outcome: str, detail: str) -> None:
    try:
        from core.audit_log import audit_log

        audit_log().record(
            action="supercerebro_grant",
            risk="HIGH",
            outcome=outcome,
            error=detail[:200],
        )
    except Exception:
        pass  # auditoria nunca quebra o caminho da trava


def write_grant(
    minutes: float = 30,
    note: str = "",
    scope: str = GRANT_SCOPE_EXPECTED,
    path: Path | None = None,
) -> Path:
    """Escreve um grant via WhatsApp valido por `minutes`.

    USO RESTRITO: chamar somente apos autorizacao EXPLICITA do Alex no chat.
    Nunca chamar automaticamente, nunca em loop, nunca por outro agente.
    """
    mins = float(minutes)
    if not 0 < mins <= MAX_GRANT_MINUTES:
        raise ValueError(f"minutes deve estar entre 0 e {MAX_GRANT_MINUTES}")
    if scope != GRANT_SCOPE_EXPECTED:
        raise ValueError(f"scope desconhecido: {scope!r}")
    start = datetime.now(timezone.utc)
    payload = {
        "granted_at": start.isoformat(),
        "expires_at": (start + timedelta(minutes=mins)).isoformat(),
        "granted_via": GRANT_VIA_EXPECTED,
        "scope": scope,
        "note": str(note or "")[:280],
    }
    grant_path = path or grant_file_path()
    grant_path.parent.mkdir(parents=True, exist_ok=True)
    grant_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _audit_grant_event("granted", f"expires_at={payload['expires_at']}")
    return grant_path


def revoke_grant(path: Path | None = None) -> bool:
    """Apaga o grant (encerra a janela de autorizacao mais cedo)."""
    grant_path = path or grant_file_path()
    try:
        grant_path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    _audit_grant_event("revoked", "grant removido pela zoe")
    return True
