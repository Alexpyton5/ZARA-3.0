#!/usr/bin/env python3
"""ZARA-PYTHON-PROPRIO-001 — dá à ZARA um Python que só é dela.

O problema que isto resolve
---------------------------
Até 2026-08-13 não existia nenhum Python instalado nesta máquina além do que o
uv baixou para o Hermes. Todo `python` dos .bat da ZARA resolvia para
`%LOCALAPPDATA%\\hermes\\hermes-agent\\venv\\Scripts\\python.exe`. Ou seja: a
ZARA buildava, testava e rodava dentro do ambiente de outro projeto, contra o
que `.claude/rules/managing-build-environments` manda. Se o Hermes fosse
removido ou atualizado, a ZARA parava de buildar sem ninguém entender por quê.

O que este script faz
---------------------
1. Baixa um CPython autocontido (python-build-standalone) para
   %LOCALAPPDATA%/ZARA3/toolchain/python, se ainda não existir. Não precisa de
   administrador, não instala nada no Windows e não toca no PATH global.
2. Cria o virtualenv da ZARA em <raiz>/.venv a partir desse Python.
3. Instala requirements.txt e as ferramentas de build/teste.

É idempotente: rodar de novo não refaz o que já está pronto.

Uso:
    python tools/preparar_python.py            # prepara o que faltar
    python tools/preparar_python.py --recriar  # apaga o .venv e refaz
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLCHAIN = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ZARA3" / "toolchain"
PYTHON_DIR = TOOLCHAIN / "python"
PYTHON_EXE = PYTHON_DIR / "python.exe"
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"

# Ferramentas que os portões de build exigem e que não estão em requirements.txt
FERRAMENTAS = ["pyinstaller", "pytest", "pytest-asyncio", "ruff"]

RELEASES = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
PADRAO_ASSET = "cpython-3.11."
SUFIXO_ASSET = "x86_64-pc-windows-msvc-install_only.tar.gz"


def passo(texto: str) -> None:
    print(f"\n=== {texto} ===", flush=True)


def rodar(exe: Path, *args: str) -> None:
    subprocess.run([str(exe), *args], cwd=ROOT, check=True)


def baixar_python() -> None:
    if PYTHON_EXE.exists():
        print(f"Python da ZARA já existe: {PYTHON_EXE}")
        return

    passo("baixando CPython autocontido (não precisa de administrador)")
    with urllib.request.urlopen(RELEASES, timeout=60) as resp:
        release = json.load(resp)

    url = next(
        (
            a["browser_download_url"]
            for a in release["assets"]
            if a["name"].startswith(PADRAO_ASSET) and a["name"].endswith(SUFIXO_ASSET)
        ),
        None,
    )
    if not url:
        raise SystemExit(
            "Nenhum CPython 3.11 para Windows na release mais recente. "
            "Baixe manualmente de github.com/astral-sh/python-build-standalone "
            f"e extraia em {PYTHON_DIR}."
        )

    TOOLCHAIN.mkdir(parents=True, exist_ok=True)
    tgz = TOOLCHAIN / "python311.tar.gz"
    print(f"origem: {url}")
    urllib.request.urlretrieve(url, tgz)
    with tarfile.open(tgz) as tf:
        tf.extractall(TOOLCHAIN)
    tgz.unlink(missing_ok=True)

    if not PYTHON_EXE.exists():
        raise SystemExit(f"extração terminou mas {PYTHON_EXE} não apareceu")
    print(f"pronto: {PYTHON_EXE}")


def criar_venv(recriar: bool) -> None:
    if recriar and VENV_DIR.exists():
        passo("apagando o .venv anterior")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    if VENV_PYTHON.exists():
        print(f"venv da ZARA já existe: {VENV_PYTHON}")
        return

    passo("criando o virtualenv da ZARA")
    rodar(PYTHON_EXE, "-m", "venv", str(VENV_DIR))
    rodar(VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip")


def instalar_dependencias() -> None:
    passo("instalando requirements.txt")
    rodar(VENV_PYTHON, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"))

    passo("instalando ferramentas de build e teste")
    rodar(VENV_PYTHON, "-m", "pip", "install", *FERRAMENTAS)


def provar() -> None:
    passo("provando que o ambiente é mesmo da ZARA")
    codigo = (
        "import sys;"
        "print('executavel :', sys.executable);"
        "print('base       :', sys.base_prefix);"
        "assert 'hermes' not in sys.executable.lower(), 'AINDA APONTA PARA O HERMES';"
        "assert 'hermes' not in sys.base_prefix.lower(), 'BASE AINDA E DO HERMES';"
        "import edge_tts, miniaudio, kokoro_onnx, sounddevice;"
        "print('voz        : edge_tts, miniaudio, kokoro_onnx, sounddevice OK')"
    )
    rodar(VENV_PYTHON, "-c", codigo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recriar", action="store_true", help="apaga o .venv e refaz do zero")
    args = ap.parse_args()

    if sys.platform != "win32":
        raise SystemExit("Este script prepara o ambiente Windows da ZARA.")

    baixar_python()
    criar_venv(args.recriar)
    instalar_dependencias()
    provar()

    print("\n" + "=" * 64)
    print("AMBIENTE DA ZARA PRONTO")
    print("=" * 64)
    print(f"Python da ZARA : {VENV_PYTHON}")
    print("Os .bat do projeto já usam este caminho automaticamente.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
