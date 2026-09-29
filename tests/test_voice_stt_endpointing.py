"""Endpointing do STT: o contador de silêncio zera a cada utterance.

Ponto fraco real: depois de uma utterance vazia (só silêncio), o
`_silence_chunks` nunca era zerado em `_process_utterance`. No modo
push-to-talk (sem Porcupine) cada chunk silencioso seguinte re-disparava
o processamento — ~4 chamadas ao Vosk por segundo de silêncio puro,
para sempre, até alguém falar ou a pipeline parar.

O teste abaixo roda o `_run_loop` DE VERDADE numa thread, com áudio
roteirizado de 25 chunks silenciosos, e conta as chamadas ao Vosk.
"""
from __future__ import annotations

import threading
import time

from core.voice_stt import VoiceConfig, VoicePipeline


class _CountingVosk:
    def __init__(self):
        self.recognize_calls = 0

    def recognize(self, audio_data: bytes):
        self.recognize_calls += 1
        return None  # silêncio: nada reconhecido

    def partial_recognize(self, audio_data: bytes):
        return ""

    def reset(self):
        return None


class _ScriptedAudio:
    """Entrega N chunks e depois silêncio vazio até a pipeline parar."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    def start(self):
        return None

    def stop(self):
        return None

    def read(self, timeout: float = 0.1):
        if self._chunks:
            return self._chunks.pop(0)
        time.sleep(0.02)
        return None


def _silent_chunk() -> bytes:
    return b"\x00\x00" * 2048  # 4096 bytes de silêncio 16-bit


def test_silence_does_not_retrigger_recognition_in_a_loop():
    config = VoiceConfig()
    config.vad_silence_chunks = 10  # mais rápido que os 30 padrão
    pipeline = VoicePipeline(config, on_wake=lambda: None, on_speech=lambda t: None)
    pipeline.vosk = _CountingVosk()
    pipeline.audio = _ScriptedAudio([_silent_chunk() for _ in range(25)])
    pipeline.porcupine = None  # push-to-talk: o modo onde o bug mordia
    pipeline._state = "LISTENING"
    pipeline._running = True

    thread = threading.Thread(target=pipeline._run_loop, daemon=True)
    thread.start()
    try:
        # Espera os 25 chunks serem consumidos + folga
        deadline = time.time() + 10
        while pipeline.audio._chunks and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.5)  # folga: sem o fix, cada chunk extra chamaria o Vosk
    finally:
        pipeline._running = False
        thread.join(timeout=5)

    # 25 chunks silenciosos, limiar 10: UMA utterance nos chunks 10 e 20.
    # Sem o fix seriam 16 chamadas (chunks 10..25, uma por chunk).
    assert pipeline.vosk.recognize_calls == 2
    # O contador reflete só o silêncio após a última utterance (chunks 21-25),
    # nunca o acumulado de antes dela.
    assert pipeline._silence_chunks == 5


def test_process_utterance_resets_silence_counter():
    pipeline = VoicePipeline(VoiceConfig(), on_wake=lambda: None, on_speech=lambda t: None)
    pipeline.vosk = _CountingVosk()
    pipeline._speech_buffer = [_silent_chunk() for _ in range(5)]
    pipeline._silence_chunks = 30

    pipeline._process_utterance()

    assert pipeline._silence_chunks == 0
    assert pipeline._speech_buffer == []
