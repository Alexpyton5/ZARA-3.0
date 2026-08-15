"""Isolamento de dados reais durante os testes.

Descoberto em 15/08, olhando o arquivo de medição de latência da máquina do
Alex: havia 40 registros de descarte, e parte deles eram **frases de teste** —
"e por isso que o ceu e azul", "abra o chrome agora para continuar". A suíte
estava escrevendo no arquivo de dados dele.

Isso é pior do que sujeira: aquele arquivo existe para responder "onde o tempo da
ZARA está indo" e "o que ela descartou em silêncio". Misturar frase de teste com
fala real do Alex envenena exatamente a evidência que ele usa para decidir — e
este projeto inteiro é construído sobre a evidência ser confiável.

A instrumentação nova (`core/cronometro.py`) é chamada de dentro do caminho de
voz, então qualquer teste que exercite wake gate ou eco escreve lá sem querer.
Isolar aqui, uma vez, protege a suíte inteira — inclusive os testes que ainda
não existem, que é onde o mesmo erro voltaria.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _nunca_escrever_nos_dados_do_alex(monkeypatch, tmp_path):
    """Manda toda medição para uma pasta temporária do próprio teste."""
    from core import cronometro

    monkeypatch.setattr(
        cronometro, "_arquivo", lambda: tmp_path / "latencia.jsonl", raising=False
    )
