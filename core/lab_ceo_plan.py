"""ZARA Lab — O plano do turno (mecânica da Fase D "LAB VIVO").

A CEO (a zoe) olha o backlog aprovado e transforma em ordens para os
assentos: um item aprovado vira uma tarefa com dono. Regras:

- Só item APPROVED entra no plano. PROPOSED/REJECTED/CLAIMED/DONE ficam fora.
- A CEO nunca é dona de tarefa — ela aprova e distribui.
- Uma tarefa, um dono; por padrão, um assento leva no máximo 1 tarefa por
  plano (divisão justa; `max_per_seat` ajusta).
- Cada tarefa recebe tipo (VOICE, UI, BACKEND, TEST, LAB, DOCS, RESEARCH,
  REVIEW, BUILD, MISC) por tabela de palavras-chave determinística —
  nada de "achismo" escondido: o tipo é auditável.
- Tarefa que nenhum assento livre alcança vai para `unassigned` COM o motivo
  (NO_SEAT_FOR_KIND ou ALL_CAPABLE_BUSY) — o plano não finge que cobriu tudo.
- Cada tarefa carrega budget_usd + max_turns (padrão zero custo): tarefa é
  limitada, como no `lab_task_split`.
- `to_dropbox_messages()` empacota o plano em recados prontos para a
  caixinha dos assentos (`lab_dropbox`): uma ordem por assento + um resumo
  para TODOS. A ordem nunca carrega conteúdo de arquivo — só nomes e estados.

Lógica pura, stdlib, zero custo/rede/quota.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
except ImportError:  # rodando flat (testes locais)
    from lab_backlog import BacklogError, BacklogState, LabBacklog


class PlanError(ValueError):
    """O plano não pôde ser montado."""


# Ordem oficial dos 11 assentos (a mesma do fixed_seats / ping).
SEATS: Tuple[str, ...] = (
    "CEO", "ARCHITECT", "UI_DESIGNER", "ENGINEER", "SCRIBE",
    "REVIEWER", "CRITIC", "SECRETARY", "TESTER", "RESEARCHER", "PACKAGER",
)

CEO = "CEO"

# Tipos de tarefa. MISC = "ninguém sabe fazer" — vai para unassigned com motivo.
KINDS: Tuple[str, ...] = (
    "BACKEND", "VOICE", "UI", "TEST", "LAB",
    "DOCS", "RESEARCH", "REVIEW", "BUILD", "MISC",
)

# O que cada assento sabe fazer. A CEO não executa — só aprova e distribui.
SEAT_KINDS: Dict[str, Tuple[str, ...]] = {
    "CEO": (),
    "ARCHITECT": ("BACKEND", "LAB"),
    "UI_DESIGNER": ("UI",),
    "ENGINEER": ("BACKEND", "VOICE", "LAB"),
    "SCRIBE": ("DOCS",),
    "REVIEWER": ("REVIEW", "TEST"),
    "CRITIC": ("REVIEW",),
    "SECRETARY": ("DOCS",),
    "TESTER": ("TEST", "VOICE"),
    "RESEARCHER": ("RESEARCH",),
    "PACKAGER": ("BUILD",),
}

# Tabela de palavras-chave: primeira que casar (nesta ordem) define o tipo.
# Minúsculas, sem acento duplicado — determinística e auditável.
_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("VOICE", ("voz", "voice", "tts", "microfone", "vosk", "fala",
                "kore", "kokoro", "edge-tts", "stt")),
    ("TEST", ("teste", "test", "suite", "suíte", "gate", "regressao",
               "regressão", "flak", "coverage", "cobertura")),
    ("BUILD", ("build", "exe", "instalador", "empacot", "release",
                "publica", "publicar", "push", "installer")),
    ("UI", ("interface", "tela", "botao", "botão", "frontend", "tsx",
             "electron", "janela", "painel", "componente", "css")),
    ("LAB", ("lab", "assento", "bot", "agente", "caixinha", "dropbox",
              "conselho", "council", "megazord")),
    ("DOCS", ("doc", "manual", "readme", "mapa", "guia", "leia-me",
               "documenta", "changelog")),
    ("RESEARCH", ("pesquisa", "levantamento", "benchmark", "auditoria",
                   "research", "comparar", "avalia")),
    ("REVIEW", ("revis", "review", "triagem", "critic", "auditoria de",
                 "aprovacao", "aprovação")),
    ("BACKEND", ("ipc", "backend", "python", "core/", "refator",
                  "scheduler", "router", "orkestr", "memoria", "memória",
                  "nervos", "websocket", "api", "banco", "cache")),
)


def kind_for(title: str, description: str = "") -> str:
    """Tipo determinístico da tarefa a partir do título + descrição."""
    text = f"{title or ''} {description or ''}".lower()
    for kind, keywords in _KEYWORDS:
        if any(kw in text for kw in keywords):
            return kind
    return "MISC"


@dataclass(frozen=True)
class PlanEntry:
    plan_seq: int
    item_id: str
    title: str
    kind: str
    score: int
    seat: str                 # o dono
    budget_usd: float
    max_turns: int
    cycle: str


@dataclass(frozen=True)
class UnassignedItem:
    item_id: str
    title: str
    kind: str
    score: int
    reason: str               # NO_SEAT_FOR_KIND | ALL_CAPABLE_BUSY


@dataclass
class TurnPlan:
    cycle: str
    entries: List[PlanEntry]
    unassigned: List[UnassignedItem]
    journal: List[Dict[str, Any]] = field(default_factory=list)


class CeoPlan:
    """A CEO monta o plano do turno a partir do backlog aprovado."""

    def __init__(self, *, now: Callable[[], float] = time.time) -> None:
        self._now = now
        self._cycle_seq = 0

    # ---------- montagem ----------
    def build(
        self,
        backlog: LabBacklog,
        cycle: str,
        *,
        max_per_seat: int = 1,
        budget_usd: float = 0.0,
        max_turns: int = 10,
    ) -> TurnPlan:
        if not isinstance(cycle, str) or not cycle.strip():
            raise PlanError("cycle não pode ser vazio")
        if not isinstance(max_per_seat, int) or max_per_seat < 1:
            raise PlanError("max_per_seat deve ser inteiro >= 1")
        cycle = cycle.strip()
        self._cycle_seq += 1
        plan = TurnPlan(cycle=cycle, entries=[], unassigned=[])
        load: Dict[str, int] = {seat: 0 for seat in SEATS}

        approved = [i for i in backlog.ranked()
                    if i.state is BacklogState.APPROVED]
        if not approved:
            self._log(plan, "plan_empty", "nenhum item APPROVED no backlog")
            return plan

        seq = 0
        for item in approved:
            kind = kind_for(item.title, item.description)
            seat = self._pick_seat(kind, load, max_per_seat)
            if seat is None:
                reason = ("NO_SEAT_FOR_KIND" if kind == "MISC"
                          else "ALL_CAPABLE_BUSY")
                plan.unassigned.append(UnassignedItem(
                    item_id=item.item_id, title=item.title,
                    kind=kind, score=item.score, reason=reason))
                self._log(plan, "unassigned",
                          f"{item.item_id} ({kind}): {reason}")
                continue
            seq += 1
            load[seat] += 1
            plan.entries.append(PlanEntry(
                plan_seq=seq, item_id=item.item_id, title=item.title,
                kind=kind, score=item.score, seat=seat,
                budget_usd=budget_usd, max_turns=max_turns, cycle=cycle))
            self._log(plan, "assigned",
                      f"{item.item_id} -> {seat} ({kind}, score {item.score})")
        return plan

    @staticmethod
    def _pick_seat(kind: str, load: Dict[str, int],
                   max_per_seat: int) -> Optional[str]:
        for seat in SEATS:
            if seat == CEO:
                continue
            if kind not in SEAT_KINDS.get(seat, ()):
                continue
            if load[seat] >= max_per_seat:
                continue
            return seat
        return None

    # ---------- empacotamento para a caixinha ----------
    def to_dropbox_messages(self, plan: TurnPlan,
                            run_id: str) -> List[Dict[str, str]]:
        """Ordens prontas para a caixinha: uma por assento + resumo p/ TODOS.

        Formato compatível com `lab_dropbox.deposit`: para / de / correlation_id
        / tipo / conteudo. O conteúdo leva só nomes e estados — nunca conteúdo
        de arquivo.
        """
        if not isinstance(run_id, str) or not run_id.strip():
            raise PlanError("run_id não pode ser vazio")
        run_id = run_id.strip()
        messages: List[Dict[str, str]] = []
        for entry in plan.entries:
            corr = f"plan-{plan.cycle}-{entry.item_id}"
            body = (
                f"[PLANO {plan.cycle}] Ordem da CEO\n"
                f"Item: {entry.item_id} — {entry.title}\n"
                f"Tipo: {entry.kind} | Score: {entry.score}\n"
                f"Limites: budget_usd={entry.budget_usd} max_turns={entry.max_turns}\n"
                f"Regras: uma tarefa, um dono. Reporte por FEITO/ESTADO/ERRO/SUGESTAO "
                f"(lab_report). Se travar de verdade, peça decisao no modo silencioso."
            )
            messages.append({
                "para": entry.seat,
                "de": CEO,
                "correlation_id": corr,
                "tipo": "RECADO",
                "conteudo": body,
            })
        summary_lines = [
            f"[PLANO {plan.cycle}] Resumo do turno",
            f"Tarefas distribuidas: {len(plan.entries)}",
        ]
        for entry in plan.entries:
            summary_lines.append(f"- {entry.item_id} ({entry.kind}) -> {entry.seat}")
        if plan.unassigned:
            summary_lines.append(f"Sem dono ({len(plan.unassigned)}):")
            for u in plan.unassigned:
                summary_lines.append(f"- {u.item_id} ({u.kind}): {u.reason}")
        messages.append({
            "para": "TODOS",
            "de": CEO,
            "correlation_id": f"plan-{plan.cycle}-resumo",
            "tipo": "RECADO",
            "conteudo": "\n".join(summary_lines),
        })
        # A caixinha é recado, não relatório: 64KB é o teto (lab_dropbox).
        for msg in messages:
            if len(msg["conteudo"]) > 64 * 1024:
                raise PlanError("mensagem do plano passou de 64KB")
        return messages

    # ---------- interno ----------
    def _log(self, plan: TurnPlan, op: str, detail: str) -> None:
        plan.journal.append({"t": self._now(), "op": op, "detail": detail})
