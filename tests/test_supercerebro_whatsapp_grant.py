"""Testes do grant via WhatsApp (ZARA-WHATSAPP-GRANT-001).

A trava do Supercerebro continua FAIL-CLOSED: o grant e so uma segunda forma
de abrir a mesma trava, com prazo curto, e qualquer arquivo ausente, expirado
ou malformado nega.
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import supercerebro_grant as sg  # noqa: E402
from core.action_registry import (  # noqa: E402
    ActionResult,
    ActionSpec,
    action,
    get_registry,
)


@action(
    name="grant_test_noop",
    capability="PC_CONTROL",
    description="noop inofensivo so para testar o gate do grant",
)
def _grant_test_noop() -> ActionResult:
    return ActionResult(True, output="noop-ok")


@pytest.fixture()
def grant_file(tmp_path, monkeypatch):
    p = tmp_path / "whatsapp_grant.json"
    monkeypatch.setenv("ZARA_WHATSAPP_GRANT_PATH", str(p))
    return p


@pytest.fixture()
def registry():
    reg = get_registry()
    reg.pc_control_allowed = False
    yield reg
    reg.pc_control_allowed = False


def _pc_spec():
    return ActionSpec(
        name="fake_pc_control",
        description="t",
        parameters={},
        capability="PC_CONTROL",
    )


def _payload(**over):
    base = {
        "granted_at": time.time(),
        "expires_at": time.time() + 1800,
        "granted_via": "whatsapp",
        "scope": "use-computer",
        "note": "teste",
    }
    base.update(over)
    return base


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


# ------------------------- check_whatsapp_grant -------------------------

def test_sem_arquivo_nega(grant_file):
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "no-grant-file"


def test_grant_valido_permite(grant_file):
    _write(grant_file, _payload())
    allowed, reason, info = sg.check_whatsapp_grant()
    assert allowed is True
    assert reason == "ok"
    assert info["granted_via"] == "whatsapp"


def test_grant_expirado_nega(grant_file):
    _write(grant_file, _payload(granted_at=time.time() - 3700,
                               expires_at=time.time() - 100))
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-expired"


def test_grant_malformado_nega(grant_file):
    grant_file.write_text("{isso nao e json", encoding="utf-8")
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-malformed"


def test_grant_json_nao_dict_nega(grant_file):
    grant_file.write_text("[1, 2, 3]", encoding="utf-8")
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-malformed"


def test_grant_via_errada_nega(grant_file):
    _write(grant_file, _payload(granted_via="email"))
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-via-mismatch"


def test_grant_scope_errado_nega(grant_file):
    _write(grant_file, _payload(scope="tudo"))
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-scope-mismatch"


def test_grant_expiry_ilegivel_nega(grant_file):
    _write(grant_file, _payload(expires_at="amanha de manha"))
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "grant-malformed-expiry"


def test_grant_iso_com_timezone_funciona(grant_file):
    _write(grant_file, _payload(
        granted_at="2026-09-28T19:00:00-03:00",
        expires_at="2036-09-28T19:00:00-03:00",
    ))
    allowed, _, _ = sg.check_whatsapp_grant()
    assert allowed is True


# ------------------------- write_grant / revoke -------------------------

def test_write_grant_cria_arquivo_valido(grant_file):
    sg.write_grant(minutes=30, note="teste", path=grant_file)
    allowed, reason, info = sg.check_whatsapp_grant()
    assert allowed is True
    assert reason == "ok"
    assert info["note"] == "teste"
    data = json.loads(grant_file.read_text(encoding="utf-8"))
    assert data["granted_via"] == "whatsapp"
    assert data["scope"] == "use-computer"


@pytest.mark.parametrize("minutes", [0, -5, 99999])
def test_write_grant_recusa_prazo_invalido(grant_file, minutes):
    with pytest.raises(ValueError):
        sg.write_grant(minutes=minutes, path=grant_file)
    assert not grant_file.exists()


def test_revoke_grant_encerra_janela(grant_file):
    sg.write_grant(minutes=30, path=grant_file)
    assert sg.check_whatsapp_grant()[0] is True
    assert sg.revoke_grant(path=grant_file) is True
    allowed, reason, _ = sg.check_whatsapp_grant()
    assert allowed is False
    assert reason == "no-grant-file"


# ------------------------- gate do registry -------------------------

def test_gate_permite_com_grant_valido(registry, grant_file):
    sg.write_grant(minutes=30, path=grant_file)
    blocked, decision = registry._check_action_gates("grant_test_noop", _pc_spec(), {})
    assert blocked is None, "grant valido deveria liberar o gate"


def test_gate_nega_com_grant_expirado(registry, grant_file):
    _write(grant_file, _payload(granted_at=time.time() - 3700,
                               expires_at=time.time() - 100))
    blocked, decision = registry._check_action_gates("grant_test_noop", _pc_spec(), {})
    assert blocked is not None
    assert blocked.success is False
    assert "Superc" in blocked.error


def test_gate_nega_sem_grant(registry, grant_file):
    blocked, decision = registry._check_action_gates("grant_test_noop", _pc_spec(), {})
    assert blocked is not None
    assert blocked.success is False
    assert "Superc" in blocked.error


def test_execute_noop_com_grant_valido(registry, grant_file):
    sg.write_grant(minutes=30, path=grant_file)
    result = registry.execute("grant_test_noop")
    assert result.success is True
    assert result.output == "noop-ok"


def test_execute_noop_negado_sem_grant(registry, grant_file):
    result = registry.execute("grant_test_noop")
    assert result.success is False
    assert "Superc" in result.error


def test_chave_manual_nao_burla_grant_whatsapp(registry, grant_file):
    """Ordem do Alex (02/10/2026): controle do PC SÓ com autorização via WhatsApp.
    A chave manual LIGADA não burla o portão."""
    registry.pc_control_allowed = True
    result = registry.execute("grant_test_noop")
    assert result.success is False
    assert "Superc" in result.error
