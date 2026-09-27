"""ZARA-TELEGRAM-001 — Alex comandando a equipe pelo celular.

Ele: "eu nao posso ficar o dia todo sentado em frente ao computador, isso
ajudaria muito." É a prioridade número um dele, e é a que mais devolve tempo de
vida: hoje qualquer instrução exige ele estar na cadeira.

**Por que Telegram e não WhatsApp.** O WhatsApp oficial exige conta de empresa,
aprovação e cobra por mensagem. O caminho não-oficial (bibliotecas de QR code)
derruba número — o risco é o telefone pessoal dele ser banido. Telegram tem bot
gratuito, oficial e sem risco de banimento.

**Sem servidor e sem abrir porta.** A ZARA pergunta ao Telegram se há mensagem
nova (long polling). Nada entra no computador dele por iniciativa de fora, o que
é a diferença entre uma ponte e uma porta aberta na internet.

**Só ele fala.** O bot ignora qualquer pessoa que não seja o dono. Sem isso,
quem descobrisse o nome do bot teria controle do computador dele.

Roteamento das mensagens:

    "claude: ..."  -> digita no Claude Code
    "codex: ..."   -> digita no Codex
    "zara: ..."    -> comando para a própria ZARA
    qualquer outra -> tratada como comando da ZARA
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from pathlib import Path

_API = "https://api.telegram.org/bot{token}/{metodo}"
_ESPERA_LONGA = 25  # segundos que o Telegram segura a conexão esperando mensagem
_LIMITE_MENSAGEM = 3500  # o Telegram corta em 4096; folga para o prefixo

# ZARA-TELEGRAM-SEM-REPETICAO-001
#
# Alex: "a zara ta mandando isso aqui o tempo todo no telegram".
#
# O Telegram guarda por 24h toda mensagem que o bot não confirmou ter lido, e
# reentrega tudo na próxima vez que alguém pergunta. Como o marcador de leitura
# vivia só na memória e voltava a zero a cada abertura da ZARA, cada vez que ele
# abria o app ela reexecutava as MESMAS mensagens antigas e reenviava as mesmas
# respostas. Não era um erro repetido: era o mesmo erro, de novo, do começo.
#
# Três travas, nesta ordem:
#   1. o marcador vive em disco e sobrevive a reinício
#   2. na primeira vez de todas, pula o acumulado e começa do agora
#   3. mensagem velha demais é descartada, mesmo que reapareça
_IDADE_MAXIMA = 60 * 60  # segundos; mais velho que isso não se executa sozinho
_JANELA_REPETICAO = 120  # não repetir a mesma resposta dentro deste intervalo


def _chamar(token: str, metodo: str, **parametros) -> dict | None:
    """Uma chamada à API do Telegram. Devolve None em qualquer falha."""
    url = _API.format(token=token, metodo=metodo)
    dados = urllib.parse.urlencode(
        {k: v for k, v in parametros.items() if v is not None}
    ).encode()
    try:
        with urllib.request.urlopen(url, data=dados, timeout=_ESPERA_LONGA + 10) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return corpo if corpo.get("ok") else None


class PonteTelegram:
    """Recebe ordens do celular do Alex e devolve as respostas."""

    def __init__(
        self,
        token: str,
        executar: Callable[[str, str], Awaitable[str]],
        *,
        dono: int | None = None,
        interceptar: Callable[[int, str], Awaitable[str | None]] | None = None,
    ):
        self.token = str(token or "").strip()
        # executar(destino, texto) -> resposta em texto
        self.executar = executar
        # ZARA-TELEGRAM-LAB-BRIDGE-001: gancho opcional, chamado ANTES do
        # roteamento normal, para o portão de aprovação do Lab
        # (core.lab_v1.telegram_gate) decidir se uma mensagem do dono é um
        # comando dele (SIM/NÃO/RESTAURAR/VOLTAR) sem precisar de um segundo
        # consumidor de getUpdates. Devolve None quando não é um comando do
        # Lab — aí o fluxo de sempre continua, sem mudança nenhuma. Quando
        # ninguém passa este parâmetro (comportamento padrão), esta ponte se
        # comporta exatamente como antes.
        self._interceptar = interceptar
        # Aprendido na primeira mensagem: a partir daí, só este chat é aceito.
        self.dono = dono
        self._ultimo_update = 0
        self._parar = asyncio.Event()
        self._tarefa: asyncio.Task | None = None
        self._ultima_resposta = ("", 0.0)
        # ZARA-TELEGRAM-VIVA-001: hora da ultima volta bem-sucedida no
        # Telegram. E o unico fato que prova que a ponte esta viva.
        self._ultimo_sucesso = 0.0

    # ------------------------------------------------------------------
    @property
    def configurado(self) -> bool:
        return bool(self.token) and "COLE" not in self.token.upper()

    # ZARA-TELEGRAM-SEM-REPETICAO-001 -----------------------------------
    @staticmethod
    def _arquivo_marcador() -> Path | None:
        try:
            from core.paths import config_dir

            return config_dir() / "telegram_lido.json"
        except Exception:
            return None

    def _carregar_marcador(self) -> bool:
        """Devolve True se já havia marcador (ou seja: não é a primeira vez).

        Vale o ARQUIVO existir, não o número ser maior que zero. Se a primeira
        abertura pegasse a caixa vazia, o marcador ficaria em 0 e ela trataria
        toda abertura seguinte como a primeira — jogando fora justamente o que
        ele mandou enquanto a ZARA estava fechada.
        """
        arquivo = self._arquivo_marcador()
        if arquivo is None or not arquivo.exists():
            return False
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            self._ultimo_update = int(dados.get("ultimo_update") or 0)
            if self.dono is None and dados.get("dono"):
                self.dono = int(dados["dono"])
        except Exception:
            return False
        return True

    def _gravar_marcador(self) -> None:
        arquivo = self._arquivo_marcador()
        if arquivo is None:
            return
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(
                json.dumps({"ultimo_update": self._ultimo_update, "dono": self.dono}),
                encoding="utf-8",
            )
        except Exception:
            pass  # perder o marcador atrasa, não quebra

    def _pular_acumulado(self) -> None:
        """Primeira vez de todas: descarta o que está represado no Telegram.

        Sem isso, tudo que ele mandou antes da ponte existir chega de uma vez e
        é executado como se fosse pedido agora.
        """
        pacote = _chamar(self.token, "getUpdates", offset=-1, timeout=0)
        for update in (pacote or {}).get("result") or []:
            self._ultimo_update = max(self._ultimo_update, int(update.get("update_id", 0)))
        if self._ultimo_update:
            # Confirma a leitura no servidor para o Telegram parar de reentregar.
            _chamar(self.token, "getUpdates", offset=self._ultimo_update + 1, timeout=0)
            print(f"[TELEGRAM] acumulado antigo descartado ate {self._ultimo_update}", flush=True)
        self._gravar_marcador()

    # ------------------------------------------------------------------
    async def iniciar(self) -> bool:
        if not self.configurado or self._tarefa is not None:
            return False
        eu = await asyncio.to_thread(_chamar, self.token, "getMe")
        if not eu:
            print("[TELEGRAM] token recusado pelo Telegram; ponte nao ligou", flush=True)
            return False
        nome = (eu.get("result") or {}).get("username", "?")
        if not self._carregar_marcador():
            await asyncio.to_thread(self._pular_acumulado)
        self._parar.clear()
        self._ultimo_sucesso = time.time()
        self._tarefa = asyncio.create_task(self._escutar(), name="zara-telegram")
        print(f"[TELEGRAM] ponte ligada como @{nome} (a partir de {self._ultimo_update})", flush=True)
        return True

    async def parar(self) -> None:
        self._parar.set()
        if self._tarefa:
            self._tarefa.cancel()
            self._tarefa = None

    # ------------------------------------------------------------------
    async def avisar(self, texto: str) -> bool:
        """Manda uma mensagem para o celular do Alex."""
        if not self.configurado or not self.dono:
            return False
        corpo = str(texto or "").strip()
        if not corpo:
            return False
        # ZARA-TELEGRAM-SEM-REPETICAO-001. Última trava: mesmo que algo volte a
        # disparar duas vezes, ele não recebe a mesma frase duas vezes seguidas.
        anterior, quando = self._ultima_resposta
        agora = time.time()
        if corpo == anterior and (agora - quando) < _JANELA_REPETICAO:
            return True
        self._ultima_resposta = (corpo, agora)
        if len(corpo) > _LIMITE_MENSAGEM:
            corpo = corpo[:_LIMITE_MENSAGEM] + "\n\n[...] o resto está no computador."
        resposta = await asyncio.to_thread(
            _chamar, self.token, "sendMessage", chat_id=self.dono, text=corpo
        )
        return resposta is not None

    # ------------------------------------------------------------------
    @staticmethod
    def rotear(texto: str) -> tuple[str, str]:
        """Descobre para quem é a mensagem. Devolve (destino, conteúdo).

        ZARA-TELEGRAM-ROTEAMENTO-002. Alex escreveu "codex, tamo so testando a
        conexao" e a mensagem foi parar na ZARA, que respondeu "não entendi".
        O casamento exigia `codex:` ou `codex ` — vírgula depois do nome não
        contava. Ninguém escreve chamando alguém sem vírgula.

        Também aceita "todos", porque ele escreveu "todos- se voces 3 estao
        vendo esta mensagem responda sim" e não existia esse destino.
        """
        limpo = " ".join(str(texto or "").split())
        # ZARA-TELEGRAM-ROTEAMENTO-003. Alex escreveu "@claude de uma analisada
        # nestes videos" e a mensagem foi parar na ZARA. No Telegram, marcar
        # alguém com @ é o gesto natural — e era justamente o que não funcionava.
        # Comandos de bot em grupos chegam como `/codex@Thunderbot pedido`.
        # O sufixo identifica o bot, não o destino. Só removemos a barra quando
        # o comando aponta para um destino conhecido; comandos desconhecidos
        # continuam inteiros para a ZARA decidir o que fazer com eles.
        if limpo.startswith("/"):
            comando, _separador, conteudo = limpo[1:].partition(" ")
            nome = comando.split("@", 1)[0].rstrip(":,-—–.!?").casefold()
            destinos_de_comando = {
                "claude": "claude",
                "codex": "codex",
                "zara": "zara",
                "todos": "todos",
                "galera": "todos",
            }
            if nome in destinos_de_comando:
                return destinos_de_comando[nome], conteudo.strip(" :,-—–.!?")
            return "zara", limpo

        limpo = limpo.lstrip("@").lstrip()
        baixo = limpo.casefold()
        for nome, destino in (
                    ("claude", "claude"),
                    ("codex", "codex"),
                    ("zara", "zara"),
                    ("todos", "todos"),
                    ("todo mundo", "todos"),
                    ("galera", "todos"),
                ):
            if not baixo.startswith(nome):
                continue
            resto = limpo[len(nome):]
            # O nome tem de terminar ali: pontuação ou espaço. Sem isso,
            # "codexplorer" viraria mensagem para o Codex.
            if resto and resto[0] not in " :,-—–.!?":
                continue
            return destino, resto.strip(" :,-—–.!?")
        return "zara", limpo

    # ZARA-TELEGRAM-VIVA-001
    #
    # Alex ia sair e me pediu para conferir se estava tudo de pé. A ZARA estava
    # aberta e o Telegram estava MUDO — ela não estava escutando o bot. Se ele
    # tivesse saído, teria mandado mensagem para o vazio e só descobriria ao
    # voltar. Foi eu que peguei por acaso; ele não teria como perceber.
    #
    # A causa está aqui: o laço engolia qualquer exceção e seguia, e uma falha
    # persistente virava silêncio permanente sem ninguém saber. Pior: se o laço
    # morresse de vez, nada notava.
    #
    # Agora o laço marca a hora de cada volta bem-sucedida. Quem olha de fora
    # consegue perguntar "você está viva?" e receber uma resposta baseada em
    # fato, não na existência do objeto. Ver `esta_viva`.
    @property
    def esta_viva(self) -> bool:
        """Deu uma volta completa no Telegram há pouco tempo?

        Não basta a tarefa existir: tarefa existindo e falhando em silêncio foi
        exatamente o defeito. O que conta é ter conversado com o Telegram.
        """
        if self._tarefa is None or self._tarefa.done():
            return False
        # Uma volta demora no máximo `_ESPERA_LONGA` + a folga do erro. Três
        # vezes isso já é sinal de que parou de verdade.
        return (time.time() - self._ultimo_sucesso) < (_ESPERA_LONGA * 3)

    async def _escutar(self) -> None:
        falhas = 0
        while not self._parar.is_set():
            try:
                pacote = await asyncio.to_thread(
                    _chamar, self.token, "getUpdates",
                    offset=self._ultimo_update + 1, timeout=_ESPERA_LONGA,
                )
                if not pacote:
                    falhas += 1
                    # Falha isolada é rede. Falha repetida é problema, e
                    # precisa aparecer no log em vez de virar silêncio.
                    if falhas in (3, 10, 30):
                        print(f"[TELEGRAM] {falhas} tentativas sem resposta", flush=True)
                    # Espera crescente: bater de 3 em 3 segundos numa API que
                    # está recusando só piora e mascara o problema.
                    await asyncio.sleep(min(3 * falhas, 30))
                    continue
                falhas = 0
                self._ultimo_sucesso = time.time()
                for update in pacote.get("result") or []:
                    self._ultimo_update = max(self._ultimo_update, int(update.get("update_id", 0)))
                    self._gravar_marcador()  # antes de tratar: falha não repete
                    await self._tratar(update)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                falhas += 1
                print(f"[TELEGRAM] erro no laco: {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(min(5 * falhas, 30))

    async def _tratar(self, update: dict) -> None:
        mensagem = update.get("message") or update.get("edited_message") or {}
        texto = str(mensagem.get("text") or "").strip()
        chat = (mensagem.get("chat") or {}).get("id")

        # ZARA-TELEGRAM-AUDIO-001. Ele prefere falar a digitar — é o motivo de a
        # ZARA existir. Áudio vira texto e segue pela MESMA porta: mesmo
        # roteamento, mesma trava de dono, nenhuma permissão a mais por ter
        # vindo em outro formato.
        transcrito = False
        if not texto and chat is not None and (mensagem.get("voice") or mensagem.get("audio")):
            if self.dono is not None and int(chat) != int(self.dono):
                return  # nem transcreve áudio de estranho: custa token
            from core.telegram_audio import transcrever

            texto, erro = await asyncio.to_thread(transcrever, self.token, mensagem)
            if erro:
                await self.avisar(f"Ouvi seu áudio mas {erro}.")
                return
            transcrito = True
            print(f"[TELEGRAM] audio transcrito: {texto[:60]!r}", flush=True)

        if not texto or chat is None:
            return

        # ZARA-TELEGRAM-SEM-REPETICAO-001. Pedido de horas atrás não se executa
        # sozinho: o computador mudou de estado desde então, e "abre o YouTube"
        # às 3h da manhã não é o que ele quer às 9h. Mas sumir com o pedido em
        # silêncio é pior — ele fica esperando resposta. Ela avisa e devolve a
        # decisão para ele.
        quando = int(mensagem.get("date") or 0)
        atraso = time.time() - quando if quando else 0
        if atraso > _IDADE_MAXIMA:
            print(f"[TELEGRAM] mensagem antiga ({int(atraso)}s) nao executada", flush=True)
            horas = int(atraso // 3600)
            await self.avisar(
                f'Vi sua mensagem de {horas}h atrás ("{texto[:60]}"), mas não executei — '
                "muita coisa mudou desde então. Se ainda vale, é só repetir."
            )
            return

        # O primeiro que falar vira o dono. Depois disso, mais ninguém entra —
        # sem isso, quem descobrisse o bot comandaria o computador dele.
        if self.dono is None:
            self.dono = int(chat)
            self._gravar_marcador()
            print(f"[TELEGRAM] dono registrado: {self.dono}", flush=True)
            await self.avisar(
                "Pronto, Alex. Agora só você fala comigo por aqui.\n\n"
                "Use assim:\n"
                "claude: <o que quer que eu faça>\n"
                "codex: <tarefa para o Codex>\n"
                "zara: <comando para mim>"
            )
            return
        if int(chat) != int(self.dono):
            return  # não é ele; ignora em silêncio

        # ZARA-TELEGRAM-LAB-BRIDGE-001: pergunta ao portão do Lab se isto é
        # um comando dele antes de rotear como conversa/comando normal. O
        # conteúdo da mensagem continua sendo DADO — quem decide "isto é
        # SIM/NÃO/RESTAURAR/VOLTAR de verdade" é a allowlist fechada de
        # `classify_command`, dentro do próprio gate, nunca esta ponte.
        if self._interceptar is not None:
            try:
                resposta_do_lab = await self._interceptar(chat, texto)
            except Exception as exc:
                resposta_do_lab = None
                print(f"[TELEGRAM] portao do lab falhou ao decidir: {type(exc).__name__}", flush=True)
            if resposta_do_lab is not None:
                if transcrito:
                    resposta_do_lab = f'Ouvi: "{texto}"\n\n{resposta_do_lab}'
                await self.avisar(resposta_do_lab)
                return

        destino, conteudo = self.rotear(texto)
        if not conteudo:
            await self.avisar("Chegou vazio. Manda o que você quer.")
            return

        try:
            resposta = await self.executar(destino, conteudo)
        except Exception as exc:
            resposta = f"Não consegui: {type(exc).__name__}"

        resposta = resposta or "Feito."
        if transcrito:
            # ZARA-TELEGRAM-AUDIO-001: ele precisa ver o que ela ENTENDEU, não
            # só o que ela fez. Transcrição errada com resposta confiante é o
            # jeito mais rápido de ela executar a coisa errada sem ninguém notar.
            resposta = f'Ouvi: "{texto}"\n\n{resposta}'
        await self.avisar(resposta)
