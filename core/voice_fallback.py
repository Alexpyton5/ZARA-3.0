"""Bounded Kore attempts for the voice cascade; later turns probe recovery."""

from __future__ import annotations

import asyncio
from typing import Any


class KoreRecoveryPolicy:
    """Limit each Kore wait and let the existing local cascade take over.

    Kore is retried on each later utterance, so a transient failure does not
    permanently pin ZARA to a fallback engine.
    """

    def __init__(
        self,
        *,
        minimum_timeout_seconds: float = 6.0,
        maximum_timeout_seconds: float = 12.0,
        base_timeout_seconds: float = 4.0,
        characters_per_second: float = 24.0,
    ) -> None:
        if minimum_timeout_seconds <= 0 or maximum_timeout_seconds < minimum_timeout_seconds:
            raise ValueError("invalid Kore timeout bounds")
        if base_timeout_seconds < 0 or characters_per_second <= 0:
            raise ValueError("invalid Kore timeout calculation")
        self.minimum_timeout_seconds = float(minimum_timeout_seconds)
        self.maximum_timeout_seconds = float(maximum_timeout_seconds)
        self.base_timeout_seconds = float(base_timeout_seconds)
        self.characters_per_second = float(characters_per_second)
        self.consecutive_failures = 0
        self.last_outcome = "not-attempted"
        self.current_engine = "kore"

    def timeout_for(self, text: str) -> float:
        estimate = self.base_timeout_seconds + len(text) / self.characters_per_second
        return min(
            self.maximum_timeout_seconds,
            max(self.minimum_timeout_seconds, estimate),
        )

    async def try_kore(self, kore: Any, text: str) -> bool:
        """Return promptly on Kore failure; caller continues the local cascade."""
        if kore is None or not bool(getattr(kore, "active", False)):
            self._failed("unavailable")
            return False

        timeout = self.timeout_for(text)
        started = asyncio.get_running_loop().time()
        try:
            result = await asyncio.wait_for(
                kore.speak(text, timeout=timeout), timeout=timeout
            )
        except asyncio.TimeoutError:
            self._failed("timeout")
            return False
        except Exception as exc:
            self._failed(f"error:{type(exc).__name__}")
            return False

        elapsed = asyncio.get_running_loop().time() - started
        if result is True:
            self.consecutive_failures = 0
            self.last_outcome = "kore"
            self.current_engine = "kore"
            return True

        # GeminiLiveVoice handles its own timeout and may return False rather
        # than raise. Classify a near-deadline False as the same bounded timeout.
        outcome = "timeout" if elapsed >= timeout * 0.95 else "no-audio"
        self._failed(outcome)
        return False

    def _failed(self, outcome: str) -> None:
        self.consecutive_failures += 1
        self.last_outcome = outcome
        self.current_engine = "fallback"
