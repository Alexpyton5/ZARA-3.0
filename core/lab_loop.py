"""ZARA Lab — O condutor do loop contínuo (mecânica da GIGANTE 2 "LAB VIVO").

O motor do turno (lab_turn) roda UM turno. Este módulo é o que mantém o Lab
vivo de verdade: ciclos repetidos, com memória entre eles.

O que o condutor faz a cada ciclo:

1. WATCHDOG: item CLAIMED há mais de `stuck_after_cycles` ciclos sem concluir
   = o dono sumiu. A CEO devolve o item pra fila (release → APPROVED) e manda
   ALERTA. Silêncio nunca vira tarefa presa pra sempre.
2. ORÇAMENTO DO LOOP: cada ciclo pode conceder até `budget_usd`; o total
   concedido nunca passa de `total_budget_usd`. Estourou → o loop para ocioso
   (BUDGET_EXHAUSTED). O Alex odeia custo-surpresa; o loop não gasta no escuro.
3. BACKOFF: `max_consecutive_failures` ciclos falhando seguidos → o loop PAUSA.
   A CEO decide e chama resume(). O loop nunca gira em falso queimando cota.
4. TRABALHO: delega o turno ao `turn_runner` (padrão: lab_turn de verdade).

Tudo injetável (backlog, dropbox, turn runner, worker, relógio, notify):
lógica pura, stdlib, zero custo/rede/quota. O notify recebe só nomes e
estados — nunca conteúdo de arquivo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
except ImportError:  # rodando flat (testes locais)
    from lab_backlog import BacklogError, BacklogState, LabBacklog

try:
    from core.lab_ceo_plan import CEO
except ImportError:
    from lab_ceo_plan import CEO

try:
    from core.lab_turn import LabTurn
except ImportError:
    from lab_turn import LabTurn


class LoopError(Exception):
    """Configuração inválida ou uso ilegal do condutor."""


# Motivos de ociosidade (idle_reason do CycleReport)
NO_APPROVED_WORK = "NO_APPROVED_WORK"    # nada aprovado na fila
NO_ASSIGNABLE = "NO_ASSIGNABLE"          # aprovados, mas ninguém sabe fazer
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"    # orçamento do loop acabou
PAUSED = "PAUSED"                        # loop pausado (backoff)


@dataclass
class CycleReport:
    cycle: int                            # número do ciclo (1, 2, 3...)
    idle: bool                            # True = nada rodou neste ciclo
    idle_reason: Optional[str]            # motivo da ociosidade (ou None)
    dispatched: int                       # tarefas despachadas no turno
    completed: int                        # tarefas concluídas no turno
    failed: int                           # tarefas que falharam no turno
    stuck_released: List[str]             # item_ids devolvidos pelo watchdog
    released_failed: List[str] = field(default_factory=list)  # falhas de volta pra fila
    paused: bool = False                  # o loop pausou neste ciclo (backoff)
    journal: List[Dict[str, Any]] = field(default_factory=list)


class LabLoop:
    """O condutor: roda ciclos do Lab até acabar o trabalho (ou pausar)."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.time,
        turn_runner: Optional[Callable[..., Any]] = None,
        notify: Optional[Callable[[str, str], None]] = None,
        max_consecutive_failures: int = 3,
        stuck_after_cycles: int = 2,
    ) -> None:
        if max_consecutive_failures < 1:
            raise LoopError("max_consecutive_failures precisa ser >= 1")
        if stuck_after_cycles < 1:
            raise LoopError("stuck_after_cycles precisa ser >= 1")
        self._now = now
        self._turn_runner = turn_runner or self._default_turn_runner()
        self._notify = notify or (lambda tipo, resumo: None)
        self._max_consecutive_failures = max_consecutive_failures
        self._stuck_after_cycles = stuck_after_cycles
        self._cycle = 0
        self._consecutive_failures = 0
        self._paused = False
        self._granted_usd = 0.0
        self._claimed_seen: Dict[str, int] = {}
        self._journal: List[Dict[str, Any]] = []

    # ---------- estado ----------

    @property
    def state(self) -> str:
        return PAUSED if self._paused else "RUNNING"

    def journal(self) -> List[Dict[str, Any]]:
        return list(self._journal)

    def resume(self) -> None:
        """A CEO decide: o loop volta a rodar (zera o contador de falhas)."""
        self._paused = False
        self._consecutive_failures = 0
        self._log("resumed", by=CEO)

    # ---------- ciclo ----------

    def run_cycle(
        self,
        backlog: LabBacklog,
        dropbox: Any,
        worker: Callable[..., Any],
        *,
        budget_usd: float = 0.0,
        total_budget_usd: float = 0.0,
        max_turns: int = 0,
        max_per_seat: int = 1,
        max_splits: int = 3,
    ) -> CycleReport:
        self._cycle += 1
        n = self._cycle
        report = CycleReport(
            cycle=n, idle=False, idle_reason=None, dispatched=0,
            completed=0, failed=0, stuck_released=[], paused=False,
        )

        if self._paused:
            report.idle = True
            report.idle_reason = PAUSED
            report.paused = True
            self._log("cycle_skipped_paused", cycle=n)
            report.journal = list(self._journal)
            return report

        # 1) watchdog: dono sumiu? devolve pra fila.
        report.stuck_released = self._watchdog(backlog, n)

        # 2) orçamento do loop
        cycle_grant = budget_usd
        if total_budget_usd > 0:
            remaining = total_budget_usd - self._granted_usd
            if remaining <= 0:
                return self._idle(report, BUDGET_EXHAUSTED, n,
                                  "orçamento do loop esgotado")
            cycle_grant = min(cycle_grant, remaining)

        # 3) há trabalho aprovado?
        approved = [i for i in backlog.plan_for_ceo()
                    if i.state is BacklogState.APPROVED]
        if not approved:
            return self._idle(report, NO_APPROVED_WORK, n,
                              "nada aprovado na fila")

        # 4) roda o turno (o motor de verdade)
        cycle_label = f"LOOP-{n}"
        claimed_before = {i.item_id for i in backlog.ranked([BacklogState.CLAIMED])}
        try:
            outcome = self._turn_runner(
                backlog=backlog, dropbox=dropbox, worker=worker,
                cycle=cycle_label,
                budget_usd=cycle_grant, max_turns=max_turns,
                max_per_seat=max_per_seat, max_splits=max_splits,
            )
        except Exception as exc:  # o turno quebrou: conta como ciclo falho
            self._consecutive_failures += 1
            self._log("cycle_turn_crashed", cycle=n,
                      detail=str(exc)[:200])
            report.failed = 1
            self._check_backoff(report, n)
            report.journal = list(self._journal)
            return report

        # 4b) o que o turno reivindicou e não concluiu volta pra fila:
        #     falha não vira tarefa presa, e o próximo ciclo tenta de novo.
        #     (Se falhar direto de novo, o backoff pausa o loop.)
        for item in backlog.ranked([BacklogState.CLAIMED]):
            if item.item_id in claimed_before:
                continue
            try:
                backlog.release(item.item_id, by=CEO,
                                reason="FALHA_NO_TURNO")
            except BacklogError as exc:
                self._log("failed_release_failed", cycle=n,
                          detail=f"{item.item_id}: {exc}"[:200])
                continue
            report.released_failed.append(item.item_id)
            self._log("failed_released", cycle=n,
                      detail=f"{item.item_id} falhou no turno — de volta pra fila")

        report.dispatched = outcome.dispatched
        report.completed = outcome.completed
        report.failed = outcome.failed
        if outcome.dispatched > 0:
            self._granted_usd += cycle_grant

        if outcome.dispatched == 0:
            reason = NO_ASSIGNABLE if outcome.unassigned else NO_APPROVED_WORK
            return self._idle(report, reason, n,
                              "turno não despachou trabalho")

        # 5) placar de falhas consecutivas
        if outcome.failed > 0:
            self._consecutive_failures += 1
            self._log("cycle_failed", cycle=n,
                      detail=f"{outcome.failed} falha(s)")
        elif outcome.completed > 0:
            self._consecutive_failures = 0
        self._check_backoff(report, n)

        self._log("cycle_done", cycle=n,
                  detail=(f"dispatched={outcome.dispatched} "
                          f"completed={outcome.completed} "
                          f"failed={outcome.failed}"))
        report.journal = list(self._journal)
        return report

    def run_until_idle(
        self,
        backlog: LabBacklog,
        dropbox: Any,
        worker: Callable[..., Any],
        *,
        max_cycles: int = 10,
        **turn_kwargs: Any,
    ) -> List[CycleReport]:
        """Roda ciclos até ociosidade, pausa ou o teto de ciclos."""
        if max_cycles < 1:
            raise LoopError("max_cycles precisa ser >= 1")
        reports: List[CycleReport] = []
        for _ in range(max_cycles):
            rep = self.run_cycle(backlog, dropbox, worker, **turn_kwargs)
            reports.append(rep)
            if rep.idle or rep.paused:
                break
        return reports

    # ---------- interno ----------

    def _default_turn_runner(self) -> Callable[..., Any]:
        turn = LabTurn(now=self._now)
        return turn.run

    def _idle(self, report: CycleReport, reason: str, n: int,
              detail: str) -> CycleReport:
        report.idle = True
        report.idle_reason = reason
        self._log("cycle_idle", cycle=n, detail=f"{reason}: {detail}")
        report.journal = list(self._journal)
        return report

    def _check_backoff(self, report: CycleReport, n: int) -> None:
        if self._consecutive_failures >= self._max_consecutive_failures:
            self._paused = True
            report.paused = True
            msg = (f"loop pausado após {self._consecutive_failures} "
                   f"ciclos falhando seguidos (ciclo {n})")
            self._log("loop_paused", cycle=n, detail=msg)
            # só nomes e estados — nunca conteúdo de arquivo
            self._notify("ALERTA", f"LOOP_PAUSADO ciclo={n} "
                                   f"falhas_seguidas={self._consecutive_failures}")

    def _watchdog(self, backlog: LabBacklog, n: int) -> List[str]:
        """Devolve pra fila o que está CLAIMED há ciclos demais."""
        released: List[str] = []
        try:
            claimed = backlog.ranked([BacklogState.CLAIMED])
        except Exception:
            return released
        seen_now = set()
        for item in claimed:
            seen_now.add(item.item_id)
            count = self._claimed_seen.get(item.item_id, 0) + 1
            if count > self._stuck_after_cycles:
                try:
                    backlog.release(item.item_id, by=CEO,
                                    reason="STUCK_SEM_PROGRESSO")
                except BacklogError as exc:
                    self._log("watchdog_release_failed", cycle=n,
                              detail=f"{item.item_id}: {exc}"[:200])
                    continue
                released.append(item.item_id)
                self._log("watchdog_released", cycle=n,
                          detail=(f"{item.item_id} CLAIMED há {count} ciclos "
                                  f"sem concluir — devolvido pra fila"))
                # só nomes e estados — nunca conteúdo de arquivo
                self._notify("ALERTA",
                             f"STUCK_RELEASED item={item.item_id} "
                             f"ciclos_claimed={count}")
            else:
                self._claimed_seen[item.item_id] = count
        for item_id in [k for k in self._claimed_seen if k not in seen_now]:
            del self._claimed_seen[item_id]
        return released

    def _log(self, event: str, **kw: Any) -> None:
        entry: Dict[str, Any] = {"t": self._now(), "event": event}
        entry.update(kw)
        self._journal.append(entry)
