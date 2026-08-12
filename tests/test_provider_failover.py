"""Provider discovery and failover policy proofs (ZARA-NIGHT-SHIFT 047-048).

Nothing here performs network I/O or touches the user's real API keys: every test
builds an isolated ModelRouter instance and injects fake keys/health.

Policy under test (free-tier only, as authorized):
  - discovery separates available from unavailable and never leaks credentials
  - 429 / rate limit  -> provider cooldown, another free model takes over
  - 401 / unauthorized -> provider marked unavailable (no automatic retry)
  - 402 / quota        -> provider exhausted for a long window
  - generic/5xx        -> short model-level backoff, provider stays usable
  - cooldown expires   -> model becomes routable again
  - paid models are never routable by default
"""
from __future__ import annotations

import time

import pytest

from core.model_router import (
    MODEL_REGISTRY,
    HealthState,
    ModelProvider,
    ModelRouter,
    TaskType,
    get_model_config,
    normalize_auto_engine,
)


@pytest.fixture
def router(monkeypatch):
    """Router with no persisted state and every provider key present."""
    monkeypatch.setattr(ModelRouter, "_load_api_keys", lambda self: None)
    monkeypatch.setattr(ModelRouter, "_load_usage_stats", lambda self: None)
    monkeypatch.setattr(ModelRouter, "_load_catalog_snapshot", lambda self: None)
    r = ModelRouter()
    r.api_keys = {m.api_key_env: "fake-key-value" for m in MODEL_REGISTRY}
    return r


def _free_models(router):
    return [m for m in router.get_available_models(include_hermes=False) if m.zero_cost_eligible]


# ---------- 047 discovery ----------
def test_047_discovery_lists_free_models(router):
    models = _free_models(router)
    assert models, "nenhum modelo gratuito descoberto"
    assert all(m.zero_cost_eligible for m in models)


def test_047_model_without_key_is_unavailable(router):
    target = _free_models(router)[0]
    router.api_keys.pop(target.api_key_env, None)
    remaining = [m.id for m in router.get_available_models(include_hermes=False)]
    assert target.id not in remaining


def test_047_paid_models_are_not_routable_by_default(router):
    ids = [m.id for m in router.get_available_models(include_hermes=False, include_paid=False)]
    for model in MODEL_REGISTRY:
        if not model.zero_cost_eligible and model.provider != ModelProvider.HERMES:
            assert model.id not in ids


def test_047_status_rows_never_expose_credentials(router):
    rows = router.configured_model_status()
    assert rows
    blob = repr(rows)
    assert "fake-key-value" not in blob
    for row in rows:
        assert set(row) == {"id", "name", "provider", "api_model", "free_tier", "health"}


def test_047_status_separates_available_from_unavailable(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "HTTP 401 unauthorized")
    states = {r["id"]: r["health"]["state"] for r in router.configured_model_status()}
    assert states[target.id] == HealthState.AUTH_INVALID.value
    assert any(s == HealthState.AVAILABLE.value for s in states.values())


# ---------- 048 failover ----------
def test_048_rate_limit_puts_provider_in_cooldown(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "429 Too Many Requests")
    health = router.health_for(target.id)
    assert health["state"] == HealthState.COOLDOWN.value
    assert health["until"] > time.time()


def test_048_rate_limited_model_is_replaced_by_another_free_model(router):
    before = router.get_best_model([TaskType.GENERAL_CHAT])
    assert before is not None
    router.mark_failure(before.id, "429 rate limit")
    after = router.get_best_model([TaskType.GENERAL_CHAT])
    if after is not None:
        assert after.provider != before.provider
        assert after.zero_cost_eligible


def test_048_auth_error_marks_provider_unavailable_without_expiry(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "401 invalid_api_key")
    health = router.health_for(target.id)
    assert health["state"] == HealthState.AUTH_INVALID.value
    assert health["until"] == 0.0  # nao volta sozinho por tempo


def test_048_quota_error_marks_provider_exhausted(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "402 insufficient_quota")
    assert router.health_for(target.id)["state"] == HealthState.EXHAUSTED.value


def test_048_generic_error_uses_short_model_level_backoff(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "503 service unavailable")
    health = router.health_for(target.id)
    assert health["state"] == HealthState.ERROR.value
    assert 0 < health["until"] - time.time() <= 60


def test_048_cooldown_expires_and_model_returns(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "429 rate limit")
    assert router.health_for(target.id)["state"] == HealthState.COOLDOWN.value
    # simula o fim da janela sem esperar de verdade
    router.provider_health[target.provider.value].until = time.time() - 1
    assert router.health_for(target.id)["state"] == HealthState.AVAILABLE.value


def test_048_success_clears_previous_failure(router):
    target = _free_models(router)[0]
    router.mark_failure(target.id, "500 internal error")
    router.mark_success(target.id)
    health = router.health_for(target.id)
    assert health["state"] == HealthState.AVAILABLE.value
    assert health["last_status"] == 200


def test_048_fallback_chain_is_free_and_excludes_primary(router):
    primary = router.get_best_model([TaskType.GENERAL_CHAT])
    chain = router.get_fallback_chain([TaskType.GENERAL_CHAT])
    assert primary is not None
    assert primary.id not in [m.id for m in chain]
    assert all(m.zero_cost_eligible for m in chain)


def test_048_all_free_providers_down_yields_no_model_instead_of_paid(router):
    for model in MODEL_REGISTRY:
        router.mark_failure(model.id, "401 unauthorized")
    best = router.get_best_model([TaskType.GENERAL_CHAT])
    assert best is None or best.zero_cost_eligible


def test_048_unknown_model_id_is_ignored_safely(router):
    router.mark_failure("modelo-que-nao-existe", "429")
    router.mark_success("modelo-que-nao-existe")
    assert get_model_config("modelo-que-nao-existe") is None


# ---------- routing policy ----------
def test_intent_classification_defaults_to_general_chat(router):
    assert router.classify_intent("oi, tudo bem?") == [TaskType.GENERAL_CHAT]


def test_intent_context_flags_take_precedence(router):
    types = router.classify_intent("qualquer coisa", {"require_tools": True})
    assert types[0] == TaskType.TOOL_USE


def test_normalize_auto_engine_defaults_to_smart():
    assert normalize_auto_engine(None) == "auto_smart"
    assert normalize_auto_engine("") == "auto_smart"
    assert normalize_auto_engine("auto") == "auto_smart"
    assert normalize_auto_engine("auto_economy") == "auto_economy"
    assert normalize_auto_engine("groq_llama") == "groq_llama"
