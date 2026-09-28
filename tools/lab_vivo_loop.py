# -*- coding: utf-8 -*-
"""O loop contínuo do Lab Vivo — GIGANTE 2 "LAB VIVO".

Roda ciclos até a fila de propostas esvaziar (ou bater no limite):
a cada ciclo a CEO aprova a proposta do topo e o turno executa de
verdade (worker no disco, conversa pela caixinha). No fim, imprime o
boletim: o que andou, o que falhou, o que sobrou.

É limitado de propósito (max_cycles): o 24/7 fica para uma tarefa
agendada quando o Alex pedir — aqui a mecânica é provada sem daemon.

Uso (na raiz do app):
    .\\.venv\\Scripts\\python.exe tools\\lab_vivo_loop.py [max_cycles]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lab_vivo import LabVivo  # noqa: E402


def main() -> int:
    max_cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    raiz = Path(__file__).resolve().parent.parent
    vivo = LabVivo(raiz)
    vivo.preparar()

    print("=" * 60)
    print(f"LAB VIVO — loop contínuo (até {max_cycles} ciclos)")
    print("=" * 60)
    rels = vivo.rodar_ate_ocioso(max_cycles=max_cycles)
    falhas = 0
    for rel in rels:
        print(f"ciclo {rel.cycle}: despachadas={rel.dispatched} "
              f"concluídas={rel.completed} falhas={rel.failed} "
              f"ocioso={rel.idle} pausado={rel.paused}")
        falhas += rel.failed
    print("-" * 60)
    resumo = vivo.resumo()
    print(f"backlog: {resumo['backlog_estados']}")
    print(f"ciclos rodados: {len(rels)} | falhas: {falhas}")
    print("RESULTADO:", "LOOP CONTÍNUO OK" if falhas == 0 else
          "LOOP RODOU COM FALHAS — ver journal da caixinha")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
