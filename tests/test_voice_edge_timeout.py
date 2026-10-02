"""Edge TTS em streaming: timeout acompanha o tamanho do texto.

Ponto fraco real: o produtor do streaming limitava a síntese INTEIRA ao
`edge_timeout` (8s padrão). Texto longo = frase cortada no meio — e o
erro era engolido em silêncio porque o áudio já tinha começado a tocar
(`wrote_any=True`). Agora o piso continua 8s (rede morta falha rápido),
mas textos longos ganham folga proporcional.

Também cobre o gancho de normalização PT-BR no `TTSManager.speak()`:
todo texto da cascata passa por `normalize_for_tts` antes de sintetizar.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from core.voice_tts import EdgeTTS, TTSConfig, TTSManager


def _edge_engine(edge_timeout: float = 8.0) -> EdgeTTS:
    engine = EdgeTTS.__new__(EdgeTTS)
    engine._config = SimpleNamespace(edge_timeout=edge_timeout)
    return engine


def test_short_text_keeps_configured_timeout():
    engine = _edge_engine(edge_timeout=8.0)
    # Piso + folga proporcional (2 chars -> 8 + 2/24); nunca abaixo do piso
    assert engine._producer_timeout("oi") == 8.0 + 2 / 24.0
    assert engine._producer_timeout("") == 8.0
    assert engine._producer_timeout("oi") >= 8.0


def test_long_text_gets_proportional_allowance():
    engine = _edge_engine(edge_timeout=8.0)
    # ~24 caracteres/s de fala: 2400 chars ganham 100s além do piso
    assert engine._producer_timeout("x" * 2400) == 8.0 + 100.0


def test_timeout_never_below_floor_or_above_cap():
    engine = _edge_engine(edge_timeout=8.0)
    assert engine._producer_timeout("x" * 10_000_000) == 600.0
    tiny = _edge_engine(edge_timeout=0.1)
    # piso mínimo de 1s + folga proporcional
    assert tiny._producer_timeout("oi") == 1.0 + 2 / 24.0


def test_speak_normalizes_text_before_cascade():
    """O texto que chega ao engine já vem normalizado (R$ -> 'reais'...)."""
    config = TTSConfig()
    manager = TTSManager(config)
    fake_edge = Mock()
    manager.edge = fake_edge
    manager.kokoro = None
    manager.gemini = None

    manager.speak("o plano custa R$ 5,50", blocking=True)

    spoken = fake_edge.play.call_args.args[0]
    assert spoken == "o plano custa cinco reais e cinquenta centavos"


def test_speak_leaves_plain_text_untouched():
    config = TTSConfig()
    manager = TTSManager(config)
    fake_edge = Mock()
    manager.edge = fake_edge
    manager.kokoro = None
    manager.gemini = None

    manager.speak("bom dia Alex", blocking=True)

    assert fake_edge.play.call_args.args[0] == "bom dia Alex"
