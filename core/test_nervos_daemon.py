"""test_nervos_daemon.py — Testes da ronda da zoe (NERVOS Fase 2).

Roda com: python -m pytest core/test_nervos_daemon.py -v
(ou python core/test_nervos_daemon.py)
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nervos_daemon import NervosRonda, LIMITE_AUSENCIA_S


def _inbox_com(heartbeat):
    d = tempfile.mkdtemp(prefix="inbox-teste-")
    if heartbeat is not None:
        with open(os.path.join(d, "heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump(heartbeat, f)
    return d


def test_ronda_detecta_zoe_presente():
    inbox = _inbox_com({"ts": time.time(), "hora": "2026-09-27T22:00:00"})
    r = NervosRonda(inbox, intervalo_s=9999)
    s = r.get_status()
    assert s["zoe_presente"] is True, s
    assert s["idade_s"] is not None and s["idade_s"] < 5, s
    print("OK: detecta zoe presente")


def test_ronda_detecta_zoe_ausente_sinal_velho():
    inbox = _inbox_com({"ts": time.time() - (LIMITE_AUSENCIA_S + 60), "hora": "velho"})
    r = NervosRonda(inbox, intervalo_s=9999)
    s = r.get_status()
    assert s["zoe_presente"] is False, s
    print("OK: detecta zoe ausente (sinal velho)")


def test_ronda_sem_arquivo_nao_quebra():
    inbox = _inbox_com(None)
    r = NervosRonda(inbox, intervalo_s=9999)
    s = r.get_status()
    assert s["zoe_presente"] is False, s
    assert s["ultimo_sinal"] is None, s
    print("OK: sem heartbeat não quebra")


def test_ronda_json_invalido_nao_quebra():
    d = tempfile.mkdtemp(prefix="inbox-teste-")
    with open(os.path.join(d, "heartbeat.json"), "w", encoding="utf-8") as f:
        f.write("{json quebrado")
    r = NervosRonda(d, intervalo_s=9999)
    s = r.get_status()
    assert s["zoe_presente"] is False, s
    print("OK: json inválido não quebra")


def test_ronda_thread_inicia_e_para():
    inbox = _inbox_com({"ts": time.time()})
    r = NervosRonda(inbox, intervalo_s=0.05)
    r.iniciar()
    time.sleep(0.2)
    assert r._thread is not None and r._thread.is_alive()
    r.parar()
    assert not r._thread.is_alive()
    print("OK: thread inicia e para")


def test_ronda_e_so_monitoramento():
    # A ronda NUNCA altera nada: só lê e informa.
    inbox = _inbox_com({"ts": time.time()})
    antes = os.listdir(inbox)
    r = NervosRonda(inbox, intervalo_s=9999)
    r.atualizar()
    r.get_status()
    assert os.listdir(inbox) == antes, "a ronda escreveu no inbox!"
    print("OK: ronda é só leitura")


if __name__ == "__main__":
    test_ronda_detecta_zoe_presente()
    test_ronda_detecta_zoe_ausente_sinal_velho()
    test_ronda_sem_arquivo_nao_quebra()
    test_ronda_json_invalido_nao_quebra()
    test_ronda_thread_inicia_e_para()
    test_ronda_e_so_monitoramento()
    print("\n6/6 testes verdes.")
