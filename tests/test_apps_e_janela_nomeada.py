"""Apps que faltavam na lista segura e janela por NOME.

Três buracos encontrados rodando a lista de comandos do Alex pela cadeia
real (detector -> action registrada -> gate):

1. "Abra a calculadora" e "abra o explorador de arquivos" não existiam na
   lista segura — caíam no LLM, que responde como se tivesse aberto.
2. "Reduza o volume" não era reconhecido; "diminua o volume" sim. Mesma
   ordem, verbo diferente.
3. "Minimize o Chrome" não tinha caminho nenhum: só existia janela ATIVA ou
   hwnd de contexto.
"""

import pytest

from core.action_registry import get_registry
from core.actions.os_ops import (
    _SAFE_CLOSE_APPS,
    _SAFE_WINDOWS_APPS,
    resolve_app_alias,
)
from core.pc_voice_intent import PcVoiceIntentDetector

import core.actions  # noqa: F401  (registra as actions)


@pytest.mark.parametrize(
    ("frase", "app"),
    [
        ("abra a calculadora", "calculator"),
        ("abre o calc", "calculator"),
        ("abra o explorador de arquivos", "file_explorer"),
        ("abre o explorer", "file_explorer"),
        ("abra meu computador", "file_explorer"),
        ("abra o gerenciador de arquivos", "file_explorer"),
    ],
)
def test_apps_novos_viram_os_app_com_id_canonico(frase, app):
    result = PcVoiceIntentDetector().detect(frase)
    assert result.is_pc_intent is True
    assert result.blocked is False
    assert result.action == "os_app"
    assert result.param == app
    assert app in _SAFE_WINDOWS_APPS


def test_explorer_nunca_entra_no_fechamento_seguro():
    """`explorer.exe` é a shell do Windows: fechar derruba a barra de tarefas."""
    assert "file_explorer" not in _SAFE_CLOSE_APPS
    assert "calculator" in _SAFE_CLOSE_APPS


@pytest.mark.parametrize(
    "frase", ["reduza o volume", "reduz o volume", "reduzir o volume", "Reduza o volume."]
)
def test_reduzir_volume_e_a_mesma_ordem_de_diminuir(frase):
    result = PcVoiceIntentDetector().detect(frase)
    assert result.action == "os_volume"
    assert result.param == "down"


def test_reduzir_com_intensidade_mantem_o_passo_maior():
    result = PcVoiceIntentDetector().detect("reduza muito o volume")
    assert result.action == "os_volume"
    assert result.param == "down_muito"


@pytest.mark.parametrize(
    ("frase", "action", "app"),
    [
        ("minimize o chrome", "window_minimize_named", "chrome"),
        ("minimize a janela do chrome", "window_minimize_named", "chrome"),
        ("maximize o vs code", "window_maximize_named", "vs_code"),
        ("restaure o spotify", "window_restore_named", "spotify"),
    ],
)
def test_janela_por_nome_resolve_app_da_lista_segura(frase, action, app):
    result = PcVoiceIntentDetector().detect(frase)
    assert result.is_pc_intent is True
    assert result.blocked is False
    assert result.action == action
    assert result.param == app
    assert get_registry().get_spec(action) is not None


def test_janela_generica_continua_usando_a_janela_ativa():
    """A forma sem nome não pode ter sido capturada pelo padrão novo."""
    for frase in ("minimize", "minimize a janela", "maximize a janela"):
        result = PcVoiceIntentDetector().detect(frase)
        assert result.action in {"window_minimize", "window_maximize"}
        assert result.param == "active"


def test_app_desconhecido_em_janela_nomeada_e_recusado_e_nao_executado():
    result = PcVoiceIntentDetector().detect("minimize o foguete lunar")
    assert result.action == "window_minimize_named"
    assert result.blocked is True
    assert result.physical_effect == 0


@pytest.mark.parametrize("frase", ["minimize && powershell", "alt+f4", "mate o processo"])
def test_texto_perigoso_nunca_vira_acao_de_janela(frase):
    """Bloqueado não basta: sintaxe de shell nem pode CASAR com janela."""
    result = PcVoiceIntentDetector().detect(frase)
    assert not result.action.startswith("window_")


def test_os_app_list_devolve_os_apps_novos():
    from core.actions.os_ops import os_app_list_action

    result = os_app_list_action()
    assert result.success is True
    ids = {a["id"] for a in result.data["apps"]}
    assert {"calculator", "file_explorer", "chrome", "vs_code", "spotify"} <= ids


# ZARA-COMPOUND-E-SOLTO-002 ------------------------------------------------
# "abra o chrome e vá para o youtube" não tem vírgula nem "depois", e por
# isso nem entrava no caminho composto: a frase inteira caía no catch-all de
# abrir app e virava "não conheço esse app".

import asyncio  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

from core.ipc_handlers import IPCHandler  # noqa: E402


def _partes_do_composto(frase, monkeypatch):
    """Roda o caminho composto capturando as etapas que ele decidiu executar."""
    handler = IPCHandler(AsyncMock())
    executadas: list[str] = []

    async def fake_try(part):
        executadas.append(part)
        return f"ok:{part}"

    monkeypatch.setattr(handler, "_try_pc_intent", fake_try)
    resposta = asyncio.run(handler._try_compound_pc_intent(frase))
    return resposta, executadas


def test_frase_ligada_so_por_e_vira_duas_etapas(monkeypatch):
    resposta, etapas = _partes_do_composto("abra o chrome e vá para o youtube", monkeypatch)
    assert etapas == ["abra o chrome", "vá para o youtube"]
    assert resposta is not None and "1)" in resposta and "2)" in resposta


def test_navegador_e_apelido_do_chrome(monkeypatch):
    _, etapas = _partes_do_composto("abra o navegador e vá para o youtube", monkeypatch)
    assert etapas == ["abra o navegador", "vá para o youtube"]
    assert PcVoiceIntentDetector().detect("abra o navegador").param == "chrome"


@pytest.mark.parametrize(
    "frase",
    [
        "pesquise rock e blues no youtube",   # uma query só, nunca duas etapas
        "me fale sobre o mar e o céu",        # conversa, não comando
    ],
)
def test_e_solto_em_frase_indivisivel_nao_vira_composto(frase, monkeypatch):
    resposta, etapas = _partes_do_composto(frase, monkeypatch)
    assert resposta is None
    assert etapas == []
