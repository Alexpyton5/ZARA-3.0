#!/usr/bin/env python3
"""ZARA 3.0 — mantem a raiz do projeto limpa. Roda sozinho ao fim de cada build.

Alex nao quer arquivo temporario acumulando na pasta dele. A limpeza deixou de
ser uma tarefa que alguem precisa lembrar de rodar: virou o ultimo passo do
build.

Regras que nao mudam (de .claude/rules/build-release.md e governance.md):
  - NUNCA apagar a baseline (frontend/release/)
  - NUNCA apagar o candidato atual nem o imediatamente anterior
  - NUNCA apagar .zara-dev/, config/, core/, tests/, tools/, .claude/, docs/
  - relatorio de diagnostico e arquivado em .zara-dev/reports/, nao apagado

Modos:
    python tools/limpar_pasta.py            mostra o que faria
    python tools/limpar_pasta.py --apply    executa
    python tools/limpar_pasta.py --auto     executa em silencio (usado no build)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
REPORTS = ROOT / ".zara-dev" / "reports"

# Os unicos .bat que sobrevivem. Qualquer outro na raiz e considerado gasto.
BAT_PERMANENTES = {
    "CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat",
    "MEUS-LEMBRETES.bat",
    "ABRIR-A-ZARA.bat",
    "LIGAR-O-EXECUTOR.bat",
}

# Arquivos de saida que o projeto gera. Vao para .zara-dev/reports/.
PREFIXOS_DE_SAIDA = ("ZARA-", "zara-")
SUFIXOS_DE_SAIDA = (".txt", ".log")

# Nunca mexer nestes, mesmo que casem com as regras acima.
INTOCAVEIS = {
    "requirements.txt", "LICENSE.txt", "INSTALL_HERMES.txt",
    "SHA256_MANIFEST.txt", "PATCH_SHA256_MANIFEST.txt", "CLEAN_BUILD_ID.txt",
    "ZARA_ACTIVE_BUILD.json", "ZARA_ACTIVE_BUILD.txt",
}

# ZARA-UM-CANDIDATO-SO-001 (Alex, 2026-08-13): so o atual sobrevive.
# Guardar o anterior foi o que fez Alex testar EXE velho sem perceber.
CANDIDATOS_A_PRESERVAR = 1


def tamanho(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except Exception:
        return 0


def humano(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def levantar() -> list[tuple[str, Path, str]]:
    acoes: list[tuple[str, Path, str]] = []

    for p in ROOT.glob("*.bat"):
        if p.name not in BAT_PERMANENTES:
            acoes.append(("remover", p, "atalho ja usado"))

    for p in ROOT.iterdir():
        if not p.is_file() or p.name in INTOCAVEIS:
            continue
        if p.suffix.lower() in SUFIXOS_DE_SAIDA and p.name.startswith(PREFIXOS_DE_SAIDA):
            acoes.append(("arquivar", p, "relatorio -> .zara-dev/reports/"))

    for p in ROOT.glob("*.bak*"):
        acoes.append(("remover", p, "backup temporario"))
    for p in ROOT.glob(".gitignore.bak*"):
        acoes.append(("remover", p, "backup temporario"))

    cands = sorted(
        [d for d in FRONTEND.glob("release-candidate-*") if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for d in cands[CANDIDATOS_A_PRESERVAR:]:
        acoes.append(("remover", d, "versao antiga"))

    vistos, unicas = set(), []
    for a in acoes:
        if a[1] not in vistos:
            vistos.add(a[1])
            unicas.append(a)
    return unicas


def main() -> int:
    auto = "--auto" in sys.argv
    aplicar = auto or "--apply" in sys.argv
    acoes = levantar()

    if not acoes:
        if not auto:
            print("A pasta ja esta limpa.")
        return 0

    liberado = sum(tamanho(p) for v, p, _ in acoes if v == "remover")

    if not auto:
        print("=" * 68)
        print("LIMPEZA" + ("  [EXECUTANDO]" if aplicar else "  [PREVIA]"))
        print("=" * 68)
        for verbo, p, motivo in acoes:
            print(f"  {verbo:9} {p.name:48} {humano(tamanho(p)):>9}  {motivo}")
        print(f"\nespaco a liberar: {humano(liberado)}")
        if not aplicar:
            print("\nNada foi alterado. Use --apply para executar.")
            return 0

    def forcar_escrita(func, caminho, _exc):
        """Windows marca arquivo de build como somente-leitura; libera e repete."""
        import os
        import stat
        try:
            os.chmod(caminho, stat.S_IWRITE)
            func(caminho)
        except Exception:
            pass

    REPORTS.mkdir(parents=True, exist_ok=True)
    removidos = arquivados = 0
    liberado_real = 0
    falhas: list[str] = []

    for verbo, p, _ in acoes:
        peso = tamanho(p)
        try:
            if verbo == "arquivar":
                destino = REPORTS / f"diagnostico-{p.name}"
                if destino.exists():
                    destino.unlink()
                shutil.move(str(p), str(destino))
                arquivados += 1
            elif p.is_dir():
                shutil.rmtree(p, onerror=forcar_escrita)
                if p.exists():
                    raise OSError("a pasta continua no disco")
                removidos += 1
                liberado_real += peso
            else:
                p.unlink()
                removidos += 1
                liberado_real += peso
        except Exception as exc:
            falhas.append(f"{p.name}: {exc}")

    # So conta o que realmente saiu do disco. Anunciar espaco liberado sem
    # ter liberado seria a mesma mentira que este projeto combate no resto
    # do codigo.
    print(f"Limpeza: {removidos} item(ns) removido(s), "
          f"{arquivados} relatorio(s) arquivado(s), {humano(liberado_real)} liberados.")
    if falhas:
        print(f"Nao consegui remover {len(falhas)} item(ns):")
        for f in falhas[:5]:
            print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
