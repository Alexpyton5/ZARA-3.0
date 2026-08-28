#!/usr/bin/env python3
"""ZARA 3.0 — auditoria de compreensao de fala natural. NENHUMA acao e executada.

Roda o PcVoiceIntentDetector real contra as frases que Alex usaria de verdade e
mede quantos comandos a ZARA entende. Nivel de evidencia: TEST.

Serve como guarda de regressao: ao mexer em core/pc_voice_intent.py, rodar isto
antes e depois. "comandos PERDIDOS" nunca deve subir, e "falsos positivos"
(conversa virando comando) tem de permanecer ZERO — falso positivo e a porta de
entrada do falso sucesso.

Historico:
  2026-08-12 antes do ZARA-VOICE-VERBOS: 27 entendidos / 46 perdidos
  2026-08-12 depois                     : 67 entendidos /  6 perdidos / 0 falsos
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.pc_voice_intent import PcVoiceIntentDetector as D

FRASES = {
"VOLUME": ["diminui o volume","abaixa o volume","aumenta o volume","sobe o volume","coloca o volume em 30",
           "poe o volume a 50","volume 20","muta","tira o som","volta o som","deixa mudo"],
"BRILHO": ["diminui o brilho","abaixa o brilho ai","aumenta o brilho","coloca o brilho em 70","escurece","clareia"],
"NIGHT":  ["ativa o modo noturno","liga a luz noturna","desliga o modo noturno","tira o modo noturno"],
"WIFI":   ["liga o wifi","desliga o wifi","ativa o wi-fi","o wifi ta ligado?"],
"BLUET":  ["liga o bluetooth","desliga o bluetooth"],
"APPS":   ["abre o chrome","abre a calculadora","abre o bloco de notas","fecha o chrome","abre o spotify",
           "abre a pasta downloads","abre meus documentos"],
"JANELA": ["minimiza","minimiza essa janela","maximiza","restaura a janela","fecha essa janela",
           "move a janela pra esquerda","aumenta essa janela","vai pra proxima janela","foca no chrome"],
"YOUTUBE":["abre o youtube","va para o youtube","procura pink floyd no youtube","toca pink floyd",
           "pausa","continua","proxima","pula essa","o que ta tocando?","pula o anuncio",
           "coloca outra dele","avanca 30 segundos"],
"BROWSER":["abre uma aba nova","volta no navegador","avanca no navegador","fecha essa aba",
           "rola a pagina pra baixo","o que diz essa pagina","pesquisa receita de bolo"],
"SISTEMA":["que horas sao?","como esta o computador","quanto de bateria","lista os processos",
           "mostra as informacoes do sistema","como esta o audio"],
"OUTROS": ["tira uma captura de tela","copia isso pra area de transferencia","le a area de transferencia",
           "mostra uma notificacao dizendo oi","digita bom dia"],
"CONVERSA_NAO_E_COMANDO": ["oi tudo bem","me conta uma piada","o que voce acha disso",
           "quem foi einstein","obrigado","voce e legal"],
}

d = D(pc_control_allowed=False)
res = {}
for cat, fs in FRASES.items():
    res[cat] = []
    for f in fs:
        r = d.detect(f)
        res[cat].append((f, r.action if r.is_pc_intent else None, r.blocked))

tot = pega = perde = falso = 0
print("="*94)
print("AUDITORIA DE COMPREENSAO — fala natural  (Supercerebro OFF, nada executado)")
print("="*94)
for cat, itens in res.items():
    conversa = cat.startswith("CONVERSA")
    print(f"\n--- {cat} ---")
    for f, act, blk in itens:
        tot += 1
        if conversa:
            ok = act is None
            if not ok: falso += 1
        else:
            ok = act is not None and not blk
            if ok: pega += 1
            else: perde += 1
        flag = "OK " if ok else ("BLOQ" if blk else "NAO")
        print(f"  {flag:4} {f:44} -> {act}")
print("\n"+"="*94)
print(f"comandos entendidos : {pega}")
print(f"comandos PERDIDOS   : {perde}")
print(f"falsos positivos    : {falso}  (conversa virando comando)")
print("="*94)
