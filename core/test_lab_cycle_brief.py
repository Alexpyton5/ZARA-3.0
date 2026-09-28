"""Testes do boletim do ciclo da CEO — lab_cycle_brief.

Runner próprio (padrão dos módulos do alicerce): cada check é uma função que
levanta AssertionError se falhar. Roda nos 2 layouts:
  pacote: python -m core.test_lab_cycle_brief   (de dentro do sandbox core/)
  flat:   python test_lab_cycle_brief.py          (de dentro do sandbox flat/)

Nos testes flat os CycleReports são montados à mão (o boletim lê por
duck-typing e não importa o lab_loop). No layout pacote há um ponta-a-ponta
com o LabLoop + LabBacklog REAIS.
"""

from __future__ import annotations

import os
import sys
import traceback
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab_cycle_brief import (  # noqa: E402
    agregar,
    boletim_de_ciclos,
    montar_brief,
    texto_brief,
)
from lab_report import BLOQUEIO, PROGRESSO, STATUS, analisar  # noqa: E402

CHECKS = []


def check(nome):
    def deco(fn):
        CHECKS.append((nome, fn))
        return fn
    return deco


def relatorio_fake(**kw):
    base = dict(cycle=1, idle=False, idle_reason=None, dispatched=1,
                completed=1, failed=0, stuck_released=[],
                released_failed=[], paused=False, journal=[])
    base.update(kw)
    return SimpleNamespace(**base)


@check("PROGRESSO quando há tarefa concluída, e passa no portão")
def t_progresso():
    rel = montar_brief(agregar([relatorio_fake(completed=2, dispatched=2)]))
    assert rel.tipo == PROGRESSO, rel.tipo
    assert rel.feito, "PROGRESSO exige FEITO"
    assert rel.pode_falar(), rel.validar()
    texto = texto_brief(rel)
    assert "2 tarefa(s) concluída(s)" in texto
    assert len(texto.splitlines()) <= 12  # cabeçalho + 10 linhas


@check("BLOQUEIO quando o loop pausou, com DECISÃO PEDIDA")
def t_bloqueio():
    rel = montar_brief(agregar([relatorio_fake(paused=True, failed=3,
                                               journal=[{"t": 1, "event": "loop_paused"}])]))
    assert rel.tipo == BLOQUEIO, rel.tipo
    assert rel.decisao_pedida.strip(), "BLOQUEIO exige decisão pedida"
    assert "retomar" in rel.decisao_pedida
    assert rel.pode_falar(), rel.validar()
    assert "PAUSADO" in texto_brief(rel)


@check("STATUS quando o ciclo está ocioso (fila aprovada vazia)")
def t_status_ocioso():
    rel = montar_brief(agregar([relatorio_fake(idle=True,
                                               idle_reason="NO_APPROVED_WORK",
                                               dispatched=0, completed=0)]))
    assert rel.tipo == STATUS, rel.tipo
    assert rel.pode_falar(), rel.validar()
    texto = texto_brief(rel)
    assert "fila de aprovados vazia" in texto
    assert "aprovar mais propostas no backlog" in texto


@check("STATUS com orçamento esgotado sugere a CEO decidir")
def t_status_budget():
    rel = montar_brief(agregar([relatorio_fake(idle=True,
                                               idle_reason="BUDGET_EXHAUSTED",
                                               dispatched=0, completed=0)]),
                       budget_used_usd=5.0)
    assert rel.tipo == STATUS
    assert "US$ 5.00" in texto_brief(rel)
    assert "amplia o orçamento" in texto_brief(rel)
    assert rel.pode_falar()


@check("boletim de 10 ciclos com falhas cabe no teto de 10 linhas")
def t_teto():
    reports = [
        relatorio_fake(cycle=n, dispatched=1, completed=0, failed=1,
                       journal=[{"t": n, "event": "cycle_failed"}])
        for n in range(1, 11)
    ]
    rel = montar_brief(agregar(reports))
    assert rel.total_linhas() <= 10, rel.total_linhas()
    assert rel.pode_falar(), rel.validar()


@check("detalhe do journal NUNCA vaza para as linhas (segredo)")
def t_sem_vazamento():
    segredo = "CHAVE-SECRETA-12345-NAO-VAZA"
    reports = [relatorio_fake(
        cycle=1, completed=1,
        journal=[{"t": 1, "event": "loop_paused", "detail": segredo}],
    )]
    texto = boletim_de_ciclos(reports)
    assert segredo not in texto, "conteúdo do journal vazou no boletim"
    assert "RELATÓRIO" in texto


@check("watchdog conta itens travados devolvidos (só nomes)")
def t_watchdog():
    rel = montar_brief(agregar([relatorio_fake(
        stuck_released=["BLG-0007", "BLG-0009"])]))
    texto = texto_brief(rel)
    assert "2 item(ns) travado(s)" in texto
    assert rel.pode_falar()


@check("analisar(formatar()) preserva o tipo")
def t_roundtrip():
    rel = montar_brief(agregar([relatorio_fake(completed=1)]))
    rel2 = analisar(texto_brief(rel))
    assert rel2.tipo == PROGRESSO, rel2.tipo
    assert rel2.pode_falar()


@check("idle reason desconhecido não quebra o boletim")
def t_idle_desconhecido():
    rel = montar_brief(agregar([relatorio_fake(
        idle=True, idle_reason="ALGO_NOVO", dispatched=0, completed=0)]))
    assert rel.pode_falar(), rel.validar()
    assert "ALGO_NOVO" in texto_brief(rel)


@check("sem relatórios: STATUS quieto que passa no portão")
def t_vazio():
    rel = montar_brief(agregar([]))
    assert rel.tipo == STATUS
    assert rel.pode_falar(), rel.validar()


def _tem_pacote():
    try:
        import core.lab_loop  # noqa: F401
        return True
    except ImportError:
        return False


if _tem_pacote():
    from core.lab_backlog import LabBacklog  # noqa: E402
    from core.lab_loop import LabLoop  # noqa: E402

    @check("P2P pacote: loop real com 1 tarefa concluída → boletim PROGRESSO")
    def t_p2p_progresso():
        bl = LabBacklog()
        item = bl.propose("zerar falha X", "motivo", "TESTER", 5, 5, 1)
        bl.approve(item.item_id, by="CEO")

        def fake_turn(*, backlog, **kw):
            it = backlog.claim(item.item_id, "TESTER")
            backlog.complete(it.item_id, "TESTER")
            return SimpleNamespace(dispatched=1, completed=1, failed=0,
                                   unassigned=[])

        loop = LabLoop(turn_runner=fake_turn, notify=lambda t, r: None)
        reports = loop.run_until_idle(bl, object(), lambda **kw: None,
                                      max_cycles=3)
        texto = boletim_de_ciclos(reports, loop_state=loop.state)
        assert "PROGRESSO" in texto, texto
        assert "1 tarefa(s) concluída(s)" in texto

    @check("P2P pacote: 2 ciclos falhando seguidos → loop pausa → BLOQUEIO")
    def t_p2p_bloqueio():
        import tempfile
        from core.lab_dropbox import Dropbox
        bl = LabBacklog()
        item = bl.propose("corrigir teste quebrado da voz", "o teste falha",
                          "TESTER", 5, 5, 1)
        bl.approve(item.item_id, by="CEO")

        def boom(**kw):
            raise RuntimeError("worker explodiu")

        with tempfile.TemporaryDirectory() as tmp:
            dropbox = Dropbox(tmp)
            loop = LabLoop(notify=lambda t, r: None,
                           max_consecutive_failures=2)
            reports = loop.run_until_idle(bl, dropbox, boom, max_cycles=5)
        assert loop.state == "PAUSED", loop.state
        texto = boletim_de_ciclos(reports, loop_state=loop.state)
        assert "BLOQUEIO" in texto, texto
        assert "DECISÃO PEDIDA" in texto
        assert "CHAVE" not in texto  # sanidade: nada de segredo inventado

    @check("P2P pacote: backlog vazio → STATUS fila aprovada vazia")
    def t_p2p_ocioso():
        loop = LabLoop(notify=lambda t, r: None)
        reports = loop.run_until_idle(LabBacklog(), object(),
                                      lambda **kw: None, max_cycles=2)
        texto = boletim_de_ciclos(reports, loop_state=loop.state)
        assert "STATUS" in texto, texto
        assert "fila de aprovados vazia" in texto


def main():
    ok = 0
    falhas = []
    for nome, fn in CHECKS:
        try:
            fn()
            ok += 1
            print("ok -", nome)
        except Exception:
            falhas.append(nome)
            print("FALHOU -", nome)
            traceback.print_exc()
    print("%d/%d checks verdes" % (ok, len(CHECKS)))
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
