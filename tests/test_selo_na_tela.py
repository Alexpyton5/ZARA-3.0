"""ZARA-SELO-NA-TELA-001 — a tela precisa saber o que foi verificado.

A interface nova mostra, ao lado de cada turno, se aquilo aconteceu de verdade.
É a peça central do desenho: o que separa a ZARA de qualquer outro assistente.

Só que ninguém mandava essa informação para ela. O Codex notou e relatou:

    "as mensagens não carregam selo estruturado; portanto aparecem
     corretamente como NÃO VERIFICADO"

Ou seja: a tela inteira ficaria cinza, e a feature mais importante do desenho
pareceria quebrada — inclusive nas ações que a ZARA prova de verdade, como
volume e brilho, que ela relê do Windows depois de mexer.
"""
from __future__ import annotations

from core.action_registry import ActionResult
from core.ipc_handlers import IPCHandler


def _handler(resultado):
    h = IPCHandler.__new__(IPCHandler)
    h._ultimo_resultado_de_acao = resultado
    return h


def test_acao_provada_leva_selo_de_verificado():
    h = _handler(ActionResult(success=True, output="Volume em 60%.", verificado=True))

    assert h._selo_do_ultimo_resultado() == "verificado"


def test_acao_sem_prova_leva_selo_cinza():
    h = _handler(ActionResult(success=True, output="Mandei.", verificado=False))

    assert h._selo_do_ultimo_resultado() == "nao-verificado"


def test_falha_leva_selo_de_falha():
    h = _handler(ActionResult(success=False, error="não achei o botão"))

    assert h._selo_do_ultimo_resultado() == "nao-consegui"


def test_conversa_nao_ganha_selo_de_duvida():
    """Papo não tem o que verificar.

    Marcar conversa como "não verificado" inventaria uma dúvida que não existe —
    e o selo perderia o sentido justamente por aparecer em tudo.
    """
    h = _handler(None)

    assert h._selo_do_ultimo_resultado() == "conversa"


def test_o_selo_nunca_mente_para_o_lado_bom():
    """Na dúvida entre verificado e não verificado, nunca escolher verificado."""
    for resultado in (
        ActionResult(success=True, output="x", verificado=False),
        ActionResult(success=False, error="x"),
        None,
    ):
        assert _handler(resultado)._selo_do_ultimo_resultado() != "verificado"


# ---------- auditoria do Codex, achado 3 ----------
#
# O selo so saia pelo caminho de VOZ. Alex digita "diminua o volume", a mesma
# acao executa pelo mesmo executor, e a tela ficava sem saber se aquilo tinha
# sido verificado — mostrando cinza para uma acao que a ZARA provou.
#
# Voz e texto compartilham a cadeia inteira; e invariante do projeto. Passaram
# a compartilhar a prova tambem.

import inspect


def test_o_caminho_de_texto_tambem_manda_o_selo():
    from core import ipc_handlers

    fonte = inspect.getsource(ipc_handlers.IPCHandler.handle_send_message)
    assert "_selo_do_ultimo_resultado" in fonte, (
        "o comando digitado executa a mesma acao e precisa levar a mesma prova"
    )


def test_voz_e_texto_usam_a_mesma_funcao_de_selo():
    """Duas fontes de verdade para o mesmo selo divergiriam com o tempo."""
    from core import ipc_handlers

    fonte = inspect.getsource(ipc_handlers)
    assert fonte.count("def _selo_do_ultimo_resultado") == 1
