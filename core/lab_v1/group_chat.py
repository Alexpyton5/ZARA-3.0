"""Grupo único persistente do ZARA Lab — FRENTE 1 / MISSÃO LAB VIVO.

Um time "ZARA Lab" tem exatamente UMA sessão de grupo (id fixo
`GROUP_SESSION_ID`), onde Alex e os agentes conversam com @menções ou em
broadcast. Diferente de `runtime.send_agent_message` (que exige exatamente
1 destinatário), o grupo permite broadcast — por isso este módulo existe.

Regras duras:
- fail-closed: menção desconhecida ou ambígua = erro, nunca roteia no escuro;
- remetente precisa ser membro ativo não-arquivado do time;
- sem menção = broadcast (to_agent_id None, to_role "ALL");
- o diário no Obsidian (TeamChatMemory) nunca quebra um post.
"""
from __future__ import annotations

from typing import Any

try:  # layout real: core/lab_v1/...
    from core.lab_v1.domain import (
        Message, MessageKind, Run, RunState, Session, Team, new_id, now,
    )
    from core.lab_v1.store import LabStore
    from core.lab_v1 import messages as message_protocol
    from core.lab_v1.mentions import MentionResolutionError, resolve_mentions
    from core.lab_v1.providers.fallback import complete_with_fallback
    from core.lab_v1.seat_engines import default_ladder_for
except ImportError:  # cópia de trabalho plana (só para teste local)
    from domain import Message, MessageKind, Run, RunState, Session, Team, new_id, now  # type: ignore[no-redef]
    from store import LabStore  # type: ignore[no-redef]
    import messages as message_protocol  # type: ignore[no-redef]
    from mentions import MentionResolutionError, resolve_mentions  # type: ignore[no-redef]
    from fallback import complete_with_fallback  # type: ignore[no-redef]
    from seat_engines import default_ladder_for  # type: ignore[no-redef]

__all__ = [
    "GROUP_TEAM_NAME",
    "GROUP_SESSION_ID",
    "BROADCAST_ROLE",
    "MentionResolutionError",
    "EngineError",
    "ensure_group_chat",
    "post_user_message",
    "post_agent_message",
    "reply_to",
    "read_thread",
    "agent_inbox",
    "mirror_journal",
    "speak_with_engine",
    "answer_inbox",
]

GROUP_TEAM_NAME = "ZARA Lab"
GROUP_SESSION_ID = "sess_grupo_zara_lab"
GROUP_OBJECTIVE = "Conversa única do grupo ZARA Lab"
BROADCAST_ROLE = "ALL"
_JOURNAL_MISSION_ID = "zara-lab-grupo"


# ---------------------------------------------------------------------------
# FASE 2 PEÇA 3 (zoe, 28/09): memória compartilhada dentro da conversa.
# O bloco abaixo monta o contexto da visão unificada (peças 1-4 da memória
# compartilhada) para o prompt do bot. Aditivo: se shared_memory não for
# passado, o prompt segue exatamente igual ao de antes (fail-closed).

def _shared_context_block(shared_memory: dict[str, Any] | None) -> str:
    """Monta o bloco de memória compartilhada p/ o prompt (ou "").

    shared_memory: dict com lab_memory/zara_turns/sources/max_chars.
    Qualquer problema -> "" (fail-closed): o turno segue com o prompt
    antigo, nunca com fato inventado.
    """
    if not shared_memory:
        return ""
    try:
        try:
            from core.lab_shared_context import build_shared_context
        except ImportError:
            from lab_shared_context import build_shared_context  # type: ignore[no-redef]
    except ImportError:
        return ""
    try:
        return build_shared_context(
            lab_memory=shared_memory.get("lab_memory"),
            zara_turns=shared_memory.get("zara_turns"),
            bot_id=str(shared_memory.get("bot_id", "lab-bot")),
            sources=shared_memory.get("sources", ("lab",)),
            max_entries=int(shared_memory.get("max_entries", 40)),
            max_chars=int(shared_memory.get("max_chars", 4000)),
        )
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _normalize(content: Any) -> str:
    """Texto limpo e limitado, com erros em PT-BR simples."""
    if not str(content or "").strip():
        raise ValueError("A mensagem precisa ter texto.")
    try:
        return message_protocol.normalize_message_text(content)
    except ValueError:
        raise ValueError(
            "A mensagem é longa demais "
            f"(máximo de {message_protocol.MESSAGE_MAX_CHARS} caracteres)."
        )


def _active_member(store: LabStore, team_id: str, agent_id: str | None):
    """Devolve o AgentProfile se for membro ativo não-arquivado, senão None."""
    if not agent_id:
        return None
    agent = store.get_agent(agent_id)
    if agent is None or agent.archived:
        return None
    if agent_id not in message_protocol.active_member_ids(store, team_id):
        return None
    return agent


def _require_session(store: LabStore, session_id: str) -> Session:
    session = store.get_session(session_id)
    if session is None:
        raise ValueError("Sessão não encontrada.")
    return session


def _resolve_recipient(
    store: LabStore, team_id: str, text: str, to_agent_id: str | None
) -> str | None:
    """Devolve o agent_id destinatário, ou None quando é broadcast.

    Fail-closed: menção desconhecida/ambígua levanta MentionResolutionError
    (nunca roteia no escuro); mais de 1 menção também é erro — no grupo,
    mensagem com menção é 1-para-1 e mensagem sem menção é broadcast.
    """
    if to_agent_id is not None and _active_member(store, team_id, to_agent_id) is None:
        raise MentionResolutionError(
            "O destinatário precisa ser um agente com membership ativo."
        )
    # Levanta MentionResolutionError se alguma menção for desconhecida/ambígua.
    mentioned = resolve_mentions(store, team_id, text)
    if to_agent_id is not None:
        if any(agent_id != to_agent_id for agent_id in mentioned):
            raise MentionResolutionError(
                "A menção no texto diverge do destinatário informado."
            )
        return to_agent_id
    if len(mentioned) > 1:
        raise MentionResolutionError(
            "O grupo aceita no máximo 1 menção por mensagem; "
            "sem menção a mensagem vai para todo o grupo."
        )
    return mentioned[0] if mentioned else None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def ensure_group_chat(store: LabStore) -> Session:
    """Garante o time "ZARA Lab" e sua sessão única. Idempotente.

    Se a sessão `GROUP_SESSION_ID` já existir mas pertencer a outro time,
    levanta erro em vez de sequestrar a conversa alheia.
    """
    store.initialize()
    team = next(
        (t for t in store.list_teams(include_archived=True) if t.name == GROUP_TEAM_NAME),
        None,
    )
    if team is None:
        team = Team(
            id=new_id("team"),
            name=GROUP_TEAM_NAME,
            objective="Grupo único do ZARA Lab",
        )
        store.save_team(team)
    elif team.archived:
        team.archived = False
        store.save_team(team)

    session = store.get_session(GROUP_SESSION_ID)
    if session is None:
        session = Session(
            id=GROUP_SESSION_ID,
            team_id=team.id,
            objective=GROUP_OBJECTIVE,
        )
        store.save_session(session)
    elif session.team_id != team.id:
        raise ValueError(
            "A sessão do grupo pertence a outro time; recusei abrir."
        )
    return session


def post_user_message(
    store: LabStore,
    session_id: str,
    author_name: str,
    content: str,
    to_agent_id: str | None = None,
) -> dict[str, Any]:
    """Mensagem do Alex no grupo. Sem menção = broadcast para todo o grupo."""
    store.initialize()
    session = _require_session(store, session_id)
    text = _normalize(content)
    recipient_id = _resolve_recipient(store, session.team_id, text, to_agent_id)
    recipient = _active_member(store, session.team_id, recipient_id)
    message = Message(
        id=new_id("msg"),
        session_id=session_id,
        kind=MessageKind.USER,
        author=author_name or "Alex",
        content=text,
        to_agent_id=recipient_id,
        to_role=recipient.role.value if recipient else BROADCAST_ROLE,
        correlation_id=message_protocol.new_correlation_id(),
    )
    store.add_message(message)
    return message_protocol.message_to_dict(message)


def post_agent_message(
    store: LabStore,
    session_id: str,
    from_agent_id: str,
    content: str,
    to_agent_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Mensagem de um agente no grupo. Sem menção = broadcast."""
    store.initialize()
    session = _require_session(store, session_id)
    sender = _active_member(store, session.team_id, from_agent_id)
    if sender is None:
        raise ValueError(
            "O remetente precisa ser um agente do time com membership ativo."
        )
    text = _normalize(content)
    recipient_id = _resolve_recipient(store, session.team_id, text, to_agent_id)
    if recipient_id == from_agent_id:
        raise ValueError("Uma mensagem precisa de dois agentes distintos.")
    recipient = _active_member(store, session.team_id, recipient_id)
    message = Message(
        id=new_id("msg"),
        session_id=session_id,
        kind=MessageKind.AGENT,
        author=sender.name,
        content=text,
        author_agent_id=from_agent_id,
        run_id=run_id,
        to_agent_id=recipient_id,
        to_role=recipient.role.value if recipient else BROADCAST_ROLE,
        correlation_id=message_protocol.new_correlation_id(),
    )
    store.add_message(message)
    return message_protocol.message_to_dict(message)


def reply_to(
    store: LabStore,
    session_id: str,
    from_agent_id: str,
    reply_to_id: str,
    content: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Resposta de um agente a uma mensagem que foi endereçada a ele.

    Só o destinatário canônico da mensagem original pode responder, e a
    resposta preserva a correlation_id da mensagem raiz.
    """
    store.initialize()
    session = _require_session(store, session_id)
    sender = _active_member(store, session.team_id, from_agent_id)
    if sender is None:
        raise ValueError(
            "O remetente precisa ser um agente do time com membership ativo."
        )
    root = next(
        (
            item
            for item in store.list_messages(session_id, limit=10000)
            if item.id == reply_to_id
        ),
        None,
    )
    if root is None:
        raise ValueError("A mensagem original não foi encontrada.")
    if root.to_agent_id != from_agent_id:
        raise ValueError("Somente o destinatário da mensagem original pode responder.")
    if root.author_agent_id == from_agent_id:
        raise ValueError("Não dá para responder à própria mensagem.")
    text = _normalize(content)

    if root.author_agent_id is None:
        # A mensagem original foi do Alex: a resposta volta para ele.
        to_agent_id, to_role = None, "OWNER"
    else:
        original_author = _active_member(store, session.team_id, root.author_agent_id)
        to_agent_id = root.author_agent_id
        to_role = original_author.role.value if original_author else BROADCAST_ROLE

    message = Message(
        id=new_id("msg"),
        session_id=session_id,
        kind=MessageKind.AGENT,
        author=sender.name,
        content=text,
        author_agent_id=from_agent_id,
        run_id=run_id,
        to_agent_id=to_agent_id,
        to_role=to_role,
        reply_to=reply_to_id,
        correlation_id=root.correlation_id or message_protocol.new_correlation_id(),
    )
    store.add_message(message)
    return message_protocol.message_to_dict(message)


def read_thread(store: LabStore, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Todas as mensagens da sessão em ordem cronológica."""
    store.initialize()
    _require_session(store, session_id)
    return [
        message_protocol.message_to_dict(message)
        for message in store.list_messages(session_id, limit=limit)
    ]


def agent_inbox(store: LabStore, session_id: str, agent_id: str) -> list[dict[str, Any]]:
    """Mensagens endereçadas ao agente que ainda não tiveram resposta."""
    store.initialize()
    _require_session(store, session_id)
    messages = store.list_messages(session_id, limit=10000)
    pending = message_protocol.pending_reply_ids(messages, for_agent_id=agent_id)
    return [
        message_protocol.message_to_dict(message)
        for message in messages
        if message.id in pending
    ]


def mirror_journal(
    store: LabStore, message: Any, agent_role: str = "ZARA"
) -> dict[str, bool]:
    """Espelha uma mensagem no diário do Obsidian (TeamChatMemory).

    Melhor esforço: qualquer falha (vault indisponível, conteúdo sensível,
    módulo ausente) é engolida e reportada como mirrored=False. Nunca
    quebra o post da mensagem.
    """
    try:
        try:
            from core.lab_v1.team_chat_memory import TeamChatMemory
        except ImportError:  # cópia de trabalho plana (só para teste local)
            from team_chat_memory import TeamChatMemory  # type: ignore[no-redef]
        if isinstance(message, Message):
            summary = message.content
        elif isinstance(message, dict):
            summary = str(message.get("content") or "")
        else:
            summary = str(message or "")
        journal = TeamChatMemory()
        result = journal.append(
            mission_id=_JOURNAL_MISSION_ID,
            role=str(agent_role or "ZARA"),
            state="OBSERVED",
            summary=summary,
        )
        mirrored = bool(result.get("success")) if isinstance(result, dict) else False
    except Exception:
        mirrored = False
    return {"mirrored": mirrored}


# ---------------------------------------------------------------------------
# Fala com motor (integração FRENTE 2): o assento fala pela sua escada
# ---------------------------------------------------------------------------

class EngineError(ValueError):
    """Nenhum motor da escada respondeu; nada foi postado no grupo."""


def _call_engine(runtime: Any, session: Session, agent: Any, *, prompt: str,
                 system: str | None, timeout_s: int):
    """Roda o prompt na escada do assento e devolve (Run, outcome).

    Grátis primeiro (NVIDIA NIM), Luna via Codex só se tudo falhar.
    A linha Run é salva ANTES (STARTED) e atualizada depois — sem Run
    não há chamada real, como no resto do Lab.
    """
    store = runtime.store
    run = Run(
        id=new_id("run"), session_id=session.id, agent_id=agent.id,
        provider_id=agent.provider_id, model=agent.model,
        state=RunState.STARTED, effort=agent.effort,
    )
    store.save_run(run)
    ladder = default_ladder_for(agent.role)
    outcome = complete_with_fallback(
        runtime.registry, ladder, prompt=prompt, system=system,
        timeout_s=timeout_s,
    )
    run.provider_id = outcome.provider_id or agent.provider_id
    run.model = outcome.model or agent.model
    run.model_reported = outcome.result.model_reported
    run.duration_ms = outcome.result.duration_ms
    if outcome.ok:
        run.state = RunState.COMPLETED
    else:
        run.state = RunState.FAILED
        run.error = outcome.result.error or "Todos os degraus da escada falharam."
    run.ended_at = now()
    store.save_run(run)
    return run, outcome


def _attempts_summary(outcome: Any) -> str:
    tried = [
        f"{a.provider_id}/{str(a.model).split('/')[-1]}"
        for a in (outcome.attempts or []) if not a.skipped
    ]
    return ", ".join(tried) if tried else "nenhum degrau pôde ser tentado"


def speak_with_engine(
    runtime: Any,
    session_id: str,
    agent_id: str,
    *,
    prompt: str,
    system: str | None = None,
    to_agent_id: str | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """O agente fala no grupo de verdade, pela escada do seu assento.

    Se nenhum degrau responder, levanta EngineError e nada é postado
    (fail-closed: sem resposta inventada).
    """
    store = runtime.store
    store.initialize()
    session = _require_session(store, session_id)
    agent = _active_member(store, session.team_id, agent_id)
    if agent is None:
        raise ValueError("O agente precisa estar no time com membership ativo.")
    if not str(prompt or "").strip():
        raise ValueError("O prompt precisa ter texto.")
    run, outcome = _call_engine(
        runtime, session, agent, prompt=str(prompt), system=system,
        timeout_s=timeout_s,
    )
    if not outcome.ok:
        raise EngineError(
            "Nenhum motor respondeu para o agente falar no grupo. "
            f"Tentados: {_attempts_summary(outcome)}."
        )
    message = post_agent_message(
        store, session_id, agent_id, outcome.result.text,
        to_agent_id=to_agent_id, run_id=run.id,
    )
    return {
        "message": message,
        "run_id": run.id,
        "provider_id": outcome.provider_id,
        "model": outcome.model,
        "attempts": [
            {"provider_id": a.provider_id, "model": a.model, "ok": a.ok,
             "skipped": a.skipped, "error": a.error}
            for a in outcome.attempts
        ],
    }


def answer_inbox(
    runtime: Any,
    session_id: str,
    agent_id: str,
    *,
    system: str | None = None,
    history_limit: int = 20,
    timeout_s: int = 120,
    shared_memory: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """O agente lê a menção pendente mais antiga e responde com seu motor.

    Devolve None quando não há nada pendente. A resposta sai ligada à
    mensagem original (reply_to) e carrega o run_id da chamada real.
    shared_memory (FASE 2 PEÇA 3): dict opcional {lab_memory, zara_turns,
    sources, max_chars} — injeta os fatos da memória compartilhada no
    prompt. None = comportamento antigo, prompt inalterado.
    """
    store = runtime.store
    store.initialize()
    session = _require_session(store, session_id)
    agent = _active_member(store, session.team_id, agent_id)
    if agent is None:
        raise ValueError("O agente precisa estar no time com membership ativo.")
    pending = agent_inbox(store, session_id, agent_id)
    if not pending:
        return None
    target = pending[0]
    thread = read_thread(store, session_id, limit=history_limit)
    context = "\n".join(
        f"{item['author']}: {item['content']}" for item in thread
    )
    prompt = (
        "Conversa do grupo ZARA Lab:\n" + context +
        f"\n\nVocê é {agent.name}. Responda de forma curta e útil, em português."
    )
    system_prompt = system or (
        f"Você é {agent.name}, {agent.role.value} do ZARA Lab. "
        "Responda curto, em português, sem JSON. "
        "Não afirme que executou, testou ou alterou código sem evidência."
    )
    shared_block = _shared_context_block(shared_memory)  # FASE2-PECA3
    if shared_block:
        prompt = prompt + "\n\n" + shared_block
    run, outcome = _call_engine(
        runtime, session, agent, prompt=prompt, system=system_prompt,
        timeout_s=timeout_s,
    )
    if not outcome.ok:
        raise EngineError(
            "Nenhum motor respondeu para o agente responder no grupo. "
            f"Tentados: {_attempts_summary(outcome)}."
        )
    message = reply_to(
        store, session_id, agent_id, target["id"], outcome.result.text,
        run_id=run.id,
    )
    return {
        "message": message,
        "run_id": run.id,
        "provider_id": outcome.provider_id,
        "model": outcome.model,
        "answered_message_id": target["id"],
    }
