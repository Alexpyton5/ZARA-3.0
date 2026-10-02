"""Sonda OFFLINE do SDK google-genai instalado.

Nao faz chamada de rede. So le o que a biblioteca declara, para que a decisao
arquitetural de voz seja tomada sobre a superficie REAL do SDK desta maquina, e
nao sobre suposicao de documentacao.
"""
from __future__ import annotations

import inspect

from google import genai
from google.genai import types

print("=== VERSAO ===")
print("google-genai:", getattr(genai, "__version__", "?"))

print("\n=== Modality enum ===")
mod = getattr(types, "Modality", None)
print("existe:", mod is not None)
if mod is not None:
    print("valores:", [m.name for m in mod])

print("\n=== LiveConnectConfig: campos ===")
campos = sorted(types.LiveConnectConfig.model_fields.keys())
for c in campos:
    print(" -", c)

print("\n=== AutomaticActivityDetection: campos ===")
aad = getattr(types, "AutomaticActivityDetection", None)
print("existe:", aad is not None)
if aad is not None:
    for c in sorted(aad.model_fields.keys()):
        print(" -", c)

print("\n=== ActivityStart / ActivityEnd ===")
for nome in ("ActivityStart", "ActivityEnd", "ActivityHandling", "TurnCoverage"):
    obj = getattr(types, nome, None)
    print(f"{nome}: {'SIM' if obj is not None else 'NAO'}")
    if obj is not None and hasattr(obj, "model_fields"):
        print("   campos:", sorted(obj.model_fields.keys()))
    elif obj is not None and inspect.isclass(obj):
        try:
            print("   valores:", [m.name for m in obj])
        except Exception:
            pass

print("\n=== RealtimeInputConfig: campos ===")
ric = getattr(types, "RealtimeInputConfig", None)
if ric is not None:
    for c in sorted(ric.model_fields.keys()):
        print(" -", c)

print("\n=== send_realtime_input: assinatura ===")
try:
    from google.genai import live as live_mod

    sess = live_mod.AsyncSession
    for nome in ("send_realtime_input", "send_client_content", "send_tool_response", "send"):
        fn = getattr(sess, nome, None)
        if fn is None:
            print(f"{nome}: AUSENTE")
            continue
        print(f"{nome}{inspect.signature(fn)}")
except Exception as exc:  # pragma: no cover
    print("falhou:", type(exc).__name__, exc)

print("\n=== LiveServerContent: campos (marcos de fim) ===")
lsc = getattr(types, "LiveServerContent", None)
if lsc is not None:
    for c in sorted(lsc.model_fields.keys()):
        print(" -", c)

print("\n=== Transcription: campos (tem 'finished'?) ===")
for nome in ("Transcription", "AudioTranscriptionConfig"):
    obj = getattr(types, nome, None)
    print(f"{nome}: {'SIM' if obj is not None else 'NAO'}")
    if obj is not None and hasattr(obj, "model_fields"):
        print("   campos:", sorted(obj.model_fields.keys()))
