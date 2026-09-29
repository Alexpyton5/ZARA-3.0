"""Fiacao IPC da memoria compartilhada (peca 4 de "memoria compartilhada").

Liga o SharedMemoryAPI (peca 3) ao despachante do backend: cada tipo de
mensagem 'shared-memory-*' chama a operacao correspondente da API e
devolve o resultado pela via normal (send_response / send_error, erro
sempre em portugues).

O ipc_handlers.py NAO precisa de metodos novos: ele importa
build_shared_memory_handlers(self) e mistura o resultado no handler_map
local de handle_message. Cada rota e uma funcao (owner, msg) - o owner e
quem sabe responder (o IPCHandler de verdade ou um duplo de teste).

Como a API acha as fontes no app de verdade:
- fonte 'zara': owner.conversation_history.list_recent (o fio unificado);
- fonte 'lab': owner._shared_memory_lab_memory, se o runtime injetou o
  LabMemory do Lab (senao, a API usa um LabMemory novo - vazio, honesto).
Testes injetam a propria API em owner._shared_memory_api.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Mapping

try:  # dentro do app (pacote core.*)
    from core.shared_memory_api import SharedMemoryAPI, SharedMemoryAPIError
except ImportError:  # teste flat
    from shared_memory_api import SharedMemoryAPI, SharedMemoryAPIError

_ZARA_TURNS_LIMIT = 200


def _api_of(owner) -> SharedMemoryAPI:
    """A API da memoria compartilhada do dono; cria preguiçosamente e
    guarda no owner.

    Liga as fontes reais do app quando existirem: o fio unificado vem de
    owner.conversation_history; o LabMemory do Lab vem de
    owner._shared_memory_lab_memory (injetado pelo runtime).
    """
    api = getattr(owner, "_shared_memory_api", None)
    if api is not None:
        return api
    zara_turns = None
    history = getattr(owner, "conversation_history", None)
    list_recent = getattr(history, "list_recent", None)
    if callable(list_recent):
        zara_turns = lambda: list_recent(_ZARA_TURNS_LIMIT)  # noqa: E731
    api = SharedMemoryAPI(
        lab_memory=getattr(owner, "_shared_memory_lab_memory", None),
        zara_turns=zara_turns,
    )
    try:
        owner._shared_memory_api = api
    except AttributeError:
        pass
    return api


def _payload(msg) -> Mapping[str, Any]:
    payload = getattr(msg, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


async def shared_memory_read(owner, msg) -> None:
    spec_data = _payload(msg).get("spec")
    if not isinstance(spec_data, Mapping):
        await owner.send_error(msg, "spec da visao ausente ou invalida")
        return
    try:
        # list_recent bate no SQLite: nao trava o loop do backend.
        result = await asyncio.to_thread(_api_of(owner).read_view, spec_data)
    except SharedMemoryAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def shared_memory_validate(owner, msg) -> None:
    spec_data = _payload(msg).get("spec")
    if not isinstance(spec_data, Mapping):
        await owner.send_error(msg, "spec da visao ausente ou invalida")
        return
    try:
        result = _api_of(owner).read_spec(spec_data)
    except SharedMemoryAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def shared_memory_describe(owner, msg) -> None:
    await owner.send_response(msg.request_id, SharedMemoryAPI.describe())


SHARED_MEMORY_ROUTES: dict[str, Callable[..., Awaitable[None]]] = {
    "shared-memory-read": shared_memory_read,
    "shared-memory-validate": shared_memory_validate,
    "shared-memory-describe": shared_memory_describe,
}


def _bind(owner, fn: Callable[..., Awaitable[None]]):
    async def bound(msg):
        return await fn(owner, msg)

    return bound


def build_shared_memory_handlers(owner) -> dict[str, Callable[..., Awaitable[None]]]:
    """Liga cada rota 'shared-memory-*' ao dono: {tipo: coroutine(msg)}.

    O despachante faz handler_map.update(build_shared_memory_handlers(self)).
    """
    return {msg_type: _bind(owner, fn) for msg_type, fn in SHARED_MEMORY_ROUTES.items()}
