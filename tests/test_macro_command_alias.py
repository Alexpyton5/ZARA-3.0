"""Atalhos de comando: frase curta -> macro (EQUIPE 2, rodada 2026-10-02).

Camada deterministica "frase exata -> macro" (item 7 do backlog de pesquisa
competitiva, PESQUISA-CONCORRENTES.md - padrao VoiceAttack/Talon): comandos
curtos de voz/ditado resolvem direto para uma macro, sem passar pelo LLM.
A execucao delega para a action "macro_run", entao cada passo continua sob
os portoes de seguranca normais - o atalho e so um apelido, nunca um bypass.

O isolamento de dados (tests/conftest.py) garante que macros e atalhos
criados aqui caem na home isolada do teste, nunca nos dados do Alex.
"""
from __future__ import annotations

import itertools

import pytest

from core.action_registry import ActionResult, action, get_registry
from core.actions.macro_actions import (
    macro_alias_list_action,
    macro_alias_remove_action,
    macro_alias_set_action,
    macro_create_action,
    macro_run_phrase_action,
)

CHAMADAS: list = []
_CONTADOR = itertools.count(1)


@action(name="test_alias_ping", category="test", description="Action de teste: so registra a chamada")
def _test_alias_ping_action(mensagem: str = "pong") -> ActionResult:
    CHAMADAS.append(mensagem)
    return ActionResult(True, f"ping: {mensagem}")


def _nova_macro(params=None) -> str:
    nome = f"m_alias_teste_{next(_CONTADOR)}"
    passo = {"action": "test_alias_ping"}
    if params:
        passo["params"] = params
    resultado = macro_create_action(nome, [passo])
    assert resultado.success, resultado.error
    return nome


@pytest.fixture(autouse=True)
def _limpa_chamadas():
    CHAMADAS.clear()
    yield
    CHAMADAS.clear()


def test_set_e_run_por_frase_executa_a_macro():
    macro = _nova_macro({"mensagem": "ola"})
    criado = macro_alias_set_action("liga a luz", macro)
    assert criado.success, criado.error
    assert criado.data["macro"] == macro

    executado = macro_run_phrase_action("  LIGA   A LUZ ")
    assert executado.success, executado.error
    assert CHAMADAS == ["ola"]


def test_normalizacao_ignora_acento_caixa_e_espaco():
    macro = _nova_macro({"mensagem": "tocando"})
    assert macro_alias_set_action("música", macro).success
    assert macro_run_phrase_action("MUSICA").success
    assert macro_run_phrase_action("música").success
    assert CHAMADAS == ["tocando", "tocando"]


def test_set_com_macro_inexistente_falha_e_nao_cria_atalho():
    falhou = macro_alias_set_action("abracadabra", "macro_que_nao_existe")
    assert not falhou.success
    assert "nao encontrada" in (falhou.error or "")

    sem_atalho = macro_run_phrase_action("abracadabra")
    assert not sem_atalho.success
    assert "Nenhum atalho" in (sem_atalho.error or "")
    assert CHAMADAS == []


def test_frase_vazia_falha():
    falhou = macro_alias_set_action("   ", "qualquer_macro")
    assert not falhou.success
    assert CHAMADAS == []


def test_remove_atalho():
    macro = _nova_macro()
    assert macro_alias_set_action("desliga tudo", macro).success
    removido = macro_alias_remove_action("DESLIGA TUDO")
    assert removido.success, removido.error

    depois = macro_run_phrase_action("desliga tudo")
    assert not depois.success
    assert CHAMADAS == []

    de_novo = macro_alias_remove_action("desliga tudo")
    assert not de_novo.success


def test_list_e_atualizacao_de_atalho():
    macro_a = _nova_macro()
    macro_b = _nova_macro()
    assert macro_alias_set_action("modo cinema", macro_a).success
    assert macro_alias_set_action("hora do cafe", macro_b).success

    lista = macro_alias_list_action()
    assert lista.success
    assert lista.data == {"hora do cafe": macro_b, "modo cinema": macro_a}

    atualizado = macro_alias_set_action("MODO CINEMA", macro_b)
    assert atualizado.success
    assert "atualizado" in (atualizado.output or "")
    assert macro_alias_list_action().data["modo cinema"] == macro_b


def test_parametros_chegam_na_macro_pela_frase():
    macro = _nova_macro({"mensagem": "{saudacao}"})
    assert macro_alias_set_action("bom dia", macro).success

    executado = macro_run_phrase_action("bom dia", parameters={"saudacao": "bom dia, Alex"})
    assert executado.success, executado.error
    assert CHAMADAS == ["bom dia, Alex"]


def test_run_por_frase_via_registry_usa_os_gates_normais():
    # Prova que o atalho nao e bypass: indo pelo registry.execute, a action
    # "macro_run_phrase" passa pelos portoes como qualquer outra action, e a
    # macro executa passo a passo pelos gates de cada acao aninhada.
    macro = _nova_macro({"mensagem": "via registry"})
    assert macro_alias_set_action("prova de gate", macro).success

    via_registry = get_registry().execute("macro_run_phrase", phrase="prova de gate")
    assert via_registry.success, via_registry.error
    assert CHAMADAS == ["via registry"]
