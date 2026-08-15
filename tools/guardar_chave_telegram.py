#!/usr/bin/env python3
"""Guarda a chave do robô do Telegram no config da ZARA.

ZARA-TELEGRAM-001. Alex perguntou se não daria para eu configurar tudo. O login
na conta dele do Telegram é dele — número e código de verificação não passam por
mim. Mas editar arquivo de configuração à mão é o tipo de coisa que ele não
deveria precisar fazer, então sobra só colar a chave numa caixa.

Confere o formato antes de gravar: chave errada faria a ponte falhar em silêncio
na próxima abertura, e ele levaria um tempo até descobrir por quê.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Formato do Telegram: <numeros>:<letras, numeros, - e _>
FORMATO = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


def main() -> int:
    if len(sys.argv) < 2:
        print("  Nenhuma chave recebida.")
        return 1

    chave = " ".join(sys.argv[1:]).strip().strip('"').strip("'")

    if not FORMATO.match(chave):
        print("  Essa chave nao parece do Telegram.")
        print("  Ela tem esta cara:  8123456789:AAF-abcdefGHIJ...")
        print("  Confira se copiou inteira, sem faltar pedaco.")
        return 1

    # ZARA-CONFIG-DOIS-LUGARES-001
    # O app EMPACOTADO nao le a config do projeto: `core.paths.config_dir()`
    # aponta para %LOCALAPPDATA%\ZARA3\config quando esta congelado. Gravar so
    # no projeto fez a chave "sumir" — a ponte do Telegram nunca subiu e as
    # mensagens do Alex ficaram esperando sem ninguem responder.
    # Grava nos dois, sempre.
    import os

    destinos = [RAIZ / "config" / "api_keys.json"]
    base = os.environ.get("LOCALAPPDATA")
    if base:
        destinos.append(Path(base) / "ZARA3" / "config" / "api_keys.json")

    gravados = 0
    for arquivo in destinos:
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
        except Exception as exc:
            print(f"  Nao consegui abrir {arquivo}: {exc}")
            continue

        try:
            reserva = arquivo.with_suffix(".json.antes-do-telegram")
            if arquivo.exists() and not reserva.exists():
                reserva.write_text(
                    json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception:
            pass

        dados["telegram_bot_token"] = chave
        try:
            arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            print(f"  Nao consegui gravar em {arquivo}: {exc}")
            continue

        if json.loads(arquivo.read_text(encoding="utf-8")).get("telegram_bot_token") == chave:
            gravados += 1

    if not gravados:
        print("  Nao consegui guardar em lugar nenhum. Avise o Claude.")
        return 1

    print(f"  Chave guardada e conferida em {gravados} lugar(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
