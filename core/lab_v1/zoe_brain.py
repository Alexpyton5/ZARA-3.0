"""Rota "cerebro pesado" do Lab — FRENTE 2 (MISSAO LAB VIVO, 28/09/2026).

VERDADE DURA: nao existe "compartilhar a cota do Muse". Nao ha chave,
API ou endpoint que divida a cota do chat do Alex com os bots.

O desenho real, que ja funciona, e este:
  1. O bot escreve a pergunta dificil na ZOE-INBOX (ask_zoe).
  2. A zoe le a caixinha no turno vanguarda (a cada ~10 min, 24h).
  3. A zoe responde criando RESPOSTA-ZOE-<id>.md na mesma pasta.
  4. O bot le a resposta de volta (read_zoe_answer).

E assim que "a cota do Muse" entra no Lab: pela zoe, nao por chave.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

INBOX_ENV = "ZARA_ZOE_INBOX"
QUESTION_PREFIX = "PERGUNTA-ZOE-"
ANSWER_PREFIX = "RESPOSTA-ZOE-"


def inbox_dir() -> Path:
    """Pasta da caixinha do loop. Overridavel via env (testes)."""
    env = os.environ.get(INBOX_ENV, "").strip()
    if env:
        return Path(env)
    # <projeto>/core/lab_v1/zoe_brain.py -> <projeto>/ZOE-INBOX
    return Path(__file__).resolve().parents[2] / "ZOE-INBOX"


_ask_counter = 0


def _new_id() -> str:
    # ms + pid + contador do processo: duas perguntas nunca colidem,
    # nem na mesma fracao de segundo (a FASE 2 escala uma por tarefa).
    global _ask_counter
    _ask_counter += 1
    return f"{int(time.time() * 1000)}-{os.getpid() % 100000}-{_ask_counter}"


def ask_zoe(
    question: str,
    *,
    context: str = "",
    asked_by: str = "lab",
    session_id: str | None = None,
    task_id: str | None = None,
) -> str:
    """Deixa uma pergunta para a zoe na caixinha. Devolve o id da pergunta.

    A zoe responde criando RESPOSTA-ZOE-<id>.md na mesma pasta, no proximo
    turno vanguarda. Nao e instantaneo: orcar ~10 min.

    FASE 2 PECA 6 (28/09/2026): session_id/task_id opcionais viram
    cabecalho legivel por maquina (sessao:/tarefa:) no arquivo da pergunta,
    para o runtime re-registrar escalacoes pendentes depois de um restart
    (o _pending do leitor e em memoria). Perguntas antigas, sem cabecalho,
    continuam validas — o restore so ignora o que nao entende.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("pergunta vazia")
    qid = _new_id()
    inbox = inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    routing = ""
    if session_id:
        sid = str(session_id).replace("\n", " ").strip()
        tid = str(task_id).replace("\n", " ").strip() if task_id else "-"
        routing = f"sessao: {sid}\ntarefa: {tid}\n"
    body = (
        f"[ZOE-BRAIN] Pergunta do Lab para a zoe (cerebro pesado)\n"
        f"id: {qid}\n"
        f"de: {asked_by}\n"
        f"{routing}"
        f"quando: {time.strftime('%d/%m/%Y %H:%M')}\n"
        f"\n"
        f"COMO RESPONDER: crie o arquivo {ANSWER_PREFIX}{qid}.md nesta mesma\n"
        f"pasta com a resposta. Nao apague este arquivo.\n"
        f"\n"
        f"--- CONTEXTO ---\n{(context or '(sem contexto)').strip()}\n"
        f"\n"
        f"--- PERGUNTA ---\n{question}\n"
    )
    (inbox / f"{QUESTION_PREFIX}{qid}.md").write_text(body, encoding="utf-8")
    return qid


def read_zoe_answer(question_id: str) -> str | None:
    """Le a resposta da zoe, se ela ja respondeu. None = ainda nao."""
    qid = "".join(c for c in str(question_id) if c.isdigit() or c == "-").strip("-")
    if not qid:
        return None
    path = inbox_dir() / f"{ANSWER_PREFIX}{qid}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None
