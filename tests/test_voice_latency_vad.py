"""ZARA-VOICE-LATENCY-002 — a espera antes de ela começar a responder.

O dispatcher da ZARA responde em centésimos de segundo (medido no histórico de
conversa: 0,01 s em conversa direta, 0,34 s em ação). Mesmo assim Alex sentia
lentidão. O motivo é que essa espera acontece ANTES do dispatcher: o servidor
do Gemini Live decide sozinho quando Alex parou de falar, e a sessão nunca
configurou esse tempo — rodava no padrão de fábrica.

Estes testes travam três coisas:
  1. a configuração de fim de turno é realmente enviada na sessão;
  2. o valor é ajustável sem rebuild, por api_keys.json;
  3. valores absurdos são contidos, para um erro de digitação não deixar a ZARA
     surda (silêncio enorme) nem cortando toda frase (silêncio quase zero).
"""
from __future__ import annotations

import json

import pytest

from core.gemini_live_voice import GeminiLiveVoiceConfig
from core.ipc_handlers import IPCHandler


def test_config_tem_fim_de_turno_definido():
    """Sem isto a sessão volta ao padrão do servidor, que era o problema."""
    cfg = GeminiLiveVoiceConfig(api_key="x")
    assert cfg.vad_silencio_ms > 0
    assert cfg.vad_padding_ms >= 0
    assert cfg.vad_fim_sensivel is True


def test_padrao_e_mais_rapido_que_um_segundo():
    """Um segundo de silêncio já é sentido como travada."""
    assert GeminiLiveVoiceConfig(api_key="x").vad_silencio_ms < 1000


@pytest.mark.parametrize(
    "escrito,esperado",
    [
        (300, 300),      # valor normal passa
        (50, 150),       # curto demais cortaria Alex no meio da frase
        (9999, 2000),    # longo demais pareceria que ela travou
        ("400", 400),    # veio como texto do JSON
    ],
)
def test_valor_do_arquivo_e_contido_em_faixa_segura(tmp_path, monkeypatch, escrito, esperado):
    arquivo = tmp_path / "api_keys.json"
    arquivo.write_text(json.dumps({"vad_silencio_ms": escrito}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("chave")

    assert cfg.vad_silencio_ms == esperado


def test_arquivo_ilegivel_nao_derruba_a_voz(tmp_path, monkeypatch):
    """Config quebrada não pode deixar Alex sem voz — cai no padrão."""
    (tmp_path / "api_keys.json").write_text("{ isto nao e json", encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("chave")

    assert cfg.vad_silencio_ms == 450
