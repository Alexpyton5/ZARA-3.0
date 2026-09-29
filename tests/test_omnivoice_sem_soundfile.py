"""Regressao EQUIPE2-20260929 (vigia 30min): a voz da Zara ficava muda.

Causa raiz: `OmniVoiceWorkerTTS.play()` lia o WAV do worker com o pacote
`soundfile`, que NAO esta instalado no .venv nem entra no pacote do backend
(`zara-backend.exe`). O primeiro motor da cascata de TTS quebrava sempre com
`ModuleNotFoundError: No module named 'soundfile'` e a fala so saia (lenta)
pelo fallback do Edge — para o Alex, "nao sai som".

A leitura agora usa o modulo `wave` da stdlib (`read_wav_mono_pcm16`).
Estes testes provam que o WAV no formato exato do worker e lido SEM o
soundfile instalado.
"""
import sys
import wave

import numpy as np

from core.omnivoice_runtime import read_wav_mono_pcm16


def _wav_do_worker(path, amostras, taxa=24000):
    """Grava igual ao omnivoice_worker._write_wave: mono, 16-bit, 24kHz."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(amostras.tobytes())


def test_leitura_wav_funciona_sem_soundfile(tmp_path, monkeypatch):
    # Simula o .venv real do PC: 'import soundfile' levanta ImportError.
    monkeypatch.setitem(sys.modules, "soundfile", None)

    amostras = (np.sin(np.linspace(0, 6.28, 2400)) * 10000).astype(np.int16)
    wav_path = tmp_path / "worker.wav"
    _wav_do_worker(wav_path, amostras)

    audio, taxa = read_wav_mono_pcm16(wav_path)

    assert taxa == 24000
    assert audio.dtype == np.int16
    assert (audio == amostras).all()


def test_formato_inesperado_levanta_erro_claro(tmp_path):
    amostras_8bit = (np.linspace(0, 255, 240, dtype=np.uint8)).tobytes()
    wav_path = tmp_path / "ruim.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(24000)
        w.writeframes(amostras_8bit)

    try:
        read_wav_mono_pcm16(wav_path)
    except RuntimeError as exc:
        assert "sampwidth" in str(exc)
    else:
        raise AssertionError("devia ter levantado RuntimeError para sampwidth=1")
