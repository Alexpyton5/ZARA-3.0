# -*- coding: utf-8 -*-
"""Demonstração viva do Lab — Fase B da GIGANTE 2 "LAB VIVO".

Roda de verdade (nada simulado): propõe a tarefa no backlog, a CEO
aprova, o turno despacha pela caixinha, o worker REAL executa no disco
(ESCREVE o arquivo), pede divisão para o TESTER pela caixinha, o
TESTER CHECA o arquivo no disco, a mãe completa e o resultado existe.

Uso (na raiz do app):
    .\\.venv\\Scripts\\python.exe tools\\lab_vivo_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lab_backlog import BacklogState  # noqa: E402
from core.lab_vivo import LabVivo  # noqa: E402

ORDEM_DEMO = (
    "ESCREVER relatorio-turno-vivo.txt\n"
    "Relatório do turno vivo, escrito por um bot de verdade.\n"
    "Os bots conversaram pela caixinha e executaram de verdade.\n"
    'DIVIDIR-PARA TESTER: CHECAR relatorio-turno-vivo.txt CONTEM executaram de verdade'
)


def main() -> int:
    raiz = Path(__file__).resolve().parent.parent
    vivo = LabVivo(raiz)
    vivo.preparar()

    item = vivo.backlog.propose(
        title="Bot redator: escrever relatório do turno vivo no disco",
        description=ORDEM_DEMO,
        proposed_by="CEO", impact=4, urgency=4, cost=2)
    vivo.backlog.approve(item.item_id, by="CEO")
    vivo.salvar_backlog()

    saida = vivo.rodar_turno("demo-viva", budget_usd=1.0)
    estado = vivo.backlog.get(item.item_id).state
    alvo = vivo.dir_work / "relatorio-turno-vivo.txt"

    print("=" * 60)
    print("LAB VIVO — demonstração da Fase B (tarefa dividida de verdade)")
    print("=" * 60)
    print(f"Tarefa mãe: {item.item_id} -> {estado.value}")
    print(f"Arquivo no disco: {alvo} (existe={alvo.exists()})")
    if alvo.exists():
        print("Conteúdo:")
        print("---")
        print(alvo.read_text(encoding="utf-8").strip())
        print("---")
    print(f"Despachados: {saida.dispatched}  Concluídos: {saida.completed}  "
          f"Falhas: {saida.failed}  Divisões: {saida.splits_used}")
    print(f"Caixinha: {vivo.dir_caixinha} "
          f"({len(list(vivo.dir_caixinha.glob('*.json')))} recados)")
    ok = (estado == BacklogState.DONE and alvo.exists()
          and "executaram de verdade" in alvo.read_text(encoding="utf-8"))
    print("RESULTADO:", "VIVO — bots criaram, conversaram e entregaram"
          if ok else "FALHOU — ver journal")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
