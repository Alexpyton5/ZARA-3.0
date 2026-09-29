# -*- coding: utf-8 -*-
"""Guarda do ponto cego da voz (EQUIPE 1, 2026-09-29).

Em 29/09 o Alex testou a voz e ela nao funcionava ("nao sai som/nao responde")
ENQUANTO a suite estava verde: o modelo Vosk (STT local) nunca tinha sido
instalado em %LOCALAPPDATA%/ZARA3/models/vosk e nenhum teste cobria isso.
Estes testes fecham o ponto cego em duas camadas:
1. contrato: sem modelo, o erro e honesto e acionavel (nunca falha muda);
2. saude da maquina: o modelo de producao esta instalado onde o app procura.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.voice_stt import VoiceConfig, VoskSTT, VoiceNotConfiguredError

# Onde o app em producao procura o modelo (perfil do usuario dono do PC).
# A suite redireciona ZARA3_HOME para um temp dir por teste, entao este
# caminho precisa ser resolvido aqui, fora do override.
PROD_VOSK_MODEL = (
    Path(r"C:\Users\alexp\AppData\Local\ZARA3")
    / "models"
    / "vosk"
    / "vosk-model-small-pt-0.3"
)
# O small-pt-0.3 tem layout flat: final.mdl fica na raiz do modelo.
PROD_VOSK_FINAL_MDL = PROD_VOSK_MODEL / "final.mdl"


def test_missing_model_raises_honest_actionable_error(tmp_path):
    """Sem modelo, o STT levanta erro honesto dizendo onde instalar."""
    cfg = VoiceConfig(vosk_model_path=str(tmp_path / "inexistente"))
    with pytest.raises(VoiceNotConfiguredError) as excinfo:
        VoskSTT(cfg)
    msg = str(excinfo.value)
    assert "STT_MODEL_NOT_CONFIGURED" in msg
    assert "vosk" in msg.lower()


@pytest.mark.skipif(os.name != "nt", reason="modelo de producao so existe no PC Windows")
def test_production_vosk_model_installed_and_transcribes():
    """O modelo de producao existe e o reconhecedor abre nele sem quebrar."""
    if not PROD_VOSK_FINAL_MDL.exists():
        pytest.fail(
            "modelo Vosk de producao ausente em %s - o microfone (STT local) "
            "nao funciona e a aba de voz da Zoe fica muda. Baixe "
            "vosk-model-small-pt-0.3 de https://alphacephei.com/vosk/models/ "
            "e extraia em %%LOCALAPPDATA%%/ZARA3/models/vosk/." % PROD_VOSK_MODEL
        )
    stt = VoskSTT(VoiceConfig(vosk_model_path=str(PROD_VOSK_MODEL)))
    # 2 segundos de silencio (16 kHz, mono, 16-bit): nao pode quebrar,
    # e o resultado final tem que ser texto (mesmo que vazio).
    stt.reset()
    stt.recognize(b"\x00" * 64000)
    final = json.loads(stt.recognizer.FinalResult())
    assert isinstance(final.get("text", ""), str)
