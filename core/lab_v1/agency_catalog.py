"""Bundled Agency Agents persona catalog for ZARA Lab.

The Markdown in this catalog is third-party task data. It does not grant tools,
permissions, system authority, or approval to perform an action. Callers may
offer it to a selected worker model as persona context within the worker's
existing permissions and task boundaries.
"""

from __future__ import annotations

import base64
import json
import re
import unicodedata
import zlib
from functools import lru_cache
from typing import Any

from .agency_data.catalog_payload import (
    AGENT_COUNT,
    DIVISIONS,
    LICENSE_TEXT,
    PAYLOAD,
    SOURCE_COMMIT,
    SOURCE_URL,
)

_SUMMARY_KEYS = (
    "id",
    "name",
    "description",
    "division",
    "emoji",
    "vibe",
    "source_path",
    "source_url",
    "source_sha256",
)

_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "de", "do", "da", "dos", "das",
    "e", "em", "for", "from", "i", "in", "me", "my", "o", "os", "of",
    "no", "na", "nos", "nas", "on", "or", "our", "para", "por", "que", "the", "to", "um", "uma",
    "we", "with", "you", "your", "com", "criar", "fazer", "create", "make",
    "build", "help", "ajuda", "ajudar", "preciso", "quero", "please",
}

# Small vocabulary bridge for the Portuguese requests ZARA normally receives.
_PT_ALIASES = {
    "acessibilidade": "accessibility",
    "analise": "analysis",
    "analisar": "analysis",
    "anuncio": "ads",
    "anuncios": "ads",
    "aplicativo": "app",
    "arquitetura": "architecture",
    "atendimento": "support",
    "auditoria": "audit",
    "banco": "database",
    "bugs": "debugging",
    "campanha": "campaign",
    "cliente": "customer",
    "clientes": "customers",
    "codigo": "code",
    "conteudo": "content",
    "dados": "data",
    "desempenho": "performance",
    "desenvolvedor": "developer",
    "desenvolvimento": "development",
    "design": "design",
    "diagnosticar": "debugging",
    "engenharia": "engineering",
    "escrita": "writing",
    "financas": "finance",
    "financeiro": "finance",
    "interface": "frontend",
    "jogo": "game",
    "jogos": "games",
    "marketing": "marketing",
    "mercado": "market",
    "melhorar": "improvement",
    "lancamento": "launch",
    "pagina": "page",
    "pesquisa": "research",
    "pesquisar": "research",
    "planejamento": "planning",
    "produto": "product",
    "programacao": "programming",
    "revisao": "review",
    "saude": "healthcare",
    "seguranca": "security",
    "site": "website",
    "tela": "frontend",
    "suporte": "support",
    "teste": "testing",
    "testes": "testing",
    "validacao": "validation",
    "vendas": "sales",
    "voz": "voice",
}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _tokens(value: str) -> tuple[str, ...]:
    words = re.findall(r"[\w]+", _normalize(value), flags=re.UNICODE)
    return tuple(
        _PT_ALIASES.get(word, _PT_ALIASES.get(word[:-1], word) if word.endswith("s") else word)
        for word in words
        if len(word) > 1 and word not in _STOPWORDS
    )


def _field_tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w]+", _normalize(value), flags=re.UNICODE))


def _contains(tokens: set[str], token: str) -> bool:
    if token in tokens:
        return True
    if len(token) < 5:
        return False
    return any(
        len(word) >= 5 and (word.startswith(token) or token.startswith(word))
        for word in tokens
    )


@lru_cache(maxsize=1)
def _records() -> tuple[dict[str, Any], ...]:
    raw = zlib.decompress(base64.b85decode(PAYLOAD.encode("ascii")))
    records = json.loads(raw)
    if len(records) != AGENT_COUNT:
        raise ValueError("Agency Agents catalog count does not match its manifest")
    return tuple(records)


@lru_cache(maxsize=1)
def _by_id() -> dict[str, dict[str, Any]]:
    return {row["id"].casefold(): row for row in _records()}


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in _SUMMARY_KEYS}


def _score(row: dict[str, Any], tokens: tuple[str, ...], phrase: str) -> int:
    if not tokens:
        return 0
    name = _normalize(row["name"])
    identifier = _normalize(row["id"])
    name_words = _field_tokens(row["name"])
    id_words = _field_tokens(row["id"])
    description_words = _field_tokens(row["description"])
    vibe_words = _field_tokens(row["vibe"])
    division_words = _field_tokens(row["division"])
    score = 0
    if phrase and phrase in (name, identifier, identifier.rsplit("/", 1)[-1]):
        score += 1000
    for token in set(tokens):
        if _contains(name_words, token):
            score += 20
        if _contains(id_words, token):
            score += 10
        if _contains(division_words, token):
            score += 32
        if _contains(description_words, token):
            score += 4
        if _contains(vibe_words, token):
            score += 2
    return score


def _ranked(
    query: str,
    division: str | None = None,
    role: str | None = None,
) -> list[dict[str, Any]]:
    objective_tokens = _tokens(query)
    role_tokens = _tokens(role or "")
    objective_phrase = _normalize(query.strip())
    role_phrase = _normalize((role or "").strip())
    division_key = _normalize(division.strip()) if division else None
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in _records():
        if division_key and division_key not in {
            _normalize(row["division"]),
            _normalize(DIVISIONS[row["division"]]),
        }:
            continue
        score = _score(row, objective_tokens, objective_phrase)
        if role_tokens:
            score += _score(row, role_tokens, role_phrase) * 3
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1]["name"].casefold(), item[1]["id"]))
    return [row for _, row in scored]


def list_templates(
    query: str | None = None,
    division: str | None = None,
    limit: int | None = 50,
) -> list[dict[str, Any]]:
    """Return serializable agent summaries; Markdown instructions stay out of lists.

    With no query, rows are ordered by division, then name. Pass ``limit=None``
    to retrieve the entire catalog.
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative or None")
    if query and _tokens(query):
        rows = _ranked(query, division)
    else:
        division_key = _normalize(division.strip()) if division else None
        rows = [
            row for row in _records()
            if not division_key or division_key in {
                _normalize(row["division"]),
                _normalize(DIVISIONS[row["division"]]),
            }
        ]
    if limit is not None:
        rows = rows[:limit]
    return [_summary(row) for row in rows]


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return one template with its complete upstream Markdown instructions."""
    if not isinstance(template_id, str) or not template_id.strip():
        return None
    row = _by_id().get(template_id.strip().casefold())
    return dict(row) if row else None


def select_template(objective: str, role: str | None = None) -> dict[str, Any] | None:
    """Choose one relevant persona deterministically for a task and optional role.

    An exact role ID or name wins. Otherwise metadata matching chooses the
    highest score; an unrelated or empty request returns ``None``.
    """
    if role:
        by_id = get_template(role)
        if by_id:
            return by_id
        role_key = _normalize(role.strip())
        for row in _records():
            if _normalize(row["name"]) == role_key:
                return dict(row)
    rows = _ranked(objective or "", role=role)
    return dict(rows[0]) if rows else None


def catalog_info() -> dict[str, Any]:
    """Return license and source attribution available in the packaged app."""
    return {
        "count": AGENT_COUNT,
        "divisions": dict(DIVISIONS),
        "source_url": SOURCE_URL,
        "source_commit": SOURCE_COMMIT,
        "license": "MIT",
        "license_text": LICENSE_TEXT,
    }
