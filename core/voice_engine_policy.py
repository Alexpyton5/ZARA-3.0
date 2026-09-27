"""Fail-safe output-engine ordering for Kore and optional local TTS engines."""

from __future__ import annotations

from collections.abc import Iterable


VOICE_ENGINES = ("kore", "omnivoice", "edge", "kokoro")


def normalize_voice_engine(value: object) -> str:
    selected = str(value or "").strip().casefold()
    return selected if selected in {"kore", "omnivoice"} else "kore"


def voice_output_order(
    selected: object,
    *,
    kore_ready: bool,
    omnivoice_ready: bool,
    edge_ready: bool,
    kokoro_ready: bool,
) -> tuple[str, ...]:
    """Choose a safe output cascade without inventing unavailable engines.

    Explicit OmniVoice selection stays local; if its runtime is missing, Kore
    becomes the safe configured fallback. Kore mode uses OmniVoice immediately
    after Kore fails or times out.
    """
    mode = normalize_voice_engine(selected)
    candidates: list[tuple[str, bool]] = []
    if mode == "omnivoice" and omnivoice_ready:
        candidates.append(("omnivoice", True))
    elif kore_ready:
        candidates.append(("kore", True))
        if omnivoice_ready:
            candidates.append(("omnivoice", True))
    elif omnivoice_ready:
        candidates.append(("omnivoice", True))

    candidates.extend((("edge", edge_ready), ("kokoro", kokoro_ready)))
    return tuple(name for name, available in candidates if available)


def first_engine(order: Iterable[str]) -> str | None:
    return next(iter(order), None)
