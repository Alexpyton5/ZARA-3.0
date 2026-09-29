"""Escada de fallback de motores do Lab — FRENTE 2 (MISSAO LAB VIVO, 28/09/2026).

Ordem padrao: modelos GRATIS (NVIDIA NIM) primeiro; se todos falharem,
a Luna via Codex (cota do Alex) entra como ultimo recurso.

Uso:
    from core.lab_v1.providers.fallback import complete_with_fallback
    from core.lab_v1 import seat_engines

    outcome = complete_with_fallback(
        registry,
        seat_engines.default_ladder_for("ENGINEER"),
        prompt="Explique este erro...",
        system="Voce e o engenheiro do Lab ZARA.",
    )
    if outcome.result.ok:
        print(outcome.provider_id, outcome.model, outcome.result.text)

Regras duras:
- Nunca inventa resposta: se todos os degraus falharem, devolve ok=False
  com o historico de tentativas, para o chamador decidir o que fazer.
- Cada tentativa e registrada no registry (record_result), entao o health
  tracking de provedores continua funcionando.
- Provedor sem credencial ou fora do ar e pulado SEM gastar chamada.
- Um degrau que explode com excecao inesperada nao derruba a escada:
  vira uma tentativa falha e o proximo degrau e tentado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.lab_v1.domain import Availability, ProviderResult


# Provedores que podem provar acesso com UMA chamada real mesmo com
# probe UNKNOWN (mesma regra do runtime._run_agent).
_FIRST_USE_PROVIDERS = frozenset({"opencode", "nvidia"})


@dataclass(frozen=True)
class LadderRung:
    """Um degrau da escada: (provedor, modelo)."""
    provider_id: str
    model: str


@dataclass
class FallbackAttempt:
    provider_id: str
    model: str
    ok: bool
    availability: Availability
    error: str = ""
    duration_ms: int = 0
    skipped: bool = False


@dataclass
class FallbackOutcome:
    result: ProviderResult
    provider_id: str | None
    model: str | None
    attempts: list[FallbackAttempt] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.result.ok


def _as_rungs(ladder: Any) -> list[LadderRung]:
    rungs: list[LadderRung] = []
    for item in ladder or []:
        if isinstance(item, LadderRung):
            rungs.append(item)
        else:
            provider_id, model = item
            rungs.append(LadderRung(str(provider_id), str(model)))
    # Remove degraus duplicados mantendo a ordem.
    seen: set[tuple[str, str]] = set()
    unique: list[LadderRung] = []
    for rung in rungs:
        key = (rung.provider_id, rung.model)
        if key not in seen:
            seen.add(key)
            unique.append(rung)
    return unique


def _may_attempt(adapter: Any, model: str) -> tuple[bool, str]:
    """Probe barato: pode tentar de verdade ou deve pular o degrau?"""
    try:
        probe = adapter.probe()
    except Exception as exc:  # probe nunca deveria explodir, mas nao derruba a escada
        return False, f"probe explodiu: {exc}"
    availability = probe.availability
    first_use = (
        availability is Availability.UNKNOWN
        and getattr(adapter, "id", "") in _FIRST_USE_PROVIDERS
        and any(item.model_id == model for item in (getattr(adapter, "declared_models", None) or ()))
    )
    if getattr(availability, "can_work", False) or first_use:
        return True, ""
    return False, getattr(probe, "detail", "") or f"provedor {availability.value}"


def complete_with_fallback(
    registry: Any,
    ladder: Any,
    *,
    prompt: str,
    system: str | None = None,
    timeout_s: int = 120,
) -> FallbackOutcome:
    """Percorre a escada e devolve a primeira resposta real.

    `registry` precisa de `.get(provider_id)` e, opcionalmente,
    `.record_result(provider_id, model, result)`.
    """
    rungs = _as_rungs(ladder)
    attempts: list[FallbackAttempt] = []
    record = getattr(registry, "record_result", None)

    for rung in rungs:
        adapter = registry.get(rung.provider_id) if registry is not None else None
        if adapter is None:
            attempts.append(FallbackAttempt(
                rung.provider_id, rung.model, ok=False,
                availability=Availability.OFFLINE,
                error=f"Provedor '{rung.provider_id}' nao registrado.",
                skipped=True,
            ))
            continue

        may, reason = _may_attempt(adapter, rung.model)
        if not may:
            attempts.append(FallbackAttempt(
                rung.provider_id, rung.model, ok=False,
                availability=Availability.OFFLINE, error=reason, skipped=True,
            ))
            continue

        try:
            # invoke() e o ponto de entrada padrao; complete() e o legado.
            if hasattr(adapter, "invoke"):
                result = adapter.invoke(
                    prompt=prompt, model=rung.model, system=system,
                    timeout_s=timeout_s,
                )
            else:
                result = adapter.complete(
                    prompt=prompt, model=rung.model, system=system,
                    timeout_s=timeout_s,
                )
        except Exception as exc:
            result = ProviderResult(
                False, availability=Availability.ERROR,
                error=f"Falha inesperada no degrau: {exc}"[:300],
            )

        if callable(record):
            try:
                record(rung.provider_id, rung.model, result)
            except Exception:
                pass

        attempts.append(FallbackAttempt(
            rung.provider_id, rung.model, ok=bool(result.ok),
            availability=result.availability,
            error="" if result.ok else (result.error or ""),
            duration_ms=int(result.duration_ms or 0),
        ))
        if result.ok:
            return FallbackOutcome(
                result=result, provider_id=rung.provider_id,
                model=rung.model, attempts=attempts,
            )

    return FallbackOutcome(
        result=ProviderResult(
            False, availability=Availability.OFFLINE,
            error="Todos os degraus da escada falharam.",
        ),
        provider_id=None, model=None, attempts=attempts,
    )
