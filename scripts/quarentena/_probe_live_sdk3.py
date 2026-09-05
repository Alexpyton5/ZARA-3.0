"""Sonda OFFLINE #3 — sinais de controle de turno e o que a ZARA ja usa.

Sem rede. Fecha as tres perguntas que faltam para a decisao:

  A) Existe um sinal de fim de fala MAIS CEDO que o primeiro audio do modelo?
  B) Da para o cliente controlar quando o turno fecha (VAD manual)?
  C) O codigo da ZARA hoje le esses campos, ou os ignora?
"""
from __future__ import annotations

import re
from pathlib import Path

from google.genai import types

RAIZ = Path(__file__).resolve().parents[1]

print("=== A. Enums de fim de turno ===")
for nome in ("TurnCompleteReason", "InteractionStatus", "StartSensitivity", "EndSensitivity"):
    obj = getattr(types, nome, None)
    if obj is None:
        print(f"{nome}: AUSENTE")
        continue
    try:
        print(f"{nome}: {[m.name for m in obj]}")
    except Exception:
        print(f"{nome}: presente, nao enumeravel")

print("\n=== B. WordInfo (timing por palavra) ===")
wi = getattr(types, "WordInfo", None)
if wi is not None and hasattr(wi, "model_fields"):
    print("campos:", sorted(wi.model_fields.keys()))

print("\n=== C. O que o codigo da ZARA le hoje do server_content ===")
alvo = RAIZ / "core" / "gemini_live_voice.py"
fonte = alvo.read_text(encoding="utf-8", errors="replace")
campos_do_sdk = sorted(types.LiveServerContent.model_fields.keys())
for campo in campos_do_sdk:
    usa = re.search(rf'["\']{re.escape(campo)}["\']', fonte) or re.search(
        rf"\.{re.escape(campo)}\b", fonte
    )
    print(f"{'USA   ' if usa else 'IGNORA'} {campo}")

print("\n=== D. Campos do LiveConnectConfig que a ZARA configura ===")
for campo in sorted(types.LiveConnectConfig.model_fields.keys()):
    usa = re.search(rf"\b{re.escape(campo)}\s*=", fonte)
    print(f"{'CONFIG' if usa else '  --  '} {campo}")

print("\n=== E. VAD local disponivel neste ambiente? ===")
for mod in ("webrtcvad", "vosk", "numpy", "silero_vad", "faster_whisper"):
    try:
        __import__(mod)
        print(f"[OK]      {mod}")
    except Exception as exc:
        print(f"[AUSENTE] {mod} ({type(exc).__name__})")
