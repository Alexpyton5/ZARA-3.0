"""Testes da FRENTE 4 — parser PT-BR e trava do Supercerebro (sem enfraquecer nada)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.actions import computer_command as cc  # noqa: E402
from core.action_registry import ActionResult, ActionSpec, get_registry  # noqa: E402


def plan_of(text):
    plan, refusal = cc.parse_computer_command(text)
    assert refusal == "", refusal
    assert plan is not None
    return plan


def test_abrir_bloco_de_notas():
    plan = plan_of("abra o bloco de notas")
    assert plan == [{"action": "os_app", "params": {"app": "notepad"}}]


def test_fechar_bloco_de_notas():
    plan = plan_of("fechar o bloco de notas")
    assert plan == [{"action": "__close_named__", "params": {"query": "bloco de notas"}}]


def test_fechar_janela_exige_alvo_unico(monkeypatch):
    class FakeRegistry:
        def execute(self, name, **params):
            if name == "computer_list_windows":
                return ActionResult(True, data={"windows": [
                    {"hwnd": 10, "title": "Sem título - Bloco de Notas"},
                    {"hwnd": 11, "title": "Notas - Bloco de Notas"},
                ]})
            raise AssertionError(f"Não deveria executar {name} {params}")

    monkeypatch.setattr(cc, "get_registry", lambda: FakeRegistry())
    result = cc._resolve_close_named("bloco de notas")
    assert not result.success
    assert "2 janelas" in result.error


def test_fechar_janela_despacha_e_exige_resultado(monkeypatch):
    calls = []

    class FakeRegistry:
        def execute(self, name, **params):
            calls.append((name, params))
            if name == "computer_list_windows":
                return ActionResult(True, data={"windows": [{"hwnd": 10, "title": "Sem título - Bloco de Notas"}]})
            if name == "window_close":
                return ActionResult(True, output="Janela fechada e verificada.", verificado=True)
            raise AssertionError(name)

    monkeypatch.setattr(cc, "get_registry", lambda: FakeRegistry())
    result = cc._resolve_close_named("bloco de notas")
    assert result.success and result.verificado
    assert calls[-1] == ("window_close", {"hwnd": 10})


def test_clique_coordenadas():
    plan = plan_of("clique em 500 300")
    assert plan[0]["action"] == "computer_click"
    assert plan[0]["params"]["x"] == 500
    assert plan[0]["params"]["y"] == 300


def test_digite_com_aspas():
    plan = plan_of('digite "ola mundo"')
    assert plan[0]["action"] == "computer_type_text"
    assert plan[0]["params"]["text"] == "ola mundo"


def test_pressione_enter():
    plan = plan_of("pressione enter")
    assert plan[0]["action"] == "computer_press_key"
    assert plan[0]["params"]["key"] == "enter"


def test_role_para_baixo():
    plan = plan_of("role para baixo 3")
    assert plan[0]["action"] == "computer_scroll"
    assert plan[0]["params"]["steps"] == -3


def test_traga_janela_para_frente():
    plan = plan_of("traga o chrome para frente")
    assert plan[0]["action"] == "__focus_named__"
    assert plan[0]["params"]["query"] == "chrome"


def test_multiplos_passos():
    plan = plan_of("abra o bloco de notas e digite 'oi'")
    assert len(plan) == 2
    assert plan[0]["action"] == "os_app"
    assert plan[1]["action"] == "computer_type_text"


def test_texto_com_e_dentro_de_aspas_nao_quebra():
    plan = plan_of("digite 'pao e queijo'")
    assert len(plan) == 1
    assert plan[0]["params"]["text"] == "pao e queijo"


def test_desconhecido_recusa_honesta():
    plan, refusal = cc.parse_computer_command("faca um bolo de cenoura")
    assert plan is None
    assert "Não entendi" in refusal


def test_sem_grant_bloqueia_controle():
    """Ordem do Alex (02/10/2026): sem grant via WhatsApp, o PC não é controlado."""
    reg = get_registry()
    spec = ActionSpec(name="fake_pc", description="", parameters={}, capability="PC_CONTROL")
    blocked, decision = reg._check_action_gates("fake_pc", spec, {})
    assert blocked is not None
    assert blocked.success is False
    assert "Superc" in blocked.error


def test_auditoria_nao_vaza_texto():
    cc.computer_audit("computer_type_text", "success", window="Bloco de Notas", chars=11)
    path = cc._audit_path()
    assert path.exists()
    last = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    entry = json.loads(last)
    assert entry["action"] == "computer_type_text"
    assert entry["outcome"] == "success"
    assert "chars" in entry
    assert "text" not in entry
    blob = json.dumps(entry, ensure_ascii=False)
    assert "segredo" not in blob
