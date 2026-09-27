r"""Inventário somente leitura da raiz da ZARA.

Uso no Windows:
  python tools\inventory_root.py

O script não move, apaga ou edita arquivos. Gera um relatório JSON e Markdown
em .zara-tests\inventories\, com hashes apenas de arquivos regulares da raiz.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".zara-tests" / "inventories"


def sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def classify(path: Path) -> str:
    name = path.name.lower()
    if name == "_quarentena":
        return "quarantine"
    if name in {"core", "frontend", "memory", "memory_system", "scripts", "tools", "tests", "skills"}:
        return "source"
    if name in {"config", "data", "profiles", "lembretes", "voice", "windows-ops"}:
        return "runtime-data"
    if name in {"docs", "wiki", "dossie zara"}:
        return "documentation"
    if name in {"artifacts", ".zara-tests"}:
        return "evidence"
    if "build" in name or name.startswith("dist") or "release" in name:
        return "build-artifact"
    if name.startswith(".") or name.endswith(".log"):
        return "temporary-or-hidden"
    return "root-entry"


def main() -> int:
    if not ROOT.is_dir():
        print(f"Projeto não encontrado: {ROOT}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entries = []
    for item in sorted(ROOT.iterdir(), key=lambda p: p.name.casefold()):
        record = {
            "name": item.name,
            "kind": "directory" if item.is_dir() else "file" if item.is_file() else "other",
            "classification": classify(item),
            "size_bytes": item.stat().st_size if item.is_file() else None,
            "sha256": sha256(item) if item.is_file() else None,
        }
        entries.append(record)
    payload = {
        "schema": "zara-root-inventory-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(ROOT),
        "read_only": True,
        "entries": entries,
    }
    json_path = OUT / f"root-inventory-{stamp}.json"
    md_path = OUT / f"root-inventory-{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Inventário da raiz da ZARA",
        "",
        f"- Gerado em UTC: `{payload['generated_at_utc']}`",
        f"- Raiz: `{ROOT}`",
        "- Modo: **somente leitura**; nenhum arquivo foi movido ou apagado.",
        "",
        "| Nome | Tipo | Classificação | Tamanho | SHA-256 |",
        "|---|---|---|---:|---|",
    ]
    for item in entries:
        digest = item["sha256"] or "—"
        size = str(item["size_bytes"]) if item["size_bytes"] is not None else "—"
        lines.append(f"| `{item['name']}` | {item['kind']} | {item['classification']} | {size} | `{digest}` |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
