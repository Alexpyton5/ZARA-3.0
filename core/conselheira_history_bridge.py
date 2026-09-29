"""Ponte Conselheira -> historico unificado (CONVERSA-UNICA, passo 2).

A Conselheira (ponte Gmail da zoe) tem fio proprio no backend
(`lab_ceo_gmail_bridge.ZoeChatRelay`). A meta "uma conversa so" pede que
o Alex veja TUDO num fio so: o que ele digitou, o que falou por voz,
o que a zoe respondeu pela ponte e o que o Lab decidiu (como resumo).

Este modulo e a peca de traducao: recebe o payload do `send_message`
e o resultado do `sync()` do relay e devolve turnos prontos para
`ConversationHistory.append(role, content, engine=...)`.

Regras:
- engine SEMPRE "ponte-zoe" (origem honesta no fio).
- `send_message` -> ("user", texto do Alex).
- `sync()["replies"]` -> um ("assistant", resposta) por resposta NOVA.
  O `sync_inbox` do relay ja e idempotente (visto por message_id do
  Gmail, persistido em disco): `replies` so traz o que acabou de chegar,
  entao espelhar a lista e seguro contra duplicata, inclusive apos reboot.
- Nada que nao seja dict/str valido vira turno (lixo nao entra no fio).
- Logica pura, stdlib, zero custo/rede/quota.
"""

from __future__ import annotations

from typing import Any

ENGINE_PONTE_ZOE = "ponte-zoe"


def outgoing_turn(send_payload: Any) -> tuple[str, str, str] | None:
    """Turno do Alex a partir do retorno de `relay.send_message()`.

    Devolve ("user", texto, "ponte-zoe") ou None se o payload nao
    tiver texto valido.
    """
    if not isinstance(send_payload, dict):
        return None
    text = str(send_payload.get("text") or "").strip()
    if not text:
        return None
    return ("user", text, ENGINE_PONTE_ZOE)


def incoming_turns(sync_result: Any) -> list[tuple[str, str, str]]:
    """Turnos da zoe a partir do retorno de `relay.sync()`.

    Cada resposta nova vira ("assistant", resposta, "ponte-zoe").
    Lista vazia (ou resultado malformado) -> nenhum turno.
    """
    if not isinstance(sync_result, dict):
        return []
    replies = sync_result.get("replies")
    if not isinstance(replies, list):
        return []
    turns: list[tuple[str, str, str]] = []
    for item in replies:
        if not isinstance(item, dict):
            continue
        reply = str(item.get("reply") or "").strip()
        if not reply:
            continue
        turns.append(("assistant", reply, ENGINE_PONTE_ZOE))
    return turns
