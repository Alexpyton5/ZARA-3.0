"""Testes da decisão da CEO (core/lab_ceo_decision.py).

Roda em 2 layouts: pacote (core.*) e flat. Lógica pura contra os módulos REAIS
do app (loop + backlog com archive()): custo/rede/quota = zero.
Uso:
    python test_lab_ceo_decision.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
    from core.lab_ceo_decision import (
        CeoDecision,
        DecisionError,
        DecisionRegistry,
        DecisionType,
        aplicar,
        ciclos_restantes,
        decisao_valida,
        resumir_para_boletim,
    )
    from core.lab_dropbox import Dropbox
    from core.lab_loop import PAUSED, LabLoop
    LAYOUT = "pacote"
except ImportError:
    from lab_backlog import BacklogError, BacklogState, LabBacklog
    from lab_ceo_decision import (
        CeoDecision,
        DecisionError,
        DecisionRegistry,
        DecisionType,
        aplicar,
        ciclos_restantes,
        decisao_valida,
        resumir_para_boletim,
    )
    from lab_dropbox import Dropbox
    from lab_loop import PAUSED, LabLoop
    LAYOUT = "flat"

PASSOU = 0


def check(nome, cond, detalhe=""):
    global PASSOU
    assert cond, f"FALHOU: {nome} {detalhe}"
    PASSOU += 1
    print(f"  ok: {nome}")


def check_erro(nome, fn, exc=DecisionError):
    global PASSOU
    try:
        fn()
    except exc:
        PASSOU += 1
        print(f"  ok: {nome}")
        return
    raise AssertionError(f"FALHOU: {nome} — não levantou {exc.__name__}")


def make_clock():
    t = [1000]

    def clock():
        t[0] += 1
        return f"t{t[0]}"

    return clock


def make_backlog(*titles):
    bl = LabBacklog(clock=lambda: "t")
    out = []
    for title in titles:
        # título com palavra-chave de tipo (ex.: "teste") p/ o plano achar dono
        it = bl.propose("Corrigir teste: " + title, "desc", "ENGINEER", 3, 3, 3)
        bl.approve(it.item_id, "CEO")
        out.append(it)
    return bl, out


def make_dropbox():
    tmp = tempfile.mkdtemp(prefix="decbox-")
    return Dropbox(pasta=tmp, clock=lambda: "t")


def w_fail(seat, order, ctx):
    return {"ok": False, "report": "RELATÓRIO (PROGRESSO)\nFEITO:\n- nada"}


def pausar_loop():
    bl, _ = make_backlog("tarefa")
    loop = LabLoop(now=make_clock(), max_consecutive_failures=1)
    rep = loop.run_cycle(bl, make_dropbox(), w_fail)
    assert rep.paused, "setup: loop deveria ter pausado"
    return loop, bl


print(f"[layout {LAYOUT}] decisão da CEO")

# 1. registrar RETOMAR válida: id d1 + journal
reg = DecisionRegistry(clock=make_clock())
d = reg.registrar("RETOMAR", 7, "falha foi flake isolado", decidido_por="CEO")
check("registra RETOMAR", isinstance(d, CeoDecision) and d.decision_id == "d1")
check("journal tem registro", any(e["event"] == "decision_registered" for e in reg.journal()))

# 2. ids sequenciais
d2 = reg.registrar("ENCERRAR", 7, "sem trabalho útil")
check("ids sequenciais d1/d2", d2.decision_id == "d2")
check("get d1", reg.get("d1") is d)
check_erro("get desconhecido", lambda: reg.get("d99"))

# 3. motivo obrigatório e com teto
check_erro("motivo vazio", lambda: reg.registrar("RETOMAR", 1, "   "))
check_erro("motivo 6 linhas", lambda: reg.registrar("RETOMAR", 1, "a\nb\nc\nd\ne\nf"))
check_erro("linha >140 chars", lambda: reg.registrar("RETOMAR", 1, "x" * 141))

# 4. tipo/ciclo/decisor inválidos
check_erro("tipo inválido", lambda: reg.registrar("VOAR", 1, "ok"))
check_erro("cycle 0", lambda: reg.registrar("RETOMAR", 0, "ok"))
check_erro("decisor inválido", lambda: reg.registrar("RETOMAR", 1, "ok", decidido_por="X"))

# 5. pertinência: sem parâmetro morto, sem falta
check_erro("RETOMAR com limite", lambda: reg.registrar("RETOMAR", 1, "ok", limite={"max_cycles": 2}))
check_erro("ENCERRAR com targets", lambda: reg.registrar("ENCERRAR", 1, "ok", targets=("t1",)))
check_erro("ARQUIVAR sem targets", lambda: reg.registrar("ARQUIVAR_TAREFA", 1, "ok"))
check_erro("COM_LIMITE sem limite", lambda: reg.registrar("RETOMAR_COM_LIMITE", 1, "ok"))
check_erro("limite chave estranha",
           lambda: reg.registrar("RETOMAR_COM_LIMITE", 1, "ok", limite={"coisas": 1}))
check_erro("max_cycles 0",
           lambda: reg.registrar("RETOMAR_COM_LIMITE", 1, "ok", limite={"max_cycles": 0}))
check_erro("budget_usd negativo",
           lambda: reg.registrar("RETOMAR_COM_LIMITE", 1, "ok", limite={"budget_usd": -1}))
check_erro("target vazio", lambda: reg.registrar("ARQUIVAR_TAREFA", 1, "ok", targets=("",)))

# 6. RETOMAR_COM_LIMITE válido: expira no ciclo + max_cycles
dlim = reg.registrar("RETOMAR_COM_LIMITE", 5, "tentar de novo com teto",
                     limite={"max_cycles": 3, "budget_usd": 0.5})
check("expira no ciclo certo", dlim.expires_after_cycle == 8)
check("limite_dict", dlim.limite_dict() == {"budget_usd": 0.5, "max_cycles": 3})
check("válida no ciclo 5", decisao_valida(dlim, 5))
check("válida no ciclo 8", decisao_valida(dlim, 8))
check("expirada no ciclo 9", not decisao_valida(dlim, 9))
check("restantes no 6", ciclos_restantes(dlim, 6) == 2)
check("restantes no 9", ciclos_restantes(dlim, 9) == 0)
check("sem limite nunca expira", decisao_valida(d, 999) and ciclos_restantes(d, 999) is None)

# 7. aplicar RETOMAR num loop pausado de verdade -> RUNNING
loop, _ = pausar_loop()
check("loop pausado no setup", loop.state == PAUSED)
reg2 = DecisionRegistry(clock=make_clock())
dr = reg2.registrar("RETOMAR", 2, "flake confirmado")
ef = aplicar(dr, loop, registry=reg2)
check("aplicar RETOMAR retoma", loop.state == "RUNNING")
check("efeito loop_retomado", ef["efeito"] == "loop_retomado")
check("journal tem decision_applied",
      any(e["event"] == "decision_applied" for e in reg2.journal()))

# 8. aplicar RETOMAR_COM_LIMITE -> resume + limite no efeito
loop, _ = pausar_loop()
ef = aplicar(dlim, loop)
check("retoma com limite", loop.state == "RUNNING" and ef["efeito"] == "loop_retomado_com_limite")
check("limite viaja no efeito", ef["limite"]["max_cycles"] == 3)

# 9. ARQUIVAR_TAREFA arquiva item APPROVED real no backlog real
bl, (it,) = make_backlog("tarefa problemática")
reg3 = DecisionRegistry(clock=make_clock())
da = reg3.registrar("ARQUIVAR_TAREFA", 3, "quebra toda vez que roda", targets=(it.item_id,))
ef = aplicar(da, None, backlog=bl)
check("item arquivado", bl.get(it.item_id).state is BacklogState.REJECTED)
check("efeito arquivados", ef["efeito"] == "tarefas_arquivadas" and ef["arquivados"] == [it.item_id])
check("claimed_by limpo", bl.get(it.item_id).claimed_by is None)

# 10. archive não pega concluído; só CEO/Alex arquivam
bl2, (it2,) = make_backlog("feita")
bl2.claim(it2.item_id, "ENGINEER")
bl2.complete(it2.item_id, "ENGINEER")
check_erro("archive em DONE", lambda: bl2.archive(it2.item_id, by="CEO", reason="x"),
           exc=BacklogError)
check_erro("archive por estranho", lambda: bl2.archive(it2.item_id, by="X", reason="x"),
           exc=BacklogError)
bl2b, (it2b,) = make_backlog("proposta")
check("archive pelo ALEX", bl2b.archive(it2b.item_id, by="ALEX", reason="ok").state is BacklogState.REJECTED)

# 11. aplicar ARQUIVAR sem backlog -> erro honesto
check_erro("arquivar sem backlog", lambda: aplicar(da, None, backlog=None))

# 12. ENCERRAR: loop fica pausado
loop, _ = pausar_loop()
ef = aplicar(d2, loop)
check("ENCERRAR não retoma", loop.state == PAUSED and ef["efeito"] == "loop_encerrado")

# 13. ESCALAR: notify com só nomes e estados; sem notify -> erro
avisos = []
reg4 = DecisionRegistry(clock=make_clock())
de_ = reg4.registrar("ESCALAR", 4, "preciso do Alex decidir")
ef = aplicar(de_, None, notify=lambda tipo, texto: avisos.append((tipo, texto)))
check("escalou com ALERTA", ef["efeito"] == "escalado_para_alex" and avisos[0][0] == "ALERTA")
texto = avisos[0][1]
check("texto só nomes e estados", "ESCALAR" in texto and "d1" in texto)
check_erro("escalar sem notify", lambda: aplicar(de_, None))

# 14. resumir_para_boletim: até 4 linhas, com tipo e motivo
linhas = resumir_para_boletim(dlim)
check("boletim <= 4 linhas", len(linhas) <= 4)
check("boletim tem tipo e motivo",
      any("RETOMAR_COM_LIMITE" in l for l in linhas) and any("tentar de novo" in l for l in linhas))
check("boletim mostra validade", any("ciclo 8" in l for l in linhas))

print(f"\n{PASSOU} checks verdes [layout {LAYOUT}]")
