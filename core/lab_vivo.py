# -*- coding: utf-8 -*-
"""O Lab Vivo plugado — a fiação que liga o alicerce de verdade.

GIGANTE 2 "LAB VIVO". Junta as peças prontas (backlog, plano da CEO,
caixinha, turno, loop, memória) com o worker REAL (lab_workers) e
estado persistido em .lab-vivo/ dentro do app.

Nada aqui chama modelo, rede ou API paga: custo zero.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.lab_backlog import BacklogItem, BacklogState, LabBacklog
from core.lab_ceo_plan import CeoPlan
from core.lab_dropbox import Dropbox
from core.lab_loop import LabLoop
from core.lab_memory import LabMemory
from core.lab_seed_proposals import seed as semear_propostas
from core.lab_turn import LabTurn
from core.lab_workers import SEAT_ROLES, worker_vivo_factory


class LabVivoError(ValueError):
    """Configuração inválida do Lab Vivo."""


def _item_para_dict(item: BacklogItem) -> Dict[str, Any]:
    d = dataclasses.asdict(item)
    d["state"] = item.state.value
    return d


def _dict_para_item(d: Dict[str, Any]) -> BacklogItem:
    d = dict(d)
    d["state"] = BacklogState(d["state"])
    return BacklogItem(**d)


class LabVivo:
    """O Lab rodando de verdade: backlog em arquivo, caixinha no disco,
    turno com worker real e loop contínuo até esvaziar a fila."""

    def __init__(self, raiz_app: Path,
                 relogio: Optional[Callable[[], str]] = None) -> None:
        self.raiz = Path(raiz_app)
        self.estado = self.raiz / ".lab-vivo"
        self.dir_caixinha = self.estado / "caixinha"
        self.dir_work = self.estado / "work"
        self.dir_alvo_update = self.estado / "sandbox-alvo"
        self.dir_publicado = self.estado / "publicado"
        self.arq_backlog = self.estado / "backlog.json"
        self._relogio = relogio or (lambda: "AGORA")
        self.backlog = LabBacklog(clock=self._relogio)
        self.caixinha = Dropbox(self.dir_caixinha, clock=self._relogio)
        self.memoria = LabMemory()
        self.turno = LabTurn()
        self.loop = LabLoop()
        self.plano_ceo = CeoPlan()
        self._worker = worker_vivo_factory(self.dir_work, self.backlog)

    # ---------- estado ----------

    def preparar(self) -> None:
        """Cria as pastas, carrega o backlog do disco e semeia propostas."""
        for p in (self.dir_caixinha, self.dir_work, self.dir_alvo_update,
                  self.dir_publicado):
            p.mkdir(parents=True, exist_ok=True)
        self.carregar_backlog()
        semeadas = semear_propostas(self.backlog)
        if semeadas:
            self.salvar_backlog()
        # reabre a caixinha sobre a pasta (Dropbox lê do disco)
        self.caixinha = Dropbox(self.dir_caixinha, clock=self._relogio)

    def salvar_backlog(self) -> None:
        itens = [_item_para_dict(i) for i in self.backlog.ranked()]
        self.arq_backlog.write_text(
            json.dumps({"itens": itens}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    def carregar_backlog(self) -> None:
        if not self.arq_backlog.exists():
            return
        dados = json.loads(self.arq_backlog.read_text(encoding="utf-8"))
        for d in dados.get("itens", []):
            item = _dict_para_item(d)
            self.backlog._items[item.item_id] = item
            try:
                seq = int(item.item_id.split("-")[1])
            except (IndexError, ValueError):
                seq = 0
            self.backlog._seq = max(self.backlog._seq, seq, item.seq)

    # ---------- operação ----------

    def aprovar_topo(self) -> Optional[BacklogItem]:
        """A CEO aprova a proposta de maior prioridade ainda PROPOSTA."""
        propostos = [i for i in self.backlog.ranked()
                     if i.state == BacklogState.PROPOSED]
        if not propostos:
            return None
        topo = propostos[0]
        self.backlog.approve(topo.item_id, by="CEO")
        self.salvar_backlog()
        return self.backlog.get(topo.item_id)

    def rodar_turno(self, ciclo: str, budget_usd: float = 1.0) -> Any:
        """Roda um turno real: plano da CEO -> caixinha -> worker -> DONE."""
        saida = self.turno.run(
            backlog=self.backlog,
            dropbox=self.caixinha,
            worker=self._worker,
            cycle=ciclo,
            budget_usd=budget_usd,
            max_turns=10,
            max_per_seat=2,
            max_splits=3,
        )
        self.salvar_backlog()
        return saida

    def rodar_ate_ocioso(self, max_cycles: int = 6,
                         budget_usd: float = 1.0) -> List[Any]:
        """Loop contínuo: aprova o topo e roda turnos até a fila esvaziar."""
        relatorios = []
        for _ in range(1, max_cycles + 1):
            if self.aprovar_topo() is None:
                break
            rel = self.loop.run_cycle(
                backlog=self.backlog,
                dropbox=self.caixinha,
                worker=self._worker,
                budget_usd=budget_usd,
                max_turns=10,
                max_per_seat=2,
                max_splits=3,
            )
            relatorios.append(rel)
            self.salvar_backlog()
            if getattr(rel, "paused", False):
                break
        return relatorios

    def resumo(self) -> Dict[str, Any]:
        contagem: Dict[str, int] = {}
        for i in self.backlog.ranked():
            contagem[i.state.value] = contagem.get(i.state.value, 0) + 1
        return {
            "assentos": len(SEAT_ROLES),
            "backlog_estados": contagem,
            "backlog_arquivo": str(self.arq_backlog),
            "caixinha": str(self.dir_caixinha),
            "work": str(self.dir_work),
        }
