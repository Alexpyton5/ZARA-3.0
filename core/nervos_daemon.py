"""nervos_daemon.py — Ronda da zoe (NERVOS Fase 2).

Vigia o heartbeat.json da ponte e expõe o estado da presença da zoe
para o app. NÃO controla nada sozinho: é só monitoramento (ronda).
A chave do supercérebro é manual do Alex (MISSÃO 03).

Uso:
    from core.nervos_daemon import NervosRonda
    ronda = NervosRonda(inbox_dir=".../ZOE-INBOX")
    ronda.get_status()  # {"zoe_presente": bool, "ultimo_sinal": str, "idade_s": float}
    ronda.iniciar()     # thread de ronda; ronda.parar() para encerrar.

Stdlib puro, zero dependências.
"""
from __future__ import annotations

import json
import os
import threading
import time

HEARTBEAT_ARQUIVO = "heartbeat.json"
# Sem sinal fresco por mais que isso, a zoe é considerada ausente (só informa).
LIMITE_AUSENCIA_S = 600


class NervosRonda:
    def __init__(self, inbox_dir: str, intervalo_s: float = 60.0):
        self.inbox_dir = inbox_dir
        self.intervalo_s = intervalo_s
        self._status = {"zoe_presente": False, "ultimo_sinal": None, "idade_s": None}
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()
        self.atualizar()

    def _ler_heartbeat(self) -> dict | None:
        caminho = os.path.join(self.inbox_dir, HEARTBEAT_ARQUIVO)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def atualizar(self) -> dict:
        hb = self._ler_heartbeat()
        agora = time.time()
        if not hb:
            novo = {"zoe_presente": False, "ultimo_sinal": None, "idade_s": None}
        else:
            ts = hb.get("ts") or hb.get("timestamp") or hb.get("hora") or 0
            try:
                ts_f = float(ts)
            except (TypeError, ValueError):
                ts_f = 0.0
            idade = agora - ts_f if ts_f > 0 else None
            presente = idade is not None and idade <= LIMITE_AUSENCIA_S
            novo = {"zoe_presente": presente, "ultimo_sinal": hb.get("hora") or ts, "idade_s": idade}
        with self._lock:
            self._status = novo
            return dict(novo)

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _loop(self):
        while not self._parar.wait(self.intervalo_s):
            try:
                self.atualizar()
            except Exception:
                pass

    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="nervos-ronda")
        self._thread.start()

    def parar(self):
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=5)
