"""ZARA Lab — O motor do turno (mecânica da GIGANTE 2 "LAB VIVO").

Um turno do Lab, de ponta a ponta, em lógica pura:

1. A CEO pega os itens APPROVED do backlog (lab_backlog)
2. Monta o plano (lab_ceo_plan) — uma tarefa, um dono
3. Deposita as ordens na caixinha (lab_dropbox) — da CEO para cada assento
4. Cada assento reclama a sua ordem; o "trabalho" é um worker INJETADO
   (em produção seria o modelo do assento; aqui é lógica pura, custo zero)
5. A resposta volta no mesmo fio; o texto passa pelo portão do modo
   silencioso (lab_report): quem não passa ganha UMA chance de corrigir
6. Item concluído vira DONE no backlog; falha fica registrada no journal
7. O worker pode pedir divisão (lab_task_split): filhas limitadas,
   despachadas no mesmo turno, com teto de divisões por turno

Lógica pura, stdlib, zero custo/rede/quota. A GIGANTE 2 pluga este motor
no boot do Lab em vez de reconstruir do zero.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from core.lab_backlog import LabBacklog
except ImportError:  # rodando flat (testes locais)
    from lab_backlog import LabBacklog

try:
    from core.lab_ceo_plan import CEO, CeoPlan
except ImportError:
    from lab_ceo_plan import CEO, CeoPlan

try:
    from core.lab_dropbox import Dropbox
except ImportError:
    from lab_dropbox import Dropbox

try:
    from core.lab_report import analisar
except ImportError:
    from lab_report import analisar

try:
    from core.lab_task_split import (
        SplitPart,
        TaskSplitError,
        complete_child,
        fail_child,
        parent_outcome,
        split_task,
    )
except ImportError:
    from lab_task_split import (
        SplitPart,
        TaskSplitError,
        complete_child,
        fail_child,
        parent_outcome,
        split_task,
    )

try:
    from core.lab_v1.domain import Task, TaskState
except ImportError:
    from lab_v1.domain import Task, TaskState


class TurnError(ValueError):
    """Uso errado do motor do turno (contrato violado)."""


@dataclass
class TurnOutcome:
    """O resultado de um turno: contadores + journal auditável."""

    cycle: str
    dispatched: int = 0
    completed: int = 0
    failed: int = 0
    unassigned: int = 0
    splits_used: int = 0
    journal: List[Dict[str, Any]] = field(default_factory=list)


# Contrato do worker (injetado; em produção = o modelo do assento):
#   worker(seat, order_text, ctx) -> {"ok": bool, "report": str, "split": [...]?}
#   ctx = {"attempt": 1|2, "item_id": str, "cycle": str,
#          "errors": [...] (só no attempt 2), "parent_item_id": str (só em filha)}
# "split", quando presente, é lista de dicts com:
#   title, instruction, assigned_agent_id, budget_usd,
#   acceptance? (""), max_turns? (1)


class LabTurn:
    """Roda um turno completo do Lab sobre os módulos do alicerce."""

    def __init__(self, *, now: Callable[[], float] = time.time) -> None:
        self._now = now
        self._ceo = CeoPlan(now=now)
        self._worker: Optional[Callable] = None
        self._max_splits = 0
        self._journal: List[Dict[str, Any]] = []

    # ---------- turno ----------

    def run(
        self,
        *,
        backlog: LabBacklog,
        dropbox: Dropbox,
        worker: Callable[[str, str, Dict[str, Any]], Dict[str, Any]],
        cycle: str,
        budget_usd: float = 0.0,
        max_turns: int = 10,
        max_per_seat: int = 1,
        max_splits: int = 3,
    ) -> TurnOutcome:
        """Executa um turno: planeja, despacha, coleta, valida, registra."""
        if not isinstance(cycle, str) or not cycle.strip():
            raise TurnError("cycle não pode ser vazio")
        if not callable(worker):
            raise TurnError("worker precisa ser chamável")
        if not isinstance(max_splits, int) or max_splits < 0:
            raise TurnError("max_splits deve ser inteiro >= 0")

        self._worker = worker
        self._max_splits = max_splits
        outcome = TurnOutcome(cycle=cycle.strip())
        self._journal = outcome.journal

        plan = self._ceo.build(
            backlog,
            outcome.cycle,
            max_per_seat=max_per_seat,
            budget_usd=budget_usd,
            max_turns=max_turns,
        )
        self._log("plan", entradas=len(plan.entries),
                  sem_dono=len(plan.unassigned))
        for u in plan.unassigned:
            outcome.unassigned += 1
            self._log("unassigned", item_id=u.item_id, motivo=u.reason)

        messages = self._ceo.to_dropbox_messages(
            plan, run_id=f"turn-{outcome.cycle}")
        por_corr = {m["correlation_id"]: m for m in messages}

        for entry in plan.entries:
            corr = f"plan-{plan.cycle}-{entry.item_id}"
            msg = por_corr[corr]
            try:
                backlog.claim(entry.item_id, entry.seat)
            except Exception as e:  # item saiu de APPROVED no meio do caminho
                self._log("claim_failed", item_id=entry.item_id,
                          seat=entry.seat, motivo=str(e))
                outcome.failed += 1
                continue
            recado = dropbox.depositar(
                de=msg["de"], para=msg["para"], tipo=msg["tipo"],
                conteudo=msg["conteudo"], correlation_id=msg["correlation_id"])
            dropbox.reclamar(recado.msg_id, entry.seat)
            outcome.dispatched += 1
            self._log("dispatched", item_id=entry.item_id, seat=entry.seat,
                      msg_id=recado.msg_id)
            self._run_entry(entry, recado, backlog, dropbox, outcome,
                            budget_usd=budget_usd)

        self._worker = None
        return outcome

    # ---------- uma tarefa ----------

    def _run_entry(self, entry, recado, backlog, dropbox, outcome,
                   budget_usd: float) -> None:
        seat = entry.seat
        cycle = outcome.cycle
        ctx: Dict[str, Any] = {"attempt": 1, "item_id": entry.item_id,
                               "cycle": cycle}

        result, erro = self._call_worker(seat, recado.conteudo, ctx)
        if erro:
            return self._fail(dropbox, seat, entry, recado, erro, outcome)
        if not result["ok"]:
            motivo = ((result.get("report") or "").strip().split("\n")[0]
                      [:200] or "worker devolveu ok=False")
            return self._fail(dropbox, seat, entry, recado, motivo, outcome)

        # 1) o worker pediu divisão? (só com budget; turno zero-custo não divide)
        if result.get("split"):
            if self._run_split(entry, recado, result["split"], backlog,
                               dropbox, outcome, budget_usd):
                return
            # divisão recusada (já registrada no journal): segue o caminho
            # normal com o relatório que o worker já devolveu.

        # 2) portão do modo silencioso, com UMA chance de corrigir
        rel = analisar(result["report"])
        viol = rel.validar()
        if viol:
            dropbox.depositar(
                de=CEO, para=seat, tipo="RECADO",
                conteudo=("Seu relatório não passou no portão do modo "
                          "silencioso: " + "; ".join(viol) +
                          ". Reenvie em FEITO/ESTADO/ERRO/SUGESTÃO, "
                          "máx 10 linhas."),
                correlation_id=recado.correlation_id)
            self._log("report_retry", item_id=entry.item_id, seat=seat,
                      violacoes=viol)
            ctx["attempt"] = 2
            ctx["errors"] = viol
            result, erro = self._call_worker(seat, recado.conteudo, ctx)
            if erro:
                return self._fail(dropbox, seat, entry, recado, erro, outcome)
            rel = analisar(result["report"])
            viol = rel.validar()
            if viol:
                return self._fail(
                    dropbox, seat, entry, recado,
                    "relatório reprovado 2x no portão: " + "; ".join(viol),
                    outcome)

        # 3) responde no fio e conclui no backlog
        dropbox.responder(recado.msg_id, seat, result["report"])
        nota = rel.feito[0] if rel.feito else ""
        backlog.complete(entry.item_id, seat, note=nota)
        self._log("completed", item_id=entry.item_id, seat=seat)
        outcome.completed += 1

    # ---------- divisão de tarefa ----------

    def _run_split(self, entry, recado, split, backlog, dropbox, outcome,
                   budget_usd: float) -> bool:
        """Tenta executar a divisão pedida pelo worker. True = assumiu."""
        seat = entry.seat
        cycle = outcome.cycle
        if outcome.splits_used >= self._max_splits:
            self._log("split_rejected", item_id=entry.item_id, seat=seat,
                      motivo="teto de divisões do turno atingido")
            return False
        if not isinstance(split, list) or not split:
            self._log("split_rejected", item_id=entry.item_id, seat=seat,
                      motivo="pedido de divisão vazio ou malformado")
            return False
        if budget_usd <= 0:
            self._log("split_rejected", item_id=entry.item_id, seat=seat,
                      motivo="turno sem budget não divide em partes pagas")
            return False
        try:
            parts = [
                SplitPart(
                    title=p["title"],
                    instruction=p["instruction"],
                    acceptance=p.get("acceptance", ""),
                    assigned_agent_id=p["assigned_agent_id"],
                    budget_usd=p["budget_usd"],
                    max_turns=p.get("max_turns", 1),
                )
                for p in split
            ]
        except (KeyError, TypeError, AttributeError) as e:
            self._log("split_rejected", item_id=entry.item_id, seat=seat,
                      motivo=f"parte malformada: {e}")
            return False

        parent = Task(
            id=entry.item_id, session_id=cycle, title=entry.title,
            instruction=recado.conteudo, created_by_agent_id=CEO,
            assigned_agent_id=seat, state=TaskState.ASSIGNED,
            budget_usd=budget_usd, max_turns=entry.max_turns)
        try:
            children = split_task(parent, parts, splitter_agent_id=seat,
                                  journal=outcome.journal, clock=self._now)
        except TaskSplitError as e:
            self._log("split_rejected", item_id=entry.item_id, seat=seat,
                      motivo=str(e))
            return False

        outcome.splits_used += 1
        self._log("split_accepted", item_id=entry.item_id, seat=seat,
                  filhas=len(children))

        for child in children:
            cmsg = dropbox.depositar(
                de=seat, para=child.assigned_agent_id, tipo="RECADO",
                conteudo=child.instruction,
                correlation_id=recado.correlation_id)
            dropbox.reclamar(cmsg.msg_id, child.assigned_agent_id)
            cctx = {"attempt": 1, "item_id": child.id, "cycle": cycle,
                    "parent_item_id": entry.item_id}
            cres, cerro = self._call_worker(child.assigned_agent_id,
                                            child.instruction, cctx)
            if cerro:
                fail_child(child, cerro, child.assigned_agent_id,
                           journal=outcome.journal, clock=self._now)
                self._log("child_failed", child_id=child.id, motivo=cerro)
                continue
            if not cres.get("ok"):
                motivo = ((cres.get("report") or "").strip().split("\n")[0]
                          [:200] or "ok=False")
                fail_child(child, motivo, child.assigned_agent_id,
                           journal=outcome.journal, clock=self._now)
                self._log("child_failed", child_id=child.id, motivo=motivo)
                continue
            if cres.get("split"):
                # divisão aninhada: o turno só divide um nível.
                self._log("split_ignored_nested", child_id=child.id)
            crel = analisar(cres["report"])
            cviol = crel.validar()
            if cviol:
                motivo = "relatório da filha reprovado no portão: " \
                    + "; ".join(cviol)
                fail_child(child, motivo, child.assigned_agent_id,
                           journal=outcome.journal, clock=self._now)
                self._log("child_failed", child_id=child.id, motivo=motivo)
                continue
            dropbox.responder(cmsg.msg_id, child.assigned_agent_id,
                              cres["report"])
            nota = crel.feito[0] if crel.feito else "(sem FEITO)"
            complete_child(child, nota, child.assigned_agent_id,
                           journal=outcome.journal, clock=self._now)
            self._log("child_completed", child_id=child.id)

        estado, resumo = parent_outcome(children)
        if estado == TaskState.COMPLETED:
            linhas = [l for l in resumo.split("\n") if l.strip()]
            texto = ("RELATÓRIO (PROGRESSO)\nFEITO:\n"
                     + "\n".join("- " + l for l in linhas))
            dropbox.responder(recado.msg_id, seat, texto)
            backlog.complete(entry.item_id, seat,
                             note=f"{len(children)} partes concluídas")
            self._log("split_completed", item_id=entry.item_id,
                      filhas=len(children))
            outcome.completed += 1
        else:
            dropbox.depositar(
                de=seat, para=CEO, tipo="ALERTA",
                conteudo=(f"[TURNO {cycle}] Divisão de {entry.item_id} "
                          f"falhou: {resumo}"),
                correlation_id=recado.correlation_id)
            self._log("split_failed", item_id=entry.item_id, motivo=resumo)
            outcome.failed += 1
        return True

    # ---------- apoio ----------

    def _call_worker(self, seat: str, order_text: str,
                     ctx: Dict[str, Any]):
        """Chama o worker e valida o contrato. (result, None) ou (None, erro)."""
        try:
            result = self._worker(seat, order_text, ctx)
        except Exception as e:
            return None, f"worker explodiu: {e}"
        if not isinstance(result, dict):
            return None, "worker não devolveu um dicionário"
        if not isinstance(result.get("ok"), bool):
            return None, "worker não devolveu 'ok' (bool)"
        if not isinstance(result.get("report"), str):
            return None, "worker não devolveu 'report' (str)"
        return result, None

    def _fail(self, dropbox, seat, entry, recado, motivo, outcome) -> None:
        dropbox.depositar(
            de=seat, para=CEO, tipo="ALERTA",
            conteudo=(f"[TURNO {outcome.cycle}] {seat} não concluiu "
                      f"{entry.item_id}: {motivo}"),
            correlation_id=recado.correlation_id)
        self._log("failed", item_id=entry.item_id, seat=seat, motivo=motivo)
        outcome.failed += 1

    def _log(self, event: str, **fields: Any) -> None:
        entry: Dict[str, Any] = {"ts": self._now(), "event": event}
        entry.update(fields)
        self._journal.append(entry)
