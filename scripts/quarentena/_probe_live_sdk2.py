"""Sonda OFFLINE #2 — os campos que decidem a arquitetura de voz.

Continua sem rede. O objetivo e separar TRES coisas que costumam ser
confundidas numa decisao de arquitetura:

  FATO-LOCAL   o SDK instalado aceita/rejeita isto (validacao Pydantic aqui).
  FATO-CODIGO  o codigo da ZARA usa / ignora este campo hoje.
  SUPOSICAO    o servidor do Google honra isto em runtime — NAO se prova aqui.
"""
from __future__ import annotations

from google.genai import types


def _tenta(nome: str, fn):
    try:
        valor = fn()
        print(f"[ACEITA-LOCAL] {nome} -> {valor}")
    except Exception as exc:
        print(f"[REJEITA-LOCAL] {nome} -> {type(exc).__name__}: {str(exc)[:220]}")


print("=== 1. response_modalities: quantos cabem? (validacao local) ===")
_tenta("AUDIO", lambda: types.LiveConnectConfig(response_modalities=["AUDIO"]).response_modalities)
_tenta("TEXT", lambda: types.LiveConnectConfig(response_modalities=["TEXT"]).response_modalities)
_tenta(
    "TEXT+AUDIO",
    lambda: types.LiveConnectConfig(response_modalities=["TEXT", "AUDIO"]).response_modalities,
)
_tenta("lista vazia", lambda: types.LiveConnectConfig(response_modalities=[]).response_modalities)

print("\n=== 2. Existe modalidade por TURNO? (procurando fora do connect) ===")
for nome in (
    "LiveClientContent",
    "LiveClientRealtimeInput",
    "LiveClientSetup",
    "LiveSendClientContentParameters",
    "LiveSendRealtimeInputParameters",
):
    obj = getattr(types, nome, None)
    if obj is None or not hasattr(obj, "model_fields"):
        print(f"{nome}: AUSENTE")
        continue
    campos = sorted(obj.model_fields.keys())
    tem = [c for c in campos if "modalit" in c or "config" in c]
    print(f"{nome}: {campos}")
    print(f"   -> campos de modalidade/config: {tem or 'NENHUM'}")

print("\n=== 3. VAD manual: AAD desligado + activity_start/end ===")
_tenta(
    "AAD(disabled=True)",
    lambda: types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
    ).automatic_activity_detection.disabled,
)
_tenta(
    "activity_handling=NO_INTERRUPTION",
    lambda: types.RealtimeInputConfig(
        activity_handling=types.ActivityHandling.NO_INTERRUPTION
    ).activity_handling,
)
_tenta(
    "turn_coverage=TURN_INCLUDES_ONLY_ACTIVITY",
    lambda: types.RealtimeInputConfig(
        turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
    ).turn_coverage,
)

print("\n=== 4. explicit_vad_signal (campo novo do LiveConnectConfig) ===")
campo = types.LiveConnectConfig.model_fields.get("explicit_vad_signal")
print("annotation:", getattr(campo, "annotation", None))
print("default:", getattr(campo, "default", None))
print("descricao:", (getattr(campo, "description", None) or "")[:400])

print("\n=== 5. Sinais de fim que o servidor manda (LiveServerContent) ===")
for nome in (
    "generation_complete",
    "turn_complete",
    "turn_complete_reason",
    "interaction_status",
    "waiting_for_input",
    "interim_input_transcription",
    "input_transcription",
):
    campo = types.LiveServerContent.model_fields.get(nome)
    if campo is None:
        print(f"{nome}: AUSENTE")
        continue
    desc = (getattr(campo, "description", None) or "").replace("\n", " ")[:300]
    print(f"{nome}: {getattr(campo, 'annotation', None)}")
    if desc:
        print(f"   doc: {desc}")

print("\n=== 6. Transcription.finished / words (fim de fala mais cedo?) ===")
for nome in ("finished", "words", "text"):
    campo = types.Transcription.model_fields.get(nome)
    desc = (getattr(campo, "description", None) or "").replace("\n", " ")[:300]
    print(f"{nome}: {getattr(campo, 'annotation', None)}")
    if desc:
        print(f"   doc: {desc}")
