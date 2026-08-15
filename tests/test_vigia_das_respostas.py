"""ZARA-VIGIA-001 — ela avisa quando o Claude ou o Codex terminam de responder.

O risco desta funcionalidade não é deixar de avisar: é avisar demais. Um agente
escreve em pedaços, e um alarme a cada pedaço seria pior que nenhum alarme.

Estes testes travam as quatro regras que a tornam suportável:
  1. avisa quando o texto novo PARA de crescer (o outro terminou);
  2. não avisa enquanto o texto ainda está crescendo;
  3. não avisa duas vezes a mesma resposta;
  4. não avisa por cima da fala dela nem da fala do Alex.
"""
from __future__ import annotations

import asyncio

import pytest

from core.vigia_das_respostas import VigiaDasRespostas


def _vigia(avisos, **kw):
    async def avisar(texto):
        avisos.append(texto)

    v = VigiaDasRespostas(avisar, vigiar_codex=False, **kw)
    return v


@pytest.mark.asyncio
async def test_avisa_quando_a_resposta_para_de_crescer(monkeypatch):
    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)
    avisos: list[str] = []
    v = _vigia(avisos)

    # Simula o ciclo interno: apareceu texto novo, depois ele parou de mudar.
    v._ultimo["claude"] = "antigo"
    leituras = iter(["resposta nova", "resposta nova", "resposta nova"])
    monkeypatch.setattr(
        "core.vigia_das_respostas._INTERVALO_CLAUDE", 0.01
    )

    tarefa = asyncio.create_task(v._vigiar("claude", lambda: next(leituras, "resposta nova"), 0.01))
    await asyncio.sleep(0.15)
    await v.parar()
    tarefa.cancel()

    assert avisos == ["O Claude respondeu."]


@pytest.mark.asyncio
async def test_nao_avisa_enquanto_ainda_esta_escrevendo(monkeypatch):
    """Texto crescendo = ele não terminou. Avisar aqui vira alarme constante."""
    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 5.0)
    avisos: list[str] = []
    v = _vigia(avisos)
    v._ultimo["claude"] = ""

    crescendo = iter(["a", "ab", "abc", "abcd", "abcde"])
    tarefa = asyncio.create_task(
        v._vigiar("claude", lambda: next(crescendo, "abcde"), 0.01)
    )
    await asyncio.sleep(0.1)
    await v.parar()
    tarefa.cancel()

    assert avisos == []


@pytest.mark.asyncio
async def test_nao_avisa_duas_vezes_a_mesma_resposta(monkeypatch):
    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)
    avisos: list[str] = []
    v = _vigia(avisos)
    v._ultimo["claude"] = "antigo"

    tarefa = asyncio.create_task(v._vigiar("claude", lambda: "mesma resposta", 0.01))
    await asyncio.sleep(0.2)
    await v.parar()
    tarefa.cancel()

    assert len(avisos) == 1, f"avisou {len(avisos)} vezes"


@pytest.mark.asyncio
async def test_nao_fala_por_cima_dela_nem_do_alex(monkeypatch):
    """Aviso é útil; atropelo não."""
    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)
    avisos: list[str] = []
    v = _vigia(avisos, pode_avisar=lambda: False)
    v._ultimo["claude"] = "antigo"

    tarefa = asyncio.create_task(v._vigiar("claude", lambda: "resposta nova", 0.01))
    await asyncio.sleep(0.1)
    await v.parar()
    tarefa.cancel()

    assert avisos == []


@pytest.mark.asyncio
async def test_o_que_ja_estava_na_tela_nao_e_novidade(monkeypatch):
    """Ao ligar, a conversa que já existia não pode disparar aviso."""
    monkeypatch.setattr(
        "core.vigia_das_respostas.VigiaDasRespostas._ler_claude",
        staticmethod(lambda: "conversa que ja existia"),
    )
    avisos: list[str] = []
    v = _vigia(avisos)

    await v.iniciar()
    await asyncio.sleep(0.05)
    await v.parar()

    assert avisos == []
    assert v._ultimo["claude"] == "conversa que ja existia"


@pytest.mark.asyncio
async def test_falha_ao_ler_nao_derruba_a_voz(monkeypatch):
    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)
    avisos: list[str] = []
    v = _vigia(avisos)

    def explode():
        raise RuntimeError("janela sumiu")

    tarefa = asyncio.create_task(v._vigiar("claude", explode, 0.01))
    await asyncio.sleep(0.08)
    await v.parar()
    tarefa.cancel()

    assert avisos == []  # falhou calado, sem derrubar nada


# ---------- ZARA-VIGIA-CONTEUDO-001 ----------

@pytest.mark.asyncio
async def test_o_aviso_leva_o_texto_junto(monkeypatch):
    """Alex: "porque nao ta aparecendo o que voces tao conversando la no telegram?"

    Porque o vigia mandava so o aviso: "O Codex respondeu." No computador da
    para virar a cabeca e ler. No celular, nao — saber que existe uma resposta
    ilegivel e pior do que nao ser avisado.

    A frase curta continua existindo, porque e ela que vai para a voz. Quem
    separa uma coisa da outra e quem recebe o aviso, nao o vigia.
    """
    import asyncio

    from core.vigia_das_respostas import VigiaDasRespostas

    recebidos = []

    async def avisar(frase, conteudo=""):
        recebidos.append((frase, conteudo))

    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)

    vigia = VigiaDasRespostas(avisar, pode_avisar=lambda: True)
    resposta = "Chegou perfeitamente, Claude. A ponte esta funcionando."

    tarefa = asyncio.create_task(vigia._vigiar("codex", lambda: resposta, 0.01))
    for _ in range(60):
        if recebidos:
            break
        await asyncio.sleep(0.02)
    tarefa.cancel()

    assert recebidos, "o vigia nao avisou"
    frase, conteudo = recebidos[0]
    assert frase == "O Codex respondeu.", "a voz continua curta"
    assert conteudo == resposta, "o celular precisa do texto inteiro"


@pytest.mark.asyncio
async def test_vigia_nao_quebra_com_aviso_de_um_argumento_so(monkeypatch):
    """Compatibilidade: um ouvinte antigo nao pode derrubar o vigia."""
    import asyncio

    from core.vigia_das_respostas import VigiaDasRespostas

    recebidos = []

    async def avisar_antigo(frase):
        recebidos.append(frase)

    monkeypatch.setattr("core.vigia_das_respostas._SILENCIO_PARA_CONCLUIR", 0.0)

    vigia = VigiaDasRespostas(avisar_antigo, pode_avisar=lambda: True)
    tarefa = asyncio.create_task(vigia._vigiar("claude", lambda: "pronto", 0.01))
    for _ in range(60):
        if recebidos:
            break
        await asyncio.sleep(0.02)
    tarefa.cancel()

    assert recebidos == ["O Claude respondeu."]
