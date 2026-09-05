#!/usr/bin/env python3
"""ZARA 3.0 — testa o detector de intents contra fala natural. SEM efeito fisico.

Nivel de evidencia: TEST. Roda o PcVoiceIntentDetector real do projeto contra
as frases que o Alex usaria de verdade e confere se casam com a action certa.
NAO executa nenhuma action: nada muda no Windows.

Isto NAO substitui o teste falado (VOICE_PHYSICAL). Prova que o intent casa,
nao que o executor funciona nem que o STT transcreveu certo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pc_voice_intent import PcVoiceIntentDetector  # noqa: E402

# (frase, action esperada). None = deve ser ignorada (conversa normal).
CASOS: list[tuple[str, str | None]] = [
    # --- brilho: o que ANTES falhava ---
    ("diminui o brilho", "os_brightness_down"),
    ("Zara, diminui o brilho", "os_brightness_down"),
    ("abaixa o brilho ai", "os_brightness_down"),
    ("baixa um pouco o brilho", "os_brightness_down"),
    ("reduz o brilho por favor", "os_brightness_down"),
    ("escurece", "os_brightness_down"),
    ("deixa mais escuro", "os_brightness_down"),
    ("aumenta o brilho", "os_brightness_up"),
    ("sobe o brilho", "os_brightness_up"),
    ("clareia", "os_brightness_up"),
    ("mais claro", "os_brightness_up"),
    ("coloca o brilho em 70", "os_brightness_absolute"),
    ("poe o brilho a 30", "os_brightness_absolute"),
    ("brilho em 40", "os_brightness_absolute"),
    ("ajusta o brilho pra 80", "os_brightness_absolute"),
    # --- brilho: forma culta, nao pode ter regredido ---
    ("diminua o brilho", "os_brightness_down"),
    ("aumente o brilho", "os_brightness_up"),
    # --- volume: ja funcionava, guarda contra regressao ---
    ("diminui o volume", "os_volume"),
    ("abaixa o volume", "os_volume"),
    ("coloca o volume em 30", "os_volume"),
    # --- outros que ja funcionavam ---
    ("que horas sao?", "system_time"),
    ("abra o youtube", "youtube_open"),
    ("va para o youtube", "youtube_open"),
    ("ativar modo noturno", "os_night_light_on"),
    # --- conversa normal: NAO pode virar comando ---
    ("oi tudo bem", None),
    ("me conta uma piada", None),
    ("o que voce acha do brilho das estrelas", None),
]


def main() -> int:
    det = PcVoiceIntentDetector()
    ok = falhas = 0
    print("=" * 72)
    print("TESTE DE INTENTS - fala natural  (NENHUMA acao e executada)")
    print("=" * 72)
    print(f"{'RES':4} {'FRASE':40} {'ESPERADO':26} OBTIDO")
    print("-" * 100)
    for frase, esperado in CASOS:
        r = det.detect(frase)
        obtido = r.action if r.is_pc_intent else None
        bom = (obtido == esperado)
        aviso = "  <<< BLOQUEADO" if (r.is_pc_intent and r.blocked) else ""
        print(f"{'OK ' if bom else 'FALHA':4} {frase:40} {str(esperado):26} {str(obtido)}{aviso}")
        if bom:
            ok += 1
        else:
            falhas += 1
    print("-" * 100)
    print(f"\n{ok} de {len(CASOS)} corretos, {falhas} falhas")
    print("\nNIVEL DE EVIDENCIA: TEST.")
    print("Prova que o intent casa. NAO prova executor, STT nem voz.")
    print("So o Alex falando fecha isso (VOICE_PHYSICAL).")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
