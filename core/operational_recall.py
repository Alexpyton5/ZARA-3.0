"""Deterministic, bounded recall for ZARA's local operational memories."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from core.paths import user_data_dir


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(char for char in value if not unicodedata.combining(char)).strip(" .?!")


def _read_text(path: Path, max_chars: int = 80_000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except (OSError, UnicodeError):
        return ""


def _catalog_rows() -> list[tuple[str, str]]:
    path = (
        user_data_dir()
        / "data" / "project-memory" / "caderninho"
        / "ZARA_VOICE_CAPABILITY_CATALOG.md"
    )
    rows: list[tuple[str, str]] = []
    for line in _read_text(path).splitlines():
        if not line.startswith("|") or "---" in line or "Capacidade" in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[1]:
            rows.append((cells[0], cells[1]))
    return rows


def _current_work_reply() -> str:
    rows = _catalog_rows()
    proven = [name for name, status in rows if "RUNTIME" in status][:6]
    if not proven:
        return "O Catálogo Vivo ainda não tem estado operacional suficiente para responder."
    return (
        "Estamos consolidando capacidades reais de voz e texto da ZARA. "
        "Já estão comprovadas em runtime: " + ", ".join(proven) + "."
    )


def _pending_reply() -> str:
    rows = _catalog_rows()
    pending_tokens = ("NOT_PROVEN", "NOT_SUPPORTED", "BLOCKED", "TEST_PASS", "AWAITING")
    pending = [(name, status) for name, status in rows if any(token in status for token in pending_tokens)]
    if not pending:
        return "O Catálogo Vivo não registra pendências atuais."
    summary = "; ".join(f"{name}: {status}" for name, status in pending[:8])
    return f"Pendências registradas no Catálogo Vivo: {summary}."


def _ideas_reply() -> str:
    path = user_data_dir() / "data" / "project-memory" / "caderninho_de_ideias.md"
    headings = []
    for line in _read_text(path).splitlines():
        match = re.match(r"^###\s+\d+\.\s+(.+)$", line.strip())
        if match:
            headings.append(match.group(1).strip())
    if not headings:
        return "O Caderninho não tem ideias legíveis neste momento."
    return "Ideias registradas no Caderninho: " + "; ".join(headings[:8]) + "."


def recall_operational_memory(text: str, *, project_memory=None, user_memory=None) -> str | None:
    """Return a local-source answer for a small closed set of recall questions."""
    query = _normalized(text)
    if query in {
        "o que estavamos fazendo", "onde paramos", "em que estavamos trabalhando",
        "qual era a tarefa atual",
    }:
        return _current_work_reply()
    if query in {
        "o que ficou pendente", "quais sao as pendencias", "o que falta fazer",
        "quais pendencias temos",
    }:
        return _pending_reply()
    if query in {
        "quais ideias estao no caderninho", "o que tem no caderninho",
        "leia o caderninho", "mostre as ideias",
    }:
        return _ideas_reply()
    if query in {
        "o que voce lembra sobre mim", "o que sabe sobre mim",
        "quais sao minhas preferencias", "quais minhas preferencias",
    }:
        if user_memory is None:
            return "A User Memory está indisponível neste momento."
        facts = [item for item in user_memory.list() if item.get("status") != "forgotten"][:6]
        if not facts:
            return "Ainda não tenho fatos ativos na User Memory sobre você."
        return "Na User Memory local: " + "; ".join(str(item.get("fact", "")) for item in facts) + "."
    if query in {"o que existe na project memory", "liste a project memory", "memoria do projeto"}:
        if project_memory is None:
            return "A Project Memory está indisponível neste momento."
        keys = project_memory.list_docs()
        return "Documentos da Project Memory: " + (", ".join(keys) if keys else "nenhum") + "."
    return None
