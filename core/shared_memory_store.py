"""Memoria compartilhada ZARA <-> bots: o store (peca 2).

Le as fontes REAIS e monta a visao unificada da peca 1
(`shared_memory_spec.build_view`). O bot LE a visao; nunca escreve
na fonte do outro lado - a escrita continua no escopo proprio de
cada lado (ex.: o Lab escreve no lab_memory).

Fontes reais ligadas aqui:
- "lab": `LabMemory.facts()` - os 11 assentos; cada fato ja traz
  procedencia (seat + written_at). Adaptado por
  `shared_memory_spec.entry_from_lab_fact`.
- "zara": o fio unificado - turnos de `ConversationHistory`
  (role, content, engine, timestamp em ms, persistidos no app).
  Cada turno vira um SharedEntry com procedencia real: autor =
  "alex" (turno do Alex) ou a engine ("ponte-zoe", "lab-resumo"...);
  quando = o timestamp do turno. Turno sem timestamp valido, sem
  texto, com role desconhecida ou maior que 4096 NAO entra
  (fail-closed: sem procedencia valida, nao entra - mesma regra
  da ponte da Conselheira).

Regras (fail-closed):
1. Fonte na spec sem leitor configurado = SharedMemoryError. Nunca
   se entrega visao inventada nem fonte silenciosamente ignorada.
2. Leitor que quebra = SharedMemoryError com o nome da fonte. Nunca
   visao parcial disfarcada de completa.
3. Leitores das fontes fora da spec NUNCA sao chamados.
4. Logica pura, stdlib, zero custo/rede/quota.

Uso no app:
    store = SharedMemoryStore.from_lab_memory(
        spec, lab_memory, zara_turns=history.list_recent)
    view = store.read()
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Callable, Iterable, Mapping

from core.shared_memory_spec import (
    SharedEntry,
    SharedMemoryError,
    SharedMemorySpec,
    SharedMemoryView,
    build_view,
    entry_from_lab_fact,
)

_ENGINE_RE = re.compile(r"[^a-z0-9]+")
_MAX_ENGINE = 30


def _sanitize_engine(engine: Any) -> str:
    """Nome da engine vira pedaco de chave: minusculo, [a-z0-9-]."""
    cleaned = _ENGINE_RE.sub("-", str(engine or "").lower()).strip("-")
    return cleaned[:_MAX_ENGINE]


def zara_key(engine: str, ts_ms: int, content: str) -> str:
    """Chave estavel do turno: mesmo turno = mesma chave (dedup)."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return f"fio.{engine}.{int(ts_ms)}.{digest}"


def zara_entry_from_turn(turn: Mapping[str, Any]) -> SharedEntry | None:
    """Turno do fio unificado -> SharedEntry (fonte zara).

    Devolve None p/ turno que nao cumpre o contrato (sem timestamp,
    sem texto, role desconhecida, texto > 4096): sem procedencia
    valida, nao entra na visao.
    """
    if not isinstance(turn, Mapping):
        return None
    role = str(turn.get("role") or "").strip().lower()
    if role == "user":
        author = "alex"
    elif role == "assistant":
        engine = _sanitize_engine(turn.get("engine"))
        if not engine:
            return None
        author = engine
    else:
        return None
    text = str(turn.get("content") or "").strip()
    if not text or len(text) > 4096:
        return None
    ts = turn.get("timestamp")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0:
        return None
    ts_ms = int(ts)
    engine_part = _sanitize_engine(turn.get("engine") or author)
    try:
        return SharedEntry(
            source="zara",
            key=zara_key(engine_part, ts_ms, text),
            value=text,
            author=author,
            written_at=ts_ms / 1000.0,
        )
    except SharedMemoryError:
        return None


def zara_entries_from_turns(
    turns: Iterable[Mapping[str, Any]],
) -> list[SharedEntry]:
    """Adapta a lista do fio (`history.list_recent()`) p/ SharedEntry.

    So entra o que cumpre o contrato; o resto e descartado.
    """
    entries: list[SharedEntry] = []
    for turn in turns or []:
        entry = zara_entry_from_turn(turn)
        if entry is not None:
            entries.append(entry)
    return entries


class SharedMemoryStore:
    """Le as fontes reais e monta a visao unificada da spec."""

    def __init__(
        self,
        spec: SharedMemorySpec,
        *,
        lab_facts: Callable[[], Mapping[str, Mapping[str, Any]]] | None = None,
        zara_turns: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(spec, SharedMemorySpec):
            raise SharedMemoryError("spec invalida pro store")
        self._spec = spec
        self._lab_facts = lab_facts
        self._zara_turns = zara_turns
        self._now = now

    @classmethod
    def from_lab_memory(
        cls,
        spec: SharedMemorySpec,
        lab_memory: Any,
        *,
        zara_turns: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
        now: Callable[[], float] = time.time,
    ) -> "SharedMemoryStore":
        """Liga o LabMemory real do app como fonte "lab"."""
        facts = getattr(lab_memory, "facts", None)
        if not callable(facts):
            raise SharedMemoryError(
                "lab_memory sem o metodo facts() - fonte 'lab' nao ligada")
        return cls(spec, lab_facts=facts, zara_turns=zara_turns, now=now)

    @property
    def spec(self) -> SharedMemorySpec:
        return self._spec

    def read_lab(self) -> list[SharedEntry]:
        """Fatos reais do lab_memory adaptados p/ SharedEntry."""
        if "lab" not in self._spec.sources:
            return []
        if self._lab_facts is None:
            raise SharedMemoryError(
                "fonte 'lab' na spec mas sem leitor configurado")
        try:
            facts = self._lab_facts()
        except Exception as exc:
            raise SharedMemoryError(
                f"fonte 'lab' falhou ao ler: {exc}") from exc
        if not isinstance(facts, Mapping):
            raise SharedMemoryError("fonte 'lab' devolveu algo invalido")
        entries: list[SharedEntry] = []
        for key, fact in facts.items():
            try:
                entries.append(entry_from_lab_fact(key, fact))
            except SharedMemoryError as exc:
                raise SharedMemoryError(
                    f"fato do lab {key!r} invalido: {exc}") from exc
        return entries

    def read_zara(self) -> list[SharedEntry]:
        """Turnos reais do fio unificado adaptados p/ SharedEntry."""
        if "zara" not in self._spec.sources:
            return []
        if self._zara_turns is None:
            raise SharedMemoryError(
                "fonte 'zara' na spec mas sem leitor configurado")
        try:
            turns = self._zara_turns()
        except Exception as exc:
            raise SharedMemoryError(
                f"fonte 'zara' falhou ao ler: {exc}") from exc
        return zara_entries_from_turns(turns)

    def read(self) -> SharedMemoryView:
        """Monta a visao unificada: le so as fontes da spec e congela."""
        entries: list[SharedEntry] = []
        entries.extend(self.read_lab())
        entries.extend(self.read_zara())
        return build_view(self._spec, entries, now=self._now)
