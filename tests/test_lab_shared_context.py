"""Testes da FASE 2 PEÇA 3: memória compartilhada dentro da conversa do Lab.

Prova que o bot, ao responder menções (answer_inbox), enxerga os fatos da
memória compartilhada no prompt — e que qualquer problema vira string
vazia (fail-closed), nunca fato inventado, nunca turno quebrado.
"""
import sys
import os
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.lab_shared_context import build_shared_context
from core.lab_memory import LabMemory
import core.lab_v1.group_chat as group_chat


def _mem_with_fact():
    m = LabMemory()
    m.write("CEO", "voz.latencia", "primeiro audio ~1,0s")
    return m


def test_contexto_traz_fato_lab_com_procedencia():
    ctx = build_shared_context(lab_memory=_mem_with_fact())
    assert "MEMÓRIA COMPARTILHADA DO LAB" in ctx
    assert "[lab] voz.latencia" in ctx
    assert "primeiro audio ~1,0s" in ctx
    assert "CEO" in ctx


def test_sem_fonte_ligada_retorna_vazio():
    assert build_shared_context() == ""


def test_memoria_vazia_nao_muda_nada():
    assert build_shared_context(lab_memory=LabMemory()) == ""


def test_fonte_desconhecida_vira_vazio_fail_closed():
    # "marciano" não é fonte conhecida -> spec inválida -> "" (nunca inventa)
    assert build_shared_context(lab_memory=_mem_with_fact(),
                                sources=("marciano",)) == ""


def test_memoria_quebrada_nao_quebra_o_turno():
    class Quebrada:
        def facts(self):
            raise RuntimeError("disco sumiu")
    assert build_shared_context(lab_memory=Quebrada()) == ""


def test_turnos_zara_entram_no_contexto():
    turns = [
        {"role": "assistant", "content": "Kore é a voz principal",
         "engine": "voz", "timestamp": 123.0},
    ]
    ctx = build_shared_context(lab_memory=_mem_with_fact(),
                               zara_turns=lambda: turns,
                               sources=("lab", "zara"))
    assert "[zara]" in ctx
    assert "Kore é a voz principal" in ctx
    assert "[lab] voz.latencia" in ctx


def test_teto_de_chars_trunca_com_marcador():
    m = LabMemory()
    m.write("CEO", "f.caro", "x" * 3000)
    ctx = build_shared_context(lab_memory=m, max_chars=200)
    assert len(ctx) <= 200
    assert ctx.endswith("…(contexto cortado pelo teto)")


def _patch_inbox(monkeypatch):
    captured = {}

    fake_store = types.SimpleNamespace(initialize=lambda: None)
    fake_session = types.SimpleNamespace(team_id="t1")
    fake_agent = types.SimpleNamespace(
        name="Revisor", role=types.SimpleNamespace(value="REVIEWER"))

    monkeypatch.setattr(group_chat, "_require_session",
                        lambda store, sid: fake_session)
    monkeypatch.setattr(group_chat, "_active_member",
                        lambda store, tid, aid: fake_agent)
    monkeypatch.setattr(group_chat, "agent_inbox",
                        lambda store, sid, aid: [{"id": "m1"}])
    monkeypatch.setattr(group_chat, "read_thread",
                        lambda store, sid, limit=20: [
                            {"author": "Engenheiro",
                             "content": "a voz está pronta"}])

    def fake_call_engine(runtime, session, agent, **kw):
        captured.update(kw)
        outcome = types.SimpleNamespace(
            ok=True, result=types.SimpleNamespace(text="entendido"),
            provider_id="fake", model="fake", attempts=[])
        return types.SimpleNamespace(id="r1"), outcome

    monkeypatch.setattr(group_chat, "_call_engine", fake_call_engine)
    monkeypatch.setattr(group_chat, "reply_to",
                        lambda *a, **k: {"id": "resp1"})

    runtime = types.SimpleNamespace(store=fake_store)
    return runtime, captured


def test_answer_inbox_injeta_memoria_no_prompt(monkeypatch):
    runtime, captured = _patch_inbox(monkeypatch)
    group_chat.answer_inbox(runtime, "s1", "a1",
                            shared_memory={"lab_memory": _mem_with_fact()})
    prompt = captured.get("prompt", "")
    assert "MEMÓRIA COMPARTILHADA DO LAB" in prompt
    assert "primeiro audio ~1,0s" in prompt
    assert "a voz está pronta" in prompt  # o fio do grupo continua lá


def test_answer_inbox_sem_memoria_prompt_inalterado(monkeypatch):
    runtime, captured = _patch_inbox(monkeypatch)
    group_chat.answer_inbox(runtime, "s1", "a1")
    prompt = captured.get("prompt", "")
    assert "MEMÓRIA COMPARTILHADA DO LAB" not in prompt
    assert "a voz está pronta" in prompt


def test_answer_inbox_com_memoria_quebrada_funciona_igual(monkeypatch):
    class Quebrada:
        def facts(self):
            raise RuntimeError("disco sumiu")
    runtime, captured = _patch_inbox(monkeypatch)
    # não explode: responde igual a sem memória
    group_chat.answer_inbox(runtime, "s1", "a1",
                            shared_memory={"lab_memory": Quebrada()})
    prompt = captured.get("prompt", "")
    assert "MEMÓRIA COMPARTILHADA DO LAB" not in prompt
    assert "a voz está pronta" in prompt
