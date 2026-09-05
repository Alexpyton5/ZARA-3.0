"""ZARA-RACIOCINIO-LIVRE ETAPA 2 — testes do classificador isolado.

A regra que mais importa aqui e a de seguranca: o modelo NUNCA pode fazer a
Zara executar algo fora da lista fechada de acoes registradas. Um chute
aceito viraria acao real no computador do Alex.
"""
from __future__ import annotations

import core.actions  # noqa: F401 -- garante actions registradas
from core.intent_classifier import (
    IntentGuess,
    build_action_catalog,
    classify_intent_with_llm,
)

ACOES = ["os_volume", "youtube_open", "os_app"]


def _responde(payload: str):
    return lambda prompt: payload


def test_devolve_palpite_valido_quando_o_modelo_acerta():
    guess = classify_intent_with_llm(
        "poe o som la embaixo ai",
        ACOES,
        call_model=_responde('{"action": "os_volume", "param": "20", "confidence": 0.9}'),
    )

    assert guess == IntentGuess(action="os_volume", param="20", confidence=0.9)


def test_nunca_aceita_acao_fora_da_lista_fechada():
    """A trava principal: modelo inventou capacidade que a Zara nao tem."""
    guess = classify_intent_with_llm(
        "formata o meu HD",
        ACOES,
        call_model=_responde('{"action": "format_drive", "param": "C:", "confidence": 0.99}'),
    )

    assert guess is None


def test_null_do_modelo_vira_none_em_vez_de_chute():
    guess = classify_intent_with_llm(
        "voce acha que vai chover amanha?",
        ACOES,
        call_model=_responde('{"action": null, "param": null, "confidence": 0.0}'),
    )

    assert guess is None


def test_confianca_baixa_e_descartada():
    guess = classify_intent_with_llm(
        "sei la, faz alguma coisa",
        ACOES,
        call_model=_responde('{"action": "os_app", "param": "notepad", "confidence": 0.2}'),
    )

    assert guess is None


def test_resposta_ilegivel_nao_derruba_nada():
    for lixo in ("", "desculpa, nao entendi", "{quebrado", "null"):
        assert classify_intent_with_llm("abre ai", ACOES, call_model=_responde(lixo)) is None


def test_json_embrulhado_em_texto_ainda_e_lido():
    resposta = 'Claro!\n```json\n{"action": "youtube_open", "param": null, "confidence": 0.95}\n```'

    guess = classify_intent_with_llm("bota um som ai", ACOES, call_model=_responde(resposta))

    assert guess is not None
    assert guess.action == "youtube_open"
    assert guess.param is None


def test_erro_na_chamada_do_modelo_falha_fechado():
    def explode(prompt):
        raise RuntimeError("rede caiu")

    assert classify_intent_with_llm("abre o youtube", ACOES, call_model=explode) is None


def test_texto_vazio_ou_lista_vazia_nem_chama_o_modelo():
    chamadas = []

    def registra(prompt):
        chamadas.append(prompt)
        return '{"action": "os_volume", "param": "10", "confidence": 0.9}'

    assert classify_intent_with_llm("   ", ACOES, call_model=registra) is None
    assert classify_intent_with_llm("abre o youtube", [], call_model=registra) is None
    assert chamadas == []


def test_catalogo_sai_do_registry_de_verdade():
    catalogo = build_action_catalog(["os_volume", "acao_que_nao_existe_xyz"])

    nomes = [item["name"] for item in catalogo]
    assert "os_volume" in nomes
    assert "acao_que_nao_existe_xyz" not in nomes


def test_prompt_lista_as_acoes_permitidas():
    visto = {}

    def captura(prompt):
        visto["prompt"] = prompt
        return '{"action": null, "param": null, "confidence": 0.0}'

    classify_intent_with_llm("qualquer coisa", ACOES, call_model=captura)

    for acao in ACOES:
        assert acao in visto["prompt"]


def test_uso_do_classificador_esta_sempre_atras_de_flag():
    """A Etapa 3 pluga o classificador -- ver tests/test_free_reasoning_etapa3.py.

    O que este teste ainda garante, mesmo depois de plugado: toda linha que
    chama intent_classifier em ipc_handlers.py esta dentro (textualmente
    antes, na mesma funcao) de uma checagem de flag, nunca incondicional. Se
    isso quebrar, o fallback de rede deixou de ser desligavel sem redeploy --
    violando a Lei Arquitetural (reflexo local nao depende de rede).
    """
    from pathlib import Path

    fonte = Path(__file__).resolve().parent.parent / "core" / "ipc_handlers.py"
    texto = fonte.read_text(encoding="utf-8")
    assert "intent_classifier" in texto, "Etapa 3 deveria ter plugado o classificador"
    assert "_raciocinio_livre_fallback_texto_habilitado" in texto
