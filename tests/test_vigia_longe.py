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
    (120.0, False),     # LENDO uma resposta longa: o furo que ele achou primeiro
    (299.0, False),     # quase cinco minutos: ainda pode estar lendo
    (301.0, True),      # cinco minutos parado: levantou
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


# ---------- ZARA-ONDE-ELE-ESTA-001 ----------
#
# Alex, depois de eu errar duas vezes seguidas o criterio de presenca:
#
#   "quando eu nao digitar aqui nesse chat por trinta minutos, voce ja sabe que
#    eu nao estou aqui, principalmente se eu digitar pelo Telegram e nao digitar
#    aqui, porque sempre que eu estou aqui, eu digito aqui."
#
# A regra dele e melhor que a minha: eu estava adivinhando presenca pelo
# teclado, e ele estava me dando um FATO. Ninguem escreve no celular estando na
# frente do computador.


def _com_canal(canal, ha_quantos_segundos):
    import time as _t
    h = IPCHandler.__new__(IPCHandler)
    h._ultimo_canal = (canal, _t.time() - ha_quantos_segundos)
    h._tela_bloqueada = staticmethod(lambda: False)
    h._ocioso_ha_quantos_segundos = staticmethod(lambda: 0.0)
    return h


def test_falou_pelo_telegram_significa_que_esta_no_telegram():
    """O caso que quebrou o dia dele: saiu, escreveu do celular, e ficou sem
    resposta porque o teclado do PC dizia que ele estava presente."""
    assert _com_canal("telegram", 60)._alex_esta_longe() is True


def test_digitou_no_app_significa_que_esta_no_computador():
    assert _com_canal("computador", 60)._alex_esta_longe() is False


def test_o_canal_vale_mais_que_o_teclado():
    """Teclado parado nao pode contradizer o fato de ele ter escrito no app."""
    h = _com_canal("computador", 30)
    h._ocioso_ha_quantos_segundos = staticmethod(lambda: 99999.0)

    assert h._alex_esta_longe() is False


def test_o_canal_vale_mais_que_a_tela_bloqueada():
    """Ele pode ter bloqueado a tela e continuar ali, de pe, olhando."""
    h = _com_canal("computador", 30)
    h._tela_bloqueada = staticmethod(lambda: True)

    assert h._alex_esta_longe() is False


def test_canal_velho_devolve_a_decisao_para_o_teclado():
    """Passada a janela, o ultimo canal nao prova mais nada sobre agora."""
    h = _com_canal("computador", IPCHandler._JANELA_DO_CANAL + 60)
    h._ocioso_ha_quantos_segundos = staticmethod(lambda: 99999.0)

    assert h._alex_esta_longe() is True


def test_sem_canal_nenhum_cai_no_criterio_antigo():
    h = IPCHandler.__new__(IPCHandler)
    h._tela_bloqueada = staticmethod(lambda: True)
    h._ocioso_ha_quantos_segundos = staticmethod(lambda: 0.0)

    assert h._alex_esta_longe() is True


def test_a_janela_e_a_que_ele_pediu():
    assert IPCHandler._JANELA_DO_CANAL == 30 * 60
