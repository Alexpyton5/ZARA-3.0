#!/usr/bin/env python3
"""ZARA 3.0 — reconcilia a configuração usada pelo app EMPACOTADO.

Problema que isto resolve
-------------------------
`core/paths.py::config_dir()` devolve caminhos DIFERENTES conforme o modo:

    rodando do source   -> <projeto>/config/api_keys.json
    EXE empacotado      -> %LOCALAPPDATA%/ZARA3/config/api_keys.json

`ModelRouter._load_api_keys()` lê desse diretório e é quem exporta
`GEMINI_API_KEY` para o ambiente. E `IPCHandler._handle_voice_start_locked()`
só liga o Gemini Live (voz Kore, baixa latência) se essa variável existir:

    gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if gemini_key and ...:   # <- sem chave, cai no Vosk/Kokoro local

Ou seja: a chave preenchida na pasta do projeto **não é vista pelo EXE**.
O app não dá erro; ele silenciosamente usa a voz local. Sintomas: voz errada,
latência alta, comportamento diferente do que funcionava antes.

Este script NÃO altera código e NÃO imprime o valor de nenhuma chave.
Faz backup antes de escrever e só preenche campos que estiverem vazios.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_CFG = ROOT / "config" / "api_keys.json"

SECRET_HINTS = ("key", "token", "secret", "password")

# Campos que o app empacotado precisa para ligar a voz Kore.
VOICE_DEFAULTS = {
    "voice_mode": "gemini_live",
    "gemini_live_model": "gemini-3.1-flash-live-preview",
    "gemini_live_voice": "Kore",
}


def is_secret(name: str) -> bool:
    return any(h in name.lower() for h in SECRET_HINTS)


def show(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "VAZIA"
    return "PREENCHIDA" if is_secret(name) else value


def packaged_config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return Path(base) / "ZARA3" / "config"


def main() -> int:
    apply = "--apply" in sys.argv

    print("=" * 64)
    print("ZARA 3.0 - CONFIG DO APP EMPACOTADO")
    print("=" * 64)

    dest_dir = packaged_config_dir()
    dest = dest_dir / "api_keys.json"

    print(f"\nconfig do source     : {SOURCE_CFG}")
    print(f"config do EMPACOTADO : {dest}")

    if not SOURCE_CFG.exists():
        print("\n[FALHOU] o config do projeto nao existe. Nada a fazer.")
        return 1

    src = json.loads(SOURCE_CFG.read_text(encoding="utf-8"))
    dst = {}
    if dest.exists():
        try:
            dst = json.loads(dest.read_text(encoding="utf-8"))
            print("\nstatus               : o config do empacotado JA EXISTE")
        except Exception as exc:
            print(f"\n[AVISO] config do empacotado ilegivel ({exc}). Sera recriado.")
            dst = {}
    else:
        print("\nstatus               : o config do empacotado NAO EXISTE")
        print("                       -> por isso o EXE nunca ve a chave do Gemini")
        print("                       -> por isso a voz Kore nao liga")

    alvo = "gemini_api_key"
    print("\n--- chave do Gemini ---")
    print(f"  no source     : {show(alvo, src.get(alvo))}")
    print(f"  no empacotado : {show(alvo, dst.get(alvo))}")

    faltando = [
        k for k, v in src.items()
        if isinstance(v, str) and v.strip() and not str(dst.get(k) or "").strip()
    ]
    faltando_voz = [k for k, v in VOICE_DEFAULTS.items() if not str(dst.get(k) or "").strip()]

    print("\n--- o que falta no config do empacotado ---")
    for k in faltando:
        print(f"  {k}: {show(k, src.get(k))} no source, VAZIA no empacotado")
    for k in faltando_voz:
        print(f"  {k}: sera definido como '{VOICE_DEFAULTS[k]}'")
    if not faltando and not faltando_voz:
        print("  nada. o config do empacotado ja esta completo.")
        print("\n  => a causa da voz errada NAO e esta. Investigar o log.")
        return 0

    if not apply:
        print("\n" + "=" * 64)
        print("MODO SOMENTE LEITURA. Nada foi alterado.")
        print("Rode de novo com --apply para corrigir.")
        print("=" * 64)
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = dest.with_name(f"api_keys.json.bak_{stamp}")
        shutil.copy2(dest, backup)
        print(f"\nbackup criado        : {backup.name}")

    merged = dict(dst)
    for k in faltando:
        merged[k] = src[k]
    for k in faltando_voz:
        merged[k] = VOICE_DEFAULTS[k]

    dest.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 64)
    print("CORRIGIDO")
    print("=" * 64)
    print(f"campos preenchidos   : {len(faltando) + len(faltando_voz)}")
    print(f"chave do Gemini      : {show(alvo, merged.get(alvo))}")
    print("\nO EXE empacotado agora enxerga a chave e pode ligar o Gemini Live.")
    print("Nenhum valor de chave foi impresso nem enviado a lugar nenhum.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
