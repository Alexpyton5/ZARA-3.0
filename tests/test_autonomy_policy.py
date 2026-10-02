"""FRENTE B — autonomia total, fronteira de dinheiro e auditoria.

ZARA-AUTONOMIA-001 (ação direta sem confirmação) e
ZARA-FRONTEIRA-DINHEIRO-001 (bloqueio por construção).

Tudo com fakes em memória: nenhuma ação real é invocada e o audit log
usa um banco temporário.
"""
from __future__ import annotations

import pytest

import core.audit_log as audit_log_mod
from core.action_confirmation import ConfirmationProof
from core.action_registry import ActionRegistry
from core.audit_log import AuditLog
from core.autonomy_policy import autonomy_enabled, autonomy_mode
from core.money_boundary import BLOCKED_BY_CONSTRUCTION, is_money_action


def _isolated_registry() -> ActionRegistry:
    registry = object.__new__(ActionRegistry)
    registry._initialized = False
    ActionRegistry.__init__(registry)
    return registry


def _grant_ok(monkeypatch, tmp_path):
    """Portão do PC exige grant WhatsApp válido (ordem do Alex, 02/10/2026)."""
    from core import supercerebro_grant as sg
    p = tmp_path / "whatsapp_grant.json"
    sg.write_grant(minutes=30, path=p)
    monkeypatch.setenv("ZARA_WHATSAPP_GRANT_PATH", str(p))


@pytest.fixture
def temp_audit(tmp_path, monkeypatch):
    log = AuditLog(db_path=tmp_path / "audit.db")
    monkeypatch.setattr(audit_log_mod, "audit_log", lambda: log)
    return log


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ZARA_AUTONOMY", raising=False)


# ---------------------------------------------------------------- B2: ação direta


def test_autonomy_is_on_by_default():
    assert autonomy_mode() == "sim-sempre"
    assert autonomy_enabled() is True


def test_legacy_ask_mode_disables_autonomy(monkeypatch):
    monkeypatch.setenv("ZARA_AUTONOMY", "perguntar")
    assert autonomy_enabled() is False


def test_medium_risk_executes_directly_without_confirm():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register("fake_medium", lambda: calls.append("ran") or "done", risk="MEDIUM")

    result = registry.execute("fake_medium")

    assert result.success
    assert calls == ["ran"]


def test_high_risk_executes_directly_without_challenge():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register("fake_destructive", lambda command: calls.append(command) or "done", risk="HIGH")

    result = registry.execute("fake_destructive", command="echo direto")

    assert result.success
    assert calls == ["echo direto"]
    assert result.data is None or result.data.get("status") != "CONFIRMATION_REQUIRED"


def test_legacy_mode_still_issues_high_risk_challenge(monkeypatch):
    monkeypatch.setenv("ZARA_AUTONOMY", "perguntar")
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "terminal",
        lambda command: calls.append(command) or "done",
        risk="HIGH",
    )

    result = registry.execute("terminal", command="echo legado")

    assert not result.success
    assert result.error == "CONFIRMATION_REQUIRED"
    assert calls == []


def test_pc_control_runs_with_whatsapp_grant_in_autonomy_mode(monkeypatch, tmp_path):
    """Ordem do Alex (02/10/2026): PC só com grant via WhatsApp; auditado pelo registry."""
    _grant_ok(monkeypatch, tmp_path)
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "fake_pc", lambda: calls.append("ran"), risk="HIGH", capability="PC_CONTROL"
    )

    result = registry.execute("fake_pc")

    assert result.success
    assert calls == ["ran"]


# ------------------------------------------------- B2: fronteira de dinheiro


def test_money_action_name_is_blocked_by_construction():
    blocked, reason = is_money_action("fazer_pagamento_pix")
    assert blocked
    assert reason.startswith("nome-da-acao-indica-dinheiro")


def test_money_signals_in_params_block_generic_actions():
    blocked, reason = is_money_action(
        "terminal", {"command": "abrir https://checkout.stripe.com/pay/xyz"}
    )
    assert blocked
    assert reason.startswith("parametro-indica-dinheiro")


def test_card_number_in_params_is_blocked():
    blocked, _ = is_money_action("browser_eval", {"script": "cartao 4111 1111 1111 1111"})
    assert blocked


def test_normal_actions_are_not_money_blocked():
    for name, params in [
        ("files_list", {"path": "C:/Users/alexp/Downloads"}),
        ("terminal", {"command": "echo oi"}),
        ("youtube_search", {"query": "futevolei"}),
    ]:
        blocked, _ = is_money_action(name, params)
        assert not blocked, name


def test_money_block_list_is_explicit():
    assert len(BLOCKED_BY_CONSTRUCTION) >= 5
    joined = " ".join(BLOCKED_BY_CONSTRUCTION).lower()
    assert "pix" in joined and "cart" in joined


def test_money_action_blocked_even_in_autonomy_mode():
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register(
        "fazer_pagamento",
        lambda valor: calls.append(valor) or "pago",
        risk="HIGH",
    )

    result = registry.execute("fazer_pagamento", valor="10.00", confirm=True)

    assert not result.success
    assert "BLOQUEADA" in result.error
    assert calls == []


def test_money_action_blocked_even_with_confirmation_proof(monkeypatch):
    """Nem o desafio one-shot legado contorna a fronteira de dinheiro."""
    monkeypatch.setenv("ZARA_AUTONOMY", "perguntar")
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register("checkout_finalizar", lambda: calls.append("ran"), risk="HIGH")

    forged = ConfirmationProof(confirmation_id="x" * 32, action_fingerprint="hmac-sha256:abc")
    result = registry.execute_confirmed(
        "checkout_finalizar", forged.confirmation_id, forged.action_fingerprint
    )

    assert not result.success
    assert "BLOQUEADA" in result.error
    assert calls == []


def test_money_blocked_before_challenge_is_issued(monkeypatch):
    """Ação de dinheiro nunca gera desafio de confirmação (modo legado)."""
    monkeypatch.setenv("ZARA_AUTONOMY", "perguntar")
    registry = _isolated_registry()
    registry.register("pagar_boleto", lambda: "pago", risk="HIGH")

    result = registry.execute("pagar_boleto", codigo="123")

    assert not result.success
    assert "BLOQUEADA" in result.error
    assert result.data is None or "confirmation" not in (result.data or {})


def test_money_policy_failure_blocks_action(monkeypatch):
    """Policy errors fail closed instead of silently allowing an action."""
    import core.money_boundary as money_boundary

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("policy unavailable")

    monkeypatch.setattr(money_boundary, "is_money_action", unavailable)
    registry = _isolated_registry()
    calls: list[str] = []
    registry.register("computer_click", lambda: calls.append("ran"), risk="LOW", capability="PC_CONTROL")

    result = registry.execute("computer_click")

    assert not result.success
    assert "BLOQUEADA" in result.error
    assert calls == []


# ---------------------------------------------------------------- B3: auditoria


def test_autonomous_execution_is_audited(temp_audit):
    registry = _isolated_registry()
    registry.register("fake_medium", lambda: "done", risk="MEDIUM")

    registry.execute("fake_medium")

    rows = temp_audit.recent(10)
    assert rows, "audit log vazio: acao autonoma sem rastro nao vale"
    row = rows[0]
    assert row["action"] == "fake_medium"
    assert row["outcome"] == "success"
    assert row["autonomous"] == 1
    assert row["why"] == "autonomia:acao-direta"


def test_money_block_is_audited(temp_audit):
    registry = _isolated_registry()
    registry.register("fazer_pagamento", lambda: "pago", risk="HIGH")

    registry.execute("fazer_pagamento", valor="10.00")

    rows = temp_audit.recent(10)
    assert rows
    row = rows[0]
    assert row["action"] == "fazer_pagamento"
    assert row["outcome"] == "blocked"
    assert row["why"] == "bloqueio:dinheiro"


def test_audit_never_logs_raw_params(temp_audit):
    registry = _isolated_registry()
    registry.register("fake_low", lambda secret: "done", risk="LOW")

    registry.execute("fake_low", secret="segredo-super-sensivel-123")

    rows = temp_audit.recent(10)
    assert rows
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert "segredo-super-sensivel-123" not in blob
