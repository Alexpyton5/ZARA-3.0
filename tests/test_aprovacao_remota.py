"""ZARA-APROVAR-DO-CELULAR-001 — a trava muda de lugar, não deixa de existir.

Alex, antes de dormir:

    "se eu deixar o computador em casa, eu não vou poder clicar nisso e a gente
     vai ficar com o projeto parado, não existe isso."

Ele está certo: hoje tudo para até ele voltar. Se sai às 8h e volta às 18h, são
dez horas de nada, com o computador ligado e todo mundo esperando.

O que estes testes protegem é o contrário do conforto: que a permissão continue
sendo permissão. Silêncio não é sim. "Ok" casual não é sim. Sim de ontem não
vale hoje.
"""
from __future__ import annotations

import time

import pytest

from core.aprovacao_remota import FilaDeAprovacao


@pytest.fixture
def fila():
    return FilaDeAprovacao()


# ---------- o pedido ----------

def test_o_pedido_diz_o_que_vai_acontecer(fila):
    p = fila.pedir("apagar a pasta de builds antigos", quem_pediu="O Claude")

    pergunta = p.como_pergunta()
    assert "apagar a pasta de builds antigos" in pergunta
    assert "SIM" in pergunta and "NÃO" in pergunta
    assert p.id in pergunta, "sem o código ele não consegue responder a um específico"


# ---------- o que É resposta ----------

@pytest.mark.parametrize("resposta", ["sim", "pode sim", "autorizo", "aprovado", "SIM"])
def test_as_formas_inequivocas_de_dizer_sim(fila, resposta):
    """So palavras que ninguem diz por reflexo autorizam sozinhas."""
    fila.pedir("qualquer coisa")

    pedido, aprovado = fila.responder(resposta)

    assert pedido is not None
    assert aprovado is True


@pytest.mark.parametrize("resposta", ["ok", "beleza", "vai", "faz", "manda", "claro"])
def test_palavra_ambigua_sozinha_nao_autoriza(fila, resposta):
    """Achado 9 da auditoria: o codigo autorizava com "ok" enquanto o
    comentario jurava que nao. O caso real: existe um pedido aberto para apagar
    builds, ele recebe outra mensagem do bot e responde so "ok"."""
    fila.pedir("apagar os builds antigos")

    pedido, aprovado = fila.responder(resposta)

    assert pedido is None and aprovado is None
    assert len(fila.abertos()) == 1, "o pedido continua esperando resposta de verdade"


@pytest.mark.parametrize("resposta", ["ok", "beleza", "pode", "manda ver"])
def test_palavra_ambigua_vale_quando_ele_cita_o_codigo(fila, resposta):
    """Citar o codigo e deliberado: ele teve de olhar qual pedido era."""
    p = fila.pedir("apagar os builds antigos")

    pedido, aprovado = fila.responder(f"{resposta} {p.id}")

    assert pedido is not None and aprovado is True


@pytest.mark.parametrize("resposta", ["não", "nao", "n", "cancela", "esquece", "NÃO"])
def test_as_formas_que_ele_usa_para_dizer_nao(fila, resposta):
    fila.pedir("qualquer coisa")

    pedido, aprovado = fila.responder(resposta)

    assert pedido is not None
    assert aprovado is False


# ---------- o que NÃO é resposta ----------

@pytest.mark.parametrize("frase", [
    "abre o youtube",
    "que horas são",
    "claude, como foi a noite?",
    "obrigado",
    "entendi",
])
def test_mensagem_normal_nao_autoriza_nada(fila, frase):
    """O perigo real: um "ok" casual liberando algo que ele nem leu."""
    fila.pedir("apagar coisa importante")

    pedido, aprovado = fila.responder(frase)

    assert pedido is None and aprovado is None
    assert len(fila.abertos()) == 1, "o pedido continua esperando"


def test_sem_pedido_aberto_um_sim_nao_faz_nada(fila):
    assert fila.responder("sim") == (None, None)


def test_silencio_nunca_vira_sim(fila):
    """Não há caminho em que a ausência de resposta autorize."""
    fila.pedir("coisa perigosa")

    assert len(fila.abertos()) == 1
    assert fila.responder("") == (None, None)


# ---------- um sim, um pedido ----------

def test_sim_solto_vale_para_o_mais_recente(fila):
    fila.pedir("primeiro pedido")
    segundo = fila.pedir("segundo pedido")

    pedido, aprovado = fila.responder("sim")

    assert pedido.id == segundo.id
    assert aprovado is True
    assert len(fila.abertos()) == 1, "o outro NÃO foi autorizado junto"


def test_ele_pode_responder_citando_o_codigo(fila):
    primeiro = fila.pedir("primeiro pedido")
    fila.pedir("segundo pedido")

    pedido, aprovado = fila.responder(f"sim {primeiro.id}")

    assert pedido.id == primeiro.id
    assert aprovado is True


# ---------- autorização não envelhece bem ----------

def test_pedido_velho_morre_sozinho(fila, monkeypatch):
    p = fila.pedir("coisa de ontem")
    monkeypatch.setattr(p, "criado_em", time.time() - (7 * 60 * 60))

    assert fila.abertos() == []
    assert fila.responder("sim") == (None, None), (
        "um sim dado horas depois autoriza uma coisa que já não existe"
    )


def test_responder_consome_o_pedido(fila):
    fila.pedir("coisa unica")

    fila.responder("sim")

    assert fila.abertos() == []
    assert fila.responder("sim") == (None, None), "não pode ser aprovado duas vezes"


# ---------- a fila ligada na ZARA ----------
#
# O caminho real: o pedido sai pelo Telegram, ele responde de onde estiver, e a
# resposta e consumida ANTES de virar comando — senao um "sim" seria interpretado
# como ordem e a permissao dele se perderia sem ninguem notar.


class _PonteFalsa:
    def __init__(self, entrega=True):
        self.enviados = []
        self.entrega = entrega

    async def avisar(self, texto):
        self.enviados.append(texto)
        return self.entrega


@pytest.mark.asyncio
async def test_o_pedido_sai_pelo_celular():
    from core.ipc_handlers import IPCHandler

    h = IPCHandler.__new__(IPCHandler)
    h._telegram = _PonteFalsa()

    ident = await h.pedir_autorizacao_ao_alex("apagar builds velhos")

    assert ident
    assert "apagar builds velhos" in h._telegram.enviados[0]
    assert h.foi_aprovado(ident) is False, "pedir nao e ser autorizado"


@pytest.mark.asyncio
async def test_sem_celular_nao_ha_pedido():
    """Sem canal para perguntar, nada pode se declarar autorizado."""
    from core.ipc_handlers import IPCHandler

    h = IPCHandler.__new__(IPCHandler)
    h._telegram = None

    assert await h.pedir_autorizacao_ao_alex("qualquer coisa") is None


@pytest.mark.asyncio
async def test_mensagem_que_nao_chegou_nao_deixa_pedido_pendurado():
    from core.ipc_handlers import IPCHandler

    h = IPCHandler.__new__(IPCHandler)
    h._telegram = _PonteFalsa(entrega=False)

    assert await h.pedir_autorizacao_ao_alex("coisa") is None
    assert h._fila_de_aprovacao().abertos() == []


@pytest.mark.asyncio
async def test_o_sim_dele_autoriza_e_nao_vira_comando():
    from core.ipc_handlers import IPCHandler

    h = IPCHandler.__new__(IPCHandler)
    h._telegram = _PonteFalsa()
    ident = await h.pedir_autorizacao_ao_alex("apagar builds velhos")

    resposta = await h._executar_do_celular("zara", "sim")

    assert h.foi_aprovado(ident) is True
    assert "pode seguir" in resposta.casefold()


@pytest.mark.asyncio
async def test_o_nao_dele_e_respeitado():
    from core.ipc_handlers import IPCHandler

    h = IPCHandler.__new__(IPCHandler)
    h._telegram = _PonteFalsa()
    ident = await h.pedir_autorizacao_ao_alex("apagar builds velhos")

    resposta = await h._executar_do_celular("zara", "não")

    assert h.foi_aprovado(ident) is False
    assert "não faço" in resposta.casefold()
