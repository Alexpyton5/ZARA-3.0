#!/usr/bin/env python3
"""Pre-voo da voz da ZARA - duplo clique e leia o resultado.

Roda no PC do Alex (com os privilegios dele): verifica arquivos,
chave da voz, modelo de reconhecimento em portugues e microfone.
Nao grava nem transmite audio. So usa a biblioteca padrao.

Saida: [OK] ou [FALTA] por item, em portugues simples.
Exit 0 = tudo pronto; 1 = falta alguma coisa.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))

resultados = []


def check(nome, ok, detalhe=""):
    resultados.append((nome, bool(ok)))
    marca = "OK   " if ok else "FALTA"
    linha = "[%s] %s" % (marca, nome)
    if detalhe:
        linha += " - %s" % detalhe
    print(linha)


print("=== Pre-voo da voz da ZARA ===\n")

# 1. Arquivos da cadeia de voz
arq_voz = [
    "core/voice_engine_policy.py",
    "core/voice_tts.py",
]
faltando = [a for a in arq_voz if not (ROOT / a).exists()]
check(
    "Cadeia de voz (Kore -> Edge -> Kokoro)",
    not faltando,
    "todos os 2 arquivos presentes" if not faltando else "faltando: " + ", ".join(faltando),
)

# 2. Chave da Kore - so confere se existe, nunca mostra o valor
tem_chave = bool(os.environ.get("GEMINI_API_KEY", "").strip())
check(
    "Chave da voz Kore (GEMINI_API_KEY)",
    tem_chave,
    "configurada" if tem_chave else "nao encontrada no ambiente",
)

# 3. Modelo de reconhecimento de voz em portugues (Vosk)
modelo = None
if LOCALAPPDATA:
    cand = LOCALAPPDATA / "ZARA3" / "models" / "vosk" / "vosk-model-small-pt-0.3"
    try:
        if cand.is_dir() and any(cand.iterdir()):
            modelo = cand
    except OSError:
        modelo = None
check(
    "Reconhecimento de voz em portugues (Vosk)",
    modelo is not None,
    ("encontrado em %s" % modelo) if modelo else "pasta vazia ou ausente",
)

# 4. Microfone: sounddevice carrega e acha dispositivo de entrada
try:
    import sounddevice as sd

    devs = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    check(
        "Microfone (sounddevice)",
        bool(devs),
        ("%d dispositivo(s) de entrada" % len(devs)) if devs else "nenhum microfone detectado",
    )
except Exception as e:  # noqa: BLE001 - queremos qualquer falha de audio aqui
    check("Microfone (sounddevice)", False, "nao carregou: %s" % type(e).__name__)

# 5. Interface: painel de voz e botao da chave do supercerebro
ui_ok = (ROOT / "frontend/src/renderer/components/zara-home/VoiceDock.tsx").exists()
chave_ok = (ROOT / "frontend/src/renderer/components/zara/interface/SupercerebroKey.tsx").exists()
check(
    "Botoes na tela (voz + chave)",
    ui_ok and chave_ok,
    "presentes" if (ui_ok and chave_ok) else "algum arquivo da interface faltando",
)

# 6. Chave do supercerebro fiada no codigo (liga/desliga + desliga sozinho)
try:
    ipc = (ROOT / "core/ipc_handlers.py").read_text(encoding="utf-8", errors="replace")
    fiacao = (
        "def handle_supercerebro_toggle" in ipc
        and "_auto_disable_supercerebro" in ipc
        and "_set_supercerebro_state" in ipc
    )
except OSError:
    fiacao = False
check(
    "Chave do supercerebro ligada no codigo",
    fiacao,
    "liga/desliga + desliga-sozinho presentes" if fiacao else "fiacao incompleta",
)

# 7. Roteador inteligente plugado no app
plug = (ROOT / "core/smart_router.py").exists()
try:
    orch = (ROOT / "core/zara_orchestrator.py").read_text(encoding="utf-8", errors="replace")
    plug = plug and ("smart_router" in orch)
except OSError:
    plug = False
check("Roteador inteligente", plug, "plugado" if plug else "nao encontrado")

print()
faltas = sum(1 for _, ok in resultados if not ok)
if faltas == 0:
    print("Tudo pronto pro teste da voz. Pode apertar o botao e falar.")
else:
    print("Faltam %d item(ns). Mostra essa tela pra zoe ou pro Codex." % faltas)
sys.exit(0 if faltas == 0 else 1)
