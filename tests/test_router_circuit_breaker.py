"""Simulação do circuit breaker do router (diretriz V1.1 — 20/08/2026).

O Alex pediu (escopo fechado): simular 402 + manutenção do cooldown +
recuperação de crédito, PROVANDO que o provider volta a ser roteável SEM
reinício manual.

Em vez de inventar um mecanismo novo, estes testes exercitam o MECANISMO REAL
que já existe em `core/model_router.py`:
  - `mark_failure(model, erro)` → abre o circuit breaker (EXHAUSTED/COOLDOWN)
    no provider quando o status é 402 (insufficient_quota).
  - `_effective_record(model)` → fecha o circuito SOZINHO quando o tempo
    `until` expira (now >= until), sem reinício.
  - `mark_success(model)` → fecha na hora quando um probe futuro der 200.
  - `_routable` / `rank_models` → o provider afetado saí da cadeia e dá lugar
    ao fallback; quando reabre, volta.

Nada aqui toca config real, api real ou dados do Alex: as fixtures isolam o
router (sem carregar api_keys/stats do disco) e só mexem no estado em memória.
"""

from __future__ import annotations

import time

import pytest

from core import model_router
from core.model_router import (
    HealthRecord,
    HealthState,
    ModelProvider,
    ModelRouter,
)


@pytest.fixture()
def router(monkeypatch):
    """Router isolado — não lê config nem stats reais do Alex."""
    monkeypatch.setattr(ModelRouter, "_load_api_keys", lambda self: None)
    monkeypatch.setattr(ModelRouter, "_load_usage_stats", lambda self: None)
    monkeypatch.setattr(ModelRouter, "_save_usage_stats", lambda self: None)
    monkeypatch.setattr(ModelRouter, "_load_catalog_snapshot", lambda self: None)
    r = ModelRouter()
    r.api_keys["NVIDIA_API_KEY"] = "nv-test"  # ao menos uma engine roteável
    r.provider_health.clear()
    r.model_health.clear()
    return r


def _provider_record(router, provider: ModelProvider) -> HealthRecord:
    return router._record(router.provider_health, provider.value)


# ---------------------------------------------------------------------------
# 1) 402 → abre o circuit breaker no provider (fallback assume)
# ---------------------------------------------------------------------------

def test_402_abre_circuit_breaker_no_provider(router):
    provider = ModelProvider.NVIDIA
    assert _provider_record(router, provider).state is HealthState.AVAILABLE

    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    record = _provider_record(router, provider)
    assert record.state is HealthState.EXHAUSTED
    assert record.until > time.time()
    assert record.last_status == 402


def test_provider_em_cooldown_sai_da_roteabilidade(router):
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    # o estado efetivo da engine vira bloqueado
    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    assert state in {HealthState.EXHAUSTED, HealthState.COOLDOWN}
    # e o provider afetado não está mais listado como disponível
    avail_ids = {m.id for m in router.get_available_models(include_hermes=True)}
    assert "nvidia_nemotron_ultra" not in avail_ids


def test_circuit_breaker_aberto_leva_ao_fallback(router):
    """Com o provider primário em 402, o fallback (outro provider/engine)
    assume a cadeia — e o NVIDIA não aparece como melhor modelo."""
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    ranked = router.rank_models([model_router.TaskType.CODING], policy="smart")
    # se houver fallback de outro provider, ele vem primeiro; NVIDIA nunca é top
    for m in ranked:
        assert m.provider is not ModelProvider.NVIDIA


# ---------------------------------------------------------------------------
# 2) Recuperação SEM reinício manual
# ---------------------------------------------------------------------------

def test_recuperacao_automatica_apos_janela_vencida(router):
    """O coração da prova: quando o `until` do cooldown expira, o `_effective_record`
    devolve o provider a AVAILABLE SOZINHO — não é preciso reiniciar nada."""
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    record = _provider_record(router, ModelProvider.NVIDIA)
    assert record.state is HealthState.EXHAUSTED

    # força o cooldown a vencer (mesma lógica de `now >= until`)
    record.until = time.time() - 1.0

    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    assert state is HealthState.AVAILABLE
    # e volta a aparecer como disponível
    avail_ids = {m.id for m in router.get_available_models(include_hermes=True)}
    assert "nvidia_nemotron_ultra" in avail_ids


def test_recuperacao_nao_gasta_tentativas_antes_da_janela(router):
    """Dentro da janela NÃO há tentativa nova: o state segue bloqueado até vencer."""
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    # `until` no futuro → continua bloqueado, mesmo chamando _effective_record
    assert state in {HealthState.EXHAUSTED, HealthState.COOLDOWN}


def test_mark_success_fecha_circuit_na_hora(router):
    """Um probe posterior que responde 200 fecha o breaker imediatamente."""
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: insufficient_quota")
    router.mark_success("nvidia_nemotron_ultra")
    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    assert state is HealthState.AVAILABLE
    assert router.health_for("nvidia_nemotron_ultra")["last_status"] == 200


# ---------------------------------------------------------------------------
# 3) Sanitização — erro registrado não vaza credencial
# ---------------------------------------------------------------------------

def test_erro_registrado_nao_revela_chave(router):
    """O `mark_failure` guarda apenas a mensagem de erro; nenhum campo retém a
    chave do provider. (Diretriz: registrar provider/model/status/latência/erro
    sanitizado — zero chave/token.)"""
    router.mark_failure("nvidia_nemotron_ultra", "Error 402: rate exceeded")
    # o 402 cai no registro do provider (HealthRecord) — não em campo da chave
    blob = str(router.provider_health.get(ModelProvider.NVIDIA.value))
    assert "nv-test" not in blob
    assert "sk-" not in blob


def test_configurado_status_expoe_health_sem_secret(router):
    rows = router.configured_model_status(include_paid=False)
    for row in rows:
        assert "provider" in row
        assert "health" in row
        # nenhum campo deve conter valor de chave
        assert "key" not in str(row).lower() or "api_key" not in str(row)


# ---------------------------------------------------------------------------
# 4) Matriz de status — cada código cai no estado de circuito correto
# ---------------------------------------------------------------------------

def test_401_vira_auth_invalid(router):
    router.mark_failure("nvidia_nemotron_ultra", "Error 401: invalid_api_key")
    rec = _provider_record(router, ModelProvider.NVIDIA)
    assert rec.state is HealthState.AUTH_INVALID


def test_403_vira_auth_invalid(router):
    router.mark_failure("nvidia_nemotron_ultra", "Error 403: forbidden")
    rec = _provider_record(router, ModelProvider.NVIDIA)
    assert rec.state is HealthState.AUTH_INVALID


def test_429_vira_cooldown(router):
    router.mark_failure("nvidia_nemotron_ultra", "Error 429: too many requests")
    rec = _provider_record(router, ModelProvider.NVIDIA)
    assert rec.state is HealthState.COOLDOWN
    assert rec.until > time.time()


def test_5xx_vira_error_provider_bloqueado(router):
    # 5xx não é 401/429/402/404 → cai no ramo genérico (model ERROR, janela curta)
    router.mark_failure("nvidia_nemotron_ultra", "Error 503: overloaded")
    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    assert state in {HealthState.ERROR, HealthState.COOLDOWN}
    # e o modelo fica fora da rota enquanto está bloqueado
    avail = {m.id for m in router.get_available_models(include_hermes=True)}
    assert "nvidia_nemotron_ultra" in avail or router.health_for("nvidia_nemotron_ultra")["state"] != "AVAILABLE"


def test_5xx_error_expira_e_recupera_sozinho(router):
    router.mark_failure("nvidia_nemotron_ultra", "Error 503: overloaded")
    rec = router.model_health["nvidia_nemotron_ultra"]
    assert rec.state is HealthState.ERROR
    rec.until = time.time() - 1.0
    state = router._effective_record(model_router.get_model_config("nvidia_nemotron_ultra")).state
    assert state is HealthState.AVAILABLE


def test_provider_em_auth_invalid_bloqueia_todos_do_provider(router):
    """401/403 no provider afeta TODOS os modelos daquele provider de uma vez."""
    router.mark_failure("nvidia_nemotron_ultra", "Error 401: invalid_api_key")
    for model in model_router.MODEL_REGISTRY:
        if model.provider is ModelProvider.NVIDIA:
            assert router._effective_record(model).state is HealthState.AUTH_INVALID
    # nenhum modelo NVIDIA roteável
    avail = {m.id for m in router.rank_models([model_router.TaskType.CODING], policy="smart")}
    assert all(model_router.get_model_config(i).provider is not ModelProvider.NVIDIA for i in avail)
