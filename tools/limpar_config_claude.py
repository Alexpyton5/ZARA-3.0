"""Remove a entrada de projeto duplicada (e contaminada) do ~/.claude.json.

Contexto: o arquivo tem o mesmo projeto duas vezes —
  "C:\\Users\\alexp\\Downloads\\ZARA 3.0 CLEAN 002"  (canonica, com trust aceito)
  "C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002"      (duplicada, sem trust)

A duplicada registra o MCP desktop-commander com um PATH cheio de caminhos do Codex
(.codex\\tmp\\arg0, codex-runtimes) e cache npm em Documents\\Codex\\...\\work.
O desktop-commander agora vive limpo no .mcp.json do projeto, entao a duplicada so
atrapalha.

Rodar com o Claude Code FECHADO: com o app aberto, ele reescreve o arquivo por cima.

    python tools/limpar_config_claude.py           # mostra o que faria
    python tools/limpar_config_claude.py --aplicar # faz o backup e limpa
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

CONFIG = Path.home() / ".claude.json"
CANONICA = r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
DUPLICADA = "C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002"


def main() -> int:
    aplicar = "--aplicar" in sys.argv

    if not CONFIG.exists():
        print(f"[ERRO] nao encontrei {CONFIG}")
        return 1

    dados = json.loads(CONFIG.read_text(encoding="utf-8"))
    projetos = dados.get("projects", {})

    if DUPLICADA not in projetos:
        print("[OK] nada a limpar: a entrada duplicada nao existe mais.")
        return 0

    if CANONICA not in projetos:
        print("[ABORTADO] a entrada canonica sumiu; nao vou apagar a unica que restou.")
        return 2

    alvo = projetos[DUPLICADA]
    mcps = list((alvo.get("mcpServers") or {}).keys())
    print(f"entrada duplicada : {DUPLICADA}")
    print(f"  mcpServers      : {mcps or 'nenhum'}")
    print(f"  trust aceito    : {alvo.get('hasTrustDialogAccepted')}")
    print(f"entrada canonica  : {CANONICA} (preservada)")

    if not aplicar:
        print("\n[SIMULACAO] rode de novo com --aplicar para limpar de verdade.")
        return 0

    backup = CONFIG.with_suffix(f".json.antes-limpeza.{int(time.time())}")
    shutil.copy2(CONFIG, backup)
    print(f"\nbackup: {backup}")

    del projetos[DUPLICADA]
    texto = json.dumps(dados, indent=2, ensure_ascii=False)
    json.loads(texto)  # valida antes de gravar
    CONFIG.write_text(texto, encoding="utf-8")
    print("[OK] entrada duplicada removida. Pode abrir o Claude Code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
