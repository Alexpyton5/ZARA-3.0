"""ZARA-SILENCIO-001 — Modo silencioso (MISSÃO GIGANTE 3, FRENTE D).

Diretriz do Alex: "trabalha quieto; só avisa quando está PRONTO ou quando
trava de verdade". Silencioso é o PADRÃO; nada de narrar o trabalho.

INVENTÁRIO D1 — o que o app narra/notifica/exibe enquanto trabalha:
  1. Resposta por turno (texto/voz): cada pedido gera UMA resposta final
     (send_event('message') + TTS). É a resposta ao Alex — mantida. É o
     "pronto" (ou a resposta da conversa), não narração intermediária.
  2. Planejador multi-ação (_try_jarvis_multi_action): executa até 5
     cláusulas em silêncio e devolve 1 resposta consolidada. Já silencioso;
     o passo a passo de cada cláusula agora vai para o ops_log (D3).
  3. Eventos state-change (THINKING/STANDBY/LISTENING): estado da interface,
     não narração — mantidos.
  4. Lembretes (reminder-fired): o Alex PEDIU para ser lembrado — exceção
     explícita: notifica. Agora roteado por esta política.
  5. Prints/traces ([VOICE_TRACE], [IPC], ...): já vão para console/log
     interno, nunca para o Alex — mantidos.
  6. Watchdogs (ProactiveMonitor: bateria/disco/CPU/downloads): quando
     ligados, passam por esta política — só criticidade alta notifica.

POLÍTICA D2 — roteamento de eventos:
  notify   -> aparece para o Alex (chat e/ou voz): "pronto", "travei",
              lembrete que ele pediu, alerta crítico.
  log_only -> vai só para o ops_log interno (core/ops_log.py): progresso
              detalhado, telemetria, etapas intermediárias.

Desligar (não recomendado): ZARA_SILENT_MODE=0 — volta a narrar.
"""
from __future__ import annotations

import os

SILENT_ENV_VAR = "ZARA_SILENT_MODE"

#: Tipos de evento que PODEM aparecer para o Alex. Todo o resto é log_only.
NOTIFY_KINDS: frozenset[str] = frozenset({
    "done",        # tarefa pronta
    "stuck",       # travou de verdade e precisa dele
    "reminder",    # lembrete que ele pediu
    "critical",    # alerta crítico do sistema
})

#: Tipos que existem mas nunca notificam (vão para o ops_log).
LOG_ONLY_KINDS: frozenset[str] = frozenset({
    "progress", "step", "info", "debug", "trace", "telemetry",
})


def silent_mode_enabled() -> bool:
    """Modo silencioso ligado por padrão. ZARA_SILENT_MODE=0 desliga."""
    raw = str(os.environ.get(SILENT_ENV_VAR, "") or "").strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    return True


def route(kind: str) -> str:
    """Decide o destino de um evento: 'notify' ou 'log_only'.

    Com o modo silencioso DESLIGADO, tudo vira notify (comportamento
    antigo). Com ele LIGADO (padrão), só os tipos em NOTIFY_KINDS
    aparecem para o Alex.
    """
    normalized = str(kind or "").strip().lower()
    if not silent_mode_enabled():
        return "notify"
    if normalized in NOTIFY_KINDS:
        return "notify"
    return "log_only"


def should_notify(kind: str) -> bool:
    """Atalho: este tipo de evento deve aparecer para o Alex?"""
    return route(kind) == "notify"


def record_progress(source: str, message: str, details=None) -> None:
    """Registra progresso detalhado SÓ no log interno (D3).

    Use durante tarefas longas em vez de mandar mensagens intermediárias.
    """
    from core.ops_log import ops_log

    ops_log().record("progress", source, message, details)
