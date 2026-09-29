"""Testes da FRENTE A - agente de use-computer (observe -> age -> verifica).

Sem hardware real: o registry e trocado por um fake. A trava fail-closed e
testada de verdade (pc_control_allowed=False -> recusa sem executar nada).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.action_registry import ActionResult  # noqa: E402
from core import computer_agent as ca  # noqa: E402


class FakeRegistry:
    """Registry falso: trava configuravel + telas OCR enfileiradas."""

    def __init__(self, pc_control_allowed=True):
        self.pc_control_allowed = pc_control_allowed
        self.calls = []
        self._screens = []

    def queue_screen(self, words):
        self._screens.append(frozenset(words))

    def execute(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == "computer_foreground":
            return ActionResult(True, data={
                "hwnd": 111, "title": "Bloco de Notas",
                "rect": {"left": 0, "top": 0, "right": 800, "bottom": 600},
            })
        if name == "vision_read_screen":
            words = self._screens.pop(0) if self._screens else frozenset()
            return ActionResult(
                True, output="ok",
                data={"words": [{"text": w} for w in words],
                      "text": " ".join(sorted(words))},
            )
        return ActionResult(True, output="ok", verificado=True)


@pytest.fixture
def fake_reg(monkeypatch):
    reg = FakeRegistry(pc_control_allowed=True)
    monkeypatch.setattr(ca, "get_registry", lambda: reg)
    monkeypatch.setattr(ca._cc, "computer_audit", lambda *a, **k: None)
    return reg


@pytest.fixture
def events():
    seen = []

    def _listener(event, payload):
        seen.append((event, payload))

    ca.add_event_listener(_listener)
    yield seen
    ca.remove_event_listener(_listener)


# --- trava fail-closed ---------------------------------------------------------

def test_trava_fail_closed_recusa_sem_executar_nada(monkeypatch, events):
    reg = FakeRegistry(pc_control_allowed=False)

    def _boom(name, **kwargs):
        raise AssertionError("nada deveria executar com a trava desligada")

    reg.execute = _boom
    monkeypatch.setattr(ca, "get_registry", lambda: reg)
    monkeypatch.setattr(ca._cc, "computer_audit", lambda *a, **k: None)

    result = ca.run_goal("abra o bloco de notas")

    assert result["refused"] is True
    assert result["success"] is False
    assert "Supercerebro" in result["error"]
    assert result["steps"] == []
    assert [e for e, _ in events] == ["computer_agent_started", "computer_agent_stopped"]


def test_simbolos_banidos_nao_existem_no_agente():
    import pathlib
    import re as _re
    src = pathlib.Path(ca.__file__).read_text(encoding="utf-8")
    # Tira o docstring do modulo: mencionar os simbolos num aviso (como faz
    # supercerebro_grant.py) nao e reimplementar. O que nao pode e existir
    # codigo de verdade com esses nomes.
    codigo = _re.sub(r'^""".*?"""', "", src, count=1, flags=_re.DOTALL)
    for banned in ("work_mode_active", "work_mode_sentinel", "_watch_supercerebro_work_mode"):
        assert banned not in codigo, f"simbolo banido reimplementado: {banned}"


# --- gatilhos ------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("use o computador para abrir o bloco de notas", "abrir o bloco de notas"),
    ("Usa o computador para clicar em 500 300", "clicar em 500 300"),
    ("no computador, digite 'oi'", "digite 'oi'"),
    ("zara, use o computador para abrir o paint", "abrir o paint"),
    ("abra o bloco de notas", None),
    ("use o computador para", None),
    ("", None),
])
def test_extract_goal(texto, esperado):
    assert ca.extract_goal(texto) == esperado


# --- parser estendido (clique em texto nomeado / aguardar texto) -----------------

def test_parser_clique_em_texto_nomeado():
    plan, refusal = ca._cc.parse_computer_command("clique em 'Salvar'")
    assert refusal == ""
    assert plan[0]["action"] == "vision_click_text"
    assert plan[0]["params"]["text"] == "salvar"


def test_parser_aguarde_texto():
    plan, refusal = ca._cc.parse_computer_command("aguarde o texto 'pronto'")
    assert refusal == ""
    assert plan[0]["action"] == "vision_wait_for_text"
    assert plan[0]["params"]["text"] == "pronto"


def test_parser_multiplos_passos_com_novos_verbos():
    plan, refusal = ca._cc.parse_computer_command(
        "abra o bloco de notas e depois clique em 'Salvar'")
    assert refusal == "", refusal
    assert [p["action"] for p in plan] == ["os_app", "vision_click_text"]


# --- fluxo de verificacao -------------------------------------------------------

def test_fluxo_ok_com_verificacao_na_tela(fake_reg, events):
    fake_reg.queue_screen({"menu", "arquivo"})
    fake_reg.queue_screen({"menu", "arquivo", "salvo"})  # mudou -> clique verificado

    result = ca.run_goal("clique em 500 300")

    assert result["success"] is True
    assert result["verified"] is True
    assert len(result["steps"]) == 1
    assert result["steps"][0]["outcome"] == "ok"
    assert result["steps"][0]["action"] == "computer_click"
    assert [e for e, _ in events] == ["computer_agent_started", "computer_agent_stopped"]
    stopped = events[1][1]
    assert stopped["success"] is True


def test_recuperacao_funciona_na_segunda_tentativa(fake_reg):
    fake_reg.queue_screen({"a"})
    fake_reg.queue_screen({"a"})          # 1a tentativa: sem efeito
    fake_reg.queue_screen({"a"})
    fake_reg.queue_screen({"a", "z"})     # 2a tentativa (re-grounding): mudou

    result = ca.run_goal("clique em 500 300")

    assert result["success"] is True
    assert result["steps"][0]["outcome"] == "recuperado"
    clicks = [c for c in fake_reg.calls if c[0] == "computer_click"]
    assert len(clicks) == 2  # exatamente 1 recuperacao, nao mais


def test_aborta_quando_verificacao_falha_duas_vezes(fake_reg):
    for _ in range(4):
        fake_reg.queue_screen({"sempre", "igual"})  # tela nunca muda

    result = ca.run_goal("clique em 500 300")

    assert result["success"] is False
    assert result["travou_no_passo"] == 1
    assert "passo 1" in result["error"]
    assert result["steps"][0]["outcome"] == "falhou"
    clicks = [c for c in fake_reg.calls if c[0] == "computer_click"]
    assert len(clicks) == 2  # tentou 1x + 1 recuperacao, depois abortou


def test_objetivo_desconhecido_nao_executa_nada(fake_reg):
    result = ca.run_goal("faca um bolo de cenoura")

    assert result["success"] is False
    assert "Não entendi" in result["error"]
    assert result["steps"] == []
    assert fake_reg.calls == []


def test_erro_interno_nunca_levanta_excecao(monkeypatch, events):
    def _boom():
        raise RuntimeError("registry sumiu")

    monkeypatch.setattr(ca, "get_registry", _boom)
    monkeypatch.setattr(ca._cc, "computer_audit", lambda *a, **k: None)

    result = ca.run_goal("clique em 500 300")

    assert result["success"] is False
    assert "Erro interno" in result["error"]
    assert [e for e, _ in events] == ["computer_agent_started", "computer_agent_stopped"]


def test_audit_nao_vaza_texto_digitado(fake_reg):
    seen = []
    fake_reg.queue_screen({"a"})
    fake_reg.queue_screen({"b"})
    import json as _json

    def _audit(action, outcome, **details):
        seen.append(_json.dumps(details, ensure_ascii=False))

    import types
    fake_cc = types.SimpleNamespace(
        parse_computer_command=ca._cc.parse_computer_command,
        computer_audit=_audit,
        _HWND=ca._cc._HWND,
        _CENTER=ca._cc._CENTER,
        _resolve_focus_named=ca._cc._resolve_focus_named,
    )
    import unittest.mock as _mock
    with _mock.patch.object(ca, "_cc", fake_cc):
        result = ca.run_goal("digite 'senha-secreta-123'")

    blob = " ".join(seen)
    assert "senha-secreta-123" not in blob
    assert result["success"] is True


# --- resumo para o chat ----------------------------------------------------------

def test_reply_recusa_fala_do_supercerebro():
    reply = ca.reply_for_result({"refused": True, "steps": [], "success": False,
                                 "verified": False, "error": "x", "goal": "y"})
    assert "Supercerebro" in reply
    assert "Nao mexi em nada" in reply


def test_reply_sucesso_curto_e_simples():
    reply = ca.reply_for_result({"refused": False, "success": True, "verified": True,
                                 "steps": [{"outcome": "ok"}, {"outcome": "recuperado"}],
                                 "error": None, "goal": "clicar"})
    assert reply.startswith("Pronto")
    assert "2 passo" in reply
