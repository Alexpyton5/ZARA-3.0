#!/usr/bin/env python3
"""Teste fisico da voz da ZARA - para o Alex rodar em casa.

Duplo clique em TESTAR-VOZ-AGORA.bat e siga o que aparece na tela.
Linguagem simples de proposito: o relatorio final diz so OUVIU / NAO OUVIU.

O que ele faz (nada e gravado, nada sai do PC):
  1. A ZARA fala uma frase de teste (voce OUVE a voz dela).
  2. Voce fala 5 segundos no microfone e SE OUVE de volta.
  3. Mostra o resumo: qual voz falou e se o microfone funcionou.
"""
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FRASE_TESTE = "Oi Alex, aqui e a ZARA. Se voce esta ouvindo isso, a minha voz esta funcionando."


def falar(frase):
    """Faz a ZARA falar usando a mesma cascata do app. Retorna (ok, nome_da_voz)."""
    from core.voice_tts import TTSConfig, TTSManager

    cfg = TTSConfig(default_voice="pf_dora")
    mgr = TTSManager(cfg)
    mgr.initialize()
    ordem = []
    try:
        from core.voice_engine_policy import voice_output_order

        ordem = voice_output_order(
            cfg.output_engine,
            kore_ready=False,
            omnivoice_ready=mgr._omnivoice_ready(),
            edge_ready=bool(mgr.edge),
            kokoro_ready=bool(mgr.kokoro),
        )
    except Exception:
        pass
    try:
        mgr.speak(frase, blocking=True)
        voz = ordem[0] if ordem else "local"
        return True, voz
    except Exception as exc:
        return False, "erro: %s" % type(exc).__name__


def testar_microfone(segundos=5, taxa=44100):
    """Grava alguns segundos e toca de volta. Retorna (ok, detalhe)."""
    try:
        import sounddevice as sd
    except Exception as exc:
        return False, "microfone nao carregou (%s)" % type(exc).__name__
    try:
        entradas = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as exc:
        return False, "nao achei o microfone (%s)" % type(exc).__name__
    if not entradas:
        return False, "nenhum microfone detectado no PC"
    try:
        print("   gravando... fale agora!", flush=True)
        gravacao = sd.rec(int(segundos * taxa), samplerate=taxa, channels=1, dtype="float32")
        sd.wait()
        pico = float(abs(gravacao).max()) if gravacao.size else 0.0
        if pico < 0.005:
            return False, "microfone mudo (nao captou sua voz)"
        print("   agora voce vai se ouvir de volta...", flush=True)
        time.sleep(0.5)
        sd.play(gravacao, taxa)
        sd.wait()
        return True, "microfone OK"
    except Exception as exc:
        return False, "falha no microfone (%s)" % type(exc).__name__


def main():
    print("=" * 52)
    print("  TESTE DA VOZ DA ZARA")
    print("=" * 52)
    print()
    print("PASSO 1 de 2 - OUVIR: a ZARA vai falar agora.")
    print("Aumente o volume e preste atencao...")
    print()
    time.sleep(1)
    ok_voz, voz = falar(FRASE_TESTE)
    print()
    if ok_voz:
        print("[OK] A ZARA falou (voz usada: %s)." % voz)
        print("     Voce ouviu a frase? Guarde a resposta para o passo final.")
    else:
        print("[FALHOU] A ZARA nao conseguiu falar (%s)." % voz)
        print("         Mostre essa tela para a zoe.")
    print()
    print("-" * 52)
    print("PASSO 2 de 2 - FALAR: teste do microfone.")
    input("Aperte ENTER e fale por 5 segundos (ex: 'testando um dois tres')... ")
    print()
    ok_mic, detalhe_mic = testar_microfone()
    print()
    print("=" * 52)
    print("  RESUMO")
    print("=" * 52)
    print("Voz da ZARA : %s" % ("OUVIU" if ok_voz else "NAO OUVIU"))
    print("Microfone   : %s" % ("OUVIU (se ouviu de volta)" if ok_mic else "NAO OUVIU"))
    if not ok_mic:
        print("              detalhe: %s" % detalhe_mic)
    print()
    if ok_voz and ok_mic:
        print("Tudo certo! Pode mandar esse resumo para a zoe: VOZ OK, MIC OK.")
    else:
        print("Algo falhou. Tire uma foto dessa tela e mande para a zoe.")
    return 0 if (ok_voz and ok_mic) else 1


if __name__ == "__main__":
    raise SystemExit(main())
