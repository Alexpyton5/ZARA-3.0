"""ZARA-PONTE-CLAUDE-001 — falar com o Claude Code pela voz, sem teclado.

Alex: "ao inves de eu ficar aqui lendo e digitando, toda vez que eu e voce
precisar se comunicar nos comunicamos atravez da zara, ela fica aberta, e eu
falo a ela, leia o que o claude mandou, ela le pra mim, ai eu falo responda
assim faça isso e isso.. ela vinha aqui no claude code e digitava tudo".

Duas direções:

  Claude -> Alex   `claude_ler`    lê a última resposta do Claude em voz alta
  Alex -> Claude   `claude_enviar` digita na caixa do Claude Code e envia

Como a ZARA sabe o que o Claude disse: o Claude Code grava cada sessão num
arquivo `.jsonl` dentro de `~/.claude/projects/<projeto>/`. Lemos de lá. É a
fonte mais confiável — não depende de ler a tela, nem de o Claude lembrar de
escrever num lugar combinado.

O texto é preparado para OUVIDO, não para olho: bloco de código vira "tem um
trecho de código aqui", tabela vira aviso, e o resto é cortado num tamanho que
dá para escutar sem cansar.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from core.action_registry import ActionResult, action

# Janela do app do Claude Code. Título e processo conferidos nesta máquina.
_TITULO_CLAUDE = "claude"
_PROCESSOS_CLAUDE = {"claude.exe", "claude"}

# ZARA-PONTE-LEITURA-COMPLETA-002 — ler tudo é o padrão.
#
# Eu tinha feito o contrário: resumir por padrão, para não cansar. Alex desfez o
# raciocínio com um argumento melhor: "ela tem que ler o texto inteiro, voces
# nao, pois voce e o codex gastam tokens o dela é de graça".
#
# Está certo. Falar não custa nada a ele — a voz da Kore já está paga na sessão
# aberta. Quem custa token sou eu e o Codex, escrevendo. Cortar o texto dela
# economizava o recurso errado e ainda escondia informação.
#
# O teto que sobra é só contra o absurdo: uma resposta gigante lida em voz alta
# vira dez minutos de monólogo, e ele pode mandar parar a qualquer momento.
_LIMITE_FALA = 3000
# Quando ele pedir explicitamente "lê resumido".
_LIMITE_RESUMO = 420


def _raiz_do_projeto() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _pasta_das_conversas() -> Path:
    """~/.claude/projects/<projeto-com-tracos>/ — só um palpite, veja abaixo."""
    apelido = re.sub(r"[^A-Za-z0-9]", "-", str(_raiz_do_projeto()))
    return Path.home() / ".claude" / "projects" / apelido


def _arquivos_de_conversa() -> list[Path]:
    """Todas as conversas do Claude Code, da mais recente para a mais antiga.

    ZARA-PONTE-CAMINHO-001. A primeira versão deduzia a pasta a partir do
    caminho deste arquivo. Isso funcionava rodando do código-fonte e QUEBRAVA no
    app empacotado: dentro do executável o arquivo mora numa pasta temporária,
    então o apelido saía errado e a ZARA respondia "não achei o histórico".

    Agora não deduzimos nada: varremos as pastas de projeto e pegamos a conversa
    mexida mais recentemente. É o que Alex quer dizer com "o que o Claude
    falou" — a conversa que está acontecendo agora, esteja ela em que pasta
    estiver.
    """
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []

    preferida = _pasta_das_conversas()
    arquivos: list[Path] = []
    try:
        for pasta in base.iterdir():
            if pasta.is_dir():
                arquivos.extend(pasta.glob("*.jsonl"))
    except Exception:
        return []

    def chave(p: Path) -> tuple[int, float]:
        try:
            recente = p.stat().st_mtime
        except Exception:
            recente = 0.0
        # Empate desfeito a favor da pasta deste projeto.
        return (1 if p.parent == preferida else 0, recente)

    return sorted(arquivos, key=chave, reverse=True)


def _preparar_para_ouvido(texto: str, limite: int | None = None) -> str:
    """Tira do texto tudo que só faz sentido lendo com os olhos."""
    limite = _LIMITE_FALA if limite is None else limite
    t = texto

    # Blocos de código: viram um aviso curto, não são lidos.
    t = re.sub(r"```[\s\S]*?```", " ... tem um trecho de código aqui ... ", t)
    # Tabelas: idem.
    if re.search(r"^\s*\|.*\|\s*$", t, re.M):
        t = re.sub(r"(?:^\s*\|.*\|\s*$\n?)+", " ... tem uma tabela aqui ... ", t, flags=re.M)
    # Links markdown: fica só o rótulo.
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    # Marcações que não se ouvem.
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"[*_#>]+", " ", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    # Caminhos de arquivo longos cansam de ouvir.
    t = re.sub(r"[A-Za-z]:\\[^\s]{12,}", "um arquivo do projeto", t)
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = t.replace("\n", " ").strip()

    if len(t) > limite:
        corte = t.rfind(".", 0, limite)
        t = t[: corte + 1 if corte > limite // 2 else limite].rstrip()
        t += " ... o resto está escrito na tela."
    return t


def _falas_do_claude(quantas: int = 6) -> list[str]:
    """As últimas falas do Claude, da mais nova para a mais velha."""
    achadas: list[str] = []
    for arquivo in _arquivos_de_conversa()[:3]:
        try:
            linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for linha in reversed(linhas):
            try:
                registro = json.loads(linha)
            except Exception:
                continue
            if registro.get("type") != "assistant":
                continue
            conteudo = (registro.get("message") or {}).get("content")
            pedacos = []
            if isinstance(conteudo, str):
                pedacos.append(conteudo)
            elif isinstance(conteudo, list):
                for bloco in conteudo:
                    if isinstance(bloco, dict) and bloco.get("type") == "text":
                        pedacos.append(bloco.get("text") or "")
            texto = "\n".join(p for p in pedacos if p).strip()
            if texto:
                achadas.append(texto)
                if len(achadas) >= quantas:
                    return achadas
    return achadas


# ZARA-LER-O-ANTERIOR-001
#
# No histórico de 15/08, Alex pediu três vezes seguidas para ela ler o que eu
# tinha escrito, e nas três recebeu O MESMO texto — inclusive quando disse
# "leia o último texto do Claude, ANTES da minha última pergunta".
#
# Ela sempre lia a fala mais recente, então pedir de novo devolvia o mesmo. Numa
# conversa entre pessoas isso não acontece: quem já leu um trecho e é chamado de
# novo entende que o outro quer o de antes.
#
# Guardo o que já foi lido e ando para trás quando o pedido se repete. É o mesmo
# instinto de qualquer pessoa: "esse eu já te li, vou pro anterior".
_JA_LIDO: list[str] = []


def _esquecer_o_que_ja_leu() -> None:
    _JA_LIDO.clear()


def _ultima_fala_do_claude(anterior: bool = False) -> tuple[str, str] | tuple[None, str]:
    if not _arquivos_de_conversa():
        return None, "Ainda não há conversa gravada com o Claude Code."

    falas = _falas_do_claude()
    if not falas:
        return None, "Não encontrei nenhuma resposta do Claude para ler."

    if anterior:
        # Pedido explícito de "o de antes": pula tudo que já foi lido.
        for texto in falas:
            if texto not in _JA_LIDO:
                _JA_LIDO.append(texto)
                return texto, ""
        return None, "Já te li tudo que o Claude escreveu nesta conversa."

    mais_nova = falas[0]
    # A pergunta é "a mais nova já foi lida?", não "foi a última que eu li".
    # Depois de recuar para a segunda fala, a última lida deixa de ser a mais
    # nova — e a comparação errada fazia ela pular de volta para o topo.
    if mais_nova in _JA_LIDO:
        # Ele pediu de novo e nada mudou do outro lado: ele quer o anterior.
        for texto in falas[1:]:
            if texto not in _JA_LIDO:
                _JA_LIDO.append(texto)
                return texto, ""
        return None, "Essa foi a última coisa que o Claude escreveu; não tem mais nada novo."

    _JA_LIDO.append(mais_nova)
    return mais_nova, ""


@action(
    name="claude_ler",
    category="os",
    description="Lê em voz alta a última resposta do Claude Code",
    capability="LOCAL_PC_CONTROL",
)
def claude_ler_action(resumido: bool = False) -> ActionResult:
    bruto, erro = _ultima_fala_do_claude()
    if bruto is None:
        return ActionResult(success=False, error=erro)

    falado = _preparar_para_ouvido(bruto, limite=_LIMITE_RESUMO if resumido else None)
    if not falado:
        return ActionResult(success=False, error="A última resposta do Claude não tem texto para ler.")

    return ActionResult(
        success=True,
        output=falado,
        data={"caracteres_originais": len(bruto), "caracteres_falados": len(falado)},
    )


def _janela_do_claude() -> int | None:
    return _janela_por(_TITULO_CLAUDE, _PROCESSOS_CLAUDE)


def _janela_por(titulo_alvo: str, processos: set[str]) -> int | None:
    from core.actions.os_ops import _eligible_windows, _window_process_name, _window_text

    for hwnd in _eligible_windows():
        processo = str(_window_process_name(hwnd) or "").casefold()
        titulo = str(_window_text(hwnd) or "").strip().casefold()
        if processo in processos or titulo == titulo_alvo:
            return hwnd
    return None


# --- Codex -----------------------------------------------------------------
#
# O Codex roda dentro do app de desktop do ChatGPT, que NÃO grava a conversa em
# disco (conferido: nada novo em ~/.codex/sessions hoje, enquanto Alex usava).
# Então a resposta dele é lida da própria janela, pela camada de acessibilidade
# do Windows — a mesma que leitores de tela usam.
#
# Isso é menos confiável que ler arquivo: depende do que está desenhado na tela.
# Se o Codex ainda estiver escrevendo, pega a resposta pela metade.
_TITULO_CODEX = "chatgpt"
_PROCESSOS_CODEX = {"chatgpt.exe", "chatgpt"}

# Linhas que são ferramenta ou enfeite da interface, não fala do Codex.
_RUIDO_CODEX = re.compile(
    r"^(?:ran\b|stopped\b|running\b|executou|executando|searched\b|reading\b|"
    r"read\b|edited\b|explored\b|thought\b|worked\b|\$|>|\d+\s*$|"
    r"faça o que quiser|acesso completo|ativar o windows|acesse configurações)",
    re.I,
)


def _parece_fala_humana(texto: str) -> bool:
    """Separa prosa de saída de terminal.

    O Codex mostra na mesma tela o que ele DIZ e o que ele RODA. Ler comando em
    voz alta é insuportável — e foi o que aconteceu no primeiro teste, com a ZARA
    pronunciando um script inteiro de PowerShell.

    Prosa tem palavras e pontuação; comando tem símbolo. A densidade de símbolos
    separa os dois melhor que qualquer lista de prefixos.
    """
    if _RUIDO_CODEX.match(texto):
        return False
    simbolos = sum(texto.count(c) for c in "$@{}|;=[]()\\<>_")
    if simbolos > max(4, len(texto) * 0.04):
        return False
    if "://" in texto or ".exe" in texto.lower():
        return False
    palavras = texto.split()
    if len(palavras) < 5:
        return False
    # Prosa em português tem espaços curtos entre palavras; comando não.
    return sum(len(p) for p in palavras) / len(palavras) < 12


def _texto_visivel_da_janela(titulo: str) -> list[str]:
    """Lê as frases desenhadas numa janela pela acessibilidade do Windows."""
    import comtypes.client

    try:
        from comtypes.gen import UIAutomationClient as UIA
    except Exception:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    condicao = uia.CreatePropertyCondition(UIA.UIA_NamePropertyId, titulo)
    janela = uia.GetRootElement().FindFirst(UIA.TreeScope_Children, condicao)
    if janela is None:
        return []

    frases = _texto_por_documento(janela, UIA)
    if frases:
        return frases
    return _texto_por_pedacos(janela, uia, UIA)


def _texto_por_documento(janela, UIA) -> list[str]:
    """Lê o documento inteiro de uma vez, do jeito que um leitor de tela lê.

    ZARA-PONTE-LEITURA-BURACO-001
    --------------------------------
    Sintoma: as respostas do Codex chegavam furadas. Ele recomendou dois
    comandos e o que a ZARA entregou foi "pode usar" seguido de "e ler o
    arquivo final" — sem o comando no meio, que era a informação inteira.

    Causa, confirmada pelo próprio Codex ("sim, uso crases de Markdown para
    nomes de comandos"): a leitura antiga catava elemento por elemento e só
    aceitava os com mais de 30 caracteres. Markdown com crase vira um elemento
    separado e curto — `stdio` tem 5, `codex exec --json` tem 17. Todos eram
    descartados, e o que sobrava eram as bordas do buraco, coladas uma na
    outra, formando uma frase que parecia inteira e não era.

    Frase incompleta que PARECE completa é pior que erro: ninguém desconfia.

    Aqui a leitura passa a ser do documento, na ordem visual, com o texto de
    dentro dos elementos de código junto. Some o costurar pedaços à mão e some
    o filtro de tamanho, que era a causa.
    """
    try:
        padrao = janela.GetCurrentPattern(UIA.UIA_TextPatternId)
        if padrao is None:
            return []
        texto = padrao.QueryInterface(UIA.IUIAutomationTextPattern).DocumentRange.GetText(-1)
    except Exception:
        return []

    frases = []
    for linha in str(texto or "").splitlines():
        limpa = " ".join(linha.split())
        if len(limpa) > 30 and _parece_fala_humana(limpa):
            frases.append(limpa)
    return frases


def _texto_por_pedacos(janela, uia, UIA) -> list[str]:
    """Reserva, para janelas sem documento legível.

    Continua juntando os pedaços curtos ao pedaço anterior em vez de jogá-los
    fora: é exatamente aí que o texto do Codex perdia os nomes de comando.
    """
    so_texto = uia.CreatePropertyCondition(
        UIA.UIA_ControlTypePropertyId, UIA.UIA_TextControlTypeId
    )
    achados = janela.FindAll(UIA.TreeScope_Descendants, so_texto)

    blocos: list[str] = []
    for i in range(achados.Length):
        nome = " ".join((achados.GetElement(i).CurrentName or "").split())
        if not nome:
            continue
        # Pedaço curto no meio da conversa é quase sempre um trecho de código
        # inline, e ele pertence à frase que veio antes.
        if len(nome) <= 30 and blocos:
            blocos[-1] = f"{blocos[-1]} {nome}"
        else:
            blocos.append(nome)

    return [b for b in blocos if len(b) > 30 and _parece_fala_humana(b)]


def _esperar_o_codex_parar_de_escrever(
    tentativas: int = 6, intervalo: float = 0.45
) -> tuple[list[str], bool]:
    """Só lê quando a tela parar de mudar. ZARA-PONTE-CLAUDE-002.

    Sugestão do Codex, e ela é certeira: lendo a janela crua, uma resposta em
    andamento é capturada pela metade e a ZARA fala um pedaço de frase. Como o
    texto cresce enquanto ele escreve, basta comparar duas leituras seguidas —
    quando param de diferir, ele terminou.

    (A proposta dele incluía também uma fila em banco compartilhado. Isso não se
    sustenta aqui: o app do Codex é fechado e não escreve em banco nenhum, então
    a fila teria de ser alimentada... lendo a tela. O problema voltaria pelo
    mesmo lugar, com uma peça a mais para quebrar.)
    """
    anterior: list[str] | None = None
    for _ in range(tentativas):
        atual = _texto_visivel_da_janela("ChatGPT")
        if anterior is not None and atual == anterior:
            return atual, True
        anterior = atual
        time.sleep(intervalo)
    return anterior or [], False


@action(
    name="codex_ler",
    category="os",
    description="Lê em voz alta a última resposta do Codex",
    capability="LOCAL_PC_CONTROL",
)
def codex_ler_action(resumido: bool = False) -> ActionResult:
    try:
        frases, estavel = _esperar_o_codex_parar_de_escrever()
    except Exception as exc:
        return ActionResult(success=False, error=f"Não consegui ler a janela do Codex: {exc}")

    if not estavel:
        return ActionResult(
            success=False,
            error="O Codex ainda está escrevendo. Me pede de novo daqui a pouco.",
        )

    if not frases:
        return ActionResult(
            success=False,
            error="Não achei texto na janela do Codex; ele está aberto e com uma resposta na tela?",
        )

    # A resposta é o FIM da tela. Vamos de trás para frente juntando blocos até
    # encher o que dá para escutar — assim uma resposta longa vem inteira, e uma
    # curta não arrasta junto a conversa anterior.
    teto = _LIMITE_RESUMO if resumido else _LIMITE_FALA
    escolhidos: list[str] = []
    tamanho = 0
    for bloco in reversed(frases):
        if escolhidos and tamanho + len(bloco) > teto:
            break
        escolhidos.append(bloco)
        tamanho += len(bloco)
    escolhidos.reverse()

    falado = _preparar_para_ouvido(" ".join(escolhidos), limite=teto)
    if not falado:
        return ActionResult(success=False, error="A última resposta do Codex não tem texto para ler.")

    return ActionResult(
        success=True,
        output=falado,
        data={"blocos_lidos": len(frases), "caracteres_falados": len(falado)},
    )


@action(
    name="codex_enviar",
    category="os",
    description="Digita uma mensagem na caixa do Codex e envia",
    capability="LOCAL_PC_CONTROL",
)
def codex_enviar_action(texto: str = "") -> ActionResult:
    mensagem_crua = str(texto or "").strip()
    return _enviar_para_janela(
        texto,
        _janela_por(_TITULO_CODEX, _PROCESSOS_CODEX),
        "O Codex não está aberto; não tenho para onde mandar a mensagem.",
        "Mandei para o Codex.",
        confirmar=lambda: _mensagem_chegou_ao_codex(mensagem_crua),
    )


def _mensagem_chegou_ao_codex(mensagem: str, espera: float = 6.0) -> bool:
    """A mensagem apareceu escrita na conversa do Codex?

    ZARA-PONTE-ENVIO-CEGO-001. O Codex não tem histórico em disco confiável
    como o Claude, então a prova é a própria tela: se o texto do Alex está
    desenhado na conversa, o Codex recebeu. É mais fraco que ler um arquivo,
    mas é uma observação do mundo — não é a ZARA acreditando em si mesma.
    """
    alvo = " ".join(str(mensagem or "").split()).casefold()[:60]
    if not alvo:
        return False
    limite = time.time() + espera
    while time.time() < limite:
        try:
            frases = _texto_visivel_da_janela("ChatGPT")
        except Exception:
            frases = []
        if alvo in " ".join(" ".join(frases).split()).casefold():
            return True
        time.sleep(0.6)
    return False


# ZARA-PONTE-REPASSE-001
#
# Alex: "tem alguma forma de voces 3 conversarem?". Tem: a ZARA no meio. Ela já
# lia de um e escrevia no outro, mas em dois comandos. Aqui vira um só.
#
# O repasse passa o texto CRU, não o preparado para voz — o outro lado é uma
# máquina lendo, não um ouvido. Preparar para fala tiraria justamente o código e
# os caminhos de arquivo que o outro precisa.
#
# Alex continua no meio de propósito: é ele quem decide o que é repassado. Dois
# agentes conversando sozinhos se enrolam em círculo e gastam token à toa.
_ORIGENS = {
    "claude": ("Claude", lambda: _ultima_fala_do_claude()),
    "codex": ("Codex", lambda: _ultima_fala_do_codex()),
}


def _ultima_fala_do_codex() -> tuple[str, str] | tuple[None, str]:
    try:
        frases, estavel = _esperar_o_codex_parar_de_escrever()
    except Exception as exc:
        return None, f"Não consegui ler a janela do Codex: {exc}"
    if not estavel:
        return None, "O Codex ainda está escrevendo. Me pede de novo daqui a pouco."
    if not frases:
        return None, "Não achei resposta do Codex na tela."
    return " ".join(frases[-3:]), ""


@action(
    name="ponte_repassar",
    category="os",
    description="Pega a última resposta de um e manda para o outro",
    capability="LOCAL_PC_CONTROL",
)
def ponte_repassar_action(rota: str = "") -> ActionResult:
    """rota no formato 'claude>codex' ou 'codex>claude'."""
    partes = str(rota or "").strip().casefold().split(">")
    if len(partes) != 2 or partes[0] not in _ORIGENS or partes[1] not in _ORIGENS:
        return ActionResult(success=False, error="Não entendi de quem para quem é o recado.")
    de, para = partes
    if de == para:
        return ActionResult(success=False, error="A origem e o destino são o mesmo.")

    nome_origem, ler = _ORIGENS[de]
    texto, erro = ler()
    if texto is None:
        return ActionResult(success=False, error=erro)

    texto = texto.strip()
    if len(texto) > 2000:
        texto = texto[:2000].rsplit(" ", 1)[0]

    recado = f"[recado do {nome_origem}, repassado pela ZARA a pedido do Alex]\n\n{texto}"

    if para == "claude":
        enviado = _enviar_para_janela(
            recado, _janela_do_claude(),
            "O Claude Code não está aberto.", "Repassei para o Claude.",
        )
    else:
        enviado = _enviar_para_janela(
            recado, _janela_por(_TITULO_CODEX, _PROCESSOS_CODEX),
            "O Codex não está aberto.", "Repassei para o Codex.",
        )
    return enviado


@action(
    name="claude_enviar",
    category="os",
    description="Digita uma mensagem na caixa do Claude Code e envia",
    capability="LOCAL_PC_CONTROL",
)
def claude_enviar_action(texto: str = "") -> ActionResult:
    mensagem_crua = str(texto or "").strip()
    resultado = _enviar_para_janela(
        texto,
        _janela_do_claude(),
        "O Claude Code não está aberto; não tenho para onde mandar a mensagem.",
        "Mandei para o Claude.",
        confirmar=lambda: _mensagem_chegou_ao_claude(mensagem_crua),
    )
    if not resultado.success:
        return resultado
    # No modo cego a confirmação já foi feita pelo histórico; não repetir a
    # espera de 6 segundos por nada.
    if (resultado.data or {}).get("modo") == "cego":
        return resultado

    # ZARA-PONTE-ENVIO-CHEGOU-001
    #
    # Digitar e apertar Enter não prova que a mensagem chegou a QUEM ela leu.
    # O app do Claude tem várias conversas abertas; a caixa que recebe o texto é
    # a da conversa que está na tela, e essa pode não ser a mesma de onde ela
    # leu a resposta. Foi o que aconteceu: ela enviou duas vezes, a caixa
    # esvaziou nas duas, e nada apareceu na conversa certa.
    #
    # A prova real é o outro lado: o Claude Code grava cada mensagem recebida no
    # histórico. Se o texto do Alex aparecer lá, chegou. Se não aparecer em
    # alguns segundos, foi para outra conversa — e ela diz isso.
    mensagem = str(texto or "").strip()
    if _mensagem_chegou_ao_claude(mensagem):
        return resultado

    return ActionResult(
        success=False,
        error=(
            "Escrevi e enviei, mas a mensagem não apareceu nesta conversa do Claude. "
            "Provavelmente foi para outra conversa aberta. Deixe na tela a conversa "
            "certa e me peça de novo."
        ),
        data={"enviado_na_janela": True, "chegou_na_conversa": False},
    )


def _mensagem_chegou_ao_claude(mensagem: str, espera: float = 6.0) -> bool:
    """Confere no histórico do Claude Code se a mensagem do Alex entrou."""
    alvo = " ".join(mensagem.split()).casefold()[:60]
    if not alvo:
        return False

    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        for arquivo in _arquivos_de_conversa()[:2]:
            try:
                linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for linha in reversed(linhas[-40:]):
                try:
                    registro = json.loads(linha)
                except Exception:
                    continue
                if registro.get("type") != "user":
                    continue
                conteudo = (registro.get("message") or {}).get("content")
                bruto = conteudo if isinstance(conteudo, str) else json.dumps(
                    conteudo, ensure_ascii=False
                )
                if alvo in " ".join(str(bruto).split()).casefold():
                    return True
        time.sleep(0.6)
    return False


def _enviar_para_janela(
    texto: str,
    hwnd: int | None,
    erro_fechado: str,
    aviso_ok: str,
    confirmar: Callable[[], bool] | None = None,
) -> ActionResult:
    """Foca a janela, cola o texto, CONFERE que entrou, e só então envia.

    ZARA-PONTE-ENVIO-VERIFICADO-001. A primeira versão dizia "Mandei para o
    Claude" sempre que o Ctrl+V não desse erro. Alex mandou "responde pro Claude
    funcionou", ela anunciou o envio, e nada chegou: a janela estava na frente,
    mas o cursor não estava na caixa de texto — a colagem caiu no vazio.

    Isso é falso sucesso, que é o defeito que este projeto mais combate. Agora a
    caixa é lida antes e depois: se o texto não aparecer lá, ela diz que não
    conseguiu, em vez de inventar que mandou.
    """
    from core.actions.os_ops import (
        _focus_window_verified,
        _focused_editable_field,
        _foreground_window,
        _send_fixed_hotkey,
        _send_unicode_text,
        _uia_field_text,
    )

    mensagem = str(texto or "").strip()
    if not mensagem:
        return ActionResult(success=False, error="Não entendi o que você quer mandar.")
    if len(mensagem) > 2000:
        return ActionResult(success=False, error="A mensagem ficou grande demais para enviar de uma vez.")
    if hwnd is None:
        return ActionResult(success=False, error=erro_fechado)

    if not _focus_window_verified(hwnd):
        return ActionResult(success=False, error="Não consegui trazer a janela para a frente.")

    time.sleep(0.3)
    if _foreground_window() != hwnd:
        return ActionResult(success=False, error="A janela não ficou em primeiro plano.")

    # A caixa de texto precisa estar com o cursor. Trazer a janela para a frente
    # não garante isso — foi exatamente o que falhou.
    campo = _focused_editable_field()
    if campo is None:
        _clicar_na_caixa_de_texto(hwnd)
        time.sleep(0.25)
        campo = _focused_editable_field()

    # ZARA-PONTE-ENVIO-CEGO-001
    #
    # Alex: "a zara ta mandando isso aqui o tempo todo no telegram" — a frase
    # repetida era exatamente a recusa daqui: "não achei a caixa de mensagem".
    #
    # O Claude Code e o Codex são apps Chromium. O Chromium só monta a árvore de
    # acessibilidade sob demanda, e às vezes não a monta a tempo para uma janela
    # que acabou de vir do segundo plano. Ou seja: a caixa existe, está com o
    # cursor, e mesmo assim a busca devolve nada. Recusar aí é desistir de uma
    # coisa que ia funcionar.
    #
    # Então, quando a caixa não aparece, ela escreve mesmo assim — mas sem
    # inventar sucesso. Nesse modo a prova deixa de ser a leitura da caixa e
    # passa a ser a única prova que realmente importa: o texto aparecer do outro
    # lado. Sem essa confirmação, ela diz que não conseguiu.
    cego = campo is None
    if cego and confirmar is None:
        return ActionResult(
            success=False,
            error="A janela abriu, mas não achei a caixa de mensagem para escrever. Clique nela uma vez e peça de novo.",
        )

    antes = "" if cego else (_uia_field_text(campo) or "")

    if not _send_unicode_text(mensagem):
        return ActionResult(success=False, error="Não consegui colar a mensagem na caixa.")

    time.sleep(0.35)
    if not cego:
        # ZARA-PONTE-ENVIO-ESPERA-001. Mesma lição da postcondição: o app do
        # ChatGPT é pesado e nem sempre atualiza a caixa em 0,35 s. Uma leitura
        # única transformava "ainda não desenhou" em "não colei", e a mensagem
        # boa era descartada sem nunca ser enviada.
        depois = None
        for _ in range(10):  # ~4 s no total, instantâneo no teste
            depois = _uia_field_text(campo)
            if depois is not None and mensagem[:40] in depois:
                break
            time.sleep(0.4)
        if depois is None or mensagem[:40] not in depois:
            return ActionResult(
                success=False,
                error="Colei a mensagem mas ela não apareceu na caixa; não enviei nada.",
                data={"antes": len(antes), "depois": len(depois or "")},
            )

    _send_fixed_hotkey((0x0D,))  # Enter

    if cego:
        # Nada foi lido da tela. Quem decide é o histórico do outro lado.
        if confirmar is not None and confirmar():
            return ActionResult(
                success=True,
                output=aviso_ok,
                data={"hwnd": hwnd, "caracteres": len(mensagem), "modo": "cego"},
            )
        return ActionResult(
            success=False,
            error=(
                "Escrevi na janela mas não consegui confirmar que a mensagem chegou. "
                "Deixe a conversa na tela e me peça de novo."
            ),
            data={"modo": "cego"},
        )

    # Postcondição real: caixa vazia = a mensagem partiu.
    #
    # ZARA-PONTE-ENVIO-ESPERA-001. Conferir uma vez, meio segundo depois do
    # Enter, dava falso NEGATIVO — que é tão ruim quanto o falso positivo, só
    # que ao contrário: a mensagem chegava ao Codex, ele respondia, e a ZARA
    # dizia ao Alex que não tinha conseguido enviar. Medido: a caixa do app do
    # ChatGPT ainda continha o texto em 0,5 s e já estava limpa depois.
    # Aplicativo pesado esvazia a caixa quando quer; ela espera.
    partiu = False
    for _ in range(12):  # ~5 s no total, e instantâneo no teste
        restou = _uia_field_text(campo)
        if restou is not None and mensagem[:40] not in restou:
            partiu = True
            break
        time.sleep(0.4)
    if not partiu:
        # Última chance antes de acusar falha: o texto apareceu na conversa?
        if confirmar is not None and confirmar():
            return ActionResult(
                success=True,
                output=aviso_ok,
                data={"hwnd": hwnd, "caracteres": len(mensagem), "verificado": "conversa"},
            )
        return ActionResult(
            success=False,
            error="Escrevi a mensagem mas ela não foi enviada; o texto continua na caixa.",
        )

    return ActionResult(
        success=True,
        output=aviso_ok,
        data={"hwnd": hwnd, "caracteres": len(mensagem), "verificado": True},
    )


def _clicar_na_caixa_de_texto(hwnd: int) -> bool:
    """Põe o cursor na caixa de mensagem, quando a janela ganha foco sem ela.

    Procura pela acessibilidade — nada de clique por coordenada, que quebra com
    resolução, idioma e tema.
    """
    try:
        import comtypes.client

        try:
            from comtypes.gen import UIAutomationClient as UIA
        except Exception:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA

        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation
        )
        janela = uia.ElementFromHandle(hwnd)
        if janela is None:
            return False
        for tipo in (UIA.UIA_EditControlTypeId, UIA.UIA_DocumentControlTypeId):
            condicao = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, tipo)
            achados = janela.FindAll(UIA.TreeScope_Descendants, condicao)
            # A caixa de digitar costuma ser a última da árvore, no rodapé.
            for i in range(achados.Length - 1, -1, -1):
                elemento = achados.GetElement(i)
                try:
                    if not elemento.CurrentIsEnabled or elemento.CurrentIsOffscreen:
                        continue
                    elemento.SetFocus()
                    return True
                except Exception:
                    continue
        return False
    except Exception:
        return False
