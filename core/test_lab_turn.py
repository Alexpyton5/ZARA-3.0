"""Testes do motor do turno (core/lab_turn.py).

Roda em 2 layouts: pacote (core.*) e flat. Lógica pura, custo zero.
Uso:
    python test_lab_turn.py
"""
import sys
import os
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from core.lab_turn import LabTurn, TurnError
    from core.lab_backlog import LabBacklog, BacklogState
    from core.lab_dropbox import Dropbox
    LAYOUT = "pacote"
except ImportError:
    from lab_turn import LabTurn, TurnError
    from lab_backlog import LabBacklog, BacklogState
    from lab_dropbox import Dropbox
    LAYOUT = "flat"

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FALHOU  {name}")


def make_clock():
    tick = [0.0]

    def now():
        tick[0] += 1.0
        return tick[0]

    return now


def make_backlog(items):
    """items: lista de (title, impact, urgency, cost). Todos APPROVED."""
    bl = LabBacklog(clock=lambda: "t")
    out = []
    for title, impact, urgency, cost in items:
        it = bl.propose(title, "desc", "ENGINEER", impact, urgency, cost)
        bl.approve(it.item_id, "CEO")
        out.append(it)
    return bl


def make_dropbox():
    tmp = tempfile.mkdtemp(prefix="turnbox-")
    return Dropbox(pasta=tmp, clock=lambda: "t"), tmp


def w_ok(seat, order, ctx):
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- fiz " + seat}


def run_turn(bl, box, worker, cycle="T1", **kw):
    turn = LabTurn(now=make_clock())
    return turn.run(backlog=bl, dropbox=box, worker=worker, cycle=cycle, **kw)


print(f"[layout {LAYOUT}] motor do turno")

# 1. turno vazio: nada APPROVED -> nada despachado
bl = LabBacklog(clock=lambda: "t")
box, tmp = make_dropbox()
out = run_turn(bl, box, w_ok)
check("turno vazio: dispatched 0", out.dispatched == 0)
check("turno vazio: completed 0", out.completed == 0)
check("turno vazio: journal tem plan",
      any(e["event"] == "plan" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 2. caminho feliz: 2 itens -> 2 assentos, respostas no fio, DONE
bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1),
                   ("Rodar suite de regressao", 4, 4, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_ok)
check("feliz: dispatched 2", out.dispatched == 2)
check("feliz: completed 2", out.completed == 2)
check("feliz: failed 0", out.failed == 0)
check("feliz: itens DONE",
      all(bl.get(i.item_id).state == BacklogState.DONE
          for i in bl.ranked()))
fios = [box.fio(f"plan-T1-{i.item_id}") for i in bl.ranked()]
check("feliz: ordens depositadas com a correlation do plano",
      all(len(f) == 1 and f[0].tipo == "RECADO" for f in fios))
resps = [r for r in box.pendentes("CEO") if r.tipo == "RESPOSTA"]
check("feliz: 2 respostas para a CEO", len(resps) == 2)
fios_resp = [box.fio(r.correlation_id) for r in resps]
check("feliz: cada fio (pelo msg_id) tem ordem + resposta",
      all(len(f) == 2 and f[1].tipo == "RESPOSTA" for f in fios_resp))
shutil.rmtree(tmp, ignore_errors=True)

# 3. worker explode -> ALERTA pra CEO, item segue CLAIMED
def w_boom(seat, order, ctx):
    raise RuntimeError("cota acabou")

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_boom)
check("boom: failed 1", out.failed == 1)
check("boom: completed 0", out.completed == 0)
check("boom: item segue CLAIMED",
      bl.get("BLG-0001").state == BacklogState.CLAIMED)
alertas = [r for r in box.pendentes("CEO") if r.tipo == "ALERTA"]
check("boom: ALERTA na caixinha pra CEO", len(alertas) == 1)
shutil.rmtree(tmp, ignore_errors=True)

# 4. relatório inválido -> 1 retry -> conserta -> completed
calls = []

def w_fix(seat, order, ctx):
    calls.append(ctx["attempt"])
    if ctx["attempt"] == 1:
        return {"ok": True,
                "report": "RELATÓRIO (BLOQUEIO)\nESTADO:\n- travado"}
    return {"ok": True,
            "report": ("RELATÓRIO (BLOQUEIO)\nESTADO:\n- travado\n"
                       "DECISÃO PEDIDA: posso pular o mic?")}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_fix)
check("retry: completed 1", out.completed == 1)
check("retry: worker chamado 2x", calls == [1, 2])
check("retry: journal tem report_retry",
      any(e["event"] == "report_retry" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 5. relatório inválido 2x -> failed + ALERTA
def w_bad(seat, order, ctx):
    return {"ok": True, "report": "RELATÓRIO (BLOQUEIO)\nESTADO:\n- travado"}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_bad)
check("2x ruim: failed 1", out.failed == 1)
alertas = [r for r in box.pendentes("CEO") if r.tipo == "ALERTA"]
check("2x ruim: ALERTA cita reprovado 2x",
      len(alertas) == 1 and "reprovado 2x" in alertas[0].conteudo)
shutil.rmtree(tmp, ignore_errors=True)

# 6. split aceito: filhas completam -> mãe DONE
def w_splitter(seat, order, ctx):
    if "parent_item_id" in ctx:
        return {"ok": True,
                "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- parte feita"}
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- vou dividir",
            "split": [
                {"title": "parte A", "instruction": "faca A",
                 "assigned_agent_id": "TESTER", "budget_usd": 1.0},
                {"title": "parte B", "instruction": "faca B",
                 "assigned_agent_id": "REVIEWER", "budget_usd": 1.0},
            ]}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_splitter, budget_usd=5.0)
check("split: splits_used 1", out.splits_used == 1)
check("split: completed 1", out.completed == 1)
check("split: mãe DONE",
      bl.get("BLG-0001").state == BacklogState.DONE)
check("split: journal tem split_accepted",
      any(e["event"] == "split_accepted" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 7. split com filha falhando -> mãe failed + ALERTA
def w_split_fail(seat, order, ctx):
    if ctx.get("item_id", "").startswith("BLG-"):
        return {"ok": True,
                "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- vou dividir",
                "split": [
                    {"title": "parte A", "instruction": "faca A",
                     "assigned_agent_id": "TESTER", "budget_usd": 1.0},
                ]}
    return {"ok": False, "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- nada"}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_split_fail, budget_usd=5.0)
check("split falha: failed 1", out.failed == 1)
check("split falha: mãe segue CLAIMED",
      bl.get("BLG-0001").state == BacklogState.CLAIMED)
alertas = [r for r in box.pendentes("CEO") if r.tipo == "ALERTA"]
check("split falha: ALERTA pra CEO", len(alertas) == 1)
shutil.rmtree(tmp, ignore_errors=True)

# 8. split com budget estourado -> recusado, caminho normal completa
def w_split_over(seat, order, ctx):
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- fiz sozinho",
            "split": [
                {"title": "parte A", "instruction": "faca A",
                 "assigned_agent_id": "TESTER", "budget_usd": 4.0},
                {"title": "parte B", "instruction": "faca B",
                 "assigned_agent_id": "REVIEWER", "budget_usd": 4.0},
            ]}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_split_over, budget_usd=5.0)
check("over: splits_used 0", out.splits_used == 0)
check("over: completed 1 (caminho normal)", out.completed == 1)
check("over: journal tem split_rejected",
      any(e["event"] == "split_rejected" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 9. turno sem budget não divide
bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_splitter)  # budget_usd=0.0 padrão
check("sem budget: splits_used 0", out.splits_used == 0)
check("sem budget: completed 1", out.completed == 1)
ev = [e for e in out.journal if e["event"] == "split_rejected"]
check("sem budget: motivo turno sem budget",
      len(ev) == 1 and "sem budget" in ev[0]["motivo"])
shutil.rmtree(tmp, ignore_errors=True)

# 10. max_splits=0 bloqueia divisão
bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_splitter, budget_usd=5.0, max_splits=0)
check("teto 0: splits_used 0", out.splits_used == 0)
check("teto 0: completed 1", out.completed == 1)
shutil.rmtree(tmp, ignore_errors=True)

# 11. divisão aninhada é ignorada (só 1 nível)
def w_nested(seat, order, ctx):
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- vou dividir de novo",
            "split": [
                {"title": "parte A", "instruction": "faca A",
                 "assigned_agent_id": "TESTER", "budget_usd": 1.0},
            ]}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_nested, budget_usd=5.0)
check("aninhado: splits_used 1 (só o primeiro nível)",
      out.splits_used == 1)
check("aninhado: journal tem split_ignored_nested",
      any(e["event"] == "split_ignored_nested" for e in out.journal))
check("aninhado: completed 1", out.completed == 1)
shutil.rmtree(tmp, ignore_errors=True)

# 12. item sem assento (MISC) -> unassigned, não despachado
bl = make_backlog([("zzz qqq xxx nada a ver", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_ok)
check("misc: unassigned 1", out.unassigned == 1)
check("misc: dispatched 0", out.dispatched == 0)
check("misc: journal tem unassigned",
      any(e["event"] == "unassigned" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 13. journal auditável: ts crescente
bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1),
                   ("Rodar suite de regressao", 4, 4, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_ok)
ts = [e["ts"] for e in out.journal]
check("journal: ts crescente", ts == sorted(ts) and len(ts) > 3)
shutil.rmtree(tmp, ignore_errors=True)

# 14. worker quebra o contrato -> failed, sem crash do turno
def w_broken(seat, order, ctx):
    return {"resultado": "ops"}  # sem 'ok'

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_broken)
check("contrato: failed 1", out.failed == 1)
check("contrato: turno não crashou", out.dispatched == 1)
shutil.rmtree(tmp, ignore_errors=True)

# 15. filha com relatório inválido (11 linhas > teto) -> child_failed
longo = "RELATÓRIO (PROGRESSO)\nFEITO:\n" + "\n".join(
    f"- linha {i}" for i in range(11))

def w_child_bad(seat, order, ctx):
    if "parent_item_id" in ctx:
        return {"ok": True, "report": longo}
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- vou dividir",
            "split": [
                {"title": "parte A", "instruction": "faca A",
                 "assigned_agent_id": "TESTER", "budget_usd": 1.0},
            ]}

bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
box, tmp = make_dropbox()
out = run_turn(bl, box, w_child_bad, budget_usd=5.0)
check("filha ruim: failed 1", out.failed == 1)
check("filha ruim: journal tem child_failed",
      any(e["event"] == "child_failed" for e in out.journal))
shutil.rmtree(tmp, ignore_errors=True)

# 16. uso errado -> TurnError
for kwargs, nome in [
    (dict(cycle=""), "cycle vazio"),
    (dict(cycle="T1", worker=None), "worker nulo"),
    (dict(cycle="T1", max_splits=-1), "max_splits negativo"),
]:
    bl = make_backlog([("Corrigir teste de voz quebrado", 5, 5, 1)])
    box, tmp = make_dropbox()
    w = kwargs.pop("worker", w_ok)
    try:
        LabTurn(now=make_clock()).run(backlog=bl, dropbox=box,
                                      worker=w, **kwargs)
        check(f"erro: {nome} levanta TurnError", False)
    except TurnError:
        check(f"erro: {nome} levanta TurnError", True)
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n[layout {LAYOUT}] PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
