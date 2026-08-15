"""ZARA-VIGIA-LONGE-001 — o celular só recebe o texto quando ele não está aqui.

Alex: "suas respostas tao saindo aqui e la ainda no telegram".

Mandar a resposta inteira para o celular resolveu uma reclamação ("porque nao
aparece o que voces tao conversando la?") e criou outra: sentado lendo na tela,
o celular apitava a mesma coisa. Aviso repetido vira aviso ignorado — e aí ele
para de olhar justamente quando importa.

O critério não é mais uma opção para ele configurar. É o teclado dele.
"""
from __future__ import annotations

import pytest

from core.ipc_handlers import IPCHandler


def _handler(ocioso: float, bloqueada: bool = False):
    h = IPCHandler.__new__(IPCHandler)
    h._ocioso_ha_quantos_segundos = staticmethod(lambda: ocioso)
    h._tela_bloqueada = staticmethod(lambda: bloqueada)
    return h


@pytest.mark.parametrize("ocioso,longe", [
    (0.0, False),       # digitando agora
    (5.0, False),       # acabou de parar
    (300.0, False),     # LENDO uma resposta longa: foi o furo que o Alex achou
    (900.0, False),     # quinze minutos lendo ainda e ele na cadeira
    (1801.0, True),     # meia hora parado com a tela aberta: saiu sem bloquear
])
def test_tempo_parado_sozinho_nao_condena_ninguem(ocioso, longe):
    """A primeira versao dizia "longe" com 3 minutos parados.

    Alex derrubou: "como assim quando eu tiver longe do computador?". Ler uma
    resposta longa passa facil de 3 minutos sem tocar em nada, e ele estaria
    sentado na cadeira classificado como ausente.
    """
    assert _handler(ocioso)._alex_esta_longe() is longe


def test_tela_bloqueada_e_prova_suficiente():
    """Bloqueou = nao esta vendo. Nao precisa de mais nada."""
    assert _handler(0.0, bloqueada=True)._alex_esta_longe() is True


def test_sem_conseguir_medir_assume_que_ele_esta_aqui():
    """Errar para o silêncio é melhor que errar para o celular apitando."""
    assert _handler(0.0, bloqueada=False)._alex_esta_longe() is False


def test_a_leitura_da_tela_nao_explode():
    assert isinstance(IPCHandler._tela_bloqueada(), bool)


def test_a_medicao_real_nao_explode():
    """No Windows tem de funcionar; em qualquer outro lugar, devolver 0."""
    valor = IPCHandler._ocioso_ha_quantos_segundos()

    assert isinstance(valor, float)
    assert valor >= 0.0
