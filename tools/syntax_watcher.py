"""ZARA-SYNTAX-WATCHER-001 (Alex, 2026-08-28)

Peca isolada. Usa ast.parse (biblioteca padrao, zero dependencia nova) pra
achar erro de sintaxe num arquivo .py SEM executa-lo. Nao roda em loop, nao
observa arquivo sozinho -- so a funcao de checagem pontual.
"""
from __future__ import annotations

import ast
from pathlib import Path


def check_python_syntax(file_path: str) -> dict:
    """Devolve {"ok": bool, "line": int|None, "column": int|None,
    "message": str} sem nunca executar o arquivo."""
    path = Path(file_path)
    if not path.exists():
        return {"ok": False, "line": None, "column": None, "message": f"Arquivo não encontrado: {path}"}

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"ok": False, "line": None, "column": None, "message": f"Não consegui ler como texto UTF-8: {exc}"}

    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return {
            "ok": False,
            "line": exc.lineno,
            "column": exc.offset,
            "message": exc.msg,
        }

    return {"ok": True, "line": None, "column": None, "message": "Sintaxe válida."}
