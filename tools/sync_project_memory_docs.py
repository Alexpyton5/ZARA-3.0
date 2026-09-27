"""Sincroniza o pacote de contexto da ZARA com a memória de projeto.

Executar a partir da raiz usando o Python do projeto:
    .venv\\Scripts\\python.exe tools\\sync_project_memory_docs.py

O ProjectMemory grava SQLite/Markdown no diretório de dados do usuário e,
quando o Obsidian é detectado, espelha os documentos em Zara-Memoria no vault
real. A operação é idempotente e não apaga documentos existentes.
"""
from __future__ import annotations

from pathlib import Path

from memory.project_memory import ProjectMemory

ROOT = Path(__file__).resolve().parents[1]
VAULT_PACKAGE = ROOT / "docs" / "vault" / "Zara-Memoria"
DOCS = {
    "architecture": ("ZARA — Arquitetura", "01-ARQUITETURA.md"),
    "state": ("ZARA — Estado Atual", "02-ESTADO-ATUAL.md"),
    "rules": ("ZARA — Regras e Validação", "03-REGRAS-E-VALIDACAO.md"),
    "memory": ("ZARA — Memória e Obsidian", "04-MEMORIA-E-OBSIDIAN.md"),
}


def main() -> int:
    memory = ProjectMemory()
    for key, (title, filename) in DOCS.items():
        content = (VAULT_PACKAGE / filename).read_text(encoding="utf-8")
        memory.save_doc(key, title, content)
        print(f"SYNCED {key}: {title}")
    print(f"PROJECT_MEMORY_DIR={memory.base_dir}")
    print(f"OBSIDIAN_VAULT={memory.obsidian_vault_dir or 'NOT_DETECTED'}")
    print("DONE: documentos sincronizados de forma idempotente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
