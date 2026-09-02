"""ZARA-SMART-CLIPBOARD-001 (Alex, 2026-08-28). Peça isolada.

`os_clipboard`/`os_clipboard_read` (core/actions/os_ops.py) já leem/escrevem
a área de transferência crua -- este módulo é a camada de cima que
RECONHECE estrutura em texto colado bagunçado (CPF, e-mail, telefone, JSON,
tabela) e devolve campos separados. `parse_clipboard_text` é pura (testável
sem tocar a área de transferência de verdade); `read_and_parse_clipboard`
só existe pra uso real, via `pyperclip` (já dependência do projeto).
"""
from __future__ import annotations

import json
import re

_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b")
_CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")


def parse_clipboard_text(text: str) -> dict:
    """Extrai estruturas conhecidas de um texto colado. Nunca inventa campo
    que não achou -- listas vazias em vez de chute. Se o texto for JSON
    válido, devolve ele já parseado em 'json'."""
    raw = str(text or "")

    result: dict = {
        "emails": sorted(set(_EMAIL_RE.findall(raw))),
        "cpfs": sorted(set(_CPF_RE.findall(raw))),
        "phones": sorted(set(_PHONE_RE.findall(raw))),
        "ceps": sorted(set(_CEP_RE.findall(raw))),
        "json": None,
        "is_table": False,
    }

    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        try:
            result["json"] = json.loads(stripped)
        except (ValueError, TypeError):
            pass

    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) >= 2:
        delimiter_counts = [line.count("\t") or line.count(",") for line in lines]
        result["is_table"] = len(set(delimiter_counts)) == 1 and delimiter_counts[0] > 0

    return result


def read_and_parse_clipboard() -> dict:
    """Lê a área de transferência REAL e aplica parse_clipboard_text.
    Best-effort: pyperclip ausente/indisponível devolve estrutura vazia em
    vez de levantar -- ler clipboard não pode derrubar quem chamou."""
    try:
        import pyperclip
        content = str(pyperclip.paste() or "")
    except Exception:
        content = ""
    return parse_clipboard_text(content)
