"""Testes de core/ditado.py — modo ditado universal v1 (ETAPA 1, isolada).

Tudo injetado: nenhum teste toca microfone, alto-falante ou teclado de
verdade. O STT, a limpeza, a digitacao, o foco e a janela sao funcoes falsas.
"""

import pytest

from core.ditado import (
    DitadoController,
    PreRollBuffer,
    ResultadoDitado,
)


def _fazer_controller(**kwargs):
    padrao = {
        "transcrever_fn": lambda audio: "texto transcrito",
        "digitar_fn": lambda texto: True,
    }
    padrao.update(kwargs)
    return DitadoController(**padrao)


# ---------------------------------------------------------------------------
# PreRollBuffer
# ---------------------------------------------------------------------------


def test_preroll_descarrega_em_ordem_e_esvazia():
    buf = PreRollBuffer(capacidade_bytes=100)
    buf.alimentar(b"aa")
    buf.alimentar(b"bb")
    assert buf.descarregar() == b"aabb"
    assert len(buf) == 0
    assert buf.descarregar() == b""


def test_preroll_descarta_o_mais_antigo():
    buf = PreRollBuffer(capacidade_bytes=4)
    buf.alimentar(b"aa")
    buf.alimentar(b"bb")
    buf.alimentar(b"cc")  # estoura: "aa" cai
    assert buf.descarregar() == b"bbcc"


def test_preroll_frame_maior_que_capacidade():
    buf = PreRollBuffer(capacidade_bytes=2)
    buf.alimentar(b"abcdef")
    # Nao ha como guardar 6 bytes em 2: o buffer fica com o fim do frame.
    # O invariante que importa: nunca passa da capacidade.
    assert len(buf) <= 2


def test_preroll_para_taxa_dimensiona_500ms():
    buf = PreRollBuffer.para_taxa(taxa_hz=16000, bytes_por_amostra=2)
    assert buf.capacidade == 16000  # 16000 * 2 * 0.5


def test_preroll_limpar_e_frame_vazio():
    buf = PreRollBuffer(capacidade_bytes=10)
    buf.alimentar(b"ab")
    buf.alimentar(b"")
    buf.alimentar(None)
    buf.limpar()
    assert len(buf) == 0


# ---------------------------------------------------------------------------
# DitadoController — fluxo feliz
# ---------------------------------------------------------------------------


def test_fluxo_feliz_cola_texto_limpo():
    colados = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "uh eu quero abrir o excel",
        limpar_fn=lambda t: "Eu quero abrir o Excel.",
        digitar_fn=lambda texto: colados.append(texto) or True,
    )
    assert ctrl.tecla_pressionada() is True
    ctrl.alimentar_audio(b"\x00\x01")
    resultado = ctrl.tecla_solta()

    assert isinstance(resultado, ResultadoDitado)
    assert resultado.motivo == "ok"
    assert resultado.colado is True
    assert resultado.texto_final == "Eu quero abrir o Excel."
    assert resultado.usou_guard is False
    assert colados == ["Eu quero abrir o Excel."]
    assert ctrl.estado == "ocioso"


def test_primeira_palavra_nao_e_cortada_pre_roll_vem_primeiro():
    recebidos = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: recebidos.append(audio) or "oi",
    )
    # O loop alimenta o pre-roll ANTES da tecla (o Alex ja estava falando).
    ctrl.alimentar_audio(b"ANTES")
    assert ctrl.tecla_pressionada() is True
    ctrl.alimentar_audio(b"DEPOIS")
    ctrl.tecla_solta()

    assert recebidos == [b"ANTESDEPOIS"]


def test_guard_barra_alucinacao_da_limpeza():
    colados = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "comprar pão",
        limpar_fn=lambda t: "Comprar pão e o balanço anual da empresa",
        digitar_fn=lambda texto: colados.append(texto) or True,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.usou_guard is True
    assert resultado.texto_final == "comprar pão"  # o cru venceu
    assert resultado.similaridade < 0.80
    assert colados == ["comprar pão"]


def test_sem_limpeza_usa_o_cru_direto():
    colados = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "  texto cru  ",
        limpar_fn=None,
        digitar_fn=lambda texto: colados.append(texto) or True,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "ok"
    assert resultado.texto_final == "texto cru"
    assert resultado.usou_guard is False
    assert colados == ["texto cru"]


# ---------------------------------------------------------------------------
# Falhas honestas (fail-closed)
# ---------------------------------------------------------------------------


def test_transcricao_vazia_nunca_cola():
    chamadas = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "   ",
        digitar_fn=lambda texto: chamadas.append(texto) or True,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "transcricao_vazia"
    assert resultado.colado is False
    assert resultado.texto_final == ""
    assert chamadas == []
    assert "entendi" in resultado.mensagem.lower()


def test_solta_sem_pressionar_nao_faz_nada():
    chamadas = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: chamadas.append(audio) or "x",
    )
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "sem_gravacao"
    assert chamadas == []


def test_transcritor_quebrando_vira_motivo_honesto():
    def quebrar(audio):
        raise RuntimeError("mic sumiu")

    ctrl = _fazer_controller(transcrever_fn=quebrar)
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()  # nao levanta

    assert resultado.motivo == "transcricao_falhou"
    assert resultado.colado is False


def test_digitacao_quebrando_vira_motivo_honesto():
    def quebrar(texto):
        raise RuntimeError("campo sumiu")

    ctrl = _fazer_controller(digitar_fn=quebrar)
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "falha_digitacao"
    assert resultado.texto_final == "texto transcrito"


def test_digitacao_retornando_false():
    ctrl = _fazer_controller(digitar_fn=lambda texto: False)
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "falha_digitacao"
    assert resultado.colado is False


def test_press_duplo_ignora_o_segundo():
    recebidos = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: recebidos.append(audio) or "x",
    )
    assert ctrl.tecla_pressionada() is True
    ctrl.alimentar_audio(b"um")
    assert ctrl.tecla_pressionada() is False  # nao reinicia a tomada
    ctrl.alimentar_audio(b"dois")
    ctrl.tecla_solta()

    assert recebidos == [b"umdois"]


def test_cancelar_descarta_a_tomada():
    chamadas = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: chamadas.append(audio) or "x",
    )
    ctrl.tecla_pressionada()
    ctrl.alimentar_audio(b"bla")
    ctrl.cancelar()
    assert ctrl.estado == "ocioso"
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "sem_gravacao"
    assert chamadas == []


# ---------------------------------------------------------------------------
# Foco / fallback window (item 16)
# ---------------------------------------------------------------------------


def test_sem_foco_vai_para_a_janela():
    na_janela = []
    colados = []
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "texto importante",
        tem_foco_fn=lambda: False,
        janela_fn=lambda texto: na_janela.append(texto),
        digitar_fn=lambda texto: colados.append(texto) or True,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "sem_foco_janela"
    assert resultado.colado is False
    assert resultado.texto_final == "texto importante"
    assert na_janela == ["texto importante"]
    assert colados == []


def test_sem_foco_sem_janela_texto_nao_some():
    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "texto importante",
        tem_foco_fn=lambda: False,
        janela_fn=None,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "sem_foco"
    assert resultado.texto_final == "texto importante"


def test_foco_quebrando_assume_sem_foco():
    def quebrar():
        raise RuntimeError("sem win32")

    ctrl = _fazer_controller(
        transcrever_fn=lambda audio: "x",
        tem_foco_fn=quebrar,
        janela_fn=None,
    )
    ctrl.tecla_pressionada()
    resultado = ctrl.tecla_solta()

    assert resultado.motivo == "sem_foco"
