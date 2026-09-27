# -*- coding: utf-8 -*-
"""Teste REAL v2: dirige o zara-backend.exe empacotado via IPC.

Teste 2 manda o engine REAL (como o TextCommandInput.tsx faz:
selection.readCurrent()) e replica a validacao CORRIGIDA do
frontBrainProvenance.ts na resposta — prova o contrato inteiro.
"""
import json
import queue
import subprocess
import threading
import time

EXE = (r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
       r"\frontend\release3\win-unpacked\resources\backend\zara-backend.exe")

FRONT_BRAIN_ENGINES = {"gpt-5.6-luna", "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra"}


def validate_provenance(response, selected):
    """Replica EXATA da validacao corrigida (frontBrainProvenance.ts)."""
    if not isinstance(response, dict):
        raise ValueError("A resposta chegou sem origem factual.")
    origin = response.get("response_origin")
    if origin == "local_deterministic":
        eng = response.get("engine")
        if not isinstance(eng, str) or not eng or eng in FRONT_BRAIN_ENGINES:
            raise ValueError("A resposta local chegou com uma origem incompativel.")
        return "local_deterministic"
    if origin == "front_brain_policy" and response.get("success") is False:
        raise ValueError(str(response.get("error") or "politica"))
    if origin != "front_brain_run":
        raise ValueError("A resposta nao prova se veio de uma acao local ou de um modelo.")
    fallback = response.get("fallback")
    rerouted = fallback is not None
    if rerouted and (not isinstance(fallback, list) or len(fallback) != 2
                     or not isinstance(fallback[0], str) or not isinstance(fallback[1], str)):
        raise ValueError("A resposta chegou sem a identificacao do transporte alternativo.")
    if not rerouted and response.get("engine") != selected:
        raise ValueError(f"O backend respondeu com {response.get('engine')} em vez de {selected}.")
    if not isinstance(response.get("run_id"), str) or not response.get("run_id"):
        raise ValueError("A resposta chegou sem run_id.")
    if not isinstance(response.get("provider"), str) or not response.get("provider"):
        raise ValueError("A resposta chegou sem provider.")
    if not rerouted and response.get("model_requested") != selected:
        raise ValueError(f"O backend respondeu com {response.get('model_requested')} em vez de {selected}.")
    reported = response.get("model_reported")
    if reported is not None and not isinstance(reported, str):
        raise ValueError("O provedor retornou uma proveniencia invalida.")
    expected = "UNREPORTED" if reported is None else (
        "MATCHED" if reported == response.get("model_requested") else "MISMATCH_REJECTED")
    if response.get("provenance_status") != expected:
        raise ValueError(f"provenance_status {response.get('provenance_status')} != {expected}")
    return ("fallback:" + "/".join(fallback)) if rerouted else "direto"


proc = subprocess.Popen(
    [EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
)
lines = queue.Queue()


def reader():
    for line in proc.stdout:
        lines.put(line.strip())


threading.Thread(target=reader, daemon=True).start()


def send(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def wait_response(rid, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("type") == "response" and data.get("request_id") == rid:
            return data
    return None


# Engine REAL como o frontend manda: o selecionado atual (padrao Luna).
SELECTED = "gpt-5.6-luna"

print(f"=== TESTE: send-message 'oi' (engine real: {SELECTED}) ===", flush=True)
send({"type": "send-message", "request_id": "t-msg-v2",
      "payload": {"message": "oi", "engine": SELECTED, "history": []}})
resp = wait_response("t-msg-v2", 600)
if resp is None:
    print("SEM RESPOSTA (timeout) — FALHOU")
else:
    if resp.get("error"):
        print(f"ERRO IPC: {resp.get('error')}")
    r = resp.get("response") if isinstance(resp.get("response"), dict) else resp
    text = str(r.get("response") or "")
    print(f"ENGINE: {r.get('engine')}")
    print(f"ORIGIN: {r.get('response_origin')}")
    print(f"FALLBACK: {r.get('fallback')}")
    print(f"PROVENANCE: {r.get('provenance_status')}")
    print(f"RESPOSTA: {text[:300]}")
    try:
        route = validate_provenance(r, SELECTED)
        print(f"VALIDACAO: PASS ({route})")
        if text.strip():
            print("RESULTADO: PASS — a resposta chega a tela com proveniencia factual")
        else:
            print("RESULTADO: FAIL — resposta vazia")
    except ValueError as exc:
        print(f"VALIDACAO: FAIL — {exc}")

proc.terminate()
print("FIM", flush=True)
