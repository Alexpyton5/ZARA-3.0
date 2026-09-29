"""Memoria compartilhada ZARA <-> bots: a especificacao (peca 1).

"Memoria unica pros dois lados": o que a ZARA sabe, os bots sabem.
Esta peca declara o CONTRATO - fontes conhecidas, regras fail-closed
e a visao unificada somente-leitura. A peca 2 (store) vai ler as fontes
reais e montar a visao; a peca 3 (api/ipc) expoe pro bot.

Regras (fail-closed):
1. Fonte tem nome conhecido - fonte desconhecida e RECUSADA, nunca inventada.
2. O bot LE a visao unificada; NUNCA escreve na fonte do outro lado.
   Escrita continua no escopo proprio de cada lado (ex.: lab_memory).
3. Todo item carrega procedencia (fonte, autor, quando) - sem procedencia,
   nao entra na visao.
4. Valor e fato, nao relatorio: teto de 4096 caracteres (igual ao lab_memory).
5. A visao e congelada (frozen): ninguem edita a visao, edita-se a fonte.

Logica pura, stdlib, custo zero.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

# Fontes que o runtime sabe ler. Qualquer outra e recusada.
KNOWN_SOURCES = frozenset({"lab", "zara"})
# "lab": fatos do lab_memory (os 11 assentos). "zara": saber do lado ZARA
# (decisoes da Conselheira, resumos de conversa - adaptador na peca 2).

_KEY_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,63}")
_BOT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
_MAX_VALUE = 4096
_MAX_AUTHOR = 120
_MAX_ENTRIES = 500


class SharedMemoryError(ValueError):
    """Uma regra da memoria compartilhada foi violada."""


@dataclass(frozen=True)
class SharedEntry:
    """Um fato com procedencia, pronto pra entrar na visao unificada."""
    source: str
    key: str
    value: str
    author: str
    written_at: float

    def __post_init__(self) -> None:
        if self.source not in KNOWN_SOURCES:
            raise SharedMemoryError(f"fonte desconhecida: {self.source!r}")
        if not isinstance(self.key, str) or not _KEY_RE.fullmatch(self.key):
            raise SharedMemoryError(f"chave invalida: {self.key!r}")
        if not isinstance(self.value, str) or not self.value \
                or len(self.value) > _MAX_VALUE:
            raise SharedMemoryError("valor invalido (vazio ou passou de 4096)")
        author = (self.author or "").strip()
        if not author or len(author) > _MAX_AUTHOR:
            raise SharedMemoryError("autor invalido (procedencia obrigatoria)")
        if not isinstance(self.written_at, (int, float)) \
                or isinstance(self.written_at, bool) or self.written_at <= 0:
            raise SharedMemoryError("written_at invalido")


@dataclass(frozen=True)
class SharedMemorySpec:
    """O que um bot pode ver: quais fontes, quantos itens no maximo."""
    bot_id: str
    sources: tuple[str, ...] = ("lab", "zara")
    max_entries: int = 100
    include_provenance: bool = True

    def __post_init__(self) -> None:
        if not _BOT_ID_RE.match(self.bot_id or ""):
            raise SharedMemoryError(
                f"bot_id invalido: {self.bot_id!r} (minusculas, numeros, hifen)")
        sources = tuple(self.sources or ())
        if not sources:
            raise SharedMemoryError("sources nao pode ser vazio")
        unknown = [s for s in sources if s not in KNOWN_SOURCES]
        if unknown:
            raise SharedMemoryError(f"fontes desconhecidas: {unknown}")
        if len(set(sources)) != len(sources):
            raise SharedMemoryError("sources com fonte repetida")
        if not isinstance(self.max_entries, int) \
                or isinstance(self.max_entries, bool):
            raise SharedMemoryError("max_entries precisa ser inteiro")
        if not 1 <= self.max_entries <= _MAX_ENTRIES:
            raise SharedMemoryError(
                f"max_entries fora de 1..{_MAX_ENTRIES}")
        if not isinstance(self.include_provenance, bool):
            raise SharedMemoryError("include_provenance precisa ser bool")


_KNOWN_FIELDS = frozenset(
    {"bot_id", "sources", "max_entries", "include_provenance"})


def from_dict(data: Mapping[str, Any]) -> SharedMemorySpec:
    """Monta a spec de um dicionario (UI/JSON). Estrito: campo desconhecido
    e recusado pra erro de digitacao nunca virar padrao silencioso."""
    if not isinstance(data, Mapping):
        raise SharedMemoryError("spec precisa ser um dicionario")
    unknown = [k for k in data if k not in _KNOWN_FIELDS]
    if unknown:
        raise SharedMemoryError(f"campos desconhecidos na spec: {unknown}")
    kw: dict[str, Any] = dict(data)
    sources = kw.get("sources", ("lab", "zara"))
    if isinstance(sources, list):
        sources = tuple(sources)
    kw["sources"] = sources
    try:
        return SharedMemorySpec(**kw)
    except TypeError as exc:
        raise SharedMemoryError(f"spec invalida: {exc}") from None


def to_dict(spec: SharedMemorySpec) -> dict[str, Any]:
    """Ida e volta: spec -> dicionario -> from_dict."""
    return {
        "bot_id": spec.bot_id,
        "sources": list(spec.sources),
        "max_entries": spec.max_entries,
        "include_provenance": spec.include_provenance,
    }


def entry_from_lab_fact(key: str, fact: Mapping[str, Any]) -> SharedEntry:
    """Adaptador: fato real do lab_memory.facts() -> SharedEntry (fonte lab).

    O fato ja traz procedencia (seat, written_at) - e ela que entra aqui.
    """
    if not isinstance(fact, Mapping):
        raise SharedMemoryError("fato do lab precisa ser um dicionario")
    try:
        return SharedEntry(
            source="lab",
            key=key,
            value=fact["value"],
            author=str(fact["seat"]),
            written_at=float(fact["written_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SharedMemoryError(f"fato do lab incompleto: {exc}") from None


@dataclass(frozen=True)
class SharedMemoryView:
    """A visao unificada que o bot LE. Congelada: so leitura."""
    bot_id: str
    sources: tuple[str, ...]
    entries: tuple[SharedEntry, ...]
    built_at: float
    include_provenance: bool = True

    def get(self, source: str, key: str) -> SharedEntry | None:
        for entry in self.entries:
            if entry.source == source and entry.key == key:
                return entry
        return None

    def list(self) -> list[SharedEntry]:
        return list(self.entries)

    def describe(self, *, max_lines: int = 12) -> list[str]:
        """Resumo pronto pra UI/debug, com teto de linhas. Se estourar,
        a ultima linha e sempre o aviso de overflow (nunca some)."""
        lines = [f"visao de {self.bot_id}: "
                 f"{len(self.entries)} itens de {', '.join(self.sources)}"]
        entries = list(self.entries)
        overflow = len(entries) - (max_lines - 1)
        if overflow > 0:
            entries = entries[:max_lines - 2]
        for entry in entries:
            if self.include_provenance:
                lines.append(f"[{entry.source}] {entry.key} "
                             f"(por {entry.author})")
            else:
                lines.append(f"[{entry.source}] {entry.key}")
        if overflow > 0:
            lines.append(f"... e mais {overflow}")
        return lines


def build_view(
    spec: SharedMemorySpec,
    entries: Iterable[SharedEntry],
    *,
    now: Callable[[], float] = time.time,
) -> SharedMemoryView:
    """Monta a visao unificada: valida, filtra pelas fontes da spec,
    ordena de forma deterministica (fonte, chave) e congela.

    Fail-closed: item de fonte fora da spec, item que nao e SharedEntry
    ou item sem procedencia = erro, nunca silencio.
    """
    if not isinstance(spec, SharedMemorySpec):
        raise SharedMemoryError("spec invalida pra montar a visao")
    allowed = set(spec.sources)
    clean: list[SharedEntry] = []
    for item in entries:
        if not isinstance(item, SharedEntry):
            raise SharedMemoryError(
                f"item nao e SharedEntry: {type(item).__name__}")
        if item.source not in allowed:
            raise SharedMemoryError(
                f"fonte fora da spec do bot: {item.source!r}")
        clean.append(item)
    clean.sort(key=lambda e: (e.source, e.key))
    if len(clean) > spec.max_entries:
        clean = clean[:spec.max_entries]
    return SharedMemoryView(
        bot_id=spec.bot_id,
        sources=tuple(spec.sources),
        entries=tuple(clean),
        built_at=now(),
        include_provenance=spec.include_provenance,
    )
