"""ZARA-RACIOCINIO-LIVRE ETAPA 3 -- testes do fallback plugado atras de flag.

docs/audits/PROPOSTA_RACIOCINIO_LIVRE_2026-08-28.md, Etapa 3: plugar o
classificador da Etapa 2 no caminho de TEXTO, atras de uma flag lida do
disco a cada chamada. A regra mais importante aqui: com a flag desligada
(o padrao de boot), o comportamento tem que ser IDENTICO ao de antes da
Etapa 3 existir -- nada de novo acontece por acidente.
"""
from __future__ import annotations

import json

import core.actions  # noqa: F401 -- garante actions registradas
import core.ipc_handlers as ipc_handlers
from core.action_registry import ActionResult
from core.intent_classifier import IntentGuess


class _HandlerFalso:
    """So o suficiente pra _tentar_raciocinio_livre_texto rodar sem montar
    um IPCHandler inteiro (que precisa de orchestrator, memoria, etc)."""
    aprendizado = None

    def _anotar_experiencia(self, *args, **kwargs):
        pass


def _grava_flag(tmp_path, monkeypatch, ligado: bool):
    monkeypatch.setattr(
        "core.paths.config_dir",
        lambda: tmp_path,
    )
    (tmp_path / "feature_flags.json").write_text(
        json.dumps({"raciocinio_livre_fallback_texto": ligado}),
        encoding="utf-8",
    )


async def test_flag_desligada_por_padrao_nao_chama_o_classificador(tmp_path, monkeypatch):
    """Sem arquivo de flag nenhum -- o estado real de boot hoje."""
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    chamado = []
    monkeypatch.setattr(
        "core.intent_classifier.classify_intent_with_llm",
        lambda *a, **k: chamado.append(1) or None,
    )

    resultado = await ipc_handlers._tentar_raciocinio_livre_texto(_HandlerFalso(), "poe o som la embaixo")

    assert resultado is None
    assert chamado == [], "com a flag desligada o classificador nem deveria ser chamado"


async def test_flag_ligada_mas_classificador_nao_entende_devolve_none(tmp_path, monkeypatch):
    _grava_flag(tmp_path, monkeypatch, ligado=True)
    monkeypatch.setattr("core.intent_classifier.classify_intent_with_llm", lambda *a, **k: None)

    resultado = await ipc_handlers._tentar_raciocinio_livre_texto(_HandlerFalso(), "voce acha que vai chover?")

    assert resultado is None


async def test_flag_ligada_executa_de_verdade_e_responde_com_resultado_real(tmp_path, monkeypatch):
    _grava_flag(tmp_path, monkeypatch, ligado=True)
    monkeypatch.setattr(
        "core.intent_classifier.classify_intent_with_llm",
        lambda *a, **k: IntentGuess(action="os_volume", param="20", confidence=0.9),
    )

    async def executor_falso(action, **params):
        assert action == "os_volume"
        assert params == {"level": 20}
        return ActionResult(success=True, output="Volume definido para 20%.")

    monkeypatch.setattr("core.action_registry.execute_action", executor_falso)

    resultado = await ipc_handlers._tentar_raciocinio_livre_texto(_HandlerFalso(), "poe o som la embaixo, uns 20")

    assert resultado == "Volume definido para 20%."


async def test_falha_de_execucao_nunca_vira_sucesso_fingido(tmp_path, monkeypatch):
    _grava_flag(tmp_path, monkeypatch, ligado=True)
    monkeypatch.setattr(
        "core.intent_classifier.classify_intent_with_llm",
        lambda *a, **k: IntentGuess(action="os_app", param="programa_fantasma", confidence=0.9),
    )

    async def executor_falso(action, **params):
        return ActionResult(success=False, error="Aplicativo não autorizado.")

    monkeypatch.setattr("core.action_registry.execute_action", executor_falso)

    resultado = await ipc_handlers._tentar_raciocinio_livre_texto(_HandlerFalso(), "abre aquele programa la")

    assert resultado == "Aplicativo não autorizado."


async def test_acao_fora_do_conjunto_pequeno_da_etapa3_nunca_executa(tmp_path, monkeypatch):
    """O classificador (Etapa 2) ja e limitado a acoes do ActionRegistry, mas
    a Etapa 3 tem uma segunda trava, mais apertada: so confia em montar
    parametro pra um conjunto pequeno e conhecido."""
    _grava_flag(tmp_path, monkeypatch, ligado=True)
    monkeypatch.setattr(
        "core.intent_classifier.classify_intent_with_llm",
        lambda *a, **k: IntentGuess(action="terminal", param="del *.*", confidence=0.95),
    )
    executado = []
    monkeypatch.setattr("core.action_registry.execute_action", lambda *a, **k: executado.append(1))

    resultado = await ipc_handlers._tentar_raciocinio_livre_texto(_HandlerFalso(), "apaga tudo ai")

    assert resultado is None
    assert executado == [], "acao fora do conjunto pequeno da Etapa 3 nunca pode executar"


def test_parametro_invalido_para_volume_nunca_executa():
    from core.ipc_handlers import _montar_parametros_etapa3

    assert _montar_parametros_etapa3("os_volume", "nao é um número") is None
    assert _montar_parametros_etapa3("os_volume", "20") == {"level": 20}
    assert _montar_parametros_etapa3("os_volume", "500") == {"level": 100}  # clamp


def test_flag_sem_arquivo_e_sem_campo_falha_fechado(tmp_path, monkeypatch):
    from core.ipc_handlers import _raciocinio_livre_fallback_texto_habilitado

    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    assert _raciocinio_livre_fallback_texto_habilitado() is False

    (tmp_path / "feature_flags.json").write_text("{}", encoding="utf-8")
    assert _raciocinio_livre_fallback_texto_habilitado() is False

    (tmp_path / "feature_flags.json").write_text("isso nao e json valido", encoding="utf-8")
    assert _raciocinio_livre_fallback_texto_habilitado() is False


def test_flag_le_do_disco_a_cada_chamada_sem_cache(tmp_path, monkeypatch):
    """Requisito da Etapa 3: desligar 'nao pede deploy' -- nem reinicio."""
    from core.ipc_handlers import _raciocinio_livre_fallback_texto_habilitado

    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    flags_path = tmp_path / "feature_flags.json"

    flags_path.write_text(json.dumps({"raciocinio_livre_fallback_texto": True}), encoding="utf-8")
    assert _raciocinio_livre_fallback_texto_habilitado() is True

    flags_path.write_text(json.dumps({"raciocinio_livre_fallback_texto": False}), encoding="utf-8")
    assert _raciocinio_livre_fallback_texto_habilitado() is False
