"""Runner standalone do portão Telegram do Lab — uso manual/diagnóstico.

ATUALIZADO (ZARA-TELEGRAM-LAB-BRIDGE-001): a ZARA de Electron já sobe com este
portão embutido — `core.telegram_ponte.PonteTelegram` chama
`TelegramLabGate.handle_message(...)` como biblioteca, sem laço próprio, então
SIM/NÃO/RESTAURAR/VOLTAR do dono já funcionam com a ZARA aberta, sem rodar
nada à mão. Este script continua existindo só para diagnóstico manual — por
exemplo, testar o gate com a ZARA fechada.

O que é isto
------------
Sobe `core.lab_v1.telegram_gate.TelegramLabGate` escutando o MESMO bot/token de
sempre (`config/api_keys.json::telegram_bot_token`), mas com um escopo estreito
e diferente da ponte geral (`core.telegram_ponte.PonteTelegram` /
`tools/zara_telegram_bot.py`): só entende SIM / NÃO / RESTAURAR / VOLTAR sobre
uma atualização candidata do Lab, e qualquer outra mensagem vira uma resposta de
estado ("tudo certo por aqui" / "tem atualização esperando").

Como rodar
----------
    .venv\\Scripts\\python.exe tools\\run_lab_telegram_gate.py

Ctrl+C encerra.

AVISO OPERACIONAL — NÃO rode isto com a ZARA de Electron aberta, nem junto de
`tools/zara_telegram_bot.py`. A API do Telegram só sustenta UM consumidor de
`getUpdates` por vez sobre o mesmo token; rodar este script em paralelo com a
ZARA (que já embute o gate) faz os dois brigarem pela mesma fila e um deles
passa a perder mensagem.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.lab_v1.release import ReleaseQueue  # noqa: E402
from core.lab_v1.store import LabStore  # noqa: E402
from core.lab_v1.telegram_gate import (  # noqa: E402
    HttpTelegramTransport,
    TelegramLabGate,
    default_ready_candidate,
)
from core.paths import api_keys_path, data_dir  # noqa: E402


def _load_token() -> str:
    import json

    path = api_keys_path()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    return str(data.get("telegram_bot_token") or "").strip()


def main() -> int:
    print(
        "[LAB-TELEGRAM] AVISO: a ZARA (Electron) ja sobe com este portao embutido em "
        "core/telegram_ponte.py (ZARA-TELEGRAM-LAB-BRIDGE-001). NAO rode este script "
        "com a ZARA aberta ao mesmo tempo — os dois vao brigar pelo mesmo getUpdates "
        "e mensagens vao comecar a sumir de forma intermitente. Use isto só para "
        "diagnostico manual, com a ZARA fechada.",
        flush=True,
    )
    token = _load_token()
    if not token:
        print("[LAB-TELEGRAM] Sem token em config/api_keys.json::telegram_bot_token", flush=True)
        return 2

    transport = HttpTelegramTransport(token)
    me = transport.get_me()
    if not me:
        print("[LAB-TELEGRAM] Token recusado pelo Telegram; portao nao ligou.", flush=True)
        return 3
    print(f"[LAB-TELEGRAM] Ligado como @{me.get('username', '?')}.", flush=True)

    store = LabStore()
    store.initialize()

    state_path = data_dir() / "lab" / "telegram_gate_state.json"
    gate = TelegramLabGate(
        transport=transport,
        state_path=state_path,
        api_keys_path=api_keys_path(),
        candidate_source=lambda: default_ready_candidate(store),
        queue_factory=lambda: ReleaseQueue(store),
    )
    print(f"[LAB-TELEGRAM] Estado em {state_path}. Aguardando mensagens... (Ctrl+C para parar)", flush=True)
    try:
        gate.run_forever()
    except (KeyboardInterrupt, SystemExit):
        print("\n[LAB-TELEGRAM] Encerrando...", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
