#!/usr/bin/env python3
"""ZARA 3.0 — sonda do backend EMPACOTADO: por que a voz Kore nao liga.

Nao abre o app, nao gera build, nao altera nada.

Detalhe que importa: 'voice-start' e despachado como TAREFA DE FUNDO
(ver o leitor de stdin em core/ipc_handlers.py). Se o stdin fechar, o
handler encerra e cancela essa tarefa antes de ela imprimir qualquer coisa.
Por isso aqui o stdin fica ABERTO, a saida e lida ao vivo por uma thread,
e o processo so e encerrado no fim da janela de observacao.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# ZARA-PROBE-ENCODING-001: a saida do backend traz emoji. No console cp1252 do
# Windows o print quebrava a sonda com UnicodeEncodeError e o VEREDITO nunca
# saia — o build automatico lia isso como "a Kore NAO subiu" mesmo com a voz OK.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
JANELA_SEGUNDOS = 45


def backend_path() -> Path:
    info = json.loads((ROOT / "ZARA_ACTIVE_BUILD.json").read_text(encoding="utf-8"))
    return Path(info["EXE_PATH"]).parent / "resources" / "backend" / "zara-backend.exe"


def main() -> int:
    backend = backend_path()
    print(f"backend: {backend}", flush=True)
    if not backend.exists():
        print("[FALHOU] backend empacotado nao encontrado")
        return 1

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "ZARA3" / "config" / "api_keys.json"
    if cfg.exists():
        try:
            key = str(json.loads(cfg.read_text(encoding="utf-8")).get("gemini_api_key") or "").strip()
            if key:
                env["GEMINI_API_KEY"] = key
                print(f"GEMINI_API_KEY injetada (len={len(key)})", flush=True)
            else:
                print("[AVISO] gemini_api_key VAZIA no config do empacotado", flush=True)
        except Exception as exc:
            print(f"[AVISO] config ilegivel: {exc}", flush=True)
    else:
        print(f"[AVISO] config do empacotado nao existe: {cfg}", flush=True)

    proc = subprocess.Popen(
        [str(backend)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
        cwd=str(backend.parent),
    )

    linhas: list[str] = []

    def leitor() -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                linhas.append(line.rstrip("\n"))
        except Exception:
            pass

    t = threading.Thread(target=leitor, daemon=True)
    t.start()

    # Deixa o backend terminar o boot antes de pedir a voz.
    time.sleep(6)
    print("enviando voice-start...", flush=True)
    try:
        proc.stdin.write(json.dumps({"type": "voice-start", "request_id": "probe", "payload": {}}) + "\n")
        proc.stdin.flush()
    except Exception as exc:
        print(f"[FALHOU] nao consegui escrever no backend: {exc}")

    # STDIN CONTINUA ABERTO de proposito. Só observa.
    print(f"observando por {JANELA_SEGUNDOS}s...", flush=True)
    for _ in range(JANELA_SEGUNDOS):
        time.sleep(1)
        if proc.poll() is not None:
            print("[AVISO] o backend morreu sozinho antes do fim da janela", flush=True)
            break

    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    t.join(timeout=5)

    print("\n----- SAIDA DO BACKEND (sem o registro de actions) -----")
    for ln in linhas:
        if "[ActionRegistry]" in ln:
            continue
        print(ln)

    print("\n----- VEREDITO -----")
    texto = "\n".join(linhas)
    if "Gemini Live voice started" in texto:
        print("GEMINI LIVE SUBIU. A voz Kore deveria estar ativa.")
    elif "Gemini Live start error" in texto or "LIVE_IMPORT result=FAIL" in texto:
        print("GEMINI LIVE FALHOU AO SUBIR. Motivo nas linhas acima.")
    elif "Local voice pipeline started" in texto:
        print("CAIU NO VOSK LOCAL. Gemini Live foi pulado ou falhou.")
    else:
        print("INCONCLUSIVO: o backend nao chegou a decidir dentro da janela.")

    for marca in ("LIVE_IMPORT", "Gemini Live start error", "Gemini Live voice started",
                  "Local voice pipeline started", "Voice start error", "Traceback",
                  "sounddevice", "PortAudio", "genai"):
        for ln in linhas:
            if marca.lower() in ln.lower():
                print(f"  > {ln}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
