"""ZARA-CLAUDE-BRAIN-001 (Alex, 2026-08-28 à noite)

Motor Claude, usando a ASSINATURA Claude Pro do Alex (sem
API paga, por decisão explícita dele) via invocação HEADLESS do Claude Code
(`claude -p`), diferente de `core/actions/ponte_claude.py` -- aquele
automatiza uma JANELA VISÍVEL do Claude Code via UI Automation (pensado pra
Alex ler/escrever manualmente); este módulo só sobe um processo e lê o
stdout, sem depender de nenhuma janela aberta.

Latência real, e não é bug: um turno de Claude Code leva de alguns segundos
a mais de um minuto, bem mais que o roteador atual (Gemini/NVIDIA). É o
preço de usar a assinatura em vez de API paga -- por isso este módulo só
fornece a CHAMADA; a integração no pipeline de voz (ipc_handlers.py) usa
isso de forma assíncrona (reconhece o pedido na hora, fala a resposta
quando ela chegar), nunca trava um turno de voz esperando.
"""
from __future__ import annotations

import asyncio
import contextlib
import shutil

_DEFAULT_TIMEOUT_S = 120.0


def claude_cli_available() -> bool:
    """True se o executável `claude` existir no PATH deste processo."""
    return shutil.which("claude") is not None


async def ask_claude(
    prompt: str,
    *,
    continue_conversation: bool = True,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    cwd: str | None = None,
) -> str | None:
    """Pergunta ao Claude Code (headless, `claude -p`) e devolve a resposta
    em texto. None sempre que não há como responder com segurança -- CLI
    ausente, timeout, erro de processo, saída vazia. Nunca inventa
    resposta nem finge sucesso."""
    text = str(prompt or "").strip()
    if not text:
        return None
    if not claude_cli_available():
        return None

    args = ["claude", "-p", text]
    if continue_conversation:
        args.append("-c")

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except OSError:
        return None

    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        return None

    if process.returncode != 0:
        return None

    response = stdout.decode("utf-8", errors="ignore").strip()
    return response or None
