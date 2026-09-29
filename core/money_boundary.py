"""ZARA-FRONTEIRA-DINHEIRO-001 — Fronteira rígida de dinheiro (FRENTE B2).

Regra do Alex: SEM dinheiro (sem cartão, sem pagamento, sem acesso a grana).
Esta fronteira é ESTRUTURAL: o bloqueio acontece no gate do registro de
ações (core/action_registry.py::_check_action_gates), ANTES de qualquer
ação rodar, e não pode ser contornado por:
  - confirmação do usuário (nem o desafio one-shot legado),
  - modo autônomo ("sim sempre"),
  - política medium_risk_open,
  - prova de confirmação vinda do IPC.

LISTA EXPLÍCITA DO QUE NUNCA EXECUTA:
  Ações cujo nome indica operação financeira:
    pagamento, pagar, checkout, compra/comprar, pix, boleto, fatura,
    cartão/cartao, crédito/credito, débito/debito, billing/cobrança,
    transferência/transferencia, depósito/deposito, saque, empréstimo,
    financiamento, assinatura paga, recarga, stripe, mercadopago,
    pagseguro, paypal, "wallet"/carteira digital, extrato bancário,
    saldo de conta, investimento, corretora, "order"/pedido de compra.
  Parâmetros que indicam operação financeira:
    número de cartão (16 dígitos), "chave pix", "qr code pix", "copia e
    cola", dados de checkout, URLs de gateways de pagamento
    (stripe.com, mercadopago.com, pagseguro.uol, paypal.com),
    "cvv", "validade do cartão", "titular do cartão".
  O bloqueio também vale para ações GENÉRICAS (terminal, browser, web)
  cujos parâmetros carreguem esses sinais: um `terminal` tentando abrir
  uma página de checkout é bloqueado igual.

O bloqueio é conservador de propósito: melhor um falso positivo (ação
legítima bloqueada, que o Alex pode renomear/reformular) do que dinheiro
movido sem ele mandar. Ação bloqueada retorna erro e é registrada no
audit log com outcome="blocked" e why="bloqueio:dinheiro".
"""
from __future__ import annotations

import re
from typing import Any, Mapping

#: Padrões sobre o NOME da ação (case-insensitive).
MONEY_ACTION_NAME_PATTERNS: tuple[str, ...] = (
    r"pagament",
    r"\bpag(ar|ue|o)?\b",
    r"checkout",
    r"compr",
    r"\bpix\b",
    r"boleto",
    r"fatura",
    r"cart[aã]o",
    r"cr[eé]dito",
    r"d[eé]bito",
    r"billing",
    r"cobran[cç]a",
    r"transfer[eê]ncia",
    r"dep[oó]sito",
    r"\bsaque\b",
    r"empr[eé]stimo",
    r"financiamento",
    r"assinatura",
    r"recarga",
    r"stripe",
    r"mercadopago",
    r"pagseguro",
    r"paypal",
    r"wallet",
    r"carteira",
    r"extrato",
    r"\bsaldo\b",
    r"investimento",
    r"corretora",
    r"\border\b",
    r"pedido",
)

#: Padrões sobre os PARÂMETROS da ação (qualquer ação, inclusive genéricas).
MONEY_PARAM_PATTERNS: tuple[str, ...] = (
    r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # número de cartão
    r"\b\d{3,4}\b.*\bcvv\b|\bcvv\b.*\b\d{3,4}\b",  # cvv
    r"chave[\s_-]?pix",
    r"qr[\s_-]?code[\s_-]?pix",
    r"copia[\s_-]?e[\s_-]?cola",
    r"\bpix\b",
    r"checkout",
    r"pagamento",
    r"stripe\.com",
    r"mercadopago\.com",
    r"pagseguro",
    r"paypal\.com",
    r"cart[aã]o",
    r"titular",
    r"validade",
    r"boleto",
    r"fatura",
)

_MONEY_NAME_RES = tuple(re.compile(p, re.IGNORECASE) for p in MONEY_ACTION_NAME_PATTERNS)
_MONEY_PARAM_RES = tuple(re.compile(p, re.IGNORECASE) for p in MONEY_PARAM_PATTERNS)


def _params_text(params: Mapping[str, Any] | None) -> str:
    if not params:
        return ""
    parts: list[str] = []
    for key, value in params.items():
        if key == "_zara_confirmation_proof":
            continue
        parts.append(str(key))
        if isinstance(value, (dict, list, tuple, set)):
            continue  # não serializa estruturas: evita falso positivo e vazamento
        text = str(value)
        if len(text) > 2000:
            text = text[:2000]
        parts.append(text)
    return "\n".join(parts)


def is_money_action(action_name: str, params: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    """Diz se a ação envolve dinheiro e deve ser BLOQUEADA por construção.

    Retorna (bloqueado, motivo). O motivo é curto e nunca contém o valor
    do parâmetro (sem vazar dado sensível no log).
    """
    name = str(action_name or "")
    for pattern in _MONEY_NAME_RES:
        if pattern.search(name):
            return True, f"nome-da-acao-indica-dinheiro:{pattern.pattern[:32]}"
    text = _params_text(params)
    if text:
        for pattern in _MONEY_PARAM_RES:
            if pattern.search(text):
                return True, f"parametro-indica-dinheiro:{pattern.pattern[:32]}"
    return False, ""


#: Lista legível da fronteira (para relatórios e para a interface ser honesta).
BLOCKED_BY_CONSTRUCTION: tuple[str, ...] = (
    "pagamentos e checkouts",
    "compras",
    "pix / boletos / faturas",
    "cartões de crédito e débito (números, cvv, validade, titular)",
    "transferências, depósitos e saques",
    "assinaturas e recargas pagas",
    "gateways: stripe, mercadopago, pagseguro, paypal",
    "saldo/extrato/investimentos/corretora",
)
