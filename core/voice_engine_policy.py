"""Fail-safe output-engine ordering for Kore and local TTS engines."""

from __future__ import annotations

from collections.abc import Iterable


VOICE_ENGINES = ("kore", "edge", "kokoro")


def normalize_voice_engine(value: object) -> str:
    # OmniVoice foi removido em 02/10 (decisao do Alex): qualquer valor antigo
    # ("omnivoice") cai pra "kore" pra nao quebrar chamadores antigos.
    return "kore"


def voice_output_order(
    selected: object,
    *,
    kore_ready: bool,
    edge_ready: bool,
    kokoro_ready: bool,
) -> tuple[str, ...]:
    """Choose a safe output cascade without inventing unavailable engines.

    Ordem: Kore (se pronta) -> Edge -> Kokoro (reserva local oficial, 02/10).
    """
    candidates: list[tuple[str, bool]] = []
    if kore_ready:
        candidates.append(("kore", True))

    candidates.extend((("edge", edge_ready), ("kokoro", kokoro_ready)))
    return tuple(name for name, available in candidates if available)


def first_engine(order: Iterable[str]) -> str | None:
    return next(iter(order), None)
