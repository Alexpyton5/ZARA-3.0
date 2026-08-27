"""ZARA-RECUSA-HONESTA-001 — recusar não é o mesmo que ficar mudo.

Um guarda de segurança colocado na entrada de `PcVoiceIntentDetector.detect`
devolvia `is_pc_intent=False` para qualquer texto que contivesse sintaxe de
shell ou o nome de um programa perigoso. Isso produziu dois defeitos:

1. "abra powershell" saía como "não é comando de PC", caía no LLM, e a ZARA
   não executava (certo) mas também não dizia que era proibido (errado).
2. A lista de nomes incluía `python`, `reg`, `sh` e `curl`, então uma busca
   inocente como "procure por Python asyncio" era recusada em silêncio.

Estes testes travam os dois lados: o perigoso é recusado EM VOZ ALTA, e o
inocente passa.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import RESPOSTA_NAO_SEI, PcVoiceIntentDetector


def _detect(phrase: str):
    return PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)


@pytest.mark.parametrize(
    "phrase",
    [
        "abra powershell",
        "abra o regedit",
        "execute powershell",
        "abra calc && powershell",
        "abra Downloads/../Windows",
        "abra C:/Windows/System32",
    ],
)
def test_pedido_perigoso_e_recusado_com_resposta_falada(phrase):
    """Nunca executa — e nunca fica mudo. Alex tem de ouvir o 'não'."""
    result = _detect(phrase)

    assert result.is_pc_intent is True, "virou silêncio em vez de recusa"
    assert result.blocked is True
    assert result.physical_effect == 0
    assert result.reply.strip(), "recusa sem frase é a mesma coisa que mudez"
    # ZARA-RECUSA-UNICA-001 (Alex): uma frase só, e ela nunca oferece
    # calculadora como prêmio de consolação.
    assert result.reply == RESPOSTA_NAO_SEI
    assert "calculadora" not in result.reply.lower()


@pytest.mark.parametrize(
    ("phrase", "esperado"),
    [
        ("procure por Python asyncio", "python asyncio"),
        ("procure por curl no windows", "curl no windows"),
        ("procure por regex em javascript", "regex em javascript"),
    ],
)
def test_busca_inocente_nao_e_confundida_com_ataque(phrase, esperado):
    """Palavra de programa dentro de uma busca é assunto, não comando."""
    result = _detect(phrase)

    assert result.action == "browser_search"
    assert result.param == esperado
    assert result.blocked is False


def test_app_seguro_continua_abrindo():
    """A defesa não pode ter custo em cima do uso normal."""
    result = _detect("abra o wordpad")

    assert result.action == "os_app"
    assert result.param == "wordpad"
    assert result.blocked is False


@pytest.mark.asyncio
async def test_dispatcher_devolve_a_recusa_em_vez_de_none(monkeypatch):
    """O silêncio aparecia aqui: `_try_pc_intent` devolvia None e a ZARA
    respondia qualquer coisa vinda do modelo."""
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("abra powershell")

    assert reply is not None
    assert reply == RESPOSTA_NAO_SEI
    execute.assert_not_awaited()
