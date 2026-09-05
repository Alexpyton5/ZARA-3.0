"""ZARA-PONTE-CODEX-CLI-001 — conversar com o Codex sem passar pela tela.

A rota antiga digitava na janela do app do ChatGPT e lia a resposta pela
acessibilidade do Windows. Ela falhou de três jeitos diferentes em um dia só:
não achava a caixa de texto, achava que não tinha colado quando tinha, e
entregava frases furadas que pareciam inteiras.

O que estes testes travam:
  1. a conversa não perde o fio entre uma mensagem e outra;
  2. `resume` não recebe as opções que ele recusa;
  3. o sandbox continua read-only nos dois caminhos;
  4. falha do CLI vira mensagem honesta, nunca exceção solta.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import ponte_codex_cli as canal


class _ProcessoFalso:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _eventos(thread_id="abc-123", texto="Chegou."):
    return "\n".join([
        json.dumps({"type": "thread.started", "thread_id": thread_id}),
        json.dumps({"type": "turn.started"}),
        json.dumps({
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": texto},
        }),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}),
    ])


@pytest.fixture(autouse=True)
def _conversa_isolada(monkeypatch, tmp_path):
    """Nunca tocar no arquivo real de conversa do Alex."""
    monkeypatch.setattr(canal, "_arquivo_da_conversa", lambda: tmp_path / "codex_conversa.json")
    monkeypatch.setattr(canal, "_executavel", lambda: "codex.cmd")


def _capturar(monkeypatch, stdout, stderr="", returncode=0):
    vistos = {}

    def run_falso(comando, **kw):
        vistos["comando"] = comando
        vistos["kw"] = kw
        # O CLI grava a resposta final no arquivo apontado por -o.
        if "-o" in comando:
            alvo = Path(comando[comando.index("-o") + 1])
            alvo.parent.mkdir(parents=True, exist_ok=True)
            if stdout:
                alvo.write_text("Chegou.", encoding="utf-8")
        return _ProcessoFalso(stdout, stderr, returncode)

    monkeypatch.setattr(canal.subprocess, "run", run_falso)
    return vistos


# ---------- o fio da conversa ----------

def test_a_primeira_mensagem_abre_a_conversa_e_guarda_o_fio(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))

    resposta, erro = canal.falar_com_codex("bom dia")

    assert erro == ""
    assert resposta == "Chegou."
    assert "resume" not in vistos["comando"], "não há o que retomar na primeira"
    assert canal._thread_guardada() == "fio-1"


def test_a_segunda_mensagem_retoma_a_mesma_conversa(monkeypatch):
    _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("bom dia")

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("e entao?")

    comando = vistos["comando"]
    assert "resume" in comando
    assert "fio-1" in comando, "sem o id, ele começaria do zero e perderia o fio"


def test_novo_assunto_recomeca_do_zero(monkeypatch):
    _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("bom dia")

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-2"))
    canal.falar_com_codex("assunto novo", novo_assunto=True)

    assert "resume" not in vistos["comando"]


# ---------- as opções que o resume recusa ----------

def test_resume_nao_recebe_as_opcoes_que_ele_rejeita(monkeypatch):
    """Medido no codex-cli 0.146.0: `exec resume` recusa -s e -C.

    Mandar assim mesmo devolvia "error: unexpected argument '-s' found", e a
    ZARA reportava que o Codex não tinha respondido — quando na verdade ela
    nem tinha conseguido perguntar.
    """
    _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("bom dia")

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("de novo")

    comando = vistos["comando"]
    assert "-s" not in comando
    assert "-C" not in comando


@pytest.mark.parametrize("segunda_vez", [False, True])
def test_o_sandbox_continua_somente_leitura_nos_dois_caminhos(monkeypatch, segunda_vez):
    """Este canal conversa e lê o projeto. Não mexe no computador do Alex."""
    if segunda_vez:
        _capturar(monkeypatch, _eventos(thread_id="fio-1"))
        canal.falar_com_codex("primeira")

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("agora vai")

    junto = " ".join(vistos["comando"])
    assert "read-only" in junto
    assert "dangerously" not in junto, "nunca sem sandbox por esta ponte"


# ---------- falhar direito ----------

def test_codex_ausente_vira_recado_e_nao_excecao(monkeypatch):
    monkeypatch.setattr(canal, "_executavel", lambda: None)

    resposta, erro = canal.falar_com_codex("oi")

    assert resposta == ""
    assert "não encontrei o codex" in erro.casefold()


def test_erro_do_cli_e_reportado_com_o_motivo(monkeypatch):
    _capturar(monkeypatch, "", stderr="error: unexpected argument", returncode=2)

    resposta, erro = canal.falar_com_codex("oi")

    assert resposta == ""
    assert "não devolveu resposta" in erro.casefold()
    assert "unexpected argument" in erro


def test_estouro_de_tempo_nao_derruba_a_ponte(monkeypatch):
    def estoura(*a, **kw):
        raise canal.subprocess.TimeoutExpired(cmd="codex", timeout=300)

    monkeypatch.setattr(canal.subprocess, "run", estoura)

    resposta, erro = canal.falar_com_codex("oi")

    assert resposta == ""
    assert "5 minutos" in erro


# ---------- ZARA-CODEX-PACIENCIA-001 ----------
#
# Cinco minutos servem para conversa e mataram duas tarefas de verdade:
# classificar 70 acoes e uma pesquisa profunda na web. Nos dois casos ele estava
# trabalhando e eu desliguei na cara dele — e o relatorio saiu como "o Codex nao
# respondeu", que e acusacao errada contra quem estava fazendo o servico.


def test_conversa_tem_teto_curto_porque_alex_esta_esperando(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    canal.falar_com_codex("tudo bem?")

    assert vistos["kw"]["timeout"] == canal._TETO_DE_ESPERA


def test_trabalho_de_fundo_ganha_paciencia(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    canal.falar_com_codex("pesquise a fundo", trabalho_longo=True)

    assert vistos["kw"]["timeout"] == canal._TETO_DE_TRABALHO
    assert canal._TETO_DE_TRABALHO > canal._TETO_DE_ESPERA


def test_o_recado_de_estouro_diz_o_tempo_certo(monkeypatch):
    """Dizer "cinco minutos" depois de esperar vinte e cinco seria mentira."""
    def estoura(*a, **kw):
        raise canal.subprocess.TimeoutExpired(cmd="codex", timeout=1500)

    monkeypatch.setattr(canal.subprocess, "run", estoura)

    _, erro = canal.falar_com_codex("pesquise", trabalho_longo=True)

    assert "25 minutos" in erro


def test_mensagem_vazia_nao_chama_o_codex(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    resposta, erro = canal.falar_com_codex("   ")

    assert resposta == ""
    assert erro == "Chegou vazio."
    assert "comando" not in vistos, "não gastar token com mensagem vazia"


# ---------- ZARA-CODEX-MULTILINHA-001 ----------
#
# Qualquer pedido com quebra de linha voltava vazio, com um resto de erro no
# lugar da resposta. Contornei a primeira vez achatando o texto numa linha so —
# e a falha voltou depois, numa tarefa longa, e ainda me fez culpar o Codex por
# nao responder.
#
# Nao era conforto: mensagem do Telegram tem quebra de linha o tempo todo.


def test_a_mensagem_vai_por_stdin_e_nao_pela_linha_de_comando(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    canal.falar_com_codex("oi")

    assert vistos["kw"].get("input") == "oi"
    assert "-" in vistos["comando"], "o CLI so le do stdin quando recebe '-'"


def test_pedido_de_varias_linhas_chega_inteiro(monkeypatch):
    pedido = "TAREFA SOMENTE LEITURA.\n\nClassifique cada acao.\n- nivel A\n- nivel B"
    vistos = _capturar(monkeypatch, _eventos())

    resposta, erro = canal.falar_com_codex(pedido)

    assert erro == ""
    assert vistos["kw"]["input"] == pedido, "as quebras de linha nao podem se perder"
    assert pedido not in " ".join(vistos["comando"]), "texto longo nao vai na linha de comando"


def test_o_resume_tambem_le_do_stdin(monkeypatch):
    _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("primeira")

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("segunda\ncom quebra")

    assert vistos["kw"]["input"] == "segunda\ncom quebra"
    assert "resume" in vistos["comando"]


# ---------- ZARA-CODEX-FIO-NOVO-001 ----------
#
# Alex, ao ver a conta subir: "isso de fio novo é o que mesmo".
#
# Um fio retomado reenvia a conversa inteira a cada mensagem. Medido em
# 2026-08-14: 16 mil tokens de entrada viraram 417 mil em um dia, e uma das
# chamadas simplesmente falhou. Quem paga é o Codex, mas quem espera é o Alex.

def _eventos_com_uso(thread_id, entrada):
    return "\n".join([
        json.dumps({"type": "thread.started", "thread_id": thread_id}),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Chegou."},
        }),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": entrada}}),
    ])


def test_fio_leve_continua_sendo_retomado(monkeypatch):
    _capturar(monkeypatch, _eventos_com_uso("fio-1", 20_000))
    canal.falar_com_codex("primeira")

    vistos = _capturar(monkeypatch, _eventos_com_uso("fio-1", 21_000))
    canal.falar_com_codex("segunda")

    assert "resume" in vistos["comando"], "fio leve não tem por que ser jogado fora"


def test_fio_pesado_se_aposenta_sozinho(monkeypatch):
    _capturar(monkeypatch, _eventos_com_uso("fio-1", 300_000))
    canal.falar_com_codex("primeira")

    vistos = _capturar(monkeypatch, _eventos_com_uso("fio-2", 16_000))
    canal.falar_com_codex("segunda")

    assert "resume" not in vistos["comando"], "fio de 300 mil tokens tem de ser aposentado"


def test_o_fio_novo_nao_comeca_sem_saber_de_nada(monkeypatch):
    """Aposentar sem resumo faria o Codex acordar sem contexto nenhum."""
    _capturar(monkeypatch, _eventos_com_uso("fio-1", 300_000))
    canal.falar_com_codex("como esta a latencia da ZARA?")

    vistos = _capturar(monkeypatch, _eventos_com_uso("fio-2", 16_000))
    canal.falar_com_codex("e agora?")

    # O texto vai por stdin desde ZARA-CODEX-MULTILINHA-001, não mais no comando.
    mandado = vistos["kw"]["input"]
    assert "onde estavamos" in mandado
    assert "latencia" in mandado, "o resumo tem de carregar o assunto anterior"


def test_o_peso_do_fio_fica_gravado(monkeypatch):
    _capturar(monkeypatch, _eventos_com_uso("fio-1", 123_456))
    canal.falar_com_codex("oi")

    assert canal._estado()["ultima_entrada"] == 123_456


# ---------- escrever é decisão explícita ----------
#
# Alex autorizou o Codex a escrever em 15/08, com condições: área delimitada
# que ninguém mais esteja tocando, e relatório do que ele mexeu. O padrão da
# ponte continua sendo somente leitura — soltar a escrita por engano seria dar
# a um agente autônomo acesso de escrita ao computador dele.


def test_o_padrao_continua_somente_leitura(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    canal.falar_com_codex("me diga o que voce acha")

    assert "read-only" in " ".join(vistos["comando"])
    assert "workspace-write" not in " ".join(vistos["comando"])


def test_escrita_so_quando_pedida_explicitamente(monkeypatch):
    vistos = _capturar(monkeypatch, _eventos())

    canal.falar_com_codex("implemente o painel", escrever=True)

    assert "workspace-write" in " ".join(vistos["comando"])
    assert "dangerously" not in " ".join(vistos["comando"]), "nunca sem sandbox"


def test_escrita_tambem_vale_ao_retomar_a_conversa(monkeypatch):
    """Sem isto, a segunda mensagem de uma tarefa de escrita voltaria a ser
    somente leitura no meio do trabalho — e o Codex ficaria sem entender por
    que de repente nao consegue mais salvar."""
    _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("primeira", escrever=True)

    vistos = _capturar(monkeypatch, _eventos(thread_id="fio-1"))
    canal.falar_com_codex("continue", escrever=True)

    assert "resume" in vistos["comando"]
    assert "workspace-write" in " ".join(vistos["comando"])
