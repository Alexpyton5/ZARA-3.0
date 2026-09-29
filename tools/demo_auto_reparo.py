"""Demonstração FRENTE F — auto-reparo de verdade contra o vault real.

Roda o motor REAL (core.auto_repair) contra o segundo-cérebro REAL do Alex:
1. Erro SIMPLES simulado (pasta de perfil de voz ausente) -> consertado
   sozinho -> nota de reparo aparece em aprendizados/ do vault.
2. Erro COMPLEXO simulado (microfone bloqueado) -> pedido curto de permissão.

Tudo aqui é SIMULADO e marcado como tal na nota — verdade radical: nada
nesta demo é apresentado como erro real.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Funciona chamado de qualquer jeito (python tools/demo.py ou -m): garante a
# raiz do projeto no sys.path (lição TOOLS.md 28/09 ~20:55).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.auto_repair import handle_error  # noqa: E402


def main() -> None:
    print("=== FRENTE F — demonstração de auto-reparo ===\n")

    # 1) Erro SIMPLES: a pasta do perfil de voz sumiu.
    from core.paths import user_data_dir
    alvo = user_data_dir() / "demo-reparo" / "perfil-voz"
    print(f"[1] Simulando erro simples: FileNotFoundError em {alvo}")
    outcome = handle_error(
        FileNotFoundError(str(alvo)),
        context={
            "target_path": str(alvo),
            "component": "voz",
            "component_pt": "a voz",
            "operation": "carregar perfil de voz",
            "how_broke": (
                "A pasta do perfil de voz não foi encontrada no disco "
                "(simulação da MISSÃO GIGANTE 3 — nenhum erro real ocorreu)."
            ),
            "note_title": "voz — FileNotFoundError (demonstração)",
        },
        simulated=True,  # marca a nota como SIMULADA no vault
    )
    print(f"    consertado sozinho: {outcome.fixed}")
    print(f"    estratégia: {outcome.strategy}")
    print(f"    nota no vault: {outcome.note_path}\n")

    # 2) Erro COMPLEXO: microfone bloqueado pelo sistema.
    print("[2] Simulando erro complexo: PermissionError no microfone")
    outcome2 = handle_error(
        PermissionError("microfone bloqueado pelo sistema"),
        context={"component": "voz", "component_pt": "a voz"},
        simulated=True,
    )
    print(f"    consertado sozinho: {outcome2.fixed}")
    print(f'    mensagem para o Alex: "{outcome2.message}"\n')

    print("=== fim da demonstração ===")


if __name__ == "__main__":
    main()
