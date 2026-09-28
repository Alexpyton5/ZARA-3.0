"""Testes do backlog do Lab (core/lab_backlog.py) — lógica pura, custo zero."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab_backlog import (
    BacklogError,
    BacklogState,
    LabBacklog,
    priority_score,
)


def _backlog():
    tick = {"n": 0}

    def clock():
        tick["n"] += 1
        return f"T{tick['n']:03d}"

    return LabBacklog(clock=clock)


def _prop(b, **kw):
    d = dict(title="Tirar a peça de museu X",
             description="Remover código morto do módulo Y",
             proposed_by="ENGINEER-1",
             impact=4, urgency=3, cost=2)
    d.update(kw)
    return b.propose(**d)


def test_score_formula():
    # impacto 5, urgência 5, custo 1 => 15+10-2 = 23
    assert priority_score(5, 5, 1) == 23
    assert priority_score(1, 1, 5) == 3 + 2 - 10
    for bad in (0, 6, "3", 3.0):
        try:
            priority_score(bad, 3, 3)
        except BacklogError:
            pass
        else:
            raise AssertionError(f"aceitou {bad!r}")


def test_propose_ok():
    b = _backlog()
    it = _prop(b)
    assert it.item_id == "BLG-0001"
    assert it.state is BacklogState.PROPOSED
    assert it.score == 4 * 3 + 3 * 2 - 2 * 2  # 14
    assert it.journal[0]["event"] == "proposed"


def test_propose_rejeita_lixo():
    b = _backlog()
    for kw in (dict(title="  "), dict(title="x" * 141),
               dict(description=""), dict(proposed_by=""),
               dict(impact=0), dict(cost=9)):
        try:
            _prop(b, **kw)
        except BacklogError:
            pass
        else:
            raise AssertionError(f"aceitou {kw}")


def test_approve_so_ceo():
    b = _backlog()
    it = _prop(b)
    try:
        b.approve(it.item_id, by="ENGINEER-1")
    except BacklogError:
        pass
    else:
        raise AssertionError("não-CEO aprovou")
    b.approve(it.item_id, by="CEO")
    assert it.state is BacklogState.APPROVED


def test_aprovar_duas_vezes_falha():
    b = _backlog()
    it = _prop(b)
    b.approve(it.item_id, by="CEO")
    try:
        b.approve(it.item_id, by="CEO")
    except BacklogError:
        pass
    else:
        raise AssertionError("aprovou duas vezes")


def test_reject_so_ceo_ou_critic():
    b = _backlog()
    it = _prop(b)
    try:
        b.reject(it.item_id, by="SCRIBE-1", reason="não")
    except BacklogError:
        pass
    else:
        raise AssertionError("SCRIBE rejeitou")
    b.reject(it.item_id, by="CRITIC", reason="duplicado do BLG-0000")
    assert it.state is BacklogState.REJECTED
    try:
        b.reject(it.item_id, by="CEO", reason="de novo")
    except BacklogError:
        pass
    else:
        raise AssertionError("rejeitou item já rejeitado")


def test_claim_so_aprovado():
    b = _backlog()
    it = _prop(b)
    try:
        b.claim(it.item_id, "ENGINEER-1")
    except BacklogError:
        pass
    else:
        raise AssertionError("reivindicou sem aprovação")
    b.approve(it.item_id, by="CEO")
    b.claim(it.item_id, "ENGINEER-1")
    assert it.state is BacklogState.CLAIMED
    assert it.claimed_by == "ENGINEER-1"


def test_claim_duplo_falha():
    b = _backlog()
    it = _prop(b)
    b.approve(it.item_id, by="CEO")
    b.claim(it.item_id, "ENGINEER-1")
    try:
        b.claim(it.item_id, "TESTER-1")
    except BacklogError:
        pass
    else:
        raise AssertionError("dois donos no mesmo item")


def test_complete_so_quem_reivindicou():
    b = _backlog()
    it = _prop(b)
    b.approve(it.item_id, by="CEO")
    b.claim(it.item_id, "ENGINEER-1")
    try:
        b.complete(it.item_id, "TESTER-1")
    except BacklogError:
        pass
    else:
        raise AssertionError("outro agente concluiu")
    b.complete(it.item_id, "ENGINEER-1", note="removido e testado")
    assert it.state is BacklogState.DONE


def test_ranked_ordem():
    b = _backlog()
    _prop(b, title="Baixo", impact=1, urgency=1, cost=5)     # 3+2-10=-5
    _prop(b, title="Alto", impact=5, urgency=5, cost=1)      # 23
    _prop(b, title="Medio", impact=3, urgency=3, cost=3)     # 9
    _prop(b, title="Alto2", impact=5, urgency=5, cost=1)     # 23, chegou depois
    got = [i.title for i in b.ranked()]
    assert got == ["Alto", "Alto2", "Medio", "Baixo"], got


def test_ranked_filtra_estado():
    b = _backlog()
    a = _prop(b, title="A", impact=5, urgency=5, cost=1)
    c = _prop(b, title="C", impact=1, urgency=1, cost=5)
    b.approve(a.item_id, by="CEO")
    got = [i.title for i in b.ranked([BacklogState.PROPOSED])]
    assert got == ["C"], got


def test_plan_for_ceo():
    b = _backlog()
    a = _prop(b, title="A", impact=5, urgency=5, cost=1)
    c = _prop(b, title="C", impact=4, urgency=4, cost=1)
    b.approve(a.item_id, by="CEO")
    b.claim(a.item_id, "ENGINEER-1")
    b.complete(a.item_id, "ENGINEER-1")
    plan = b.plan_for_ceo()
    titles = [i.title for i in plan]
    assert "A" not in titles  # concluído sai do plano
    assert titles[0] == "C"


def test_item_inexistente():
    b = _backlog()
    for fn in (b.approve, b.claim):
        try:
            fn("BLG-9999", "CEO")
        except BacklogError:
            pass
        else:
            raise AssertionError("aceitou item fantasma")


def test_journal_auditavel():
    b = _backlog()
    it = _prop(b)
    b.approve(it.item_id, by="CEO")
    b.claim(it.item_id, "ENGINEER-1")
    b.complete(it.item_id, "ENGINEER-1", note="ok")
    events = [(e["event"], e["by"]) for e in it.journal]
    assert events == [("proposed", "ENGINEER-1"), ("approved", "CEO"),
                      ("claimed", "ENGINEER-1"), ("done", "ENGINEER-1")]
    assert all(e["t"].startswith("T") for e in it.journal)


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    fails = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            fails += 1
            print(f"FALHOU {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - fails}/{len(TESTS)} verdes")
    sys.exit(1 if fails else 0)
