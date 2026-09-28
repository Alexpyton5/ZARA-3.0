# -*- coding: utf-8 -*-
"""Fase D da GIGANTE 2 "LAB VIVO" — o backlog de melhorias do próprio Lab.

- Semeia as 8 propostas reais (lab_seed_proposals, idempotente);
- registra a MELHORIA 1 do Lab Vivo com MOTIVO + RISCO explícitos;
- a CEO aprova a proposta do topo do ranking;
- tudo persiste em .lab-vivo/backlog.json (arquivo no repo).

Uso (na raiz do app):
    .\\.venv\\Scripts\\python.exe tools\\lab_melhoria_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lab_backlog import BacklogState  # noqa: E402
from core.lab_seed_proposals import seed  # noqa: E402
from core.lab_vivo import LabVivo  # noqa: E402

MELHORIA_1 = {
    "title": "Melhoria 1: dar ao TESTER o verbo RODAR-TESTES",
    "description": (
        "MOTIVO: hoje o bot TESTER só CHECA arquivos no disco; ele não consegue "
        "rodar a suíte de verdade, então a 'prova real' de uma entrega depende de "
        "alguém de fora. Com um verbo que roda pytest num alvo, o próprio Lab "
        "fecha o ciclo: codou -> testou -> publicou.\n"
        "RISCO: baixo. O verbo roda só dentro do sandbox do Lab, com timeout, "
        "sem rede e sem tocar no app de verdade. Se o teste travar, o worker "
        "responde ERRO e a mãe reatribui — nada publica sem gate verde."
    ),
    "proposed_by": "RESEARCHER",
    "impact": 4,
    "urgency": 3,
    "cost": 2,
}


def main() -> int:
    raiz = Path(__file__).resolve().parent.parent
    vivo = LabVivo(raiz)
    vivo.preparar()

    n_seed = len(seed(vivo.backlog))
    item = vivo.backlog.propose(**MELHORIA_1)
    # a CEO aprova a Melhoria 1 (motivo + risco avaliados) — a direção é dela
    vivo.backlog.approve(item.item_id, by="CEO")
    vivo.salvar_backlog()

    print("=" * 60)
    print("LAB VIVO — Fase D (backlog de melhorias do próprio Lab)")
    print("=" * 60)
    print(f"Propostas semeadas: {n_seed} | backlog: {vivo.arq_backlog}")
    print("Ranking (topo primeiro):")
    for it in vivo.backlog.ranked()[:6]:
        marca = "APROVADA PELA CEO" if it.state == BacklogState.APPROVED else it.state.value
        print(f"  - [{marca}] {it.title} (score {it.score})")
    print()
    print("Melhoria 1 registrada:")
    print(f"  id: {item.item_id}")
    print(f"  motivo+risco: na descrição ({len(item.description)} caracteres)")
    ok = (vivo.backlog.get(item.item_id).state == BacklogState.APPROVED
          and vivo.arq_backlog.exists())
    print("RESULTADO:", "BACKLOG VIVO — proposta com motivo+risco, CEO aprovou"
          if ok else "FALHOU")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
