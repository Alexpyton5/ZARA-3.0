"""ZARA-PONTE-CLAUDE-001 — falar com o Claude Code pela voz.

Alex não quer mais ler texto na tela nem digitar. A ZARA passa a ser o
intermediário: ela lê em voz alta o que o Claude respondeu e digita, na caixa do
Claude Code, o que Alex ditar.

O que estes testes travam:
  1. as frases naturais que ele vai usar caem no comando certo;
  2. conversa comum não vira comando de ponte por engano;
  3. o texto do Claude é preparado para OUVIDO — código e tabela não são lidos;
  4. a ponte nunca diz que enviou quando não enviou.
"""
from __future__ import annotations

import pytest

from core.actions import ponte_claude as ponte
from core.actions.ponte_claude import _preparar_para_ouvido, claude_enviar_action
from core.pc_voice_intent import PcVoiceIntentDetector


def _detectar(frase: str):
    # pc_control_allowed=False de propósito: é o estado padrão no boot. A ponte
    # tem de funcionar com o Supercérebro desligado.
    return PcVoiceIntentDetector(pc_control_allowed=False).detect(frase)


@pytest.mark.parametrize("frase", [
    "Zara, lê o que o Claude falou",
    "lê o que o Claude mandou",
    "leia a última resposta do Claude",
    "me lê a resposta do Claude",
    "o Claude falou o quê?",
    "o que o Claude disse",
    "Zara, o Claude respondeu alguma coisa?",
    # Alex chama o app pelo nome completo. Na primeira vez que ele usou de
    # verdade, foi exatamente assim — e não casou, porque o padrão esperava
    # "Claude falou" e veio "Claude Code falou".
    "o que o Claude Code falou",
    "lê o que o Claude Code falou",
    "o que o Cloud Code disse",
])
def test_pedidos_de_leitura_caem_na_ponte(frase):
    r = _detectar(frase)
    assert r.is_pc_intent is True, frase
    assert r.action == "claude_ler", f"{frase} -> {r.action}"
    assert r.blocked is False, "não pode depender do Supercérebro"


@pytest.mark.parametrize("frase,esperado", [
    ("Zara, responde pro Claude: conserta o volume",
     "conserta o volume"),
    ("manda pro Claude que ele faça o build",
     "ele faça o build"),
    # O detector normaliza a fala para minúsculas antes de casar os padrões,
    # então a mensagem chega assim. Não atrapalha: é texto para eu ler.
    ("diz pro Claude para deixar a ZARA mais rápida",
     "deixar a zara mais rápida"),
    ("responda ao Claude: ficou ótimo, pode seguir",
     "ficou ótimo, pode seguir"),
    ("responde pro Claude Code: pode seguir",
     "pode seguir"),
])
def test_ditado_vira_mensagem_para_o_claude(frase, esperado):
    r = _detectar(frase)
    assert r.is_pc_intent is True, frase
    assert r.action == "claude_enviar", f"{frase} -> {r.action}"
    assert r.param == esperado


@pytest.mark.parametrize("frase", [
    "que horas são",
    "abre o YouTube",
    "lê a área de transferência",
    "o que diz essa página",
    "me conta uma piada",
    "diminua o volume",
])
def test_conversa_e_comandos_normais_nao_viram_ponte(frase):
    r = _detectar(frase)
    assert r.action not in ("claude_ler", "claude_enviar"), f"{frase} virou ponte"


def test_codigo_nao_e_lido_em_voz_alta():
    """Ouvir código é insuportável — vira um aviso curto."""
    texto = "Consertei assim:\n\n```python\ndef x():\n    return 1\n```\n\nPronto."

    falado = _preparar_para_ouvido(texto)

    assert "def x()" not in falado
    assert "trecho de código" in falado
    assert "Consertei assim" in falado
    assert "Pronto" in falado


def test_tabela_vira_aviso():
    texto = "Resultado:\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nFim."

    falado = _preparar_para_ouvido(texto)

    assert "|" not in falado
    assert "tabela" in falado


def test_existe_teto_contra_monologo_de_dez_minutos():
    """Ler tudo é o padrão, mas resposta gigante ainda tem limite."""
    texto = ("Primeira frase importante. " * 600)

    falado = _preparar_para_ouvido(texto)

    assert len(falado) < 3200
    assert "na tela" in falado, "cortar em silêncio esconderia que há mais texto"


def test_marcacao_de_markdown_nao_e_falada():
    falado = _preparar_para_ouvido("**Feito**: veja o [relatório](http://x.com) e o `arquivo.py`")

    for lixo in ("**", "[", "](", "http", "`"):
        assert lixo not in falado
    assert "relatório" in falado


@pytest.mark.asyncio
@pytest.mark.parametrize("acao,texto", [
    ("claude_ler", "O eco foi resolvido, pode testar."),
    ("codex_ler", "Bom dia, Alex! Como vamos seguir hoje?"),
    ("ponte_repassar", "Repassei para o Codex."),
])
async def test_a_resposta_e_o_recado_e_nao_um_pronto(monkeypatch, acao, texto):
    """ZARA-PONTE-RESPOSTA-001 — o bug que Alex pegou no primeiro uso real.

    Ele falou "lê o que o Claude falou", a ação executou, o texto estava lá, e
    ela respondeu só "Pronto." O despachante tinha uma frase fixa no fim que
    engolia a saída do executor.
    """
    from unittest.mock import AsyncMock

    from core.ipc_handlers import IPCHandler

    resultado = type("R", (), {"success": True, "output": texto, "error": "", "data": {}})()
    monkeypatch.setattr("core.action_registry.execute_action", AsyncMock(return_value=resultado))

    handler = IPCHandler.__new__(IPCHandler)
    handler.supercerebro_active = True
    handler._last_volume_level = 40
    handler._last_window_hwnd = None
    handler._last_safe_folder = None
    handler._last_brightness_level = None
    handler._operational_context_turns = 0
    handler._context_fresh = lambda _kind: False
    handler._set_operational_context = lambda *a, **k: None
    handler._clear_operational_context = lambda: None
    handler._remember_action_failure = lambda *a, **k: None

    detectado = type("D", (), {
        "is_pc_intent": True, "action": acao, "param": "read",
        "blocked": False, "physical_effect": 1, "reply": "", "contextual": False,
    })()
    monkeypatch.setattr(
        "core.pc_voice_intent.PcVoiceIntentDetector.detect", lambda self, t: detectado
    )

    reply = await handler._try_pc_intent("lê o que o claude falou")

    assert reply is not None
    assert reply.strip() != "Pronto."
    assert texto[:18] in reply


@pytest.mark.parametrize("frase,acao", [
    ("lê resumido o que o Codex falou", "codex_ler"),
    ("me dá um resumo do que o Claude disse", "claude_ler"),
    ("lê por cima o que o Codex escreveu", "codex_ler"),
    ("resume o que o Claude falou", "claude_ler"),
])
def test_pedir_a_versao_curta(frase, acao):
    """ZARA-PONTE-LEITURA-COMPLETA-002 — resumo virou o pedido especial."""
    r = _detectar(frase)
    assert r.action == acao, f"{frase} -> {r.action}"
    assert r.param == "resumido"


@pytest.mark.parametrize("frase", [
    "lê o que o Claude falou",
    "o que o Codex disse",
])
def test_leitura_normal_e_o_texto_inteiro(frase):
    """A voz dela é gratuita — cortar economizava o recurso errado."""
    assert _detectar(frase).param == "read"


def test_por_padrao_cabe_texto_longo():
    longo = "Frase completa e importante. " * 60
    inteiro = _preparar_para_ouvido(longo)
    resumo = _preparar_para_ouvido(longo, limite=420)

    assert len(inteiro) > len(resumo) * 2
    assert len(inteiro) > 1500


# --------------------------------------------------------------------------
# ZARA-PONTE-ENVIO-VERIFICADO-001 — "Mandei" só depois de conferir.
#
# Alex disse "responde pro Claude funcionou", ela anunciou "Mandei para o
# Claude" e nada chegou: a janela estava na frente, mas o cursor não estava na
# caixa de texto. Falso sucesso é o defeito que este projeto mais combate.
# --------------------------------------------------------------------------

def _montar_envio(monkeypatch, *, campo_achado=True, texto_apos_colar="",
                  texto_apos_enter="", colagem_ok=True):
    estado = {"enter": 0}
    # A caixa é lida três vezes: antes de colar, depois de colar, e depois do
    # Enter. É essa terceira leitura que prova o envio.
    # A caixa agora e relida ate o app desenhar o texto (apps pesados demoram).
    # O roteiro continua o mesmo: vazia antes, com texto depois de colar, e o
    # que sobrar depois do Enter -- so que cada etapa pode ser lida mais de uma vez.
    leituras = iter(["", *[texto_apos_colar] * 10, *[texto_apos_enter] * 12])

    monkeypatch.setattr("core.actions.os_ops._focus_window_verified", lambda h: True)
    monkeypatch.setattr("core.actions.os_ops._foreground_window", lambda: 123)
    monkeypatch.setattr(
        "core.actions.os_ops._focused_editable_field",
        lambda: {"hwnd": 123} if campo_achado else None,
    )
    monkeypatch.setattr(
        "core.actions.os_ops._uia_field_text", lambda campo: next(leituras, texto_apos_enter)
    )
    monkeypatch.setattr("core.actions.os_ops._send_unicode_text", lambda t: colagem_ok)
    monkeypatch.setattr(
        "core.actions.os_ops._send_fixed_hotkey",
        lambda combo: estado.__setitem__("enter", estado["enter"] + 1),
    )
    monkeypatch.setattr("core.actions.ponte_claude._clicar_na_caixa_de_texto", lambda h: False)
    monkeypatch.setattr("core.actions.ponte_claude.time.sleep", lambda s: None)
    monkeypatch.setattr("core.actions.ponte_claude._janela_do_claude", lambda: 123)
    return estado


def test_envio_confirmado_quando_o_texto_entra_e_a_caixa_esvazia(monkeypatch):
    estado = _montar_envio(
        monkeypatch, texto_apos_colar="funcionou", texto_apos_enter=""
    )
    monkeypatch.setattr(
        "core.actions.ponte_claude._mensagem_chegou_ao_claude", lambda m, espera=6.0: True
    )

    r = claude_enviar_action("funcionou")

    assert r.success is True
    assert r.data["verificado"] is True
    assert estado["enter"] == 1


def test_nao_diz_que_mandou_quando_o_texto_nao_entrou_na_caixa(monkeypatch):
    """O bug real: colagem no vazio virava 'Mandei para o Claude'."""
    estado = _montar_envio(monkeypatch, texto_apos_colar="", texto_apos_enter="")

    r = claude_enviar_action("funcionou")

    assert r.success is False
    assert "não apareceu" in (r.error or "")
    assert estado["enter"] == 0, "não pode apertar Enter sem o texto estar lá"


def test_nao_diz_que_mandou_quando_o_texto_fica_parado_na_caixa(monkeypatch):
    """Enter não pegou: o texto continua escrito. Isso não é envio."""
    _montar_envio(monkeypatch, texto_apos_colar="funcionou", texto_apos_enter="funcionou")
    # Sem isto o teste iria ler o histórico real do Claude no disco do Alex.
    monkeypatch.setattr(ponte, "_mensagem_chegou_ao_claude", lambda *a, **k: False)

    r = claude_enviar_action("funcionou")

    assert r.success is False
    assert "não foi enviada" in (r.error or "")


def test_sem_caixa_visivel_ela_tenta_mas_nao_inventa_sucesso(monkeypatch):
    """ZARA-PONTE-ENVIO-CEGO-001.

    O Claude Code é Chromium e nem sempre expõe a caixa pela acessibilidade
    quando a janela acabou de vir do segundo plano — a caixa existe, só não é
    encontrada. Desistir aí era desistir de algo que ia funcionar, e foi o que
    encheu o Telegram do Alex com a mesma recusa repetida.

    Agora ela escreve mesmo sem enxergar a caixa. O que NÃO pode acontecer é
    dizer que mandou: sem o texto aparecer no histórico do outro lado, é falha.
    """
    estado = _montar_envio(monkeypatch, campo_achado=False)
    monkeypatch.setattr(ponte, "_mensagem_chegou_ao_claude", lambda *a, **k: False)

    r = claude_enviar_action("funcionou")

    assert r.success is False
    assert "não consegui confirmar" in (r.error or "")
    assert estado["enter"] == 1, "no modo cego ela ainda tenta enviar de verdade"


def test_sem_caixa_visivel_o_historico_do_outro_lado_e_a_prova(monkeypatch):
    """Se o texto apareceu no histórico do Claude, chegou — e ela pode dizer."""
    _montar_envio(monkeypatch, campo_achado=False)
    monkeypatch.setattr(ponte, "_mensagem_chegou_ao_claude", lambda *a, **k: True)

    r = claude_enviar_action("funcionou")

    assert r.success is True
    assert (r.data or {}).get("modo") == "cego"


def test_diz_que_foi_para_outra_conversa_quando_nao_chega(monkeypatch):
    """ZARA-PONTE-ENVIO-CHEGOU-001 — digitar não prova que chegou a quem ela leu.

    O app do Claude tem várias conversas. A caixa que recebe o texto é a da
    conversa que está na tela, que pode não ser a mesma de onde ela leu. Alex
    viu ela enviar duas vezes com a caixa esvaziando, e nada apareceu do lado
    certo.
    """
    _montar_envio(monkeypatch, texto_apos_colar="funcionou", texto_apos_enter="")
    monkeypatch.setattr(
        "core.actions.ponte_claude._mensagem_chegou_ao_claude", lambda m, espera=6.0: False
    )

    r = claude_enviar_action("funcionou")

    assert r.success is False
    assert "outra conversa" in (r.error or "")
    assert r.data["enviado_na_janela"] is True


def test_confirma_quando_a_mensagem_aparece_na_conversa_certa(monkeypatch):
    _montar_envio(monkeypatch, texto_apos_colar="funcionou", texto_apos_enter="")
    monkeypatch.setattr(
        "core.actions.ponte_claude._mensagem_chegou_ao_claude", lambda m, espera=6.0: True
    )

    r = claude_enviar_action("funcionou")
    assert r.success is True
    assert r.output == "Mensagem enviada e confirmada no histórico do Claude."


def test_nao_envia_mensagem_vazia():
    r = claude_enviar_action("   ")
    assert r.success is False


@pytest.mark.parametrize("frase,acao", [
    ("Zara, lê o que o Codex falou", "codex_ler"),
    ("o que o Codex disse", "codex_ler"),
    ("leia a resposta do Codex", "codex_ler"),
    ("Zara, lê o que o Claude falou", "claude_ler"),
])
def test_ela_sabe_de_qual_dos_dois_ler(frase, acao):
    r = _detectar(frase)
    assert r.is_pc_intent is True, frase
    assert r.action == acao, f"{frase} -> {r.action}"


@pytest.mark.parametrize("frase,acao,esperado", [
    ("manda pro Codex: roda os testes", "codex_enviar", "roda os testes"),
    ("responde pro Claude: pode seguir", "claude_enviar", "pode seguir"),
])
def test_ela_sabe_para_qual_dos_dois_mandar(frase, acao, esperado):
    r = _detectar(frase)
    assert r.action == acao, f"{frase} -> {r.action}"
    assert r.param == esperado


@pytest.mark.parametrize("frase,rota", [
    ("Zara, manda o que o Claude falou pro Codex", "claude>codex"),
    ("passa pro Codex o que o Claude disse", "claude>codex"),
    ("manda o que o Codex falou pro Claude", "codex>claude"),
    ("repassa o Codex pro Claude", "codex>claude"),
])
def test_repasse_entre_os_dois(frase, rota):
    """Alex no meio de propósito: é ele quem decide o que atravessa."""
    r = _detectar(frase)
    assert r.is_pc_intent is True, frase
    assert r.action == "ponte_repassar", f"{frase} -> {r.action}"
    assert r.param == rota


def test_repasse_nao_engole_o_envio_normal():
    """'manda pro Codex: roda os testes' continua sendo envio, não repasse."""
    r = _detectar("manda pro Codex: roda os testes")
    assert r.action == "codex_enviar"


def test_rota_de_repasse_invalida_e_recusada():
    from core.actions.ponte_claude import ponte_repassar_action

    for rota in ("", "claude", "claude>claude", "gemini>claude"):
        assert ponte_repassar_action(rota).success is False, rota


def test_nao_envia_quando_o_claude_nao_esta_aberto(monkeypatch):
    """Sem janela não há envio — e ela precisa DIZER isso, não fingir sucesso."""
    monkeypatch.setattr("core.actions.ponte_claude._janela_do_claude", lambda: None)

    r = claude_enviar_action("oi")

    assert r.success is False
    assert "não está aberto" in (r.error or "")


def test_codex_tambem_escreve_sem_enxergar_a_caixa(monkeypatch):
    """ZARA-PONTE-ENVIO-CEGO-001 — o Codex vive dentro do app do ChatGPT.

    Alex: "o codex nao ta falando no grupo... ja falei com ele 3 vezes e ele
    nao respondeu nenhuma". A janela estava aberta; o que faltava era a caixa
    ser encontrada pela acessibilidade. A recusa daqui era a resposta que ele
    recebia — e como não parecia resposta, parecia silêncio.
    """
    from core.actions.ponte_claude import codex_enviar_action

    estado = _montar_envio(monkeypatch, campo_achado=False)
    monkeypatch.setattr(ponte, "_janela_por", lambda *a, **k: 123)
    monkeypatch.setattr(ponte, "_mensagem_chegou_ao_codex", lambda *a, **k: True)

    r = codex_enviar_action("bom dia, tudo certo por ai?")

    assert r.success is True
    assert estado["enter"] == 1


def test_codex_nao_diz_que_mandou_sem_ver_o_texto_na_conversa(monkeypatch):
    from core.actions.ponte_claude import codex_enviar_action

    _montar_envio(monkeypatch, campo_achado=False)
    monkeypatch.setattr(ponte, "_janela_por", lambda *a, **k: 123)
    monkeypatch.setattr(ponte, "_mensagem_chegou_ao_codex", lambda *a, **k: False)

    r = codex_enviar_action("bom dia")

    assert r.success is False
    assert "não consegui confirmar" in (r.error or "")


# --------------------------------------------------------------------------
# ZARA-PONTE-LEITURA-BURACO-001 — frase furada que parece inteira.
#
# O Codex recomendou dois comandos e o que chegou ao Claude foi "pode usar"
# seguido de "e ler o arquivo final". Sumiu justamente o comando. A leitura
# antiga catava elemento por elemento e descartava tudo com 30 caracteres ou
# menos; `stdio` tem 5, `codex exec --json` tem 17. Sobravam as bordas do
# buraco, coladas, formando uma frase que ninguém desconfiaria estar quebrada.
#
# Confirmado pelo próprio Codex: "sim, uso crases de Markdown para nomes de
# comandos... os nomes que sumiram foram: stdio, threadId, codex exec --json".

class _ElementoFalso:
    def __init__(self, nome):
        self.CurrentName = nome


class _AchadosFalsos:
    def __init__(self, nomes):
        self._nomes = nomes
        self.Length = len(nomes)

    def GetElement(self, i):
        return _ElementoFalso(self._nomes[i])


class _JanelaFalsa:
    def __init__(self, nomes):
        self._nomes = nomes

    def FindAll(self, _escopo, _condicao):
        return _AchadosFalsos(self._nomes)


class _UiaFalso:
    def CreatePropertyCondition(self, *_a):
        return object()


class _ConstantesFalsas:
    UIA_ControlTypePropertyId = 1
    UIA_TextControlTypeId = 2
    TreeScope_Descendants = 4


def test_trecho_de_codigo_curto_nao_e_jogado_fora():
    """O pedaço curto pertence à frase anterior, não ao lixo."""
    janela = _JanelaFalsa([
        "Como versão mais simples, pode usar",
        "codex exec --json",           # 17 caracteres: era descartado
        "com",                         # 3 caracteres: era descartado
        "--output-last-message",       # 21 caracteres: era descartado
        "e ler o arquivo final. Assim some texto parcial e espera arbitrária.",
    ])

    frases = ponte._texto_por_pedacos(janela, _UiaFalso(), _ConstantesFalsas)

    inteiro = " ".join(frases)
    assert "codex exec --json" in inteiro
    assert "--output-last-message" in inteiro
    # E na ordem certa, não jogado no fim.
    assert inteiro.index("pode usar") < inteiro.index("codex exec --json")
    assert inteiro.index("codex exec --json") < inteiro.index("arquivo final")


def test_a_frase_furada_nao_se_forma_mais():
    """O defeito exato: 'pode usar' + 'e ler o arquivo' virando uma frase só."""
    janela = _JanelaFalsa([
        "Como versão mais simples, pode usar",
        "codex exec --json",
        "e ler o arquivo final, que e o suficiente para o caso do Alex.",
    ])

    frases = ponte._texto_por_pedacos(janela, _UiaFalso(), _ConstantesFalsas)

    assert not any(
        "pode usar e ler o arquivo" in f for f in frases
    ), "a frase se fechou por cima do buraco — é assim que ela engana"


def test_ruido_de_interface_continua_de_fora():
    """Sem o filtro de tamanho, botão e enfeite não podem virar fala."""
    janela = _JanelaFalsa([
        "OK",
        "Cancelar",
        ">>>",
        "Esta aqui e uma frase de verdade, com tamanho de frase de verdade.",
    ])

    frases = ponte._texto_por_pedacos(janela, _UiaFalso(), _ConstantesFalsas)

    assert frases == [
        "Esta aqui e uma frase de verdade, com tamanho de frase de verdade."
    ], "botao e enfeite viraram fala"
