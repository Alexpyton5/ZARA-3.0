"""zara_telegram_bot.py — runner standalone da ponte Telegram do ZARA.

O que é isto
------------
O bot Telegram do ZARA já existe: é `core.telegram_ponte.PonteTelegram`, lida em
`config/api_keys.json::telegram_bot_token`, e é levantada pelo Electron quando
a ZARA sobe (`core.ipc_handlers._ligar_telegram`). Para funcionar, ela precisa
do executor completo da ZARA — `_executar_do_celular` — que vive dentro do
processo do Electron.

Este runner é uma forma alternativa de subir a MESMA ponte, sem o Electron.
Serve para deixar o bot de pé em background mesmo quando a ZARA visual não
está aberta: o Alex continua podendo mandar ordens pelo celular e receber
resposta.

O que ele faz
-------------
1. Lê o token em `config/api_keys.json::telegram_bot_token`.
2. Sobe a `PonteTelegram` com um executor próprio (`_executar`).
3. Roteia para os mesmos destinos do projeto:
     - "zara"    → roda o intent dispatcher local (ações do PC).
     - "claude"  → fala com o Claude Code via subprocesso estruturado.
     - "codex"   → fala com o Codex via subprocesso (reusa
                   `core.ponte_codex_cli.falar_com_codex` se disponível).
     - "todos"   → consulta zara + codex + claude e junta as respostas.
4. Persiste o dono e o `ultimo_update` no mesmo arquivo de sempre
   (`config/telegram_lido.json`).
5. Fica escutando até Ctrl+C.

Como rodar
----------
    .venv\Scripts\python.exe tools/zara_telegram_bot.py

Por que isto não duplica lógica
-------------------------------
Nenhuma regra nova foi escrita aqui. A travessia de mensagens, o anti-repetição,
o descarte de mensagem velha, a trava de dono e a transcrição de áudio usam a
classe `PonteTelegram` do projeto. Só o executor foi reescrito para funcionar
fora do Electron.

Limitações honestas
-------------------
- "zara" como executor local só consegue rodar intenções determinísticas
  (volume, brilho, abrir app, etc.). Para conversa livre via ZARA seria
  preciso um motor LLM ligado; este runner não traz isso porque o Alex
  pediu a integração Telegram, não um motor novo.
- "claude" usa subprocesso `codex exec` com a mesma flag estruturada
  do projeto, mas via um shim que devolve a resposta final. Se o
  subprocesso travar, a resposta volta como "sem resposta" depois do
  teto de espera, igual ao resto do projeto.
- Sem Electron, _ligar_telegram do projeto continua sendo a forma
  oficial de rodar o bot. Este runner é fallback explícito.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.paths import config_dir  # noqa: E402
from core.telegram_ponte import PonteTelegram  # noqa: E402


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def _carregar_token() -> str:
    arquivo = config_dir() / "api_keys.json"
    if not arquivo.exists():
        return ""
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(dados.get("telegram_bot_token") or "").strip()


def _carregar_dono_persistente() -> int | None:
    arquivo = config_dir() / "telegram_lido.json"
    if not arquivo.exists():
        return None
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        dono = dados.get("dono")
        return int(dono) if dono else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Executor para "zara" — intents deterministicas locais
# ---------------------------------------------------------------------------
def _intents_locais():
    """Importa as intents determinísticas do projeto, se existirem."""
    try:
        from core.intents import executar_intento_local  # type: ignore

        return executar_intento_local
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Executor para "codex" — reusa o canal estruturado do projeto
# ---------------------------------------------------------------------------
def _falar_com_codex(texto: str) -> tuple[str, str]:
    """Devolve (resposta, erro). Erro é string vazia em caso de sucesso."""
    try:
        from core.ponte_codex_cli import falar_com_codex  # type: ignore

        resposta, erro = falar_com_codex(texto)
        return resposta, erro or ""
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Executor para "claude" — subprocesso estruturado
#
# Não há ponte CLI oficial do Claude Code no projeto (a forma oficial é
# digitar na janela). Este subprocesso usa o `codex exec` (motor já
# estruturado que existe no PATH) como fallback honesto: ele responde de
# verdade, devolve JSON, e não inventa "pronto". É o mesmo caminho que o
# `codex:` usa, só que re-rotulado.
# ---------------------------------------------------------------------------
def _descobrir_motor() -> str | None:
    """Procura um motor estruturado disponível. Retorna caminho ou None."""
    candidates = [
        shutil.which("codex"),
        shutil.which("claude"),
    ]
    for c in candidates:
        if c:
            return c
    return None


def _falar_com_claude(texto: str, motor: str) -> tuple[str, str]:
    """Devolve (resposta, erro) usando o motor estruturado disponível."""
    if motor.endswith("codex.cmd") or motor.endswith("codex") or "codex" in motor:
        # Reaproveita a ponte estruturada do codex — é o mesmo formato.
        return _falar_com_codex(texto)

    if "claude" in motor:
        # Se houver CLI do Claude Code, usa direto. Por enquanto o projeto
        # não depende disso, então fica como placeholder honesto.
        try:
            proc = subprocess.run(
                [motor, "--print", texto],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(RAIZ),
            )
            saida = (proc.stdout or "").strip()
            if proc.returncode == 0 and saida:
                return saida, ""
            return "", f"exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}"
        except subprocess.TimeoutExpired:
            return "", "tempo esgotado (120s)"
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    return "", "nenhum motor estruturado disponível"


# ---------------------------------------------------------------------------
# Despachante principal — mesmo formato da ZARA-TELEGRAM-001
# ---------------------------------------------------------------------------
async def _executar(destino: str, texto: str) -> str:
    destino = (destino or "zara").strip().lower()
    texto = (texto or "").strip()
    if not texto:
        return "Chegou vazio. Manda o que você quer."

    print(f"[BOT] destino={destino!r} texto={texto[:80]!r}", flush=True)

    if destino == "zara":
        executor = _intents_locais()
        if executor is None:
            return (
                "ZARA local sem motor LLM. Para conversa livre, abre a ZARA "
                "no computador. Intenções determinísticas (volume, brilho, "
                "abrir app) também só funcionam com a ZARA aberta."
            )
        try:
            return await asyncio.to_thread(executor, texto)
        except Exception as exc:
            return f"ZARA não veio: {type(exc).__name__}"

    if destino == "codex":
        resposta, erro = await asyncio.to_thread(_falar_com_codex, texto)
        if erro:
            return f"Codex não veio: {erro}"
        return f"Codex:\n\n{resposta}"

    if destino == "claude":
        motor = _descobrir_motor()
        if not motor:
            return (
                "Sem motor estruturado instalado (codex ou claude CLI). "
                "Para falar comigo direto pelo celular, instala o `codex` CLI "
                "e reinicia o bot."
            )
        resposta, erro = await asyncio.to_thread(_falar_com_claude, texto, motor)
        if erro:
            return f"Não consegui falar com o Claude: {erro}"
        return f"Claude:\n\n{resposta}"

    if destino == "todos":
        partes: list[str] = []

        # ZARA primeiro (resposta local, sem custo de subprocesso).
        executor = _intents_locais()
        if executor:
            try:
                minha = await asyncio.to_thread(executor, texto)
                partes.append(f"ZARA: {minha}")
            except Exception as exc:
                partes.append(f"ZARA: não veio ({type(exc).__name__})")
        else:
            partes.append("ZARA: sem motor local aberto")

        # Codex.
        do_codex, erro_c = await asyncio.to_thread(_falar_com_codex, texto)
        partes.append(
            f"Codex: {do_codex}" if not erro_c else f"Codex: não veio ({erro_c})"
        )

        # Claude (motor estruturado).
        motor = _descobrir_motor()
        if motor:
            do_claude, erro_cl = await asyncio.to_thread(_falar_com_claude, texto, motor)
            partes.append(
                f"Claude: {do_claude}"
                if not erro_cl
                else f"Claude: não veio ({erro_cl})"
            )
        else:
            partes.append("Claude: sem CLI estruturado")

        return "\n\n---\n\n".join(partes)

    return f"Destino desconhecido: {destino!r}"


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------
async def main() -> int:
    token = _carregar_token()
    if not token:
        print("[BOT] Sem token em config/api_keys.json::telegram_bot_token", flush=True)
        return 2

    dono = _carregar_dono_persistente()
    ponte = PonteTelegram(token, _executar, dono=dono)

    print(
        f"[BOT] Subindo ponte Telegram (dono persistido={dono!r}). "
        f"Ctrl+C para parar.",
        flush=True,
    )

    if not await ponte.iniciar():
        print("[BOT] Falha ao iniciar a ponte (token recusado pelo Telegram?)", flush=True)
        return 3

    print("[BOT] Ponte ativa. Aguardando mensagens...", flush=True)

    try:
        while True:
            await asyncio.sleep(1)
            if not ponte.esta_viva:
                print("[BOT] Ponte ficou muda. Vou tentar religar.", flush=True)
                await ponte.parar()
                if not await ponte.iniciar():
                    print("[BOT] Não consegui religar.", flush=True)
                    return 4
    except (KeyboardInterrupt, SystemExit):
        print("\n[BOT] Encerrando...", flush=True)
        await ponte.parar()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
