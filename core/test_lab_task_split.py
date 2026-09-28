"""Testes do protocolo de divisao de tarefa (core/lab_task_split.py).

Prova a mecanica de "tarefa dividida entre assentos" sem chamar modelo
nenhum: usa a Task real de core.lab_v1.domain. Roda do raiz do app.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lab_task_split import (
    MAX_CHILDREN,
    SplitPart,
    TaskSplitError,
    complete_child,
    fail_child,
    parent_outcome,
    split_task,
)
from core.lab_v1.domain import Task, TaskState


def _mother(**kw):
    base = dict(
        id="mae-001",
        session_id="sess-1",
        title="Construir o painel",
        instruction="faca o painel",
        created_by_agent_id="ceo-1",
        assigned_agent_id="ceo-1",
        state=TaskState.ASSIGNED,
        budget_usd=1.00,
        max_turns=5,
    )
    base.update(kw)
    return Task(**base)


def _part(**kw):
    base = dict(
        title="Frontend",
        instruction="monte a tela",
        acceptance="tela renderiza",
        assigned_agent_id="eng-1",
        budget_usd=0.40,
        max_turns=3,
    )
    base.update(kw)
    return SplitPart(**base)


def _clock():
    t = [1000.0]
    def tick():
        t[0] += 1.0
        return t[0]
    return tick


def test_split_cria_filhas_na_mesma_sessao():
    mae = _mother()
    filhas = split_task(mae, [_part(), _part(title="Backend", assigned_agent_id="eng-2", budget_usd=0.40)], "ceo-1")
    assert len(filhas) == 2
    assert all(f.session_id == "sess-1" for f in filhas)
    assert all(f.created_by_agent_id == "ceo-1" for f in filhas)
    assert all(f.state == TaskState.ASSIGNED for f in filhas)
    assert filhas[0].assigned_agent_id == "eng-1"
    assert filhas[1].assigned_agent_id == "eng-2"
    assert "[parte de mae-001]" in filhas[0].instruction


def test_split_ids_unicos():
    mae = _mother()
    filhas = split_task(mae, [_part(budget_usd=0.2), _part(title="B", assigned_agent_id="e2", budget_usd=0.2)], "ceo-1")
    assert filhas[0].id != filhas[1].id


def test_split_soma_igual_ao_budget_ok():
    mae = _mother(budget_usd=1.00)
    filhas = split_task(mae, [_part(budget_usd=0.6), _part(title="B", assigned_agent_id="e2", budget_usd=0.4)], "ceo-1")
    assert len(filhas) == 2


def test_split_soma_acima_do_budget_rejeita():
    mae = _mother(budget_usd=1.00)
    try:
        split_task(mae, [_part(budget_usd=0.7), _part(title="B", assigned_agent_id="e2", budget_usd=0.7)], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("devia rejeitar soma acima do budget da mae")


def test_split_mae_created_nao_divide():
    mae = _mother(state=TaskState.CREATED)
    try:
        split_task(mae, [_part()], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("mae CREATED nao pode ser dividida")


def test_split_mae_completed_nao_divide():
    mae = _mother(state=TaskState.COMPLETED)
    try:
        split_task(mae, [_part()], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("mae COMPLETED nao pode ser dividida")


def test_split_sem_partes_rejeita():
    try:
        split_task(_mother(), [], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("divisao vazia devia ser rejeitada")


def test_split_muitas_partes_rejeita():
    partes = [_part(title=f"P{i}", assigned_agent_id=f"e{i}", budget_usd=0.01) for i in range(MAX_CHILDREN + 1)]
    try:
        split_task(_mother(budget_usd=10.0), partes, "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError(f"mais de {MAX_CHILDREN} partes devia ser rejeitado")


def test_split_parte_sem_responsavel_rejeita():
    try:
        split_task(_mother(), [_part(assigned_agent_id="  ")], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("parte sem responsavel devia ser rejeitada")


def test_split_parte_sem_budget_rejeita():
    try:
        split_task(_mother(), [_part(budget_usd=0)], "ceo-1")
    except TaskSplitError:
        return
    raise AssertionError("parte com budget zero devia ser rejeitada")


def test_so_responsavel_conclui():
    mae = _mother()
    (filha,) = split_task(mae, [_part()], "ceo-1")
    try:
        complete_child(filha, "pronto", "intruso-9")
    except TaskSplitError:
        return
    raise AssertionError("outro agente nao pode concluir a filha")


def test_concluir_duas_vezes_rejeita():
    mae = _mother()
    (filha,) = split_task(mae, [_part()], "ceo-1")
    complete_child(filha, "pronto", "eng-1")
    try:
        complete_child(filha, "de novo", "eng-1")
    except TaskSplitError:
        return
    raise AssertionError("concluir 2x devia ser rejeitado")


def test_filha_falhou_mae_falha_com_motivo():
    mae = _mother()
    filhas = split_task(mae, [_part(budget_usd=0.4), _part(title="B", assigned_agent_id="e2", budget_usd=0.4)], "ceo-1")
    complete_child(filhas[0], "tela pronta", "eng-1")
    fail_child(filhas[1], "banco fora do ar", "e2")
    estado, resumo = parent_outcome(filhas)
    assert estado == TaskState.FAILED
    assert "banco fora do ar" in resumo


def test_todas_prontas_mae_completa_agregado():
    mae = _mother()
    filhas = split_task(mae, [_part(budget_usd=0.4), _part(title="B", assigned_agent_id="e2", budget_usd=0.4)], "ceo-1")
    complete_child(filhas[0], "tela pronta", "eng-1")
    complete_child(filhas[1], "api pronta", "e2")
    estado, resumo = parent_outcome(filhas)
    assert estado == TaskState.COMPLETED
    assert "tela pronta" in resumo and "api pronta" in resumo


def test_pendentes_mae_segue_running():
    mae = _mother()
    filhas = split_task(mae, [_part(budget_usd=0.4), _part(title="B", assigned_agent_id="e2", budget_usd=0.4)], "ceo-1")
    complete_child(filhas[0], "tela pronta", "eng-1")
    estado, resumo = parent_outcome(filhas)
    assert estado == TaskState.RUNNING
    assert "1/2" in resumo


def test_journal_auditavel_com_relogio_injetado():
    mae = _mother()
    journal = []
    clock = _clock()
    filhas = split_task(mae, [_part()], "ceo-1", journal=journal, clock=clock)
    complete_child(filhas[0], "ok", "eng-1", journal=journal, clock=clock)
    eventos = [e["event"] for e in journal]
    assert eventos == ["split", "complete"]
    assert journal[0]["ts"] < journal[1]["ts"]
    assert journal[0]["parent_id"] == "mae-001"


def test_roundtrip_completo_duas_filhas():
    # O cenario da Fase B: CEO divide, dois assentos entregam, mae fecha.
    mae = _mother()
    journal = []
    filhas = split_task(
        mae,
        [
            _part(title="Tela", instruction="monte a tela", acceptance="renderiza",
                  assigned_agent_id="eng-1", budget_usd=0.5, max_turns=3),
            _part(title="Revisao", instruction="revise a tela", acceptance="sem erro",
                  assigned_agent_id="rev-1", budget_usd=0.3, max_turns=2),
        ],
        "ceo-1",
        journal=journal,
    )
    complete_child(filhas[0], "tela no ar", "eng-1", journal=journal)
    complete_child(filhas[1], "aprovado", "rev-1", journal=journal)
    estado, resumo = parent_outcome(filhas)
    assert estado == TaskState.COMPLETED
    assert len(journal) == 4  # 2 splits + 2 completes
    assert "tela no ar" in resumo and "aprovado" in resumo


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falhas = 0
    for t in testes:
        try:
            t()
            print(f"OK  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"FALHOU {t.__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} verdes")
    raise SystemExit(1 if falhas else 0)
