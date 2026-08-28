"""Sensor de ambiente — o que estes testes travam.

A versão anterior deste módulo não subia: importava `pygetwindow`, que não está
instalado no venv do projeto. Ou seja, ninguém tinha rodado o arquivo uma vez
sequer. O primeiro teste aqui existe para que isso nunca mais passe despercebido.

O resto protege as três coisas que, quebradas, ferem a ZARA no lugar mais caro:

  1. ler o ambiente **não pode tocar a rede** — este código roda no caminho da
     voz, e um socket bloqueando ali vira gagueira na resposta;
  2. sensor que falha vira `None`, nunca exceção — não saber a bateria não pode
     custar a resposta inteira;
  3. `None` ("não sei") e `False` ("não") são estados diferentes, e o resumo em
     texto omite o que não foi medido em vez de afirmar.
"""
from __future__ import annotations

import socket
import time

import pytest

from core.perception import ambiente


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Cada teste mede do zero — senão um teste enxerga o valor do anterior.

    O `yield` espera as threads de refresco terminarem antes de limpar. Sem isso
    uma thread lenta de um teste escreve no cache **depois** dele acabar, com o
    sensor falso que já foi desfeito, e quebra o teste seguinte de um jeito que
    só aparece de vez em quando — o pior tipo de teste instável.
    """
    ambiente._limpar_cache()
    yield
    fim = time.monotonic() + 5.0
    while time.monotonic() < fim:
        with ambiente._trava:
            if not ambiente._atualizando:
                break
        time.sleep(0.01)
    ambiente._limpar_cache()


@pytest.fixture
def _sem_rede(monkeypatch):
    """Qualquer tentativa de abrir socket durante o teste vira falha imediata.

    É o único jeito honesto de provar "não faz rede": proibir, e não confiar na
    leitura do código.
    """

    def proibido(*args, **kwargs):
        raise AssertionError("caminho de leitura tentou usar a rede")

    monkeypatch.setattr(socket, "create_connection", proibido)
    monkeypatch.setattr(socket.socket, "connect", proibido)
    monkeypatch.setattr(ambiente.urllib.request, "urlopen", proibido)


# ---------------------------------------------------------------------------
# 1. O módulo sobe e responde
# ---------------------------------------------------------------------------


def test_o_modulo_importa_de_verdade():
    """A versão anterior morria no import. Esta é a regressão que não pode voltar."""
    assert callable(ambiente.ler_ambiente)
    assert callable(ambiente.resumo_ambiente)


def test_ler_ambiente_devolve_o_relogio_preenchido():
    a = ambiente.ler_ambiente()

    assert a.periodo in {"madrugada", "manhã", "tarde", "noite"}
    assert a.dia_semana in ambiente._DIAS
    assert len(a.hora) == 5 and a.hora[2] == ":"
    assert a.momento  # ISO com fuso resolvido
    assert a.utc_offset  # o fuso é obrigatório: "que horas são" depende dele


def test_cpu_e_ram_vem_preenchidos():
    """CPU/RAM saem de psutil, que é dependência do projeto: têm de existir."""
    a = ambiente.ler_ambiente()

    assert a.ram_percent is not None and 0 <= a.ram_percent <= 100
    assert a.cpu_percent is not None and a.cpu_percent >= 0
    assert a.ram_livre_gb is not None and a.ram_livre_gb >= 0


def test_processos_sao_listados_com_total():
    """A varredura é assíncrona: a primeira leitura dispara, a seguinte enxerga."""
    ambiente.ler_ambiente()
    _esperar_cache("processos")
    a = ambiente.ler_ambiente()

    assert a.total_processos is not None and a.total_processos > 0
    assert len(a.processos) <= 8  # a lista é curta de propósito, cabe no prompt
    assert all(isinstance(nome, str) for nome in a.processos)
    assert "python.exe" in " ".join(a.processos).lower() or a.processos


# ---------------------------------------------------------------------------
# 2. O caminho de leitura não toca a rede
# ---------------------------------------------------------------------------


def test_ler_ambiente_nao_usa_a_rede(_sem_rede):
    """Invariante número um: isto roda no caminho da voz."""
    a = ambiente.ler_ambiente()
    assert a.hora


def test_resumo_nao_usa_a_rede(_sem_rede):
    assert ambiente.resumo_ambiente()


def test_clima_sem_a_thread_de_fundo_e_desconhecido(_sem_rede):
    """Sem monitor ligado, clima é `None` — e não uma espera de 6 segundos."""
    assert ambiente.ler_ambiente().clima is None


def test_internet_sem_medicao_e_desconhecida_nao_offline(_sem_rede):
    """`None` é "não sei". Dizer "sem internet" sem medir seria afirmar sem prova."""
    rede = ambiente.ler_ambiente().rede

    assert rede.internet is None
    assert rede.internet is not False


# ---------------------------------------------------------------------------
# 3. Sensor cego não derruba a ZARA
# ---------------------------------------------------------------------------


def test_sensor_que_explode_vira_none(monkeypatch):
    def explode():
        raise RuntimeError("driver de bateria sumiu")

    monkeypatch.setattr(ambiente, "_bateria", explode)

    a = ambiente.ler_ambiente()
    assert a.bateria == ambiente.Bateria()
    assert a.hora  # o resto do retrato continua de pé


def test_resumo_sobrevive_a_tudo_desconhecido(monkeypatch):
    """Pior caso: nenhum sensor responde. Ainda assim tem de sair uma linha."""
    for nome in ("_bateria", "_processos", "_cpu_ram", "_janela_focada", "_ocioso_segundos"):
        monkeypatch.setattr(ambiente, nome, lambda: None)

    texto = ambiente.resumo_ambiente()

    assert texto
    assert "N/A" not in texto  # omitir o que não se mediu, não escrever "N/A"
    assert "None" not in texto


def test_falha_em_um_sensor_nao_contamina_os_outros(monkeypatch):
    monkeypatch.setattr(ambiente, "_janela_focada", lambda: (_ for _ in ()).throw(OSError("hwnd")))

    a = ambiente.ler_ambiente()

    assert a.janela == ambiente.Janela()
    assert a.ram_percent is not None


# ---------------------------------------------------------------------------
# 4. Cache: barato de chamar em todo turno de voz
# ---------------------------------------------------------------------------


def _esperar_cache(chave: str, limite: float = 3.0) -> None:
    """Espera a thread de refresco terminar. Só nos testes — nunca em produção."""
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        with ambiente._trava:
            if chave in ambiente._cache and chave not in ambiente._atualizando:
                return
        time.sleep(0.01)
    raise AssertionError(f"refresco de {chave!r} não terminou")


def test_leitura_cara_e_reaproveitada_dentro_do_ttl(monkeypatch):
    """`ler_ambiente` é chamada a cada turno; varrer processos a cada turno, não."""
    chamadas = []

    def contar():
        chamadas.append(1)
        return {"processos": ("chrome.exe",), "total": 1}

    monkeypatch.setattr(ambiente, "_processos", contar)

    ambiente.ler_ambiente()
    _esperar_cache("processos")
    ambiente.ler_ambiente()
    ambiente.ler_ambiente()

    assert len(chamadas) == 1


def test_varredura_cara_nunca_bloqueia_a_leitura(monkeypatch):
    """A medição que motivou isto: varrer processos custa ~300 ms nesta máquina.

    Pagar isso dentro do turno de voz é a gagueira que este módulo promete não
    causar. A leitura tem de voltar na hora mesmo com o sensor lento.
    """
    def lenta():
        time.sleep(1.5)
        return {"processos": ("chrome.exe",), "total": 1}

    monkeypatch.setattr(ambiente, "_processos", lenta)

    inicio = time.monotonic()
    a = ambiente.ler_ambiente()
    demorou = time.monotonic() - inicio

    assert demorou < 0.3  # não esperou o sensor lento
    assert a.processos == ()  # ainda não sabe: devolve vazio, não trava
    assert a.hora  # e o resto do retrato veio completo


def test_valor_velho_serve_enquanto_o_novo_nao_chega(monkeypatch):
    """Cache vencido devolve o anterior na hora e busca o novo para o próximo turno."""
    monkeypatch.setattr(ambiente, "_processos", lambda: {"processos": ("v1.exe",), "total": 1})
    ambiente.ler_ambiente()
    _esperar_cache("processos")
    assert ambiente.ler_ambiente().processos == ("v1.exe",)

    # Vence o cache e troca o sensor: a leitura seguinte ainda entrega o valor velho.
    monkeypatch.setattr(ambiente, "_processos", lambda: {"processos": ("v2.exe",), "total": 1})
    relogio = ambiente.time.monotonic() + ambiente._TTL_PROCESSOS + 1
    monkeypatch.setattr(ambiente.time, "monotonic", lambda: relogio)

    assert ambiente.ler_ambiente().processos == ("v1.exe",)

    monkeypatch.undo()
    _esperar_cache("processos")
    assert ambiente.ler_ambiente().processos == ("v2.exe",)


def test_cache_vencido_nao_dispara_duas_buscas_ao_mesmo_tempo(monkeypatch):
    """Três turnos seguidos com cache frio não podem virar três varreduras."""
    chamadas = []

    def contar():
        chamadas.append(1)
        time.sleep(0.2)
        return {"processos": (), "total": 0}

    monkeypatch.setattr(ambiente, "_processos", contar)

    ambiente.ler_ambiente()
    ambiente.ler_ambiente()
    ambiente.ler_ambiente()
    _esperar_cache("processos")

    assert len(chamadas) == 1


# ---------------------------------------------------------------------------
# 5. Freio da INICIATIVA — "o Alex está ocupado?"
# ---------------------------------------------------------------------------


def test_alex_ocupado_quando_acabou_de_digitar(monkeypatch):
    monkeypatch.setattr(ambiente, "_ocioso_segundos", lambda: 3.0)
    assert ambiente.alex_esta_ocupado() is True


def test_alex_livre_depois_de_um_tempo_parado(monkeypatch):
    monkeypatch.setattr(ambiente, "_ocioso_segundos", lambda: 600.0)
    assert ambiente.alex_esta_ocupado() is False


def test_sem_medicao_de_ociosidade_a_resposta_e_nao_sei(monkeypatch):
    """Fora do Windows não dá para medir. `None` — e quem chama decide."""
    monkeypatch.setattr(ambiente, "_ocioso_segundos", lambda: None)
    assert ambiente.alex_esta_ocupado() is None


# ---------------------------------------------------------------------------
# 6. Formato de saída
# ---------------------------------------------------------------------------


def test_para_dicionario_e_serializavel_em_json():
    """A tela e o IPC consomem isto como JSON."""
    import json

    dados = ambiente.ler_ambiente().para_dicionario()
    texto = json.dumps(dados, ensure_ascii=False)

    assert isinstance(dados["processos"], list)  # tupla não sobrevive a JSON
    assert "hora" in dados
    assert "bateria" in dados
    assert texto


def test_resumo_mostra_o_clima_quando_ele_foi_medido(monkeypatch):
    monkeypatch.setattr(
        ambiente,
        "_do_cache",
        lambda chave, ttl: (
            ambiente.Clima(descricao="nublado", temperatura_c=27.4, cidade="Salvador")
            if chave == "clima"
            else None
        ),
    )

    texto = ambiente.resumo_ambiente()

    assert "Salvador" in texto
    assert "nublado" in texto
    assert "27" in texto


def test_codigo_wmo_vira_texto_em_portugues():
    assert ambiente._WMO[0] == "céu limpo"
    assert ambiente._WMO[95] == "tempestade"


def test_clima_desligado_por_variavel_de_ambiente(monkeypatch, _sem_rede):
    """`ZARA_CLIMA=0` tem de cortar a consulta antes de qualquer socket."""
    monkeypatch.setenv("ZARA_CLIMA", "0")
    assert ambiente.atualizar_clima_agora() is None
