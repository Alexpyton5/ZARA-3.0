"""ZARA-NAO-VERIFICADO-001 — o terceiro estado, que faltava.

Alex: *"tente deixar ela sem mentiras e sem chutes ou invenções; se não souber,
ela deve ser sempre transparente"*.

E a regra que saiu da pesquisa do design: **ação executada mas não confirmada
nunca aparece como certa**.

Existiam dois estados — deu certo, deu errado — e faltava o mais comum de todos:
*fiz, e não tenho como provar*. Apertar uma tecla num app de terceiro, mandar uma
mensagem, disparar um atalho: nada disso devolve confirmação. Sem ressalva, tudo
isso saía afirmativo, e afirmação sem prova é o falso sucesso que este projeto
inteiro existe para combater.
"""
from __future__ import annotations

import pytest

from core.action_registry import ActionResult
from core.ipc_handlers import IPCHandler


# ---------- o estado no resultado ----------

def test_por_padrao_uma_acao_continua_sendo_verificada():
    """Regressão: nada do que já existe pode passar a se declarar incerto."""
    r = ActionResult(success=True, output="Volume em 60%.")

    assert r.verificado is True
    assert r.incerto is False


def test_acao_sem_postcondicao_fica_incerta():
    r = ActionResult(success=True, output="Mandei.", verificado=False)

    assert r.incerto is True


def test_falha_nao_e_incerteza():
    """Quem falhou já diz que falhou; ressalva ali só confundiria."""
    r = ActionResult(success=False, error="não achei o botão", verificado=False)

    assert r.incerto is False


# ---------- a ressalva na fala ----------

def _handler(resultado):
    h = IPCHandler.__new__(IPCHandler)

    async def executar(_texto):
        h._ultimo_resultado_de_acao = resultado
        return "Mandei a mensagem."

    h._executar_intent_de_pc = executar
    return h


@pytest.mark.asyncio
async def test_acao_incerta_ganha_a_ressalva():
    h = _handler(ActionResult(success=True, output="Mandei.", verificado=False))

    resposta = await h._try_pc_intent("manda mensagem")

    assert resposta.startswith("Mandei a mensagem.")
    assert "não consegui confirmar" in resposta.casefold()


@pytest.mark.asyncio
async def test_acao_verificada_fala_sem_hesitar():
    """Hesitar quando HÁ prova seria o defeito oposto, e igualmente ruim."""
    h = _handler(ActionResult(success=True, output="Volume em 60%.", verificado=True))

    resposta = await h._try_pc_intent("diminui o volume")

    assert "confirmar" not in resposta.casefold()


@pytest.mark.asyncio
async def test_nao_repete_ressalva_quando_o_executor_ja_avisou():
    h = IPCHandler.__new__(IPCHandler)

    async def executar(_texto):
        h._ultimo_resultado_de_acao = ActionResult(
            success=True, output="Escrevi, mas não consegui confirmar a entrega.",
            verificado=False,
        )
        return "Escrevi, mas não consegui confirmar a entrega."

    h._executar_intent_de_pc = executar

    resposta = await h._try_pc_intent("manda pro codex")

    assert resposta.casefold().count("confirmar") == 1


@pytest.mark.asyncio
async def test_sem_acao_nenhuma_nada_muda():
    h = IPCHandler.__new__(IPCHandler)

    async def executar(_texto):
        return None

    h._executar_intent_de_pc = executar

    assert await h._try_pc_intent("que horas são") is None
