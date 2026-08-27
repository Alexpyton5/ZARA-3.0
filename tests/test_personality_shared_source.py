"""AUDITORIA_2026-08-27: voz (gemini_live_voice.py) e texto
(zara_orchestrator.py) tinham cada um sua propria string de personalidade
hardcoded, podendo divergir sem ninguem perceber. Agora os dois leem
PERSONALIDADE_DA_ZARA.txt via core/personality.load_personality()."""
from __future__ import annotations

from core.personality import load_personality


def test_text_orchestrator_uses_shared_personality():
    from core.zara_orchestrator import CONVERSATIONAL_SYSTEM_PROMPT

    assert CONVERSATIONAL_SYSTEM_PROMPT == load_personality()


def test_voice_config_opens_with_shared_personality():
    from core.gemini_live_voice import GeminiLiveVoiceConfig

    cfg = GeminiLiveVoiceConfig(api_key="fake-key-for-test")

    assert cfg.system_instruction.startswith(load_personality())
    # As regras especificas de voz (vocabulario de STT, anti-invencao) nao
    # podem sumir so porque a abertura agora vem do arquivo compartilhado.
    assert "NUNCA invente número" in cfg.system_instruction
    assert "Claude (o assistente de programação" in cfg.system_instruction


def test_load_personality_falls_back_when_file_is_missing(tmp_path, monkeypatch):
    import core.personality as personality_module

    monkeypatch.setattr(personality_module, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(personality_module, "_cached", None)

    text = personality_module.load_personality(force_reload=True)

    assert "ZARA" in text
    assert len(text) > 0
