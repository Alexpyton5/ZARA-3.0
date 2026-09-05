"""Inventario conservador de candidatos a higiene na raiz do projeto.

Este utilitario e deliberadamente somente leitura. Ele lista nomes e motivos,
sem abrir arquivos, seguir links ou oferecer qualquer operacao de remocao.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HygieneCandidate:
    path: str
    category: str
    reason: str
    kind: str


_CACHE_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
_BACKUP_SUFFIXES = (".bak", ".backup", ".old", ".orig", ".rej", "~")
_TEMP_SUFFIXES = (".tmp", ".temp")
_HELPER_PREFIXES = (
    "check_",
    "debug_",
    "do_patch",
    "scan_",
    "smoke_test",
    "test_",
)


def _classification(name: str, *, is_dir: bool) -> tuple[str, str] | None:
    lower = name.casefold()

    if lower in _CACHE_NAMES:
        return "cache", "cache conhecido de ferramenta"
    if lower.startswith("%temp") or lower.endswith(_TEMP_SUFFIXES):
        return "temporary", "nome indica artefato temporario"
    if lower.endswith(_BACKUP_SUFFIXES) or ".backup-" in lower:
        return "backup", "nome indica copia de seguranca ou sobra de edicao"
    if not is_dir and lower.startswith(_HELPER_PREFIXES):
        return "debug-helper", "script avulso de teste, diagnostico ou patch na raiz"
    return None


def scan_project_root(project_root: Path | str) -> list[HygieneCandidate]:
    """Classifica somente entradas diretas da raiz, sem ler seu conteudo."""

    root = Path(project_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"raiz inexistente: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"raiz nao e diretorio: {root}")

    candidates: list[HygieneCandidate] = []
    with os.scandir(root) as entries:
        for entry in entries:
            is_dir = entry.is_dir(follow_symlinks=False)
            match = _classification(entry.name, is_dir=is_dir)
            if match is None:
                continue
            category, reason = match
            kind = "symlink" if entry.is_symlink() else ("directory" if is_dir else "file")
            candidates.append(
                HygieneCandidate(
                    path=entry.name,
                    category=category,
                    reason=reason,
                    kind=kind,
                )
            )
    return sorted(candidates, key=lambda item: item.path.casefold())


def _text_report(candidates: Iterable[HygieneCandidate]) -> str:
    rows = list(candidates)
    if not rows:
        return "Nenhum candidato encontrado. Nada foi alterado."
    lines = [f"{item.category}: {item.path} - {item.reason}" for item in rows]
    lines.append(f"Total: {len(rows)}. Modo somente leitura; nada foi alterado.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lista candidatos a higiene sem abrir, mover ou apagar arquivos.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="raiz a inventariar (padrao: raiz do projeto)",
    )
    parser.add_argument("--json", action="store_true", help="emite resultado JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates = scan_project_root(args.root)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print(json.dumps({"verdict": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    if args.json:
        payload = {
            "verdict": "dry_run_only",
            "mutated": False,
            "count": len(candidates),
            "candidates": [asdict(item) for item in candidates],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(_text_report(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
