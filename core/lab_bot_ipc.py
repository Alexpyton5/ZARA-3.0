"""Fiacao IPC dos bots customizaveis (peca 4 de "bots faceis").

Liga o BotAPI (peca 3) ao despachante do backend: cada tipo de mensagem
'lab-bot-*' chama a operacao correspondente da API e devolve o resultado
pela via normal (send_response / send_error, erro sempre em portugues).

O ipc_handlers.py NAO precisa de metodos novos: ele importa
build_lab_bot_handlers(self) e mistura o resultado no handler_map local
de handle_message. Cada rota e uma funcao (owner, msg) — o owner e quem
sabe responder (o IPCHandler de verdade ou um duplo de teste).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

try:  # dentro do app (pacote core.*)
    from core.lab_bot_api import BotAPI, BotAPIError
except ImportError:  # teste flat
    from lab_bot_api import BotAPI, BotAPIError


def _api_of(owner) -> BotAPI:
    """A API de bots do dono; cria preguiçosamente e guarda no owner.

    Testes injetam a propria API em owner._lab_bot_api (com stores em tmp).
    """
    api = getattr(owner, "_lab_bot_api", None)
    if api is None:
        api = BotAPI()
        try:
            owner._lab_bot_api = api
        except AttributeError:
            pass
    return api


def _payload(msg) -> Mapping[str, Any]:
    payload = getattr(msg, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def _bot_id_of(msg) -> str:
    return str(_payload(msg).get("bot_id") or "").strip()


async def lab_bot_create(owner, msg) -> None:
    data = _payload(msg)
    if not data:
        await owner.send_error(msg, "dados do bot ausentes")
        return
    try:
        result = _api_of(owner).create_bot(data)
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_get(owner, msg) -> None:
    bot_id = _bot_id_of(msg)
    if not bot_id:
        await owner.send_error(msg, "id do bot ausente")
        return
    try:
        result = _api_of(owner).get_bot(bot_id)
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_list(owner, msg) -> None:
    try:
        result = _api_of(owner).list_bots()
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_update(owner, msg) -> None:
    bot_id = _bot_id_of(msg)
    patch = _payload(msg).get("patch")
    if not bot_id:
        await owner.send_error(msg, "id do bot ausente")
        return
    if not isinstance(patch, Mapping):
        await owner.send_error(msg, "patch ausente ou invalido")
        return
    try:
        result = _api_of(owner).update_bot(bot_id, patch)
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_delete(owner, msg) -> None:
    bot_id = _bot_id_of(msg)
    if not bot_id:
        await owner.send_error(msg, "id do bot ausente")
        return
    try:
        result = _api_of(owner).delete_bot(bot_id)
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_sync(owner, msg) -> None:
    try:
        result = _api_of(owner).sync_lab()
    except BotAPIError as exc:
        await owner.send_error(msg, str(exc))
        return
    await owner.send_response(msg.request_id, result)


async def lab_bot_describe(owner, msg) -> None:
    await owner.send_response(msg.request_id, BotAPI.describe())


LAB_BOT_ROUTES: dict[str, Callable[..., Awaitable[None]]] = {
    "lab-bot-create": lab_bot_create,
    "lab-bot-get": lab_bot_get,
    "lab-bot-list": lab_bot_list,
    "lab-bot-update": lab_bot_update,
    "lab-bot-delete": lab_bot_delete,
    "lab-bot-sync": lab_bot_sync,
    "lab-bot-describe": lab_bot_describe,
}


def _bind(owner, fn: Callable[..., Awaitable[None]]):
    async def bound(msg):
        return await fn(owner, msg)

    return bound


def build_lab_bot_handlers(owner) -> dict[str, Callable[..., Awaitable[None]]]:
    """Liga cada rota 'lab-bot-*' ao dono: {tipo: coroutine(msg)}.

    O despachante faz handler_map.update(build_lab_bot_handlers(self)).
    """
    return {msg_type: _bind(owner, fn) for msg_type, fn in LAB_BOT_ROUTES.items()}
