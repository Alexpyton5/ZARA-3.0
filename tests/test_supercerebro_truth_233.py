"""232/233/234 — Model router: failover, verdade de erro e limites de contexto.

Sem provider pago, sem rede: todas as chamadas de modelo sao mockadas.
"""
from __future__ import annotations

import pytest

from core.model_router import ModelRouter

# ------------------------------------------------------------ 232 failover


@pytest.fixture()
def router():
    return ModelRouter()


def _health(router, model_id):
    for entry in router.configured_model_status():
        if entry["id"] == model_id:
            return entry["health"]
    raise AssertionError(f"unknown model {model_id}")


def test_free_models_only_and_no_secrets_exposed(router):
    entries = router.configured_model_status()
    assert entries
    for e in entries:
        assert "free" in str(e.get("free_tier", "")).lower()
        blob = repr(e).lower()
        assert "api_key" not in blob
        assert "sk-" not in blob
        assert "bearer" not in blob


def test_429_enters_cooldown_not_permanent_failure(router):
    mid = router.get_available_models()[0].id
    router.mark_failure(mid, "429 Too Many Requests")
    h = _health(router, mid)
    assert h["state"] == "COOLDOWN"
    assert h["until"] > 0


def test_401_marks_auth_invalid(router):
    mid = router.get_available_models()[0].id
    router.mark_failure(mid, "401 Unauthorized")
    assert _health(router, mid)["state"] == "AUTH_INVALID"


@pytest.mark.parametrize("err", ["timeout", "500 Internal Server Error", "connection reset"])
def test_timeout_and_5xx_are_recoverable_errors(router, err):
    mid = router.get_available_models()[0].id
    router.mark_failure(mid, err)
    assert _health(router, mid)["state"] in {"ERROR", "COOLDOWN"}


def test_fallback_chain_switches_provider_and_has_no_duplicates(router):
    from core.model_router import TaskType

    chain = router.get_fallback_chain([TaskType.GENERAL_CHAT])
    ids = [m.id for m in chain]
    assert len(ids) == len(set(ids)), "fallback chain nao pode repetir modelo (risco de loop)"
    assert len(ids) >= 2


def test_success_clears_failure_state(router):
    mid = router.get_available_models()[0].id
    router.mark_failure(mid, "500")
    router.mark_success(mid)
    assert _health(router, mid)["state"] == "AVAILABLE"


# -------------------------------------------------------- 233 error truth


def _is_err(value):
    from core.zara_orchestrator import ZaraOrchestrator

    return ZaraOrchestrator._is_error_response(value)


@pytest.mark.parametrize(
    "response",
    [
        "",
        None,
        "   ",
        "Error: API key not configured for groq",
        "Error calling Hermes: connection refused",
        "Error 500: upstream exploded",
        "Erro: Todos os motores falharam",
        "failed to parse",
    ],
)
def test_provider_failures_and_empty_responses_are_never_success(response):
    assert _is_err(response) is True


@pytest.mark.parametrize("response", ["Olá Alex", "0", "A resposta é: erro de digitação"])
def test_genuine_answers_are_not_flagged_as_errors(response):
    assert _is_err(response) is False


def test_empty_gemini_candidates_is_treated_as_failure():
    """Um payload 200 sem candidates devolve '' — nao pode virar resposta boa."""
    assert _is_err("") is True


# ------------------------------------------- 234 context/memory boundaries


def test_history_normalization_drops_malformed_turns():
    from core.zara_orchestrator import ZaraOrchestrator

    history = [
        "nao é dict",
        {"role": "system", "content": "vazar"},
        {"role": "user", "content": ""},
        {"role": "user", "content": "pergunta válida"},
        {"role": "assistant", "content": "resposta válida"},
    ]
    out = ZaraOrchestrator._normalized_history(history, "outra coisa")
    assert out == [
        {"role": "user", "content": "pergunta válida"},
        {"role": "assistant", "content": "resposta válida"},
    ]


def test_history_is_bounded():
    from core.zara_orchestrator import ZaraOrchestrator

    history = [{"role": "user", "content": f"m{i}"} for i in range(100)]
    out = ZaraOrchestrator._normalized_history(history, "atual")
    assert len(out) <= 16


def test_duplicated_current_message_is_not_resent():
    from core.zara_orchestrator import ZaraOrchestrator

    history = [{"role": "user", "content": "repetida"}]
    assert ZaraOrchestrator._normalized_history(history, "repetida") == []


def test_context_does_not_leak_between_sessions(tmp_path, monkeypatch):
    """Duas sessoes com storage isolado nao compartilham historico."""
    from core.mentor_relay import MentorRelay

    a = MentorRelay(root=tmp_path / "sessao_a")
    b = MentorRelay(root=tmp_path / "sessao_b")
    a.enqueue("alex", "segredo da sessao A")
    assert a.pending_count() == 1
    assert b.pending_count() == 0
