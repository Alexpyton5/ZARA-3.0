#!/usr/bin/env python3
"""Captura o id do grupo e o salva no config da ZARA.

ZARA-TELEGRAM-GRUPO-001. O bot @zara_project_group_bot precisa do *id numérico*
do grupo para saber a quem obedecer. Esse id não aparece na interface do
Telegram; o jeito seguro de pegá-lo é ler a mensagem que o bot recebe quando
está dentro do grupo.

Uso (rode no terminal do projeto, com o venv):
    .venv\\Scripts\\python.exe tools\\configurar_grupo_telegram.py

O que ele faz:
    1. Lê o token de grupo do config (telegram_group_token).
    2. Pergunta ao Telegram as mensagens pendentes do bot.
    3. Lista os grupos de onde o bot já recebeu mensagem e seus ids.
    4. Você digita o id do grupo desejado (ou ele pega o único grupo, se houver).
    5. Salva telegram_group_id nos dois locais de config (projeto + build).

Se o bot ainda não estiver no grupo, ele avisa: adicione o bot ao grupo e mande
qualquer mensagem, depois rode de novo.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_API = "https://api.telegram.org/bot{token}/{metodo}"


def _chamar(token: str, metodo: str, **params) -> dict | None:
    url = _API.format(token=token, metodo=metodo)
    dados = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    try:
        with urllib.request.urlopen(url, data=dados, timeout=30) as r:
            corpo = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    return corpo if corpo.get("ok") else None


def _carregar_token() -> str:
    for caminho in (RAIZ / "config" / "api_keys.json",):
        if caminho.exists():
            try:
                return str(json.loads(caminho.read_text(encoding="utf-8")).get("telegram_group_token") or "")
            except Exception:
                return ""
    return ""


def _listar_grupos(token: str) -> dict[int, dict]:
    """Devolve {chat_id: {type, title/first_name}} dos chats que o bot viu."""
    pacote = _chamar(token, "getUpdates", timeout=0, offset=-1) or {}
    grupos: dict[int, dict] = {}
    for u in pacote.get("result") or []:
        m = u.get("message") or u.get("edited_message") or {}
        c = m.get("chat") or {}
        cid = c.get("id")
        if cid is None:
            continue
        grupos[int(cid)] = {
            "type": c.get("type", "?"),
            "nome": c.get("title") or c.get("first_name") or f"chat {cid}",
        }
    return grupos


def _salvar(grupo_id: int) -> None:
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
        dados["telegram_group_id"] = grupo_id
        try:
            arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
            gravados += 1
        except Exception as exc:
            print(f"  Nao consegui gravar em {arquivo}: {exc}")
    return gravados


def main() -> int:
    token = _carregar_token()
    if not token:
        print("  Nao achei telegram_group_token no config.")
        print("  Salve o token do bot de grupo primeiro (tools/guardar_chave_telegram.py).")
        return 1

    print("  Lendo mensagens que o bot ja recebeu...")
    grupos = _listar_grupos(token)
    if not grupos:
        print("  O bot ainda nao recebeu nenhuma mensagem de grupo.")
        print("  Adicione o @zara_project_group_bot ao grupo e mande qualquer")
        print("  mensagem (mesmo 'oi'), depois rode este script de novo.")
        return 1

    # Confirma a leitura para o Telegram parar de reentregar.
    _chamar(token, "getUpdates", timeout=0, offset=-1)

    print("  Grupos/chats que o bot ja viu:")
    for cid, info in grupos.items():
        print(f"    {cid}  [{info['type']}]  {info['nome']}")

    grupos_de_verdade = {c: i for c, i in grupos.items() if i["type"] in ("group", "supergroup")}
    if not grupos_de_verdade:
        print("  Nenhum GRUPO encontrado (so privado). Adicione o bot a um grupo.")
        return 1
    if len(grupos_de_verdade) == 1:
        grupo_id = next(iter(grupos_de_verdade))
        print(f"  So ha um grupo: {grupo_id}. Usando ele.")
    else:
        try:
            escolha = int(input("  Digite o id do grupo desejado: ").strip())
        except Exception:
            print("  Id invalido.")
            return 1
        if escolha not in grupos_de_verdade:
            print("  Esse id nao e um grupo conhecido.")
            return 1
        grupo_id = escolha

    gravados = _salvar(grupo_id)
    if gravados:
        print(f"  Grupo {grupo_id} salvo em {gravados} lugar(es).")
        print("  Reinicie a ZARA para a ponte do grupo entrar em acao.")
        return 0
    print("  Nao consegui salvar em lugar nenhum.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
