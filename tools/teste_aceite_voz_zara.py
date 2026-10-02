#!/usr/bin/env python3
"""Teste de aceite da voz da ZARA (headless, sem microfone).

Para cada engine TTS disponivel:
  1. sintetiza a frase fixa e MEDE o TTFA (tempo ate o audio ficar pronto);
  2. verifica que o WAV gerado NAO e silencio (RMS acima do limiar).

Uso (no PC, a partir da raiz do projeto):
    .venv\\Scripts\\python.exe tools/teste_aceite_voz_zara.py

Exit 0: todas as engines disponiveis passaram.
Exit 1: alguma engine disponivel falhou (silencio ou erro).
Engines indisponiveis (sem pesos, sem internet, sem chave) entram como
SKIP, nao como falha. Kore/Gemini-Live nao rodam headless por desenho
(exigem sessao ao vivo); o Teste 1 do roteiro fisico cobre a Kore.
"""

from __future__ import annotations

import struct
import sys
import time
import wave
from pathlib import Path

# Frase fixa — a mesma das medicoes de TTFA (29/09 e 02/10).
FRASE = "Ola, eu sou a ZARA, sua assistente de voz."
# Limiar de nao-silencio: amostras reais deram RMS 2234 (Kokoro) e 4063 (Kore).
RMS_LIMIAR = 50

# Raiz do projeto = pasta pai de tools/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def rms_of_wav(path: Path) -> float:
    """RMS (0..32768) de um WAV 16-bit. Levanta se nao der pra ler."""
    with wave.open(str(path), "rb") as w:
        n_frames = w.getnframes()
        if n_frames == 0:
            return 0.0
        raw = w.readframes(n_frames)
    return _rms_bytes(raw)


def _rms_bytes(raw: bytes) -> float:
    n_samples = len(raw) // 2
    if n_samples == 0:
        return 0.0
    try:
        import numpy as np  # type: ignore

        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        return float((samples ** 2).mean() ** 0.5)
    except ImportError:
        vals = struct.unpack(f"<{n_samples}h", raw)
        return (sum(v * v for v in vals) / n_samples) ** 0.5


def audio_rms(path: Path) -> float:
    """RMS do arquivo de audio. Tenta WAV (wave); se nao for WAV, tenta
    decodificar via miniaudio (o Edge costuma gerar MP3)."""
    try:
        return rms_of_wav(path)
    except (wave.Error, EOFError):
        pass
    try:
        import miniaudio  # type: ignore

        decoded = miniaudio.decode_file(str(path), output_format=miniaudio.SampleFormat.SIGNED16)
        return _rms_bytes(decoded.samples)
    except ImportError:
        raise RuntimeError(f"audio nao-WAV e sem miniaudio pra decodificar: {path.name}")


def mede_kokoro(tmp: Path):
    """Kokoro local. Retorna (ttfa_s, wav_path). Levanta se indisponivel."""
    from core.voice_tts import KokoroTTS, TTSConfig

    tts = KokoroTTS(TTSConfig())  # levanta se os pesos nao estiverem instalados
    out = tmp / "aceite_kokoro.wav"
    t0 = time.perf_counter()
    tts.synthesize_to_file(FRASE, str(out))
    return time.perf_counter() - t0, out


def mede_edge(tmp: Path):
    """Edge (nuvem, gratis). Retorna (ttfa_s, wav_path). Levanta se indisponivel."""
    from core.voice_tts import EdgeTTS, TTSConfig

    tts = EdgeTTS(TTSConfig())
    out = tmp / "aceite_edge.wav"
    t0 = time.perf_counter()
    tts.synthesize_to_file(FRASE, str(out))
    return time.perf_counter() - t0, out


ENGINES = (
    ("kokoro", mede_kokoro),
    ("edge", mede_edge),
)


def main() -> int:
    tmp = ROOT / ".zara-tests" / "aceite-voz"
    tmp.mkdir(parents=True, exist_ok=True)

    resultados = []  # (engine, status, ttfa, rms, detalhe)
    for nome, medir in ENGINES:
        try:
            ttfa, wav = medir(tmp)
        except Exception as exc:  # indisponivel: SKIP, nao falha
            resultados.append((nome, "SKIP", None, None, f"{type(exc).__name__}"))
            continue
        try:
            rms = audio_rms(Path(wav))
        except Exception as exc:
            resultados.append((nome, "FALHOU", ttfa, None, f"leitura do audio: {exc}"))
            continue
        if rms < RMS_LIMIAR:
            resultados.append((nome, "FALHOU", ttfa, rms, f"silencio (RMS {rms:.0f} < {RMS_LIMIAR})"))
        else:
            resultados.append((nome, "PASSOU", ttfa, rms, ""))

    print(f"{'engine':<8} {'status':<7} {'ttfa_s':>7} {'rms':>7}  detalhe")
    falhas = 0
    for nome, status, ttfa, rms, detalhe in resultados:
        ttfa_s = f"{ttfa:.2f}" if ttfa is not None else "-"
        rms_s = f"{rms:.0f}" if rms is not None else "-"
        print(f"{nome:<8} {status:<7} {ttfa_s:>7} {rms_s:>7}  {detalhe}")
        if status == "FALHOU":
            falhas += 1

    if falhas:
        print(f"\nACEITE: FALHOU ({falhas} engine(s) com problema)")
        return 1
    if all(r[1] == "SKIP" for r in resultados):
        print("\nACEITE: INCONCLUSIVO (nenhuma engine disponivel)")
        return 1
    print("\nACEITE: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
