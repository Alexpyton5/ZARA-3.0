"""Memória compartilhada dentro da conversa do Lab — FASE 2 PEÇA 3.

O bot, ao responder menções no grupo (`group_chat.answer_inbox`), enxerga
o que a ZARA sabe: este helper monta um bloco de texto curto com os fatos
da visão unificada (peças 1-4 da memória compartilhada) e o group_chat o
cola no prompt do motor. É a mecânica de "o que a ZARA souber, os bots
sabem" funcionando de verdade.

Regras duras:
- fail-closed: memória vazia = string vazia (o prompt segue igual);
  memória quebrada (spec inválida, fonte sem leitor, leitor que explodiu)
  = string vazia, nunca inventa fato, nunca quebra o turno do bot;
- só leitura: o bloco é contexto pro prompt, nada aqui escreve em fonte
  nenhuma;
- teto de caracteres: o bloco nunca estoura o orçamento do prompt
  (marcador de corte no fim quando truncar).

Lógica pura, stdlib, zero custo/rede/quota.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

try:  # dentro do app (pacote core.*)
    from core.shared_memory_api import SharedMemoryAPI
except ImportError:  # teste flat
    from shared_memory_api import SharedMemoryAPI  # type: ignore[no-redef]

_HEADER = (
    "MEMÓRIA COMPARTILHADA DO LAB (só leitura — você não escreve nela; "
    "use como contexto e não afirme nada além do que está escrito aqui):"
)
_TRUNC_MARK = "\n…(contexto cortado pelo teto)"
_DEFAULT_MAX_CHARS = 4000


def _entry_line(entry: Mapping[str, Any]) -> str:
    source = str(entry.get("source", "?"))
    key = str(entry.get("key", "?"))
    value = str(entry.get("value", "")).replace("\n", " ").strip()
    parts = []
    author = entry.get("author")
    when = entry.get("written_at")
    if author:
        parts.append(str(author))
    if when:
        parts.append(str(when))
    prov = " (" + ", ".join(parts) + ")" if parts else ""
    return f"[{source}] {key}: {value}{prov}"


def build_shared_context(
    *,
    lab_memory: Any | None = None,
    zara_turns: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
    bot_id: str = "lab-bot",
    sources: Iterable[str] = ("lab",),
    max_entries: int = 40,
    max_chars: int = _DEFAULT_MAX_CHARS,
    include_provenance: bool = True,
) -> str:
    """Monta o bloco de contexto da memória compartilhada.

    lab_memory: instância real de LabMemory (ou None).
    zara_turns: callable que devolve os turnos do fio unificado (ou None).
    Sem fonte ligada -> "" (o turno segue sem contexto, fail-closed).
    Qualquer exceção durante a leitura -> "" (nunca inventa, nunca quebra).
    """
    if lab_memory is None and zara_turns is None:
        return ""
    try:
        api = SharedMemoryAPI(lab_memory=lab_memory, zara_turns=zara_turns)
        view = api.read_view(
            {
                "bot_id": bot_id,
                "sources": list(sources),
                "max_entries": max_entries,
                "include_provenance": include_provenance,
            }
        )
    except Exception:
        return ""
    entries = view.get("entries") or []
    lines = [_HEADER]
    for entry in entries:
        if isinstance(entry, Mapping):
            lines.append(_entry_line(entry))
    if len(lines) == 1:
        return ""
    text = "\n".join(lines)
    if len(text) > max_chars:
        keep = max(0, max_chars - len(_TRUNC_MARK))
        text = text[:keep].rstrip() + _TRUNC_MARK
    return text
