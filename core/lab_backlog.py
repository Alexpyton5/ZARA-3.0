"""
ZARA Lab — Backlog de melhorias (alicerce da Fase D "LAB VIVO").

O Lab mantém uma fila priorizada de propostas de melhoria. Regras:
- Qualquer assento do Lab pode PROPOR.
- Só a CEO (a zoe) APROVA ou REJEITA — nada entra no plano sem o OK dela.
- Item aprovado pode ser REIVINDICADO por um agente (um dono por item) e CONCLUÍDO.
- Prioridade = fórmula determinística (impacto, urgência, custo) + desempate por
  ordem de chegada. Nada de "achismo" escondido: o score é auditável.
- Tudo vira journal com timestamp (relógio injetável — testes não dependem de hora).

Lógica pura: sem rede, sem modelo, custo zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class BacklogState(str, Enum):
    PROPOSED = "PROPOSED"      # proposto, aguardando a CEO
    APPROVED = "APPROVED"      # a zoe aprovou, livre pra reivindicar
    REJECTED = "REJECTED"      # a zoe (ou o CRITIC) rejeitou, com motivo
    CLAIMED = "CLAIMED"        # um agente pegou, está trabalhando
    DONE = "DONE"              # concluído e registrado


class BacklogError(Exception):
    """Qualquer transição ilegal ou dado inválido cai aqui."""


# Pesos da fórmula de prioridade: impacto pesa mais que urgência;
# custo alto derruba a posição (o Alex odeia custo-surpresa).
_W_IMPACT = 3
_W_URGENCY = 2
_W_COST = 2


def priority_score(impact: int, urgency: int, cost: int) -> int:
    """Score determinístico 1..19. Maior = fazer primeiro."""
    for name, v in (("impact", impact), ("urgency", urgency), ("cost", cost)):
        if not isinstance(v, int) or not 1 <= v <= 5:
            raise BacklogError(f"{name} deve ser inteiro de 1 a 5, veio {v!r}")
    return impact * _W_IMPACT + urgency * _W_URGENCY - cost * _W_COST


def _check_text(value: Any, name: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BacklogError(f"{name} não pode ser vazio")
    value = value.strip()
    if len(value) > max_len:
        raise BacklogError(f"{name} passou do limite ({len(value)} > {max_len})")
    return value


@dataclass
class BacklogItem:
    seq: int                      # ordem de chegada (desempate)
    item_id: str                  # "BLG-0001"
    title: str
    description: str
    proposed_by: str              # id do agente que propôs
    impact: int                   # 1..5
    urgency: int                  # 1..5
    cost: int                     # 1..5 (esforço/custo)
    state: BacklogState = BacklogState.PROPOSED
    score: int = 0
    claimed_by: Optional[str] = None
    journal: List[Dict[str, Any]] = field(default_factory=list)


class LabBacklog:
    """O backlog do Lab. Um dono por item, a CEO aprova o plano."""

    def __init__(self, clock: Optional[Callable[[], str]] = None) -> None:
        self._items: Dict[str, BacklogItem] = {}
        self._seq = 0
        self._clock = clock or (lambda: "unknown")

    # ---------- proposta ----------
    def propose(
        self,
        title: str,
        description: str,
        proposed_by: str,
        impact: int,
        urgency: int,
        cost: int,
    ) -> BacklogItem:
        title = _check_text(title, "title", 140)
        description = _check_text(description, "description", 1000)
        proposed_by = _check_text(proposed_by, "proposed_by", 80)
        score = priority_score(impact, urgency, cost)
        self._seq += 1
        item = BacklogItem(
            seq=self._seq,
            item_id=f"BLG-{self._seq:04d}",
            title=title,
            description=description,
            proposed_by=proposed_by,
            impact=impact,
            urgency=urgency,
            cost=cost,
            score=score,
        )
        self._log(item, "proposed", by=proposed_by)
        self._items[item.item_id] = item
        return item

    # ---------- aprovação (só a CEO) ----------
    def approve(self, item_id: str, by: str) -> BacklogItem:
        item = self._get(item_id)
        if by != "CEO":
            raise BacklogError("só a CEO aprova item do backlog")
        if item.state is not BacklogState.PROPOSED:
            raise BacklogError(f"item {item_id} não está PROPOSED (está {item.state.value})")
        item.state = BacklogState.APPROVED
        self._log(item, "approved", by=by)
        return item

    def reject(self, item_id: str, by: str, reason: str) -> BacklogItem:
        item = self._get(item_id)
        if by not in ("CEO", "CRITIC"):
            raise BacklogError("só a CEO ou o CRITIC rejeitam item do backlog")
        if item.state is not BacklogState.PROPOSED:
            raise BacklogError(f"item {item_id} não está PROPOSED (está {item.state.value})")
        reason = _check_text(reason, "reason", 280)
        item.state = BacklogState.REJECTED
        self._log(item, "rejected", by=by, detail=reason)
        return item

    # ---------- execução ----------
    def claim(self, item_id: str, agent_id: str) -> BacklogItem:
        item = self._get(item_id)
        if item.state is not BacklogState.APPROVED:
            raise BacklogError(f"item {item_id} não está APPROVED (está {item.state.value})")
        agent_id = _check_text(agent_id, "agent_id", 80)
        item.state = BacklogState.CLAIMED
        item.claimed_by = agent_id
        self._log(item, "claimed", by=agent_id)
        return item

    def complete(self, item_id: str, agent_id: str, note: str = "") -> BacklogItem:
        item = self._get(item_id)
        if item.state is not BacklogState.CLAIMED:
            raise BacklogError(f"item {item_id} não está CLAIMED (está {item.state.value})")
        if item.claimed_by != agent_id:
            raise BacklogError("só quem reivindicou conclui o item")
        item.state = BacklogState.DONE
        self._log(item, "done", by=agent_id, detail=note[:280])
        return item

    def release(self, item_id: str, by: str, reason: str) -> BacklogItem:
        """Devolve um item CLAIMED para APPROVED (watchdog do loop: o dono sumiu).

        Só a CEO libera. O item volta pra fila como estava antes de ser
        reivindicado; o motivo fica no journal (auditável).
        """
        item = self._get(item_id)
        if by != "CEO":
            raise BacklogError("só a CEO libera item reivindicado")
        if item.state is not BacklogState.CLAIMED:
            raise BacklogError(f"item {item_id} não está CLAIMED (está {item.state.value})")
        reason = _check_text(reason, "reason", 280)
        item.state = BacklogState.APPROVED
        item.claimed_by = None
        self._log(item, "released", by=by, detail=reason)
        return item

    def archive(self, item_id: str, by: str, reason: str) -> BacklogItem:
        """Arquiva uma tarefa problemática: sai da fila (vira REJECTED).

        Só a CEO (ou o Alex) arquiva. Vale para PROPOSED, APPROVED e CLAIMED
        (uma tarefa que quebra toda vez que roda para de voltar pra fila).
        O motivo fica no journal (auditável).
        """
        item = self._get(item_id)
        if by not in ("CEO", "ALEX"):
            raise BacklogError("só a CEO (ou o Alex) arquiva item do backlog")
        if item.state not in (BacklogState.PROPOSED, BacklogState.APPROVED,
                              BacklogState.CLAIMED):
            raise BacklogError(f"item {item_id} não pode ser arquivado "
                               f"(está {item.state.value})")
        reason = _check_text(reason, "reason", 700)
        item.state = BacklogState.REJECTED
        item.claimed_by = None
        self._log(item, "archived", by=by, detail=reason)
        return item

    # ---------- leitura ----------
    def get(self, item_id: str) -> BacklogItem:
        return self._get(item_id)

    def ranked(self, states: Optional[List[BacklogState]] = None) -> List[BacklogItem]:
        """Fila ordenada: score maior primeiro; empate = quem chegou primeiro."""
        items = list(self._items.values())
        if states is not None:
            wanted = {s.value for s in states}
            items = [i for i in items if i.state.value in wanted]
        return sorted(items, key=lambda i: (-i.score, i.seq))

    def plan_for_ceo(self) -> List[BacklogItem]:
        """O que a zoe precisa olhar: propostos + aprovados, na ordem de prioridade."""
        return self.ranked([BacklogState.PROPOSED, BacklogState.REJECTED,
                            BacklogState.APPROVED])

    # ---------- interno ----------
    def _get(self, item_id: str) -> BacklogItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise BacklogError(f"item inexistente: {item_id}")

    def _log(self, item: BacklogItem, event: str, by: str,
             detail: str = "") -> None:
        entry: Dict[str, Any] = {"t": self._clock(), "event": event, "by": by}
        if detail:
            entry["detail"] = detail
        item.journal.append(entry)
