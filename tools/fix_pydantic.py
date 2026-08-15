#!/usr/bin/env python3
"""ZARA 3.0 — ZARA-ENV-PYDANTIC-001: conserta o par pydantic/pydantic-core.

CAUSA RAIZ PROVADA (sonda do backend empacotado, 2026-08-12 19:27):

    [VOICE_TRACE] stage=LIVE_IMPORT result=FAIL module=google.genai
    SystemError: The installed pydantic-core version (2.41.5) is incompatible
    with the current pydantic version, which requires 2.46.4

Cadeia completa:
    pydantic-core desalinhado
      -> import google.genai falha
      -> GeminiLiveVoice._run levanta RuntimeError
      -> _handle_voice_start_locked cai no pipeline Vosk local
      -> voz Kokoro/SAPI em vez de Kore, latencia alta, STT ruim

E o MESMO defeito registrado para o Hermes no handoff do Mentor. A ZARA usa o
venv do Hermes, entao herdou a quebra.

Tarefa propria e delimitada (regra de ambiente do CLAUDE.md): mexe em UM par de
pacotes, grava o estado anterior para rollback, e prova o resultado importando
google.genai de verdade.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def versao(pkg: str) -> str:
    out = run([PY, "-c", f"import importlib.metadata as m; print(m.version('{pkg}'))"])
    return out.stdout.strip() or "ausente"


def testa_genai() -> tuple[bool, str]:
    out = run([PY, "-c", "from google import genai; from google.genai import types; print('OK')"])
    if out.returncode == 0 and "OK" in out.stdout:
        return True, "import google.genai OK"
    return False, (out.stderr or out.stdout).strip().splitlines()[-1] if (out.stderr or out.stdout).strip() else "falha sem mensagem"


def main() -> int:
    aplicar = "--apply" in sys.argv

    print("=" * 64)
    print("ZARA-ENV-PYDANTIC-001")
    print("=" * 64)
    print(f"\npython usado: {PY}\n")

    antes = {p: versao(p) for p in ("pydantic", "pydantic-core", "google-genai", "sounddevice")}
    for k, v in antes.items():
        print(f"  {k:16} {v}")

    ok, msg = testa_genai()
    print(f"\nimport google.genai : {'OK' if ok else 'FALHA'}")
    if not ok:
        print(f"  {msg}")

    if ok:
        print("\nNada a consertar: google.genai ja importa neste ambiente.")
        print("Se o EXE empacotado ainda falhar, o problema e do build, nao do venv.")
        return 0

    if not aplicar:
        print("\n" + "=" * 64)
        print("MODO SOMENTE LEITURA. Rode com --apply para consertar.")
        print("=" * 64)
        return 0

    # Rollback: congela o estado atual antes de tocar em qualquer coisa.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    freeze = run([PY, "-m", "pip", "freeze"])
    backup = ROOT / f"tools/pip-freeze-antes-{stamp}.txt"
    backup.write_text(freeze.stdout, encoding="utf-8")
    print(f"\nrollback salvo em: {backup.name}")
    print("  (para reverter: pip install -r <esse arquivo>)")

    print("\nreinstalando o par pydantic/pydantic-core de forma consistente...")
    cmd = [PY, "-m", "pip", "install", "--upgrade", "--force-reinstall",
           "--no-cache-dir", "pydantic"]
    print("  " + " ".join(cmd))
    out = run(cmd)
    print(out.stdout[-2500:])
    if out.returncode != 0:
        print(out.stderr[-2500:])
        print("\n[FALHOU] pip nao concluiu.")
        return 1

    depois = {p: versao(p) for p in ("pydantic", "pydantic-core", "google-genai")}
    print("\n--- versoes depois ---")
    for k, v in depois.items():
        print(f"  {k:16} {antes.get(k,'?')}  ->  {v}")

    ok2, msg2 = testa_genai()
    print(f"\nimport google.genai : {'OK' if ok2 else 'AINDA FALHA'}")
    if not ok2:
        print(f"  {msg2}")
        print("\nNAO resolveu. Nao gere build. Rollback disponivel no arquivo acima.")
        return 1

    (ROOT / "tools" / "ZARA-ENV-PYDANTIC-001.json").write_text(
        json.dumps({"quando": stamp, "antes": antes, "depois": depois,
                    "rollback": backup.name, "resultado": "google.genai importa"},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 64)
    print("CONSERTADO. google.genai importa neste ambiente.")
    print("Proximo passo obrigatorio: gerar um build NOVO.")
    print("O EXE atual foi empacotado com o pydantic-core quebrado dentro.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
