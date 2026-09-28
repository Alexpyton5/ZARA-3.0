"""Testes do plano do turno (core/lab_ceo_plan.py).

Roda em 2 layouts: pacote (core.*) e flat. Lógica pura, custo zero.
Uso:
    python test_lab_ceo_plan.py
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from core.lab_ceo_plan import (CeoPlan, PlanError, kind_for, SEAT_KINDS)
    from core.lab_backlog import LabBacklog, BacklogState
    LAYOUT = "pacote"
except ImportError:
    from lab_ceo_plan import (CeoPlan, PlanError, kind_for, SEAT_KINDS)
    from lab_backlog import LabBacklog, BacklogState
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


def make_backlog(items):
    """items: lista de (title, description, state, impact, urgency, cost)."""
    clock = [0.0]

    def now():
        clock[0] += 1.0
        return clock[0]

    bl = LabBacklog(clock=lambda: f"t{clock[0]}")
    for title, desc, state, impact, urgency, cost in items:
        it = bl.propose(title, desc, "ENGINEER", impact, urgency, cost)
        if state == "APPROVED":
            bl.approve(it.item_id, "CEO")
        elif state == "REJECTED":
            bl.reject(it.item_id, "CEO", "nao")
        elif state == "CLAIMED":
            bl.approve(it.item_id, "CEO")
            bl.claim(it.item_id, "ag-x")
        elif state == "DONE":
            bl.approve(it.item_id, "CEO")
            bl.claim(it.item_id, "ag-x")
            bl.complete(it.item_id, "ag-x")
    return bl


def planner():
    clock = [1000.0]

    def now():
        clock[0] += 1.0
        return clock[0]

    return CeoPlan(now=now)


def T():
    print(f"== layout {LAYOUT} ==")

    # 1. tipo determinístico por palavra-chave
    check("voz -> VOICE", kind_for("Arrumar a voz do app", "") == "VOICE")
    check("suite -> TEST", kind_for("Zerar a suíte", "41 falhas") == "TEST")
    check("botão -> UI", kind_for("Botão na tela", "") == "UI")
    check("instalador -> BUILD", kind_for("Gerar o instalador", "") == "BUILD")
    check("documentação -> DOCS", kind_for("Escrever o manual", "") == "DOCS")
    check("desconhecido -> MISC",
          kind_for("Fazer aquela coisa misteriosa", "xyz") == "MISC")
    check("tipo é auditável (determinístico)",
          kind_for("voz voz voz", "") == kind_for("voz voz voz", ""))

    # 2. item aprovado vira tarefa com dono capaz
    bl = make_backlog([("Arrumar a voz", "tts travando", "APPROVED", 5, 5, 1)])
    plan = planner().build(bl, "turno-1")
    check("1 entrada", len(plan.entries) == 1)
    e = plan.entries[0]
    check("dono sabe fazer (VOICE)",
          e.kind in SEAT_KINDS[e.seat])
    check("dono não é a CEO", e.seat != "CEO")
    check("journal registrou a atribuição",
          any(j["op"] == "assigned" for j in plan.journal))

    # 3. PROPOSED nunca entra no plano
    bl = make_backlog([("Ideia nova", "pendente", "PROPOSED", 5, 5, 1)])
    plan = planner().build(bl, "turno-2")
    check("proposto fica de fora", len(plan.entries) == 0
          and len(plan.unassigned) == 0)

    # 4. REJECTED/CLAIMED/DONE ficam de fora
    bl = make_backlog([
        ("Rejeitado", "x", "REJECTED", 5, 5, 1),
        ("Em curso", "x", "CLAIMED", 5, 5, 1),
        ("Pronto", "x", "DONE", 5, 5, 1),
    ])
    plan = planner().build(bl, "turno-3")
    check("só APPROVED entra", len(plan.entries) == 0)

    # 5. ordem de prioridade respeitada (score maior primeiro)
    bl = make_backlog([
        ("Doc menor", "manual", "APPROVED", 2, 2, 2),     # score 6
        ("Voz crítica", "tts", "APPROVED", 5, 5, 1),      # score 23
    ])
    plan = planner().build(bl, "turno-4")
    check("score maior sai primeiro",
          len(plan.entries) == 2 and "Voz" in plan.entries[0].title)

    # 6. uma tarefa, um dono: segundo item vai para outro assento
    bl = make_backlog([
        ("Backend um", "refatorar core/", "APPROVED", 4, 4, 2),
        ("Backend dois", "refatorar ipc", "APPROVED", 4, 4, 2),
    ])
    plan = planner().build(bl, "turno-5")
    seats = [e.seat for e in plan.entries]
    check("donos diferentes", len(plan.entries) == 2 and seats[0] != seats[1])

    # 7. todos os capazes ocupados -> unassigned com motivo
    bl = make_backlog([
        ("Backend um", "refatorar core/", "APPROVED", 5, 5, 1),
        ("Backend dois", "refatorar ipc", "APPROVED", 5, 5, 1),
        ("Backend três", "refatorar api", "APPROVED", 5, 5, 1),
    ])
    plan = planner().build(bl, "turno-6")  # capazes: ARCHITECT, ENGINEER
    check("terceiro sem dono", len(plan.entries) == 2
          and len(plan.unassigned) == 1
          and plan.unassigned[0].reason == "ALL_CAPABLE_BUSY")

    # 8. MISC não tem assento -> unassigned com motivo
    bl = make_backlog([("Coisa misteriosa", "xyz qqq", "APPROVED", 5, 5, 1)])
    plan = planner().build(bl, "turno-7")
    check("MISC sem dono", len(plan.unassigned) == 1
          and plan.unassigned[0].reason == "NO_SEAT_FOR_KIND")

    # 9. max_per_seat=2 permite o mesmo assento duas vezes
    bl = make_backlog([
        ("Doc um", "manual", "APPROVED", 5, 5, 1),
        ("Doc dois", "guia", "APPROVED", 5, 5, 1),
    ])
    plan = planner().build(bl, "turno-8", max_per_seat=2)
    check("mesmo assento 2x",
          len(plan.entries) == 2 and plan.entries[0].seat == plan.entries[1].seat)

    # 10. cycle vazio é erro
    try:
        planner().build(make_backlog([]), "  ")
        check("cycle vazio -> erro", False)
    except PlanError:
        check("cycle vazio -> erro", True)

    # 11. backlog vazio -> plano vazio com journal, sem erro
    plan = planner().build(make_backlog([]), "turno-9")
    check("plano vazio ok", len(plan.entries) == 0
          and any(j["op"] == "plan_empty" for j in plan.journal))

    # 12. tarefa carrega limites (budget + turnos)
    bl = make_backlog([("Arrumar a voz", "tts", "APPROVED", 5, 5, 1)])
    plan = planner().build(bl, "turno-10", budget_usd=0.5, max_turns=20)
    e = plan.entries[0]
    check("limites na tarefa", e.budget_usd == 0.5 and e.max_turns == 20)

    # 13. empacota para a caixinha: uma ordem por assento + resumo
    bl = make_backlog([
        ("Arrumar a voz", "tts", "APPROVED", 5, 5, 1),
        ("Escrever o manual", "doc", "APPROVED", 4, 4, 2),
    ])
    plan = planner().build(bl, "turno-11")
    msgs = planner().to_dropbox_messages(plan, "run-1")
    check("ordens + resumo", len(msgs) == len(plan.entries) + 1)
    check("resumo é broadcast", msgs[-1]["para"] == "TODOS")
    corrs = [m["correlation_id"] for m in msgs]
    check("correlation_id único", len(set(corrs)) == len(corrs))
    check("corpo cabe na caixinha (64KB)",
          all(len(m["conteudo"]) <= 64 * 1024 for m in msgs))
    check("ordem não carrega arquivo (só nomes/estados)",
          all("budget_usd" in m["conteudo"] and ".py" not in m["conteudo"]
              for m in msgs[:-1]))

    # 14. resumo lista os sem-dono com motivo
    bl = make_backlog([("Coisa misteriosa", "xyz", "APPROVED", 5, 5, 1)])
    plan = planner().build(bl, "turno-12")
    msgs = planner().to_dropbox_messages(plan, "run-2")
    check("resumo mostra sem-dono",
          "NO_SEAT_FOR_KIND" in msgs[-1]["conteudo"])

    # 15. run_id vazio é erro
    try:
        planner().to_dropbox_messages(plan, " ")
        check("run_id vazio -> erro", False)
    except PlanError:
        check("run_id vazio -> erro", True)

    # 16. journal usa o relógio injetado
    p = planner()
    plan = p.build(make_backlog([("Voz", "tts", "APPROVED", 5, 5, 1)]),
                   "turno-13")
    check("journal com ts injetado",
          all(j["t"] >= 1000.0 for j in plan.journal))

    print(f"-- {LAYOUT}: {PASS} ok, {FAIL} falharam --")
    return FAIL


if __name__ == "__main__":
    fails = T()
    sys.exit(1 if fails else 0)
