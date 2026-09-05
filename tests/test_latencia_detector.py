"""ZARA-LATENCIA-DETECTOR-001 — o custo escondido de uma frase de conversa.

`detect()` tem um fallback que consulta um Ollama local quando nenhum padrão
casa. Ou seja: ele roda em TODA conversa normal, que é a entrada mais comum.

Dois problemas medidos com cProfile:

1. `httpx.post(...)` era chamado direto, criando um cliente — e um contexto
   SSL — a cada frase. 48 dos ~52 ms de uma frase de conversa eram
   `load_verify_locations`, antes de qualquer byte sair da máquina.
2. Com o Ollama fora do ar, a conexão que já se sabe que falha era tentada de
   novo em toda frase.

Depois: ~2 ms com o Ollama no ar (cliente reaproveitado) e ~0,5 ms com ele
fora (quarentena). O comportamento não muda em nenhum dos dois casos.
"""

import time

import httpx
import pytest

import core.pc_voice_intent as pvi
from core.pc_voice_intent import PcVoiceIntentDetector

FRASE_DE_CONVERSA = "me fale sobre o mar e o céu que estão bonitos hoje de manhã"


@pytest.fixture(autouse=True)
def _limpar_estado_global():
    """Cada teste começa sem cliente e sem quarentena."""
    pvi._OLLAMA_CLIENTE = None
    pvi._OLLAMA_INDISPONIVEL_ATE = 0.0
    yield
    pvi._OLLAMA_CLIENTE = None
    pvi._OLLAMA_INDISPONIVEL_ATE = 0.0


def test_o_cliente_http_e_criado_uma_vez_e_reaproveitado(monkeypatch):
    criados = []
    original = httpx.Client

    def contar(*args, **kwargs):
        criados.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", contar)

    primeiro = pvi._ollama_cliente()
    segundo = pvi._ollama_cliente()

    assert primeiro is segundo
    assert len(criados) == 1
    # `trust_env=False`: o endpoint é 127.0.0.1 e não deve herdar proxy nem
    # bundle de CA do ambiente — era daí que vinha o custo de SSL.
    assert criados[0].get("trust_env") is False


def test_falha_de_conexao_poe_o_ollama_em_quarentena(monkeypatch):
    tentativas = {"n": 0}

    class ClienteQueFalha:
        def post(self, *args, **kwargs):
            tentativas["n"] += 1
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(pvi, "_ollama_cliente", lambda: ClienteQueFalha())
    detector = PcVoiceIntentDetector()

    primeira = detector.detect(FRASE_DE_CONVERSA)
    assert primeira.is_pc_intent is False
    assert tentativas["n"] == 1
    assert pvi._OLLAMA_INDISPONIVEL_ATE > time.monotonic()

    # As próximas frases de conversa não tentam de novo.
    for _ in range(5):
        assert detector.detect(FRASE_DE_CONVERSA).is_pc_intent is False
    assert tentativas["n"] == 1, "o endpoint em quarentena foi consultado de novo"


def test_quarentena_expira_e_o_ollama_volta_a_ser_tentado(monkeypatch):
    tentativas = {"n": 0}

    class ClienteQueFalha:
        def post(self, *args, **kwargs):
            tentativas["n"] += 1
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(pvi, "_ollama_cliente", lambda: ClienteQueFalha())
    detector = PcVoiceIntentDetector()

    detector.detect(FRASE_DE_CONVERSA)
    assert tentativas["n"] == 1

    # Quarentena vencida: pode tentar de novo (o Ollama pode ter subido).
    pvi._OLLAMA_INDISPONIVEL_ATE = time.monotonic() - 1
    detector.detect(FRASE_DE_CONVERSA)
    assert tentativas["n"] == 2


def test_comando_reconhecido_nunca_chega_a_consultar_o_ollama(monkeypatch):
    """O caminho determinístico não pode pagar rede. É o caminho rápido."""
    def explodir():
        raise AssertionError("comando reconhecido não pode consultar o Ollama")

    monkeypatch.setattr(pvi, "_ollama_cliente", explodir)
    detector = PcVoiceIntentDetector()

    for frase in ("abra o chrome", "reduza o volume", "que horas são", "nova aba"):
        assert detector.detect(frase).is_pc_intent is True, frase


def test_ollama_no_ar_nao_ativa_quarentena_e_mantem_o_resultado(monkeypatch):
    class RespostaOk:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"action": null}'}}]}

    class ClienteOk:
        def post(self, *args, **kwargs):
            return RespostaOk()

    monkeypatch.setattr(pvi, "_ollama_cliente", lambda: ClienteOk())

    resultado = PcVoiceIntentDetector().detect(FRASE_DE_CONVERSA)

    assert resultado.is_pc_intent is False
    assert pvi._OLLAMA_INDISPONIVEL_ATE == 0.0
