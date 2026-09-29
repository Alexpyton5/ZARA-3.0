"""ZARA-AUTONOMIA-001 — Política de autonomia total (MISSÃO GIGANTE 3, FRENTE B).

Diretriz do Alex: "sim sempre". A ZARA executa o que ele pede SEM pedir
confirmação. A confirmação virou exceção (modo legado opt-out), não regra.

INVENTÁRIO B1 — pontos onde o app pedia confirmação antes de agir:
  1. core/action_registry.py::_check_action_gates
     - HIGH risk  -> desafio one-shot (ConfirmationBroker) — B2: ação direta
       quando a autonomia está ligada; o desafio continua existindo no modo
       legado ("perguntar").
     - MEDIUM risk -> confirm=true ou política medium_risk_open — B2: ação
       direta quando a autonomia está ligada.
     - PC_CONTROL capability -> trava do Supercérebro (chave manual ou grant
       via WhatsApp), FAIL-CLOSED. NÃO é confirmação: é trava de segurança
       permanente. Mantida sempre, em qualquer modo.
  2. core/lab_mission.py::set_milestone_state — marcar marco da Missão como
     "concluído" exige evidência + confirmação explícita do Alex. Governança
     interna do próprio projeto (não é UX do app): MANTIDA.
  3. core/macro_engine.py — sugestão de commit nunca commita sozinha: MANTIDA.
  4. core/ipc_handlers.py — perguntas conversacionais ("Diga sim ou não"):
     continuam como fallback de conversa, mas o motor de ações não depende
     mais delas no modo autônomo.

O QUE A AUTONOMIA NUNCA FAZ (fronteira rígida, por construção):
  - Dinheiro/pagamento/cartão: core/money_boundary.py — BLOQUEADO sempre,
    nem com confirmação, nem no modo autônomo, nem via desafio legado.
  - Controle do PC sem a trava do Supercérebro: continua negado (fail-closed).

Toda ação executada no modo autônomo é registrada em core/audit_log.py
com autonomous=1 e o motivo (B3).
"""
from __future__ import annotations

import os

#: Nome da variável de ambiente que controla o modo.
AUTONOMY_ENV_VAR = "ZARA_AUTONOMY"

#: Valor padrão: autonomia total ligada (diretriz do Alex).
DEFAULT_MODE = "sim-sempre"

#: Valores que DESLIGAM a autonomia (modo legado "perguntar").
_LEGACY_VALUES = {"perguntar", "ask", "confirm", "0", "off", "false", "no"}


def autonomy_mode() -> str:
    """Retorna o modo atual: 'sim-sempre' (padrão) ou o valor configurado."""
    raw = str(os.environ.get(AUTONOMY_ENV_VAR, "") or "").strip().lower()
    return raw or DEFAULT_MODE


def autonomy_enabled() -> bool:
    """True quando a ZARA age direto sem pedir confirmação (padrão)."""
    return autonomy_mode() not in _LEGACY_VALUES


def should_act_directly(risk: str) -> bool:
    """Diz se uma ação deste risco executa direto, sem desafio/confirmação.

    No modo autônomo: qualquer risco (LOW/MEDIUM/HIGH) executa direto.
    A fronteira de dinheiro e a trava do Supercérebro são aplicadas ANTES,
    em outro ponto do gate — este módulo nunca as afrouxa.
    """
    return autonomy_enabled()
