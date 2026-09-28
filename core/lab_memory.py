"""Memoria compartilhada de trabalho dos 11 assentos do Lab.

O que o Lab aprende persiste entre tarefas, com procedencia auditavel:
quem escreveu, quando escreveu, quem apagou. E a memoria de operacao
do Lab - nao a memoria de longo prazo da ZARA (Obsidian).

Regras:
- so os 11 assentos fixos escrevem (ancorado em core.lab_v1.fixed_seats);
- qualquer assento le; ninguem precisa de autorizacao extra pra ler;
- fato tem dono: so quem escreveu (ou a CEO) sobrescreve ou apaga;
- chave 1..64 (minusculas, numeros, _ . -); valor 1..4096 caracteres
  (memoria e fato, nao relatorio);
- journal com relogio injetavel: tudo auditavel.

Logica pura, stdlib, custo zero.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.lab_v1.fixed_seats import FIXED_SEATS

SEATS = frozenset(role.value for role in FIXED_SEATS)
CEO = "CEO"

_KEY_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,63}")
_MAX_VALUE = 4096


class MemoryDenied(ValueError):
    """Um acesso a memoria compartilhada foi recusado."""


@dataclass(frozen=True)
class MemoryEntry:
    key: str
    value: str
    seat: str
    seq: int
    written_at: float


@dataclass(frozen=True)
class JournalLine:
    seq: int
    ts: float
    op: str  # WRITE | RETRACT
    seat: str
    key: str


class LabMemory:
    """Caixa de fatos do Lab: escreve, le, apaga, tudo com rastro."""

    def __init__(self, *, now: Callable[[], float] = time.time) -> None:
        self._now = now
        self._facts: dict[str, MemoryEntry] = {}
        self._journal: list[JournalLine] = []
        self._seq = 0

    # -- validacao ----------------------------------------------------
    @staticmethod
    def _seat_name(seat: Any) -> str:
        name = seat.value if hasattr(seat, "value") else str(seat)
        if name not in SEATS:
            raise MemoryDenied(f"SEAT_UNKNOWN:{name}")
        return name

    @staticmethod
    def _check_key(key: Any) -> str:
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise MemoryDenied(f"KEY_INVALID:{key!r}")
        return key

    @staticmethod
    def _check_value(value: Any) -> str:
        if not isinstance(value, str) or not value or len(value) > _MAX_VALUE:
            raise MemoryDenied("VALUE_INVALID")
        return value

    # -- escrita ------------------------------------------------------
    def _record(self, op: str, seat: str, key: str) -> JournalLine:
        self._seq += 1
        line = JournalLine(seq=self._seq, ts=self._now(), op=op, seat=seat, key=key)
        self._journal.append(line)
        return line

    def write(self, seat: Any, key: str, value: str) -> MemoryEntry:
        """Registra (ou atualiza) um fato. Dono novo nao pisa no fato alheio."""
        name = self._seat_name(seat)
        self._check_key(key)
        self._check_value(value)
        current = self._facts.get(key)
        if current is not None and current.seat != name and name != CEO:
            raise MemoryDenied(f"MEMORY_LOCKED:{key}")
        line = self._record("WRITE", name, key)
        entry = MemoryEntry(key=key, value=value, seat=name,
                            seq=line.seq, written_at=line.ts)
        self._facts[key] = entry
        return entry

    def retract(self, seat: Any, key: str) -> JournalLine:
        """Apaga um fato. So o autor ou a CEO."""
        name = self._seat_name(seat)
        self._check_key(key)
        current = self._facts.get(key)
        if current is None:
            raise MemoryDenied(f"MEMORY_MISSING:{key}")
        if current.seat != name and name != CEO:
            raise MemoryDenied(f"MEMORY_LOCKED:{key}")
        del self._facts[key]
        return self._record("RETRACT", name, key)

    # -- leitura ------------------------------------------------------
    def read(self, key: str) -> str | None:
        """Le o valor atual de um fato, ou None se nao existir."""
        self._check_key(key)
        entry = self._facts.get(key)
        return entry.value if entry is not None else None

    def list(self) -> dict[str, str]:
        """Todos os fatos atuais: chave -> valor."""
        return {key: entry.value for key, entry in self._facts.items()}

    def facts(self) -> dict[str, dict[str, Any]]:
        """Todos os fatos atuais com procedencia."""
        return {
            key: {"value": e.value, "seat": e.seat,
                  "seq": e.seq, "written_at": e.written_at}
            for key, e in self._facts.items()
        }

    def provenance(self, key: str) -> dict[str, Any] | None:
        """Quem escreveu este fato e quando, ou None se nao existir."""
        self._check_key(key)
        entry = self._facts.get(key)
        if entry is None:
            return None
        return {"seat": entry.seat, "seq": entry.seq,
                "written_at": entry.written_at}

    def history(self, key: str) -> list[JournalLine]:
        """O rastro completo de uma chave, em ordem."""
        self._check_key(key)
        return [line for line in self._journal if line.key == key]

    def journal(self) -> list[JournalLine]:
        """O rastro completo da memoria, em ordem."""
        return list(self._journal)
