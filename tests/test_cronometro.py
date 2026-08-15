"""ZARA-LATENCIA-MEDIDA-001 — medir antes de otimizar.

Alex reclama que a ZARA é lenta desde o começo, e essa reclamação nunca foi
medida: foi sentida. A única medição que houve mostrou que o raciocínio dela
custa centésimos de segundo — ou seja, quem "otimizasse o cérebro" estaria
mexendo na parte que já é rápida.

Os marcadores `[VOICE_TRACE]` medem, mas só no console, e o console morre com o
app. Ninguém está com o terminal aberto na hora em que ele acha lento.

O que estes testes travam:
  1. o turno é gravado em disco e sobrevive ao app fechar;
  2. o relatório usa MEDIANA, para um turno travado não disfarçar vinte rápidos;
  3. o arquivo não cresce para sempre no computador dele;
  4. medir jamais derruba a voz.
"""
from __future__ import annotations

import json

import pytest

from core import cronometro


@pytest.fixture(autouse=True)
def _arquivo_isolado(monkeypatch, tmp_path):
    alvo = tmp_path / "latencia.jsonl"
    monkeypatch.setattr(cronometro, "_arquivo", lambda: alvo)
    return alvo


def test_o_turno_fica_gravado_em_disco(_arquivo_isolado):
    """O console some quando o app fecha; o arquivo não."""
    c = cronometro.Cronometro("aumenta o volume", origem="voz")
    c.marcar("antes_de_falar")
    c.fechar(rota="voz", voz="gemini_live/Kore", falou=True)

    linhas = _arquivo_isolado.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 1
    registro = json.loads(linhas[0])
    assert registro["rota"] == "voz"
    assert registro["falou"] is True
    assert registro["ouvidos"] == len("aumenta o volume")
    assert "antes_de_falar" in registro["etapas"]


def test_separa_o_pensar_do_falar(_arquivo_isolado):
    """A conta que decide a próxima otimização.

    `antes_de_falar` é tudo até a ação estar feita. O que sobra até o total é a
    segunda viagem: o preço de FALAR uma frase que já estava pronta.
    """
    c = cronometro.Cronometro("abre o youtube")
    c.marcar("antes_de_falar")
    c.fechar(rota="voz", falou=True)

    registro = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert registro["etapas"]["antes_de_falar"] <= registro["total_ms"]


def test_o_relatorio_usa_mediana_e_nao_media(_arquivo_isolado):
    """Um turno de 30 s esperando a rede não pode afundar vinte turnos bons."""
    for ms in (100, 100, 100, 100, 30_000):
        _arquivo_isolado.parent.mkdir(parents=True, exist_ok=True)
        with _arquivo_isolado.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps({
                "quando": 1.0, "rota": "voz", "total_ms": ms, "etapas": {"antes_de_falar": 50},
            }) + "\n")

    r = cronometro.relatorio()

    assert r["turnos"] == 5
    assert r["total_ms_mediano"] == 100, "a média daria 6080 e mentiria sobre o dia a dia"


def test_sem_medicao_nenhuma_ele_avisa_em_vez_de_inventar():
    r = cronometro.relatorio()

    assert r["turnos"] == 0
    assert "aviso" in r


def test_o_arquivo_nao_cresce_para_sempre(monkeypatch, _arquivo_isolado):
    monkeypatch.setattr(cronometro, "_LIMITE_DE_LINHAS", 10)

    for i in range(25):
        cronometro.Cronometro(f"turno {i}").fechar(rota="voz")

    linhas = _arquivo_isolado.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) <= 10


def test_medir_nunca_derruba_a_voz(monkeypatch):
    """Um cronômetro que quebra a fala seria pior do que não medir nada."""
    monkeypatch.setattr(cronometro, "_arquivo", lambda: (_ for _ in ()).throw(OSError("disco cheio")))

    c = cronometro.Cronometro("oi")
    c.marcar("antes_de_falar")

    registro = c.fechar(rota="voz")  # não pode levantar

    assert registro["rota"] == "voz"
    assert cronometro.relatorio()["turnos"] == 0


# ---------- ZARA-DESCARTE-SEM-SEGREDO-001 ----------
#
# Achado 18 da auditoria do Codex: o registro guardava 160 caracteres exatos do
# que foi descartado, em texto puro, no computador do Alex.
#
# E o que e descartado e justamente o que ela NAO deveria estar ouvindo:
# conversa de fundo, televisao, alguem no telefone. Se uma dessas falas contiver
# uma senha ou um assunto particular de outra pessoa, aquilo virava arquivo.


def test_a_frase_inteira_nao_vai_para_o_disco(_arquivo_isolado):
    cronometro.anotar_descarte(
        "entao eu falei pra ela que o combinado era outro e ela nao aceitou de jeito nenhum",
        "sem_wake_e_fora_da_janela",
    )

    r = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert "frase" not in r, "o campo que guardava a fala inteira precisa sumir"
    assert len(r["inicio"]) < 40
    assert "nao aceitou" not in r["inicio"]


def test_o_tamanho_e_o_motivo_continuam(_arquivo_isolado):
    """Sem eles o registro perde a razao de existir: quanto e por que."""
    frase = "uma frase qualquer de fundo"
    cronometro.anotar_descarte(frase, "eco_da_propria_voz")

    r = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert r["ouvidos"] == len(frase)
    assert r["motivo"] == "eco_da_propria_voz"


def test_da_para_reconhecer_o_tipo_da_fala(_arquivo_isolado):
    """Quatro palavras bastam para eu saber que aquilo era televisao."""
    cronometro.anotar_descarte("no canguru eles nao aceitaram nenhuma das minhas ideias", "x")

    r = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert r["inicio"].startswith("no canguru")
    assert r["inicio"].endswith("...")


@pytest.mark.parametrize("fala", [
    "minha senha é aquela de sempre",
    "o codigo do cartao e",
    "anota o cpf dele",
    "a chave secreta fica no cofre",
])
def test_fala_com_cheiro_de_segredo_nao_deixa_nem_o_comeco(_arquivo_isolado, fala):
    cronometro.anotar_descarte(fala, "sem_wake_e_fora_da_janela")

    r = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert r["inicio"] == "[assunto sensível]"
    assert "senha" not in json.dumps(r).casefold() or r["inicio"] == "[assunto sensível]"


def test_frase_vazia_nao_quebra(_arquivo_isolado):
    cronometro.anotar_descarte("", "motivo")

    r = json.loads(_arquivo_isolado.read_text(encoding="utf-8").strip())
    assert r["inicio"] == ""
