"""
ZARA User Memory Context Integration (ZARA-USER-MEMORY-CONTEXT-001).

Fluxo (spec do Mentor):
  mensagem de Alex
    -> analisar assunto
    -> buscar SOMENTE memorias relevantes
    -> top-K pequeno (3-5)
    -> adicionar contexto ao modelo
    -> resposta
    -> mark_used somente nas memorias utilizadas

Regras:
  - nunca jogar todas as memorias no prompt
  - distinguir fato confirmado != inferencia != acontecimento antigo
  - memoria irrelevante NAO entra (teste: "qual pasta abrir?" nao injeta cafe)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.user_memory import UserMemoryCore

TOP_K_DEFAULT = 4
MAX_CONTEXT_CHARS = 900


def build_memory_context(user_memory: UserMemoryCore, query: str, top_k: int = TOP_K_DEFAULT) -> str:
    """Return a compact prompt fragment with ONLY relevant memories.

    Relevance = lexic match (fact tokens) + confidence boost + recency,
    never the whole store. Format distinguishes confidence level.
    """
    if not user_memory or not (query or "").strip():
        return ""
    hits = user_memory.search(query, limit=max(1, min(top_k, 5)))
    if not hits:
        return ""
    lines = ["[MEMÓRIAS RELEVANTES DO USUÁRIO — use somente se verdadeiras e pertinentes]"]
    for h in hits:
        conf_label = (
            "CONFIRMED" if h["confidence"] >= 0.9
            else "INFERENCE" if h["confidence"] < 0.7
            else "FACT"
        )
        date = __import__("time").strftime("%Y-%m-%d", __import__("time").localtime(h["created_at"]))
        lines.append(f"[{h['category'].upper()} | {conf_label} | {date}] {h['fact']}")
        user_memory.mark_used(h["id"])
    return "\n".join(lines)[:MAX_CONTEXT_CHARS]


def is_relevant(user_memory: UserMemoryCore, query: str, threshold_tokens: int = 1) -> bool:
    """Cheap relevance gate used before building context."""
    hits = user_memory.search(query, limit=2)
    return bool(hits)
