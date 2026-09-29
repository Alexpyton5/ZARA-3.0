# -*- coding: utf-8 -*-
"""GAP-ZERO frente 3 — a verdade dos canais de comunicacao da ZARA.

Para cada canal (WhatsApp, Telegram, Instagram, Gmail) existem DOIS caminhos
prontos, e a escolha entre eles e do Alex (PENDENTE — nada aqui decide por ele):

(a) LIGAR DE VERDADE — a flag ``comms.<canal>.mode = "real"`` libera a contagem
    real. O numero SO aparece se um provedor real estiver REGISTRADO em runtime
    (ex.: Gmail via CeoMailAdapter, quando a frente 4 ligar o Gmail real;
    Telegram via PonteTelegram.configurado). Sem provedor registrado o modo
    "real" e FAIL-CLOSED: mostra "—" e NUNCA inventa numero.

(b) ATALHO HONESTO — o padrao de hoje (e o que fica valendo ate o Alex decidir):
    o botao abre o app/site real e nenhuma contagem e exibida. A interface ja
    diz isso ("contagem de mensagens nao conectada").

Regras duras deste modulo:
- numero exibido so existe se veio de um provedor real registrado;
- provedor que falha/explode = indisponivel (fail-closed), nunca numero inventado;
- sem API paga, nunca; sem bypass de trava de seguranca.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.paths import user_data_dir

CHANNELS: Tuple[str, ...] = ("whatsapp", "telegram", "instagram", "gmail")

CHANNEL_DISPLAY: Dict[str, str] = {
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "instagram": "Instagram",
    "gmail": "Gmail",
}

# (a) ligar de verdade | (b) atalho honesto. Padrao: (b) — o que vale hoje.
MODES: Tuple[str, ...] = ("atalho", "real")
DEFAULT_MODE = "atalho"


def config_flag_name(channel: str) -> str:
    """Nome da flag de config por ponto, ex.: 'comms.whatsapp.mode'."""
    return f"comms.{channel}.mode"


def comms_truth_config_path() -> Path:
    """Onde as flags moram no disco (padrao do app: config do usuario)."""
    return user_data_dir() / "config" / "comms_channel_mode.json"


def _canonical_default_json() -> bytes:
    data = {channel: DEFAULT_MODE for channel in CHANNELS}
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


#: Bytes canonicos do padrao "tudo atalho" — o que vale ate o Alex decidir.
DEFAULT_CONFIG_JSON: bytes = _canonical_default_json()

#: SHA256 dos bytes acima. Qualquer mudanca acidental no padrao quebra o teste.
GOLDEN_DEFAULT_SHA256 = "d7db6843ad057f0c10e5668d0ecf9e17a1df95ceac88fe9296ec57cb32555713"


def default_modes() -> Dict[str, str]:
    """Padrao de fabrica: todo canal e atalho honesto."""
    return {channel: DEFAULT_MODE for channel in CHANNELS}


def load_modes(path: "str | Path | None" = None) -> Dict[str, str]:
    """Le as flags do disco; arquivo ausente/invalido = padrao (atalho)."""
    modes = default_modes()
    target = Path(path) if path else comms_truth_config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return modes
    if isinstance(data, dict):
        for channel in CHANNELS:
            value = data.get(channel)
            if value in MODES:
                modes[channel] = value
    return modes


def save_mode(channel: str, mode: str, path: "str | Path | None" = None) -> str:
    """Troca a flag de UM canal. Canal/modo invalido = ValueError."""
    if channel not in CHANNELS:
        raise ValueError(f"canal desconhecido: {channel!r} (use: {', '.join(CHANNELS)})")
    if mode not in MODES:
        raise ValueError(f"modo desconhecido: {mode!r} (use: {', '.join(MODES)})")
    target = Path(path) if path else comms_truth_config_path()
    modes = load_modes(target)
    modes[channel] = mode
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="comms-truth-", suffix=".tmp", dir=str(target.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(modes, stream, sort_keys=True, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return mode


# ---------------------------------------------------------------------------
# Provedores reais (caminho "ligar de verdade"). Contrato do provedor:
#   fn() -> {"unread": int >= 0, "source": str} | None
# None (ou excecao) = indisponivel -> fail-closed, mostra "—".
# ---------------------------------------------------------------------------

_RealProvider = Callable[[], Optional[Dict[str, Any]]]
_REAL_PROVIDERS: Dict[str, _RealProvider] = {}


def register_real_provider(channel: str, provider: _RealProvider) -> None:
    """Liga um canal a fonte real de contagem (chamado quando a integracao
    existir de verdade — ex.: frente 4 para o Gmail)."""
    if channel not in CHANNELS:
        raise ValueError(f"canal desconhecido: {channel!r}")
    _REAL_PROVIDERS[channel] = provider


def unregister_real_provider(channel: str) -> None:
    _REAL_PROVIDERS.pop(channel, None)


def clear_real_providers() -> None:
    _REAL_PROVIDERS.clear()


def has_real_provider(channel: str) -> bool:
    return channel in _REAL_PROVIDERS


def honest_label(channel: str) -> str:
    """Rotulo honesto do caminho (b): atalho, sem numero."""
    name = CHANNEL_DISPLAY.get(channel, channel)
    return f"atalho — abre o {name}; contagem de mensagens nao conectada"


def pending_decision_text(channel: str) -> str:
    name = CHANNEL_DISPLAY.get(channel, channel)
    return (
        f"PENDENTE DO ALEX: ligar a contagem real do {name} "
        f"(flag {config_flag_name(channel)}=real + provedor real registrado) "
        f"ou manter como atalho honesto (padrao atual)."
    )


def resolve_channel(
    channel: str,
    modes: Optional[Dict[str, str]] = None,
    path: "str | Path | None" = None,
) -> Dict[str, Any]:
    """Verdade atual de um canal: modo, se ha contagem, e de onde ela veio.

    Nunca inventa numero: sem provedor real registrado, ``unread`` e None e
    ``counts_available`` e False — mesmo com a flag em "real" (fail-closed).
    """
    if channel not in CHANNELS:
        raise ValueError(f"canal desconhecido: {channel!r}")
    current = dict(modes) if modes else load_modes(path)
    mode = current.get(channel, DEFAULT_MODE)
    if mode not in MODES:
        mode = DEFAULT_MODE
    unread: Optional[int] = None
    source: Optional[str] = None
    provider = _REAL_PROVIDERS.get(channel)
    if mode == "real" and provider is not None:
        try:
            result = provider()
        except Exception:
            result = None
        if isinstance(result, dict):
            count = result.get("unread")
            origin = result.get("source")
            if isinstance(count, int) and count >= 0 and isinstance(origin, str) and origin:
                unread = count
                source = origin
    return {
        "channel": channel,
        "display_name": CHANNEL_DISPLAY[channel],
        "mode": mode,
        "counts_available": unread is not None,
        "unread": unread,
        "source": source,
        "honest_label": honest_label(channel),
        "pending_decision": pending_decision_text(channel),
    }


# ---------------------------------------------------------------------------
# Mapa dos pontos (o que finge ser o que, onde). Linha = evidencia na epoca
# do mapeamento (28/09/2026); o teste valida a estrutura, nao o numero exato.
# ---------------------------------------------------------------------------

SURFACES: List[Dict[str, str]] = [
    {
        "key": "comms.whatsapp",
        "label": "Card Comunicacoes — WhatsApp",
        "file": "frontend/src/renderer/components/zara-home/CommunicationsCard.tsx",
        "line": "51-79",
        "finge_ser": "badge do app com contagem de mensagens",
        "status": "atalho",
        "evidencia": "mostra '—' + title 'contagem de mensagens nao conectada' (comentario L46-50)",
        "decisao": "PENDENTE DO ALEX: ligar contagem real (provedor real ainda nao existe) ou manter atalho",
    },
    {
        "key": "comms.telegram",
        "label": "Card Comunicacoes — Telegram",
        "file": "frontend/src/renderer/components/zara-home/CommunicationsCard.tsx",
        "line": "51-79",
        "finge_ser": "badge do app com contagem de mensagens",
        "status": "atalho",
        "evidencia": "mostra '—' + title 'contagem de mensagens nao conectada'",
        "decisao": "PENDENTE DO ALEX: ligar contagem real (via PonteTelegram.configurado) ou manter atalho",
    },
    {
        "key": "comms.instagram",
        "label": "Card Comunicacoes — Instagram",
        "file": "frontend/src/renderer/components/zara-home/CommunicationsCard.tsx",
        "line": "51-79",
        "finge_ser": "badge do app com contagem de mensagens",
        "status": "atalho",
        "evidencia": "mostra '—' + title 'contagem de mensagens nao conectada'",
        "decisao": "PENDENTE DO ALEX: ligar contagem real (sem integracao oficial gratis) ou manter atalho",
    },
    {
        "key": "comms.gmail",
        "label": "Card Comunicacoes — Gmail",
        "file": "frontend/src/renderer/components/zara-home/CommunicationsCard.tsx",
        "line": "51-79",
        "finge_ser": "badge do app com contagem de mensagens",
        "status": "atalho",
        "evidencia": "mostra '—' + title 'contagem de mensagens nao conectada'",
        "decisao": "PENDENTE DO ALEX: ligar de verdade quando a frente 4 ligar o CeoMailAdapter ao Gmail real, ou manter atalho",
    },
    {
        "key": "drawer.comms",
        "label": "Gaveta — secao Comunicacoes",
        "file": "frontend/src/renderer/components/zara-home/HomeDrawer.tsx",
        "line": "317",
        "finge_ser": "lista de canais com contagens",
        "status": "atalho",
        "evidencia": "texto: 'As contagens aparecerao quando houver uma integracao conectada.'",
        "decisao": "PENDENTE DO ALEX: mesma decisao dos 4 canais acima",
    },
    {
        "key": "main.desktopLinks",
        "label": "Atalhos de desktop (main.ts)",
        "file": "frontend/src/main.ts",
        "line": "526-529",
        "finge_ser": "apps integrados (whatsapp/telegram/instagram/gmail)",
        "status": "atalho",
        "evidencia": "sao URLs abertas via desktop.openExternal; nenhuma contagem existe no codigo",
        "decisao": "PENDENTE DO ALEX: mesma decisao dos 4 canais acima",
    },
    {
        "key": "backend.gmail_relay",
        "label": "Ponte da Conselheira — Gmail",
        "file": "core/ipc_handlers.py",
        "line": "655-658",
        "finge_ser": "Gmail real da ZARA ligado",
        "status": "atalho",
        "evidencia": "TODO honesto: LoggingStubAdapter (só loga local, sem rede); CeoMailAdapter real = frente 4",
        "decisao": "PENDENTE DO ALEX (frente 4): ligar o CeoMailAdapter ao Gmail real",
    },
    {
        "key": "demo.titanium_bundle",
        "label": "Bundle demo zara-titanium-emerald",
        "file": "frontend/public/zara-titanium-emerald/",
        "line": "-",
        "finge_ser": "interface do app com dados de demonstracao",
        "status": "demo",
        "evidencia": "bundle parado em frontend/public; NAO e carregado pela interface ativa (ja registrado em core/truth_registry.py)",
        "decisao": "PENDENTE DO ALEX: remover do pacote ou rotular 'DEMONSTRACAO — dados ficticios'",
    },
]

_SURFACE_REQUIRED = ("key", "label", "file", "line", "finge_ser", "status", "evidencia", "decisao")
_SURFACE_STATUS = ("atalho", "real", "demo")


def assert_all_surfaces_honest(surfaces: Optional[List[Dict[str, str]]] = None) -> List[str]:
    """Trava da frente 3: nenhuma superficie pode exibir numero sem fonte real.

    - status "atalho"/"demo": sempre OK (nao exibem numero);
    - status "real": so OK se houver provedor real registrado para o canal.
    Devolve as chaves verificadas; falha com AssertionError caso contrario.
    """
    checked: List[str] = []
    for surface in surfaces if surfaces is not None else SURFACES:
        for field in _SURFACE_REQUIRED:
            if not surface.get(field):
                raise AssertionError(f"superficie sem campo {field!r}: {surface.get('key')}")
        if surface["status"] not in _SURFACE_STATUS:
            raise AssertionError(f"status invalido em {surface['key']}: {surface['status']!r}")
        if surface["status"] == "real":
            channel = surface["key"].split(".")[-1]
            if channel not in CHANNELS or not has_real_provider(channel):
                raise AssertionError(
                    f"TRAVA FRENTE-3 FALHOU: {surface['key']} diz 'real' sem provedor real registrado"
                )
        checked.append(surface["key"])
    return checked


def pending_decisions() -> List[Tuple[str, str]]:
    """Tudo que so o Alex pode decidir (para o documento da frente)."""
    return [(s["key"], s["decisao"]) for s in SURFACES]


def honest_summary() -> Dict[str, List[str]]:
    """Lista publicada: o que esta ligado de verdade vs. atalho honesto."""
    out = {"ligado": [], "atalho_honesto": [], "demo": []}
    for surface in SURFACES:
        entry = f"{surface['label']} — {surface['evidencia']}"
        if surface["status"] == "real":
            out["ligado"].append(entry)
        elif surface["status"] == "demo":
            out["demo"].append(entry)
        else:
            out["atalho_honesto"].append(entry)
    return out


def golden_default_sha256() -> str:
    """SHA256 dos bytes canonicos do padrao (tudo atalho)."""
    return hashlib.sha256(DEFAULT_CONFIG_JSON).hexdigest()
