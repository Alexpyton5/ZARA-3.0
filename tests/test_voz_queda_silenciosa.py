"""ZARA-VOZ-QUEDA-SILENCIOSA-001 — cair é normal; encher a conversa não é.

No histórico de 15/08, entre 08h40 e 09h01, a mesma queda apareceu doze vezes:
"keepalive ping timeout", "1006 abnormal closure", "timed out during opening
handshake". Cada uma virou uma linha de sistema na conversa do Alex, e ele abriu
o app e viu erro de websocket no meio do papo com a ZARA.

Duas coisas estavam erradas, e nenhuma era a queda em si:

  1. Recuo fixo de um segundo — bater de segundo em segundo numa conexão que
     está recusando não acelera a volta, só multiplica o erro.
  2. Toda tentativa falha virava recado — a décima segunda mensagem idêntica não
     informa nada, só faz ele parar de ler os avisos, inclusive os que importam.
"""
from __future__ import annotations

import inspect

from core import gemini_live_voice

FONTE = inspect.getsource(gemini_live_voice)


def test_o_recuo_cresce_em_vez_de_bater_de_um_em_um_segundo():
    assert "2 ** (self._quedas_seguidas - 1)" in FONTE, (
        "sem recuo crescente ela martela a API caída de segundo em segundo"
    )


def test_o_recuo_tem_teto():
    """Sem teto, na vigésima queda ela dormiria dias e nunca mais voltaria."""
    assert "min(2 ** (self._quedas_seguidas - 1), 30)" in FONTE


def test_so_a_primeira_queda_vira_recado_para_o_alex():
    trecho = FONTE[FONTE.index("_quedas_seguidas = getattr"):]
    trecho = trecho[:trecho.index("await asyncio.sleep(espera)")]
    assert "if self._quedas_seguidas == 1:" in trecho
    assert trecho.count("await self._emit_error(exc)") == 1


def test_toda_queda_continua_no_log_tecnico():
    """Silenciar para ele nao pode virar silenciar para mim."""
    assert "stage=LIVE_QUEDA" in FONTE
    assert "motivo=" in FONTE


def test_a_volta_tambem_e_avisada():
    """Avisar da queda e nao avisar da volta deixa ele achando que morreu."""
    assert "stage=LIVE_VOLTOU" in FONTE
    assert "A voz voltou" in FONTE


def test_o_contador_zera_quando_reconecta():
    """Sem zerar, a proxima queda ja comecaria com meio minuto de espera."""
    trecho = FONTE[FONTE.index("stage=LIVE_VOLTOU"):]
    assert "self._quedas_seguidas = 0" in trecho[:400]


def test_a_primeira_conexao_continua_falhando_alto():
    """Se ela nunca subiu, o erro tem de aparecer — nao e queda, e ausencia."""
    assert "if first_connection:" in FONTE
    assert "self._ready_error = exc" in FONTE
