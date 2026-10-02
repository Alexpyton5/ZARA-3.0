#!/usr/bin/env python3
"""
FRENTE 3 - VOZ (MISSAO LAB VIVO): medicao REAL de latencia do TTS.
Roda no PC do Alex. NUNCA toca audio nos alto-falantes:
sounddevice.OutputStream e' substituido por um FAKE que registra o
timestamp do primeiro write() e descarta os bytes (instrumentacao de
medicao, rotulada no relatorio).
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent
os.chdir(PROJ)
sys.path.insert(0, str(PROJ))

import sounddevice  # noqa: E402
from core.voice_tts import TTSManager, TTSConfig  # noqa: E402

RESULTS = {"quando": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "fases": {}, "notas": []}


def ms(dt):
    return round(dt * 1000.0, 1)


# ---------------------------------------------------------------- (a)
cfg = TTSConfig(output_engine="kore")
mgr = TTSManager(cfg)
buf = io.StringIO()
init_ok = True
try:
    with contextlib.redirect_stdout(buf):
        mgr.initialize()
except Exception as e:  # noqa: BLE001
    init_ok = False
    buf.write(f"[EXCECAO initialize] {type(e).__name__}: {e}")

omnivoice_ready = bool(mgr.omnivoice and getattr(mgr.omnivoice, "available", True))
edge_can_stream = bool(mgr.edge is not None and mgr.edge._can_stream())
RESULTS["fases"]["initialize"] = {
    "ok": init_ok,
    "edge_subiu": mgr.edge is not None,
    "kokoro_subiu": mgr.kokoro is not None,
    "kokoro_esperava_falhar_por_falta_de_pesos": True,
    "omnivoice_construido": mgr.omnivoice is not None,
    "omnivoice_ready": omnivoice_ready,
    "gemini_subiu": mgr.gemini is not None,
    "edge_caminho_streaming_disponivel": edge_can_stream,
    "log": buf.getvalue(),
}

# ------------------------------------------------ fake (instrumentacao)
class FakeOutputStream:
    """INSTRUMENTACAO DE MEDICAO: registra ts do 1o write() e descarta."""

    first_write_ts = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start(self):
        pass

    def write(self, data):
        if FakeOutputStream.first_write_ts is None:
            FakeOutputStream.first_write_ts = time.perf_counter()

    def stop(self):
        pass

    def close(self, ignore_errors=False):
        pass


real_output_stream = sounddevice.OutputStream
sounddevice.OutputStream = FakeOutputStream

FRASES = {
    "curta": "Olá, Alex, tudo bem?",
    "media": (
        "O ZARA Lab está funcionando bem hoje, e todos os testes de voz "
        "passaram sem nenhum problema de áudio."
    ),
    "longa": (
        "A voz neural da Microsoft transforma texto em fala quase na hora, "
        "e o modo streaming começa a falar antes mesmo de terminar de gerar "
        "a frase inteira, o que deixa a conversa muito mais natural. A meta "
        "desta medição é descobrir em quantos milissegundos o primeiro "
        "pedaço de áudio chega, do clique até o som."
    ),
}

try:
    # ------------------------------------------------------ (b) streaming
    if mgr.edge is not None and edge_can_stream:
        FakeOutputStream.first_write_ts = None
        t0 = time.perf_counter()
        erro = None
        try:
            mgr.edge._play_streaming(FRASES["curta"], None, 1.0)
        except Exception as e:  # noqa: BLE001
            erro = f"{type(e).__name__}: {e}"
        t1 = time.perf_counter()
        fw = FakeOutputStream.first_write_ts
        RESULTS["fases"]["b_edge_streaming_primeiro_bloco"] = {
            "ok": erro is None and fw is not None,
            "erro": erro,
            "latencia_ate_primeiro_audio_ms": ms(fw - t0) if fw else None,
            "tempo_total_streaming_ms": ms(t1 - t0),
            "nota": "INSTRUMENTACAO DE MEDICAO: sounddevice.OutputStream "
                    "trocado por fake que registra o ts do 1o write() e "
                    "descarta. Nenhum byte chegou aos alto-falantes.",
        }
    else:
        RESULTS["fases"]["b_edge_streaming_primeiro_bloco"] = {
            "ok": False,
            "erro": "NÃO MEDIDO: Edge ausente ou sem streaming (caminho MCI "
                    "tocaria o alto-falante real).",
        }

    # ------------------------------------------------- (c) arquivo, 3x2
    if mgr.edge is not None:
        for nome, texto in FRASES.items():
            rounds = []
            for r in range(2):
                tmp = Path(tempfile.gettempdir()) / f"tts-med-{nome}-r{r}.mp3"
                t0 = time.perf_counter()
                try:
                    mgr.edge.synthesize_to_file(texto, str(tmp))
                    dt = ms(time.perf_counter() - t0)
                    rounds.append({"ok": True, "ms": dt, "bytes": tmp.stat().st_size})
                except Exception as e:  # noqa: BLE001
                    rounds.append({"ok": False, "erro": f"{type(e).__name__}: {e}"})
                finally:
                    tmp.unlink(missing_ok=True)
            oks = [x["ms"] for x in rounds if x.get("ok")]
            RESULTS["fases"][f"c_arquivo_{nome}"] = {
                "chars": len(texto),
                "rounds": rounds,
                "media_ms": round(sum(oks) / len(oks), 1) if oks else None,
            }
    else:
        RESULTS["fases"]["c_arquivo"] = {"ok": False, "erro": "Edge não subiu."}

    # ------------------------------------------------- (d) cascata kore->?
    chamadas = []

    def envolver(nome, eng, pular=False):
        orig = eng.play

        def gravado(text, voice=None, speed=1.0, blocking=True):
            chamadas.append({"engine": nome, "t": time.perf_counter()})
            if pular:
                # INSTRUMENTACAO: o play real do OmniVoice usa sounddevice
                # de verdade (tocaria o alto-falante). Registrar e pular,
                # deixando a cascata cair para o proximo degrau.
                raise RuntimeError(
                    "INSTRUMENTACAO: play do OmniVoice pulado para não tocar "
                    "alto-falante; cascata segue para o próximo degrau."
                )
            return orig(text, voice=voice, speed=speed, blocking=blocking)

        eng.play = gravado

    for nome, eng in (("edge", mgr.edge), ("kokoro", mgr.kokoro)):
        if eng is not None:
            envolver(nome, eng)
    if mgr.omnivoice is not None and omnivoice_ready:
        envolver("omnivoice", mgr.omnivoice, pular=True)
        RESULTS["notas"].append(
            "OmniVoice estava READY: play dele instrumentado (registra e pula) "
            "para não tocar o alto-falante."
        )

    if edge_can_stream or not mgr.edge:
        FakeOutputStream.first_write_ts = None
        t0 = time.perf_counter()
        erro = None
        try:
            mgr.speak(FRASES["curta"], blocking=True)
            ok = True
        except Exception as e:  # noqa: BLE001
            ok = False
            erro = f"{type(e).__name__}: {e}"
        t1 = time.perf_counter()
        fw = FakeOutputStream.first_write_ts
        RESULTS["fases"]["d_cascata_kore_sem_kore"] = {
            "ok": ok,
            "erro": erro,
            "ordem_engines_tentados": [c["engine"] for c in chamadas],
            "caiu_para_a_edge": "edge" in [c["engine"] for c in chamadas],
            "latencia_ate_primeiro_audio_ms": ms(fw - t0) if fw else None,
            "tempo_total_ms": ms(t1 - t0),
        }
    else:
        RESULTS["fases"]["d_cascata_kore_sem_kore"] = {
            "ok": False,
            "erro": "NÃO MEDIDO: Edge sem streaming usaria MCI (alto-falante real).",
        }
finally:
    sounddevice.OutputStream = real_output_stream

out = PROJ / "medicao-tts-frente3-resultado.json"
out.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")

print("==== RESUMO ====")
for fase, dados in RESULTS["fases"].items():
    print(f"[{fase}]")
    print(json.dumps(dados, ensure_ascii=False, indent=2)[:3000])
print("notas:", RESULTS["notas"])
print("JSON salvo em:", out)
