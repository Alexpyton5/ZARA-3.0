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
    python tools/build_candidate.py --base <pasta-ou-caminho-absoluto> --tag <rotulo>

Não altera nenhum candidato existente. Só cria pasta nova.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def preserve_failed_candidate(candidate_dir: Path, reason: str) -> Path | None:
    """Move a partial candidate to quarantine instead of deleting its evidence."""
    if not candidate_dir.exists():
        return None
    quarantine = ROOT / "_quarentena" / "organizacao-2026-09-23" / "build-failures"
    quarantine.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    preserved = quarantine / f"{candidate_dir.name}-{stamp}"
    shutil.move(str(candidate_dir), str(preserved))
    manifest = {
        "status": "FAILED_BUILD_PRESERVED",
        "created_at": datetime.now().astimezone().isoformat(),
        "original_path": str(candidate_dir),
        "preserved_path": str(preserved),
        "reason": reason,
    }
    (preserved / "QUARANTINE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return preserved


def rebuild_frontend_candidate(
    build_id: str,
    candidate_dir: Path,
    *,
    allow_existing_lint_errors: bool = False,
    lint_baseline_commit: str = "",
    lint_targets: list[str] | None = None,
) -> dict[str, object]:
    """Build the checked-out renderer and Electron package into a fresh candidate."""
    if not (FRONTEND / "package-lock.json").is_file():
        fail(f"frontend/package-lock.json ausente: {FRONTEND / 'package-lock.json'}")
    electron_builder = FRONTEND / "node_modules" / ".bin" / "electron-builder.cmd"
    if not electron_builder.is_file():
        fail(
            "node_modules do frontend nao contem electron-builder.cmd. "
            "Preserve/prepare o ambiente do projeto antes de empacotar."
        )
    npm_cmd = os.environ.get("ZARA_NPM_CMD") or shutil.which("npm.cmd") or shutil.which("npm")
    node_cmd = os.environ.get("ZARA_NODE_CMD") or shutil.which("node.exe") or shutil.which("node")
    if not npm_cmd or not node_cmd:
        fail("Node/npm do projeto nao encontrados por caminhos explicitos.")
    npm_cmd = str(Path(npm_cmd).resolve())
    node_cmd = str(Path(node_cmd).resolve())
    node_result = subprocess.run(
        [node_cmd, "--version"], cwd=FRONTEND, capture_output=True, text=True
    )
    npm_result = subprocess.run(
        f'"{npm_cmd}" --version', cwd=FRONTEND, shell=True,
        capture_output=True, text=True,
    )
    if node_result.returncode != 0 or npm_result.returncode != 0:
        fail("nao consegui confirmar as versoes do Node/npm configurados")
    node_version = node_result.stdout.strip()
    npm_version = npm_result.stdout.strip()
    print(f"frontend node    : {node_cmd}")
    print(f"frontend node ver: {node_version}")
    print(f"frontend npm     : {npm_cmd}")
    print(f"frontend npm ver : {npm_version}")
    print(f"electron-builder : {electron_builder.resolve()}")

    lint_result_metadata: dict[str, object] = {}
    for script in ("typecheck", "lint", "build", "build:electron"):
        command = f'"{npm_cmd}" run {script}'
        print(f"\n[FRONTEND] {command}")
        capture_lint = script == "lint" and allow_existing_lint_errors
        result = subprocess.run(
            command, cwd=FRONTEND, shell=True,
            capture_output=capture_lint, text=capture_lint,
        )
        if result.returncode != 0:
            if script == "lint" and allow_existing_lint_errors:
                output = f"{result.stdout or ''}\n{result.stderr or ''}"
                match = re.search(r"\((\d+) errors?,\s*(\d+) warnings?\)", output)
                if not match:
                    fail("npm run lint falhou, mas nao consegui ler a contagem de erros/avisos")
                error_count = int(match.group(1))
                warning_count = int(match.group(2))
                changed_source = sorted(
                    p.removeprefix("frontend/").replace("\\", "/")
                    for p in git("diff", "--name-only", f"{lint_baseline_commit}..HEAD", "--", "frontend/src").splitlines()
                    if p.startswith("frontend/src/")
                )
                targets = sorted(lint_targets or [])
                if not lint_baseline_commit or not targets:
                    fail("lint global falhou; autorizacao de delta exige commit-base e alvos explicitamente listados")
                if changed_source != targets:
                    fail(
                        "lint global falhou e os alvos informados nao cobrem exatamente "
                        f"o delta frontend: changed={changed_source} targets={targets}"
                    )
                for target in targets:
                    target_path = Path(target)
                    if target_path.is_absolute() or ".." in target_path.parts:
                        fail(f"alvo de lint inseguro: {target}")
                    if not (FRONTEND / target_path).is_file():
                        fail(f"alvo de lint ausente: {FRONTEND / target_path}")
                eslint_cmd = FRONTEND / "node_modules" / ".bin" / "eslint.cmd"
                if not eslint_cmd.is_file():
                    fail("eslint.cmd ausente; nao posso validar o delta frontend isoladamente")
                target_args = " ".join(f'"{target}"' for target in targets)
                target_command = f'"{eslint_cmd.resolve()}" {target_args}'
                print(
                    f"[FRONTEND] lint global tem {error_count} erro(s) e "
                    f"{warning_count} aviso(s); validando somente o delta listado: {targets}"
                )
                target_result = subprocess.run(
                    target_command, cwd=FRONTEND, shell=True,
                    capture_output=True, text=True,
                )
                if target_result.returncode != 0:
                    fail(
                        "lint do delta frontend falhou:\n"
                        + (target_result.stdout or "") + (target_result.stderr or "")
                    )
                lint_result_metadata = {
                    "FRONTEND_LINT_STATUS": "GLOBAL_ERRORS_OUTSIDE_DELTA; DELTA_PASS",
                    "FRONTEND_LINT_GLOBAL_EXIT_CODE": result.returncode,
                    "FRONTEND_LINT_GLOBAL_ERRORS": error_count,
                    "FRONTEND_LINT_GLOBAL_WARNINGS": warning_count,
                    "FRONTEND_LINT_BASELINE_COMMIT": lint_baseline_commit,
                    "FRONTEND_LINT_TARGETS": targets,
                }
                continue
            fail(f"npm run {script} terminou com codigo {result.returncode}; candidato nao iniciado")

    command = (
        f'"{electron_builder.resolve()}" --dir '
        f'--config.directories.output={build_id}'
    )
    print(f"\n[FRONTEND] {command}")
    try:
        result = subprocess.run(command, cwd=FRONTEND, shell=True)
    except Exception as exc:
        preserved = preserve_failed_candidate(candidate_dir, f"electron-builder launch failed: {type(exc).__name__}: {exc}")
        suffix = f" Parcial preservado em: {preserved}" if preserved else ""
        fail(f"nao consegui iniciar electron-builder: {exc}.{suffix}")
    if result.returncode != 0:
        preserved = preserve_failed_candidate(
            candidate_dir, f"electron-builder exited {result.returncode}"
        )
        suffix = f" Parcial preservado em: {preserved}" if preserved else ""
        fail(f"electron-builder falhou com codigo {result.returncode}.{suffix}")
    return {
        "FRONTEND_NODE_PATH": node_cmd,
        "FRONTEND_NODE_VERSION": node_version,
        "FRONTEND_NPM_PATH": npm_cmd,
        "FRONTEND_NPM_VERSION": npm_version,
        "FRONTEND_PACKAGE_LOCK_SHA256": sha256(FRONTEND / "package-lock.json"),
        **lint_result_metadata,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="auto",
                    help="nome em frontend/ ou caminho absoluto do candidato base; 'auto' escolhe o mais recente")
    ap.add_argument("--tag", default="kore", help="rótulo curto do candidato")
    ap.add_argument("--delta", default="", help="o que mudou em relação ao base")
    ap.add_argument("--rebuild-sidecar", action="store_true",
                    help="forca rebuild do backend a partir deste checkout")
    ap.add_argument("--rebuild-frontend", action="store_true",
                    help="rebuild typecheck/lint/Vite/Electron e empacota em candidato novo")
    ap.add_argument("--allow-existing-frontend-lint-errors", action="store_true",
                    help="aceita apenas erros do lint global fora do delta frontend explicitamente validado")
    ap.add_argument("--frontend-baseline-commit", default="",
                    help="commit base para comparar os arquivos frontend alterados")
    ap.add_argument("--frontend-lint-target", action="append", default=[],
                    help="arquivo frontend alterado para lint isolado; repetir por arquivo")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.tag):
        fail("--tag aceita apenas letras minusculas, numeros e hifens")

    # A base pode morar fora deste worktree. Nunca troque uma base explicita
    # ausente por outra linhagem, pois isso esconderia qual app foi empacotado.
    if args.base == "auto":
        cands = [
            d for d in FRONTEND.glob("release*")
            if (d / "win-unpacked" / "ZARA 3.0.exe").exists()
            and (d / "win-unpacked" / "resources" / "backend" / "zara-backend.exe").exists()
        ]
        if not cands:
            fail("nenhuma linhagem de build utilizavel em frontend/")
        escolhida = max(cands, key=lambda d: d.stat().st_mtime)
        base_dir = escolhida
        print(f"[AUTO] base escolhida: {base_dir.name}")
    else:
        requested_base = Path(args.base).expanduser()
        base_dir = requested_base if requested_base.is_absolute() else FRONTEND / requested_base
        if not (base_dir / "win-unpacked" / "ZARA 3.0.exe").is_file():
            fail(f"candidato base explicitamente informado nao encontrado: {base_dir}")
        if not (base_dir / "win-unpacked" / "resources" / "backend" / "zara-backend.exe").is_file():
            fail(f"sidecar do candidato base explicitamente informado nao encontrado: {base_dir}")

    base_label = base_dir.name
    base_exe = base_dir / "win-unpacked" / "ZARA 3.0.exe"
    base_backend = base_dir / "win-unpacked" / "resources" / "backend" / "zara-backend.exe"

    print("=" * 64)
    print("ZARA 3.0 - GERADOR DE CANDIDATO COM IDENTIDADE")
    print("=" * 64)

    if not base_exe.exists():
        fail(f"candidato base nao encontrado: {base_exe}")
    if not base_backend.exists():
        fail(f"sidecar do candidato base nao encontrado: {base_backend}")
    if args.rebuild_sidecar or not DIST_SIDECAR.exists():
        sidecar_builder = ROOT / "build_exe.py"
        if not sidecar_builder.is_file():
            fail(f"builder oficial do sidecar nao encontrado: {sidecar_builder}")
        print("\n[BUILD] reconstruindo o sidecar a partir deste worktree...")
        result = subprocess.run([sys.executable, str(sidecar_builder)], cwd=ROOT)
        if result.returncode != 0:
            fail(f"build_exe.py falhou com codigo {result.returncode}; nenhum candidato foi criado")
        if not DIST_SIDECAR.is_file():
            fail("build_exe.py terminou sem criar dist-sidecar/zara-backend.exe")

    novo_backend_sha = sha256(DIST_SIDECAR)
    base_backend_sha = sha256(base_backend)

    print(f"\nbase              : {base_label}")
    print(f"base path         : {base_dir}")
    print(f"sidecar do base   : {base_backend_sha[:16]}...")
    print(f"sidecar novo      : {novo_backend_sha[:16]}...")

    if novo_backend_sha == base_backend_sha:
        fail(
            "o sidecar recem-gerado e IDENTICO ao do candidato base. "
            "Nenhuma mudanca de backend entrou. Nao faz sentido gerar candidato."
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    build_id = f"release-candidate-{args.tag}-{stamp}"
    dest_dir = FRONTEND / build_id
    if dest_dir.exists():
        fail(f"ja existe: {dest_dir}")

    print(f"\ncriando           : {build_id}")
    frontend_toolchain = {}
    if args.rebuild_frontend:
        frontend_toolchain = rebuild_frontend_candidate(
            build_id, dest_dir,
            allow_existing_lint_errors=args.allow_existing_frontend_lint_errors,
            lint_baseline_commit=args.frontend_baseline_commit,
            lint_targets=args.frontend_lint_target,
        )
    else:
        print("copiando o candidato base (pode levar 1-2 minutos)...")
        try:
            shutil.copytree(base_dir, dest_dir)
        except Exception as exc:
            preserved = preserve_failed_candidate(
                dest_dir, f"copytree failed: {type(exc).__name__}: {exc}"
            )
            suffix = f" Parcial preservado em: {preserved}" if preserved else ""
            fail(f"falha ao copiar o candidato base: {exc}.{suffix}")

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
        preserved = preserve_failed_candidate(dest_dir, "missing required packaged files: " + ", ".join(faltando))
        fail(
            "candidato incompleto, preservado em quarentena. Faltava: " + ", ".join(faltando)
            + (f"\n        Material preservado: {preserved}" if preserved else "")
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
        "BASE_BUILD": base_label,
        "BASE_BUILD_PATH": str(base_dir),
        "BUILD_METHOD": (
            "frontend-and-sidecar-rebuild" if args.rebuild_frontend
            else "sidecar-swap (frontend do base preservado, backend recompilado)"
        ),
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
    info.update(frontend_toolchain)
    (dest_dir / "win-unpacked" / "BUILD_INFO.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ROOT / "ZARA_ACTIVE_BUILD.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # ZARA-ABRIR-SEM-PYTHON-001: caminho puro, sem JSON e sem interpretador.
    # O ABRIR-A-ZARA.bat lia este caminho rodando Python; como a pasta do
    # projeto tem espacos no nome, a linha do cmd quebrava e o atalho morria em
    # silencio na cara do Alex. Texto simples nao tem esse problema.
    (ROOT / "ZARA_ACTIVE_BUILD.txt").write_text(str(dest_exe), encoding="utf-8")

    print("\n" + "=" * 64)
    print("CANDIDATO PRONTO")
    print("=" * 64)
    print(f"BUILD_ID        : {info['BUILD_ID']}")
    print(f"GIT_COMMIT      : {info['GIT_COMMIT'][:12]}")
    print(f"GIT_DIRTY       : {info['GIT_DIRTY']}")
    print(f"BACKEND_SHA256  : {info['BACKEND_SHA256'][:32]}...")
    print("CANDIDATE_READY: true")
    print(f"\nALEX_OPEN_THIS_EXE:\n{info['EXE_PATH']}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
