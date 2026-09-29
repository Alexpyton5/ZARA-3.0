# -*- coding: utf-8 -*-
"""Exemplo FRENTE H: relatorio da manha gerado dos dados reais de 28/09."""
import json
import sys

sys.path.insert(0, r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002")

from core.morning_report import (
    ItemNoite,
    auditoria,
    coletar_fatos,
    gerar_relatorio,
    traduzir,
)

RAIZ = r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
fatos = coletar_fatos(RAIZ)

print("== FATOS COLETADOS (24h) ==")
for sha, assunto in fatos.commits:
    print(" commit", sha, "-", assunto[:70])
print(" suite:", json.dumps(fatos.suite, ensure_ascii=False))
print(" concluidos:", fatos.concluidos)

# Traducoes curadas pelo especialista — 1 frase simples por entrega,
# cada uma com a fonte real onde foi verificada. Nada inventado.
MAPA = {
    "47c3234": "A sala do Lab ganhou uma faixa que mostra ao vivo o que o supervisor esta fazendo",
    "806a016": "Os 11 robos do Lab estao prontos e ja trocam recados entre si de verdade",
    "753fcba": "O Lab agora se atualiza sozinho com seguranca: se algo vier quebrado, ele bloqueia e desfaz",
    "f9c4f7c": "A voz reserva do app esta pronta: se a voz principal falhar, a outra assume sozinha",
}

itens, sem_traducao = traduzir(fatos, MAPA)

# Entrega verificada sem commit proprio (pedido direto dele, QUADRO 10:39)
itens.append(ItemNoite(
    texto="Os testes do app agora rodam sozinhos a cada 6 horas e so avisam se algo novo quebrar",
    fonte="QUADRO 28/09 10:39 + baseline .zara-tests/auto_suite_baseline.json",
    tocavel=True,
))

print()
print("== RELATORIO (formato dele) ==")
print(gerar_relatorio(itens))
print()
print("== AUDITORIA ==")
print(auditoria(itens))
print()
print("sem_traducao (p/ o loop curar):", sem_traducao)
