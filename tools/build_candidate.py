#!/usr/bin/env python3
"""ZARA 3.0 — gerador de candidato físico com identidade.

Resolve a dívida estrutural registrada em .claude/rules/build-release.md:
existem 9 linhagens de build no repositório e nenhuma diz a qual estado de
source corresponde. Todo candidato gerado por aqui grava BUILD_INFO.json.

Estratégia deliberada: quando o delta é somente do sidecar Python, NÃO
reconstrói o Electron. Copia o candidato base, troca apenas o
zara-backend.exe e prova por hash que a troca aconteceu. Isso evita npm,
node_modules e electron-builder numa tarefa de correção de bug, conforme
.claude/rules/path-rules/frontend-electron.md.

Uso:
    python tools/build_candidate.py --base <nome-da-pasta-base> --tag <rotulo>

Não altera nenhum candidato existente. Só cria pasta nova.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST_SIDECAR = ROOT / "dist-sidecar" / "zara-backend.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        return out.stdout.strip()
    except Exception:
        return ""


def fail(msg: str) -> None:
    print(f"\n[FALHOU] {msg}\n")
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="auto",
                    help="pasta em frontend/ usada como base, ou 'auto' para a mais recente")
    ap.add_argument("--tag", default="kore", help="rótulo curto do candidato")
    ap.add_argument("--delta", default="", help="o que mudou em relação ao base")
    args = ap.parse_args()

    # 'auto' escolhe a linhagem mais recente que realmente tem os dois binarios.
    # Sem isso, uma limpeza de disco que remova a base nomeada quebra o build
    # inteiro depois de ja ter gasto minutos compilando o sidecar.
    if args.base == "auto" or not (FRONTEND / args.base / "win-unpacked" / "ZARA 3.0.exe").exists():
        if args.base != "auto":
            print(f"[AVISO] base '{args.base}' nao existe mais. Escolhendo a mais recente.")
        cands = [
            d for d in FRONTEND.glob("release*")
            if (d / "win-unpacked" / "ZARA 3.0.exe").exists()
            and (d / "win-unpacked" / "resources" / "backend" / "zara-backend.exe").exists()
        ]
        if not cands:
            fail("nenhuma linhagem de build utilizavel em frontend/")
        escolhida = max(cands, key=lambda d: d.stat().st_mtime)
        args.base = escolhida.name
        print(f"[AUTO] base escolhida: {args.base}")

    base_dir = FRONTEND / args.base
    base_exe = base_dir / "win-unpacked" / "ZARA 3.0.exe"
    base_backend = base_dir / "win-unpacked" / "resources" / "backend" / "zara-backend.exe"

    print("=" * 64)
    print("ZARA 3.0 - GERADOR DE CANDIDATO COM IDENTIDADE")
    print("=" * 64)

    if not base_exe.exists():
        fail(f"candidato base nao encontrado: {base_exe}")
    if not base_backend.exists():
        fail(f"sidecar do candidato base nao encontrado: {base_backend}")
    if not DIST_SIDECAR.exists():
        fail(
            "dist-sidecar/zara-backend.exe nao existe. "
            "Rode 'python build_exe.py' antes deste script."
        )

    novo_backend_sha = sha256(DIST_SIDECAR)
    base_backend_sha = sha256(base_backend)

    print(f"\nbase              : {args.base}")
    print(f"sidecar do base   : {base_backend_sha[:16]}...")
    print(f"sidecar novo      : {novo_backend_sha[:16]}...")

    if novo_backend_sha == base_backend_sha:
        fail(
            "o sidecar recem-gerado e IDENTICO ao do candidato base. "
            "Nenhuma mudanca de backend entrou. Nao faz sentido gerar candidato."
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    build_id = f"release-candidate-{args.tag}-{stamp}"
    dest_dir = FRONTEND / build_id
    if dest_dir.exists():
        fail(f"ja existe: {dest_dir}")

    print(f"\ncriando           : {build_id}")
    print("copiando o candidato base (pode levar 1-2 minutos)...")
    shutil.copytree(base_dir, dest_dir)

    # ZARA-BUILD-INTEGRIDADE-001
    # Um candidato nasceu sem ffmpeg.dll, locales/ e icudtl.dat e so falhou na
    # cara do Alex, com "a execucao de codigo nao pode continuar". Copia
    # incompleta nunca mais pode virar candidato: o conteudo e conferido
    # contra a baseline certificada e o que faltar e restaurado de la.
    #
    # ZARA-ABERTURA-001 (2026-08-13): a conferencia era rasa, olhava so o
    # primeiro nivel de win-unpacked. Como resources/ existia (continha
    # backend/), ela imprimia "integridade: OK" mesmo com resources/app.asar
    # ausente. Sem o asar o Electron sai com codigo 1: sem janela, sem log,
    # sem mensagem. Dois candidatos sairam assim. Agora e recursiva.
    baseline = FRONTEND / "release" / "win-unpacked"
    destino_win = dest_dir / "win-unpacked"

    def restauravel(rel: Path) -> bool:
        """O que pode ser puxado da baseline para tapar buraco de copia.

        Duas exclusoes, por motivos diferentes:

        - `resources/app.asar` carrega a IDENTIDADE do frontend. Puxar o da
          baseline entregaria frontend velho travestido de candidato novo, que
          e a mentira que build-release.md proibe. Se faltar, o build falha e
          pede reconstrucao de verdade.
        - `resources/backend/` inteiro e territorio do sidecar: o candidato ja
          traz o seu, ele e trocado logo abaixo e conferido por hash. Alem
          disso a baseline guarda o historico `zara-backend.exe.backup-*`, e
          restaurar dali arrastava ~1,8 GB de binario morto para dentro de
          cada candidato novo.
        """
        caminho = rel.as_posix()
        if caminho == "resources/app.asar":
            return False
        return not caminho.startswith("resources/backend/")

    if baseline.exists() and destino_win.exists():
        restaurados = []
        for item in sorted(baseline.rglob("*")):
            if item.is_dir():
                continue
            rel = item.relative_to(baseline)
            if not restauravel(rel):
                continue
            alvo = destino_win / rel
            if alvo.exists():
                continue
            try:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, alvo)
                restaurados.append(rel.as_posix())
            except Exception as exc:
                fail(f"nao consegui restaurar {rel.as_posix()} da baseline: {exc}")
        if restaurados:
            print(f"integridade: {len(restaurados)} arquivo(s) restaurado(s) da baseline")
            print(f"             {', '.join(restaurados[:6])}")

    # Sem estes o Windows recusa abrir o aplicativo, ou pior, ele abre e morre
    # calado. Sao CAMINHOS, nao nomes soltos: 'resources' existir nunca provou
    # que resources/app.asar existe.
    essenciais = ["ZARA 3.0.exe", "ffmpeg.dll", "icudtl.dat", "resources.pak",
                  "v8_context_snapshot.bin", "locales",
                  "resources/app.asar", "resources/backend/zara-backend.exe"]
    faltando = [n for n in essenciais if not (destino_win / n).exists()]
    if faltando:
        shutil.rmtree(dest_dir, ignore_errors=True)
        fail(
            "candidato incompleto, foi descartado. Faltava: " + ", ".join(faltando)
            + "\n        Se faltou resources/app.asar, o frontend precisa ser"
              " reconstruido de verdade:\n"
              "        cd frontend\n"
              "        npm run typecheck && npm run build && npm run build:electron\n"
              "        npx electron-builder --dir"
              " --config.directories.output=release-candidate-<rotulo>-<AAAAMMDD-HHMM>\n"
              "        (a saida NUNCA pode ser 'release', que e a baseline)"
        )
    print("integridade: OK — o candidato tem tudo que o Windows precisa")

    dest_backend = dest_dir / "win-unpacked" / "resources" / "backend" / "zara-backend.exe"
    dest_exe = dest_dir / "win-unpacked" / "ZARA 3.0.exe"

    print("trocando o sidecar pelo recem-compilado...")
    dest_backend.unlink()
    shutil.copy2(DIST_SIDECAR, dest_backend)

    # Prova de que a troca aconteceu: byte a byte igual ao dist-sidecar.
    conferido = sha256(dest_backend)
    if conferido != novo_backend_sha:
        fail("o sidecar copiado NAO confere com dist-sidecar. Candidato invalido.")
    print("conferencia sidecar: OK (byte a byte igual ao dist-sidecar)")

    asar = dest_dir / "win-unpacked" / "resources" / "app.asar"
    info = {
        "BUILD_ID": build_id,
        "BUILD_TIMESTAMP": datetime.now().astimezone().isoformat(),
        "BASE_CANDIDATE": args.base,
        "BUILD_METHOD": "sidecar-swap (frontend do base preservado, backend recompilado)",
        "GIT_BRANCH": git("rev-parse", "--abbrev-ref", "HEAD"),
        "GIT_COMMIT": git("rev-parse", "HEAD"),
        "GIT_DIRTY": bool(git("status", "--porcelain")),
        "EXE_PATH": str(dest_exe),
        "EXE_SHA256": sha256(dest_exe),
        "BACKEND_SHA256": conferido,
        "BACKEND_SHA256_ANTERIOR": base_backend_sha,
        "ASAR_SHA256": sha256(asar) if asar.exists() else "",
        "DELTA": args.delta or "nao informado",
    }
    (dest_dir / "win-unpacked" / "BUILD_INFO.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ROOT / "ULTIMO_CANDIDATO.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # ZARA-ABRIR-SEM-PYTHON-001: caminho puro, sem JSON e sem interpretador.
    # O ABRIR-A-ZARA.bat lia este caminho rodando Python; como a pasta do
    # projeto tem espacos no nome, a linha do cmd quebrava e o atalho morria em
    # silencio na cara do Alex. Texto simples nao tem esse problema.
    (ROOT / "ULTIMO_CANDIDATO.txt").write_text(str(dest_exe), encoding="utf-8")

    # ZARA-UM-CANDIDATO-SO-001 (Alex, 2026-08-13)
    # "toda vez que voce criar um novo apague o velho para nao confundir".
    # A regra antiga guardava dois candidatos; foi assim que Alex passou dias
    # testando um EXE velho sem saber. Agora sobra exatamente um, e a baseline
    # frontend/release/ — que nao e candidato, e a copia de seguranca de onde
    # o portao de integridade restaura arquivo faltando.
    apagados = []
    for velho in FRONTEND.glob("release-candidate-*"):
        if not velho.is_dir() or velho == dest_dir:
            continue
        try:
            shutil.rmtree(velho, ignore_errors=True)
            if not velho.exists():
                apagados.append(velho.name)
        except Exception:
            pass
    if apagados:
        print(f"\nlimpeza: {len(apagados)} candidato(s) antigo(s) apagado(s)")
        for nome in apagados:
            print(f"         {nome}")

    print("\n" + "=" * 64)
    print("CANDIDATO PRONTO")
    print("=" * 64)
    print(f"BUILD_ID        : {info['BUILD_ID']}")
    print(f"GIT_COMMIT      : {info['GIT_COMMIT'][:12]}")
    print(f"GIT_DIRTY       : {info['GIT_DIRTY']}")
    print(f"BACKEND_SHA256  : {info['BACKEND_SHA256'][:32]}...")
    print(f"\nALEX_OPEN_THIS_EXE:\n{info['EXE_PATH']}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
