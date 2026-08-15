#!/usr/bin/env python3
"""ZARA 3.0 — ver e limpar lembretes.

Uso:
    python tools/lembretes.py            lista tudo
    python tools/lembretes.py --limpar   remove os ja resolvidos
    python tools/lembretes.py --zerar    remove TODOS, inclusive os agendados
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reminder_engine import ReminderEngine  # noqa: E402

ROTULO = {
    "SCHEDULED": "AGENDADO",
    "FIRED": "ja avisou",
    "MISSED": "perdido",
    "CANCELLED": "cancelado",
    "COMPLETED": "concluido",
    "FIRING": "avisando",
}


def quando(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "?"


def main() -> int:
    eng = ReminderEngine()
    todos = eng.list()

    print("=" * 74)
    print("LEMBRETES DA ZARA")
    print("=" * 74)

    if not todos:
        print("\nNenhum lembrete guardado.")
        return 0

    agendados = [r for r in todos if r.state == "SCHEDULED"]
    resolvidos = [r for r in todos if r.state != "SCHEDULED"]

    print(f"\nAINDA VAO ACONTECER ({len(agendados)}):")
    if agendados:
        for r in sorted(agendados, key=lambda x: x.due_at_utc):
            print(f"   {quando(r.due_at_utc):18} {r.message}")
    else:
        print("   nenhum")

    print(f"\nJA PASSARAM ({len(resolvidos)}):")
    if resolvidos:
        for r in sorted(resolvidos, key=lambda x: x.due_at_utc)[-15:]:
            print(f"   {quando(r.due_at_utc):18} [{ROTULO.get(r.state, r.state):10}] {r.message}")
        if len(resolvidos) > 15:
            print(f"   ... e mais {len(resolvidos) - 15}")
    else:
        print("   nenhum")

    if "--zerar" in sys.argv:
        n = len(todos)
        for r in todos:
            try:
                eng.cancel(r.id)
            except Exception:
                pass
        eng.purgar_resolvidos(dias=0)
        print(f"\nTODOS os {n} lembretes foram removidos.")
        return 0

    if "--limpar" in sys.argv:
        n = eng.purgar_resolvidos(dias=0)
        print(f"\n{n} lembrete(s) ja resolvido(s) removido(s).")
        print("Os agendados foram preservados.")
        return 0

    if resolvidos:
        print("\n" + "=" * 74)
        print("Para apagar os que ja passaram:  python tools/lembretes.py --limpar")
        print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
