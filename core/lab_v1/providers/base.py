"""ZARA LAB REAL V1 — provider adapter contract.

Every real model call in the Lab goes through one of these. The contract is
deliberately narrow: `probe()` answers "can this provider work right now"
without spending a token, and `complete()` makes exactly one real call and
returns a `ProviderResult` (see `core/lab_v1/domain.py`) that the runtime can
trust without re-parsing provider-specific text.

Why `Availability` classification lives here and not in each adapter
----------------------------------------------------------------------
Failover in the runtime reads only `ProviderResult.availability`. If each
adapter invented its own way of deciding AUTH_REQUIRED vs RATE_LIMITED vs
ERROR, failover would silently diverge between providers the day one of them
changes its error wording. `classify_error_text()` is the one place that
mapping happens, so every adapter that calls it stays consistent by
construction.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult

__all__ = [
    "InvocationConfigurationError", "InvocationOptions", "ModelDescriptor",
    "ProviderAdapter", "classify_error_text",
]


class InvocationConfigurationError(ValueError):
    """Local invocation option error; it is not a provider outage."""

    code = "INVALID_INVOCATION_OPTIONS"


@dataclass(frozen=True)
class InvocationOptions:
    effort: str | None = None


@dataclass(frozen=True)
class ModelDescriptor:
    provider_id: str
    model_id: str
    display_name: str
    source: str = "declared"
    observed_at: float | None = None
    supports_effort: bool = False
    effort_levels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "provider_id": self.provider_id, "model_id": self.model_id,
            "display_name": self.display_name, "source": self.source,
            "supports_effort": self.supports_effort,
            "effort_levels": list(self.effort_levels),
        }
        if self.observed_at is not None:
            result["observed_at"] = self.observed_at
        return result


def classify_error_text(text: str | None) -> Availability:
    """Map a provider's free-text error into the closed Availability set.

    This is intentionally conservative: wording that does not clearly match a
    known category falls through to ERROR (transient, worth a retry) rather
    than something more specific. Guessing a specific category from vague
    text is how failover logic quietly rots.
    """
    if not text:
        return Availability.ERROR

    lowered = text.lower()

    auth_markers = (
        "not logged in", "please login", "please run", "/login",
        "authentication", "unauthenticated", "auth_required", "auth required",
        "invalid api key", "invalid x-api-key", "no api key",
    )
    if any(marker in lowered for marker in auth_markers):
        return Availability.AUTH_REQUIRED

    rate_markers = ("rate limit", "rate_limit", "too many requests", "429")
    if any(marker in lowered for marker in rate_markers):
        return Availability.RATE_LIMITED

    quota_markers = (
        "quota", "usage limit", "usage_limit", "credit balance",
        "insufficient credits", "out of credits",
    )
    if any(marker in lowered for marker in quota_markers):
        return Availability.QUOTA_EXHAUSTED

    busy_markers = ("overloaded", "server is busy", "service unavailable", "503")
    if any(marker in lowered for marker in busy_markers):
        return Availability.BUSY

    return Availability.ERROR


class ProviderAdapter(ABC):
    """One real place tokens can come from.

    `id` and `label` are set by concrete adapters (as class attributes or in
    `__init__`); the registry keys on `id`.
    """

    id: str
    label: str
    declared_models: tuple[ModelDescriptor, ...] = ()
    controlled_text_only: bool = False

    def invoke(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        resume_session_id: str | None = None,
        timeout_s: int = 240,
        max_turns: int = 1,
        options: InvocationOptions | None = None,
    ) -> ProviderResult:
        """Compatibility entry point for extensible invocation options."""
        options = options or InvocationOptions()
        if options.effort is not None:
            descriptor = next((item for item in self.declared_models if item.model_id == model), None)
            if descriptor is None or not descriptor.supports_effort:
                raise InvocationConfigurationError(
                    f"O modelo '{model}' nao oferece controle de effort."
                )
            if options.effort not in descriptor.effort_levels:
                raise InvocationConfigurationError(
                    f"Effort '{options.effort}' nao e suportado por '{model}'."
                )
            return self.complete_with_options(
                prompt=prompt, model=model, system=system,
                resume_session_id=resume_session_id, timeout_s=timeout_s,
                max_turns=max_turns, options=options,
            )
        return self.complete(
            prompt=prompt, model=model, system=system,
            resume_session_id=resume_session_id, timeout_s=timeout_s,
            max_turns=max_turns,
        )

    def complete_with_options(self, **kwargs) -> ProviderResult:
        raise InvocationConfigurationError("Este adapter nao traduz opcoes de invocacao.")

    def identifies_model(self, requested: str, reported: str | None) -> bool:
        """Does `reported` name the same model the Lab asked for?

        `ProviderResult.model_reported` is the provider's own canonical id and
        exists as proof a run was real, so the runtime must be able to reject a
        run that silently used a different model. Only the adapter knows how
        its own ids relate: the default here is strict equality, which is right
        for a provider that echoes back the same id it was given. An adapter
        whose `declared_models` are *aliases* must override this — for it the
        canonical id is never equal to the alias, and strict equality would
        reject every real run as a mismatch.

        A provider that reports nothing cannot contradict the request, so an
        absent `reported` is not a mismatch (it is simply weaker evidence).
        """
        if not reported:
            return True
        return reported == requested

    @abstractmethod
    def probe(self) -> ProviderInfo:
        """Cheap, side-effect-free check of whether this provider is usable.

        Must never call a model. This is polled to populate a provider list
        in the UI; if it spent tokens, opening that screen would cost money.
        """
        raise NotImplementedError

    @abstractmethod
    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        resume_session_id: str | None = None,
        timeout_s: int = 240,
        max_turns: int = 1,
    ) -> ProviderResult:
        """Make exactly one real call to the model and return a normalized result.

        Never fabricates a successful answer. If the provider is unreachable,
        unauthenticated, or errors, this returns `ok=False` with the best
        `Availability` classification available — it does not raise for
        expected failure modes, so the runtime can fail over without a
        try/except around every call site.
        """
        raise NotImplementedError
