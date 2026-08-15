"""ZARA-VIGIA-001 — ela avisa quando o Claude ou o Codex respondem.

Alex: "seria bom tambem se ela me notificasse quando um de voces respondesse...
pq dai eu ia saber na hora em que chegasse uma mensagem de voces". Hoje ele fica
olhando a tela para saber se chegou resposta — que é exatamente o desgaste que a
ponte existe para acabar.

**O problema difícil não é ver a mensagem nova, é saber que ela ACABOU.**
Um agente escreve em pedaços: durante um único turno o Claude produz várias
mensagens de texto entre chamadas de ferramenta. Avisar a cada pedaço seria pior
que não avisar — viraria alarme a cada dez segundos.

A solução é esperar o silêncio: detectamos texto novo, e só anunciamos quando
ele para de crescer por alguns segundos. Isso é o mais perto de "ele terminou de
responder" que dá para saber de fora, sem cooperação do outro aplicativo.

O aviso é curto de propósito — "o Claude respondeu" — porque quem decide se quer
ouvir o recado inteiro é Alex, com "lê o que o Claude falou".
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

# Quanto tempo sem mudar para considerar que o outro terminou de escrever.
_SILENCIO_PARA_CONCLUIR = 6.0
# De quanto em quanto tempo olhamos cada fonte.
_INTERVALO_CLAUDE = 3.0
# O Codex é lido pela tela, que é caro: olhamos com menos frequência.
_INTERVALO_CODEX = 12.0


class VigiaDasRespostas:
    """Observa Claude e Codex e avisa uma vez, quando a resposta fecha."""

    def __init__(
        self,
        avisar: Callable[[str], Awaitable[None]],
        *,
        pode_avisar: Callable[[], bool] | None = None,
        vigiar_codex: bool = True,
    ):
        self.avisar = avisar
        # Gate do dispatcher: não interromper enquanto ela fala ou enquanto Alex
        # está no meio de uma frase. Aviso é útil; atropelo não.
        self.pode_avisar = pode_avisar or (lambda: True)
        self.vigiar_codex = vigiar_codex
        self._tarefas: list[asyncio.Task] = []
        self._parar = asyncio.Event()
        # O que já estava na tela quando ligamos não é novidade.
        self._ultimo: dict[str, str] = {}
        self._pendente: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------------
    async def iniciar(self) -> None:
        if self._tarefas:
            return
        self._parar.clear()
        # Primeira leitura só para marcar o ponto de partida, sem avisar.
        self._ultimo["claude"] = await asyncio.to_thread(self._ler_claude)
        if self.vigiar_codex:
            self._ultimo["codex"] = await asyncio.to_thread(self._ler_codex)

        self._tarefas.append(
            asyncio.create_task(self._vigiar("claude", self._ler_claude, _INTERVALO_CLAUDE),
                                name="zara-vigia-claude")
        )
        if self.vigiar_codex:
            self._tarefas.append(
                asyncio.create_task(self._vigiar("codex", self._ler_codex, _INTERVALO_CODEX),
                                    name="zara-vigia-codex")
            )
        print("[VOICE_TRACE] stage=VIGIA result=LIGADO", flush=True)

    async def parar(self) -> None:
        self._parar.set()
        for tarefa in self._tarefas:
            tarefa.cancel()
        self._tarefas.clear()

    # ------------------------------------------------------------------
    @staticmethod
    def _ler_claude() -> str:
        from core.actions.ponte_claude import _ultima_fala_do_claude

        texto, _ = _ultima_fala_do_claude()
        return str(texto or "")

    @staticmethod
    def _ler_codex() -> str:
        from core.actions.ponte_claude import _texto_visivel_da_janela

        try:
            frases = _texto_visivel_da_janela("ChatGPT")
        except Exception:
            return ""
        return " ".join(frases[-3:]) if frases else ""

    # ------------------------------------------------------------------
    def _absorver(self, texto: str, fonte: str) -> None:
        """Aprende o estado do projeto lendo o que Claude e Codex escrevem.

        ZARA-DIARIO-002. Ela fica ligada e vai entendendo sozinha o que Alex
        está construindo — sem ele precisar contar. Falha calada: aprender é
        secundário e nunca pode atrapalhar o aviso.
        """
        try:
            from core.aprendizado import Aprendizado

            if getattr(self, "_diario", None) is None:
                self._diario = Aprendizado()
            guardado = self._diario.absorver_do_projeto(texto, fonte=fonte)
            if guardado:
                print("[VOICE_TRACE] stage=APRENDIZADO result=ABSORVEU_DO_PROJETO", flush=True)
            # Vira o dia? Fecha a página sozinha, sem ninguém pedir.
            pagina = self._diario.fechar_o_dia_se_preciso()
            if pagina:
                print(
                    f"[VOICE_TRACE] stage=DIARIO result=DIA_FECHADO dia={pagina['dia']}",
                    flush=True,
                )
        except Exception:
            pass

    async def _vigiar(self, quem: str, ler, intervalo: float) -> None:
        nomes = {"claude": "O Claude respondeu.", "codex": "O Codex respondeu."}
        while not self._parar.is_set():
            try:
                await asyncio.sleep(intervalo)
                atual = await asyncio.to_thread(ler)
                if not atual:
                    continue

                if atual != self._ultimo.get(quem):
                    # Mudou: começa (ou reinicia) a contagem do silêncio.
                    self._pendente[quem] = (atual, time.monotonic())
                    self._ultimo[quem] = atual
                    continue

                pendente = self._pendente.get(quem)
                if not pendente:
                    continue
                texto, desde = pendente
                if time.monotonic() - desde < _SILENCIO_PARA_CONCLUIR:
                    continue

                # Parou de crescer: ele terminou de responder.
                # ZARA-DIARIO-002: ela absorve antes de avisar. Aprender não
                # depende de Alex estar disponível para ouvir.
                self._absorver(texto, quem)
                if not self.pode_avisar():
                    continue  # ela está falando ou Alex está no meio de uma frase
                self._pendente.pop(quem, None)
                print(f"[VOICE_TRACE] stage=VIGIA result=AVISO quem={quem}", flush=True)
                # ZARA-VIGIA-CONTEUDO-001. A frase curta é para o ouvido; o
                # texto inteiro é para o celular dele. Quem decide o que fazer
                # com cada um é quem recebe o aviso, não o vigia.
                try:
                    await self.avisar(nomes[quem], texto)
                except TypeError:
                    await self.avisar(nomes[quem])
            except asyncio.CancelledError:
                return
            except Exception as exc:
                # Vigia nunca pode derrubar a voz. Erra calado e tenta de novo.
                print(
                    f"[VOICE_TRACE] stage=VIGIA result=ERRO quem={quem} "
                    f"motivo={type(exc).__name__}",
                    flush=True,
                )
