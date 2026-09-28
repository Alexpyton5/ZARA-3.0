"""Testes do condutor do loop contínuo (core/lab_loop.py).

Roda em 2 layouts: pacote (core.*) e flat. Lógica pura contra os módulos
REAIS (backlog atualizado com release(), turn, dropbox, report):
custo/rede/quota = zero.
Uso:
    python test_lab_loop.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
    from core.lab_dropbox import Dropbox
    from core.lab_loop import (
        BUDGET_EXHAUSTED,
        NO_APPROVED_WORK,
        NO_ASSIGNABLE,
        PAUSED,
        LabLoop,
        LoopError,
    )
    LAYOUT = "pacote"
except ImportError:
    from lab_backlog import BacklogError, BacklogState, LabBacklog
    from lab_dropbox import Dropbox
    from lab_loop import (
        BUDGET_EXHAUSTED,
        NO_APPROVED_WORK,
        NO_ASSIGNABLE,
        PAUSED,
        LabLoop,
        LoopError,
    )
    LAYOUT = "flat"

PASSOU = 0


def check(nome, cond, detalhe=""):
    global PASSOU
    assert cond, f"FALHOU: {nome} {detalhe}"
    PASSOU += 1
    print(f"  ok: {nome}")


def make_clock():
    t = [1000]
    def clock():
        t[0] += 1
        return t[0]
    return clock


def make_backlog(*titles):
    bl = LabBacklog(clock=lambda: "t")
    out = []
    for title in titles:
        it = bl.propose(title, "desc", "ENGINEER", 3, 3, 3)
        bl.approve(it.item_id, "CEO")
        out.append(it)
    return bl


def make_dropbox():
    tmp = tempfile.mkdtemp(prefix="loopbox-")
    return Dropbox(pasta=tmp, clock=lambda: "t")


def w_ok(seat, order, ctx):
    return {"ok": True,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- fiz " + seat}


def w_fail(seat, order, ctx):
    return {"ok": False,
            "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- nada"}


def w_boom(seat, order, ctx):
    raise RuntimeError("pane no worker")


print(f"[layout {LAYOUT}] condutor do loop contínuo")

# 1. ocioso sem trabalho: nada aprovado -> worker nem é chamado
chamadas = []
bl = LabBacklog(clock=lambda: "t")
loop = LabLoop(now=make_clock())
rep = loop.run_cycle(bl, make_dropbox(),
                     lambda s, o, c: chamadas.append(s) or w_ok(s, o, c))
check("idle sem trabalho", rep.idle and rep.idle_reason == NO_APPROVED_WORK)
check("worker não chamado no idle", chamadas == [])
check("estado RUNNING", loop.state == "RUNNING")

# 2. ciclo feliz: aprova -> turno roda -> DONE
bl = make_backlog("Corrigir teste de voz quebrado")
loop = LabLoop(now=make_clock())
rep = loop.run_cycle(bl, make_dropbox(), w_ok)
check("ciclo feliz não idle", not rep.idle)
check("ciclo feliz completed=1", rep.completed == 1, str(rep.completed))
check("item virou DONE",
      bl.get("BLG-0001").state is BacklogState.DONE)
check("journal do ciclo registra o feito",
      any(e["event"] == "cycle_done" for e in rep.journal))
check("ciclo numerado", rep.cycle == 1)

# 3. worker falha -> conta falha consecutiva, loop segue RUNNING
bl = make_backlog("Corrigir teste de voz quebrado")
avisos = []
loop = LabLoop(now=make_clock(),
               notify=lambda t, r: avisos.append((t, r)))
rep = loop.run_cycle(bl, make_dropbox(), w_fail)
check("falha conta failed=1", rep.failed == 1)
check("loop segue RUNNING após 1 falha", loop.state == "RUNNING")
check("sem ALERTA ainda", avisos == [])
check("item falho volta pra fila (APPROVED)",
      bl.get("BLG-0001").state is BacklogState.APPROVED)
check("released_failed registra o id", rep.released_failed == ["BLG-0001"])

# 4. backoff: 2 falhas seguidas -> PAUSA + ALERTA; 3º ciclo nem roda
bl = make_backlog("Corrigir teste de voz quebrado")
avisos = []
calls = []
def w_fail_count(seat, order, ctx):
    calls.append(seat)
    return w_fail(seat, order, ctx)
loop = LabLoop(now=make_clock(), max_consecutive_failures=2,
               notify=lambda t, r: avisos.append((t, r)))
r1 = loop.run_cycle(bl, make_dropbox(), w_fail_count)
r2 = loop.run_cycle(bl, make_dropbox(), w_fail_count)
check("pausou no 2º ciclo falho", r2.paused and loop.state == PAUSED)
check("ALERTA de pausa enviado",
      any(t == "ALERTA" and "LOOP_PAUSADO" in r for t, r in avisos),
      str(avisos))
n_calls = len(calls)
r3 = loop.run_cycle(bl, make_dropbox(), w_fail_count)
check("ciclo pausado não chama worker", len(calls) == n_calls)
check("ciclo pausado é idle PAUSED",
      r3.idle and r3.idle_reason == PAUSED)

# 5. resume: a CEO decide, o loop volta
loop.resume()
check("resume volta pra RUNNING", loop.state == "RUNNING")
bl2 = make_backlog("Corrigir teste de voz quebrado")
rep = loop.run_cycle(bl2, make_dropbox(), w_ok)
check("pós-resume trabalha", rep.completed == 1 and not rep.paused)

# 6. watchdog: item CLAIMED há 3 ciclos sem concluir -> devolvido
bl = LabBacklog(clock=lambda: "t")
it = bl.propose("Corrigir teste de voz quebrado", "desc", "ENGINEER", 3, 3, 3)
bl.approve(it.item_id, "CEO")
bl.claim(it.item_id, "ENGINEER")  # dono some: ninguém completa
avisos = []
loop = LabLoop(now=make_clock(),
               notify=lambda t, r: avisos.append((t, r)))
for _ in range(3):
    rep = loop.run_cycle(bl, make_dropbox(), w_ok)
check("watchdog devolveu o travado", rep.stuck_released == [it.item_id],
      str(rep.stuck_released))
check("travado liberado voltou a andar (não fica CLAIMED pra sempre)",
      bl.get(it.item_id).state is not BacklogState.CLAIMED,
      str(bl.get(it.item_id).state))
check("ALERTA de stuck enviado",
      any(t == "ALERTA" and "STUCK_RELEASED" in r for t, r in avisos))
check("journal registra o motivo",
      any(e["event"] == "watchdog_released" for e in rep.journal))

# 7. watchdog respeita quem conclui a tempo
bl = LabBacklog(clock=lambda: "t")
it = bl.propose("Corrigir teste de voz quebrado", "desc", "ENGINEER", 3, 3, 3)
bl.approve(it.item_id, "CEO")
bl.claim(it.item_id, "ENGINEER")
loop = LabLoop(now=make_clock())
loop.run_cycle(bl, make_dropbox(), w_ok)
bl.complete(it.item_id, "ENGINEER", note="feito")
rep = loop.run_cycle(bl, make_dropbox(), w_ok)
check("concluído a tempo não é devolvido", rep.stuck_released == [])

# 8. run_until_idle: 2 aprovados -> tudo DONE, para sozinho
bl = make_backlog("Corrigir teste de voz quebrado",
                  "Escrever teste de regressão da voz")
loop = LabLoop(now=make_clock())
reps = loop.run_until_idle(bl, make_dropbox(), w_ok, max_cycles=10)
check("terminou em idle", reps[-1].idle)
check("2 itens DONE", len(bl.ranked([BacklogState.DONE])) == 2)
check("respeitou o teto", len(reps) <= 10)

# 9. orçamento: estourou -> idle BUDGET_EXHAUSTED
bl = make_backlog("Corrigir teste de voz quebrado")
loop = LabLoop(now=make_clock())
r1 = loop.run_cycle(bl, make_dropbox(), w_ok,
                    budget_usd=5.0, total_budget_usd=5.0)
check("1º ciclo usou o orçamento", not r1.idle and r1.completed == 1)
it2 = bl.propose("Escrever teste de regressão da voz", "desc",
                 "ENGINEER", 3, 3, 3)
bl.approve(it2.item_id, "CEO")
r2 = loop.run_cycle(bl, make_dropbox(), w_ok,
                    budget_usd=5.0, total_budget_usd=5.0)
check("2º ciclo idle por orçamento",
      r2.idle and r2.idle_reason == BUDGET_EXHAUSTED)

# 10. ninguém sabe fazer -> idle NO_ASSIGNABLE, worker quieto
chamadas = []
bl = make_backlog("Meditar sobre o sentido da fila")
loop = LabLoop(now=make_clock())
rep = loop.run_cycle(bl, make_dropbox(),
                     lambda s, o, c: chamadas.append(s) or w_ok(s, o, c))
check("sem assento capaz -> idle NO_ASSIGNABLE",
      rep.idle and rep.idle_reason == NO_ASSIGNABLE)
check("worker não chamado", chamadas == [])

# 11. journal com relógio injetável: timestamps crescentes
bl = make_backlog("Corrigir teste de voz quebrado")
loop = LabLoop(now=make_clock())
loop.run_cycle(bl, make_dropbox(), w_ok)
ts = [e["t"] for e in loop.journal()]
check("journal não vazio", len(ts) > 0)
check("timestamps crescentes", all(b >= a for a, b in zip(ts, ts[1:])))

# 12. turno que explode não derruba o condutor
def turn_boom(**kw):
    raise RuntimeError("turno quebrou")
bl = make_backlog("Corrigir teste de voz quebrado")
loop = LabLoop(now=make_clock(), turn_runner=turn_boom,
               max_consecutive_failures=5)
rep = loop.run_cycle(bl, make_dropbox(), w_ok)
check("turno explodido vira ciclo falho", rep.failed == 1 and not rep.idle)
check("loop segue vivo", loop.state == "RUNNING")

# 13. notify nunca recebe conteúdo de arquivo (só nomes e estados)
avisos = []
bl = LabBacklog(clock=lambda: "t")
it = bl.propose("Corrigir teste de voz quebrado", "desc", "ENGINEER", 3, 3, 3)
bl.approve(it.item_id, "CEO")
bl.claim(it.item_id, "ENGINEER")  # dono some
loop = LabLoop(now=make_clock(),
               notify=lambda t, r: avisos.append((t, r)))
for _ in range(3):
    loop.run_cycle(bl, make_dropbox(), w_ok)
check("watchdog alertou", len(avisos) == 1)
check("alerta leva só nomes e estados",
      "STUCK_RELEASED" in avisos[0][1] and it.item_id in avisos[0][1]
      and "desc" not in avisos[0][1],
      str(avisos))

# 14. max_cycles segura loop infinito (worker sempre propõe de novo)
bl = LabBacklog(clock=lambda: "t")
def w_repropoe(seat, order, ctx):
    it = bl.propose("Corrigir teste de voz quebrado", "desc",
                    "ENGINEER", 3, 3, 3)
    bl.approve(it.item_id, "CEO")
    return w_ok(seat, order, ctx)
it0 = bl.propose("Corrigir teste de voz quebrado", "desc", "ENGINEER", 3, 3, 3)
bl.approve(it0.item_id, "CEO")
loop = LabLoop(now=make_clock())
reps = loop.run_until_idle(bl, make_dropbox(), w_repropoe, max_cycles=4)
check("parou no teto de ciclos", len(reps) == 4, str(len(reps)))

# 15. release: só a CEO libera, e só CLAIMED
bl = LabBacklog(clock=lambda: "t")
it = bl.propose("Corrigir teste de voz quebrado", "desc", "ENGINEER", 3, 3, 3)
bl.approve(it.item_id, "CEO")
try:
    bl.release(it.item_id, "CEO", reason="x")
    check("release de APPROVED barra", False)
except BacklogError:
    check("release de APPROVED barra", True)
bl.claim(it.item_id, "ENGINEER")
try:
    bl.release(it.item_id, "ENGINEER", reason="x")
    check("release por não-CEO barra", False)
except BacklogError:
    check("release por não-CEO barra", True)
bl.release(it.item_id, "CEO", reason="dono sumiu")
check("release da CEO devolve pra APPROVED",
      bl.get(it.item_id).state is BacklogState.APPROVED)
check("release registra motivo no journal",
      any(e["event"] == "released" and e.get("detail") == "dono sumiu"
          for e in bl.get(it.item_id).journal))

# 16. config inválida é recusada na construção
for kwargs in ({"max_consecutive_failures": 0}, {"stuck_after_cycles": 0}):
    try:
        LabLoop(**kwargs)
        check(f"config inválida {kwargs} barra", False)
    except LoopError:
        check(f"config inválida {kwargs} barra", True)

print(f"\n{PASSOU} checks verdes (layout {LAYOUT}).")
