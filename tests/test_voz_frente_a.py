"""MISSAO GIGANTE 3 — FRENTE A: voz como canal PRINCIPAL de controle do PC.

A1. MAPA DO PIPELINE DE VOZ (microfone -> acao real no PC)
----------------------------------------------------------
1. CAPTURA: microfone -> Gemini Live (`core/gemini_live_voice.py`, voz Kore)
   transcreve a fala em tempo real. NAO ha STT local: sem internet, a entrada
   de voz morre (a cascata Kore->OmniVoice cobre so a SAIDA/TTS).
2. TEXTO: a transcricao entra em `IPCHandler._process_voice_message(text)`.
3. INTENCAO (deterministica, nesta ordem):
   jarvis multi-action -> reminder -> operational memory -> self knowledge ->
   file intent -> PC intent (`PcVoiceIntentDetector` + fallback de raciocinio
   livre via Ollama qwen3:8b LOCAL, timeout 3s) -> lab intent ->
   guarda de acao local (recusa honesta) -> conversa (`_front_conversation_reply`).
4. EXECUCAO: `_executar_intent_de_pc` mapeia acao+parametro e chama
   `execute_action()` no registry -> acao REAL no Windows
   (os_app, window_*, browser_*, input_*, vision_*, os_volume...).
5. RESPOSTA FALADA (`_speak_response`): Kore -> OmniVoice (local) ->
   Edge neural (gratis) -> Kokoro (local) -> Gemini HTTP -> silencio.
   A voz robotica do Windows (SAPI) foi REMOVIDA por decisao do Alex.
6. LATENCIA OBSERVAVEL: `core/cronometro.py` grava cada turno em disco;
   [VOICE_TRACE] marca os estagios no console.

O QUE HOJE E SO CONVERSA (nao executa nada):
- tudo que o detector rejeita (is_pc_intent=False) e o guarda nao bloqueia
  cai em `_front_conversation_reply`: resposta de LLM, zero efeito fisico.
- bloqueios (blocked=True) viram RECUSA HONESTA falada ("Isso eu ainda nao
  sei fazer..."), nunca silencio e nunca fingimento de execucao.

A2. COMANDOS EXECUTANDO DE VERDADE: os testes abaixo provam que a frase
falada vira `execute_action` com a acao certa (execucao mockada; o executor
real e o mesmo usado pelo app em producao).

A3. CASCATA: ordem travada em `core/voice_engine_policy.py` + testes em
`tests/test_voice_tts_cascade.py` e `tests/test_voice_engine_policy.py`.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch, AsyncMock

import pytest

from core.action_registry import ActionResult
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


# --- A1: o mapa em forma de contrato -------------------------------------

def test_a1_abre_chrome_vira_acao_real():
    """'abre o Chrome' nao e conversa: e os_app/chrome no executor."""
    res = PcVoiceIntentDetector().detect("zara, abre o chrome")
    assert res.is_pc_intent is True
    assert res.blocked is False
    assert res.action == "os_app"
    assert res.param == "chrome"


def test_a1_clique_em_texto_vira_acao_real():
    """ZARA-VOZ-CLIQUE-001: 'clique em X' vira vision_click_text (OCR real)."""
    res = PcVoiceIntentDetector().detect("zara, clique em Entrar")
    assert res.is_pc_intent is True
    assert res.blocked is False
    assert res.action == "vision_click_text"
    assert res.param == "entrar"


def test_a1_clique_sem_preposicao_nao_vira_acao():
    """'clique aqui' solto nao dispara clique: o padrao exige em/no/na."""
    res = PcVoiceIntentDetector().detect("zara, clique aqui")
    assert not (res.is_pc_intent and res.action == "vision_click_text")


def test_a1_comando_perigoso_bloqueia_com_recusa_honesta():
    """Formatar disco nao tem rota executavel: bloqueia e fala a recusa."""
    res = PcVoiceIntentDetector().detect("zara, formata o disco C:")
    assert res.is_pc_intent is True
    assert res.blocked is True
    assert res.reply  # recusa falada, nunca silencio


def test_a1_conversa_nao_vira_acao():
    """Papo comum nao e comando de PC: cai na conversa, sem efeito fisico."""
    res = PcVoiceIntentDetector().detect("me conta uma piada")
    assert res.is_pc_intent is False


# --- A2: prova de execucao ponta a ponta (executor mockado) ---------------

def _handler_minimo():
    handler = IPCHandler(AsyncMock())
    handler._initialized = True
    handler._tts_initialized = False
    handler.gemini_live_voice = None
    handler.voice_mode = "off"
    handler.voice_pipeline = None
    handler.tts_manager = None
    handler.memory = None
    handler.orchestrator = None
    handler.model_router = None
    handler.conversation_history = None
    handler.reminder_engine = None
    handler.user_memory = None
    handler.project_memory = None
    handler.lab = None
    handler._event_loop = asyncio.get_event_loop()
    handler._last_window_hwnd = 12345
    handler._last_volume_level = 50
    handler._operational_context_updated_at = time.monotonic()
    handler._operational_context_turns = 3
    handler._operational_context = {
        "action_type": "window",
        "canonical_target": "some_window",
        "pid": 1234,
        "hwnd": 12345,
        "verified_value": "some_value",
        "timestamp": handler._operational_context_updated_at,
        "created_by_zara": False,
    }
    return handler


@pytest.mark.asyncio
async def test_a2_zara_abre_o_chrome_executa_os_app():
    """Criterio de aceite da frente A: 'abre o Chrome' -> Chrome abre."""
    handler = _handler_minimo()
    with patch("core.action_registry.execute_action") as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Chrome aberto.")
        await handler._process_voice_message("Zara, abre o Chrome")
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "os_app"
        assert kwargs.get("app") == "chrome"


@pytest.mark.asyncio
async def test_a2_zara_clique_em_entrar_executa_vision_click_text():
    """'clique em Entrar' -> clique real via OCR no texto 'entrar'."""
    handler = _handler_minimo()
    with patch("core.action_registry.execute_action") as mock_execute:
        mock_execute.return_value = ActionResult(success=True, output="Clique enviado.")
        await handler._process_voice_message("Zara, clique em Entrar")
        mock_execute.assert_called_once()
        args, kwargs = mock_execute.call_args
        assert args[0] == "vision_click_text"
        assert kwargs.get("text") == "entrar"
