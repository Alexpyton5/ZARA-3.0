"""Generate a deterministic, triage-ready backlog of improvement candidates.

This creates candidates, not executable changes. Every candidate must pass
human/CEO policy, implementation review, tests, and rollback checks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

AREAS = [
    "controle_windows", "voz", "navegador", "visao_ocr", "memoria_obsidian",
    "zara_lab", "desempenho", "seguranca", "qualidade_codigo", "testes",
]
CAPABILITIES = [
    "detectar", "explicar", "simular", "confirmar", "executar", "verificar",
    "registrar", "cancelar", "recuperar", "otimizar",
]
TARGETS = [
    "estado", "permissao", "latencia", "proveniencia", "rollback", "acessibilidade",
    "falha", "conflito", "observabilidade", "experiencia_usuario",
]
PERSPECTIVES = ["confiabilidade", "seguranca", "velocidade", "clareza", "recuperacao"]


def build_ideas() -> list[dict[str, object]]:
    ideas: list[dict[str, object]] = []
    number = 1
    for area in AREAS:
        for capability in CAPABILITIES:
            for target in TARGETS:
                for perspective in PERSPECTIVES:
                    ideas.append({
                    "id": f"IDEA-{number:04d}",
                    "area": area,
                    "capability": capability,
                    "target": target,
                    "perspective": perspective,
                    "title": f"{capability.title()} {target.replace('_', ' ')} em {area.replace('_', ' ')} ({perspective})",
                    "status": "CANDIDATE",
                    "implementation": "PENDING_TRIAGE",
                    "requires_windows": area in {"controle_windows", "voz", "navegador", "visao_ocr"},
                    "requires_approval": area in {"controle_windows", "voz", "navegador", "seguranca"},
                    })
                    number += 1
    assert len(ideas) == 5000
    return ideas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission": "MISSAO_NOTURNA_5000_IDEIAS_2026-09-19",
        "count": 5000,
        "policy": "candidate_backlog_only",
        "ideas": build_ideas(),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"GENERATED {payload['count']} candidates -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
