"""Item 4 do backlog (PESQUISA-CONCORRENTES.md): "responder enquanto executa"
+ feedback falado + mute inteligente do microfone (anti-echo).

O problema: quando o Alex pedia algo por voz e a ZARA disparava uma automação,
ela ficava MUDA até a ação terminar. Ação demorada = silêncio = a temida
pergunta "zoe cadê você?". Este módulo resolve as três pontas:

1. ANTES de executar: anuncia em voz curta o que vai fazer
   ("abrindo o Excel...") — fire-and-forget, sem atrasar a ação.
2. MUTE INTELIGENTE: enquanto ela mesma está falando, o microfone pausa
   (a própria voz nunca volta para o STT) e retoma sozinho quando ela cala.
   O MicGuard coordena isso com contagem de referência (falas aninhadas ou
   simultâneas não reabrem o mic no meio da frase) e watchdog (se a voz
   travar ligada, o mic volta sozinho após o teto).
3. DEPOIS: a confirmação falada curta de SUCESSO já existe no fluxo de
   resposta ("Aplicativo aberto e verificado."); o narrador cobre o caso de
   FALHA ("não consegui abrir o Excel") e expõe as frases para qualquer
   outro chamador (Lab, automações).

Tudo aqui é injetável (falar / pausar / retomar / falando): nenhum teste
deste módulo toca microfone ou alto-falante de verdade.

Integração com o pipeline existente (2 pontos cirúrgicos em
core/ipc_handlers.py, feito pela FRENTE 2 em 2026-09-29):
- handle_zoe_voice_speak: envolve o speak fire-and-forget com o MicGuard
  (antes, esse caminho NÃO pausava o mic — a própria voz voltava p/ o Vosk).
- caminho do executor de voz (stage == "executor"): dispara
  NarradorDeVoz.anunciar_inicio como task imediatamente antes de
  execute_action.
O _speak_response (resposta principal) já pausava/retomava o mic sozinho;
para os dois caminhos não brigarem, VoicePipeline.pause/resume_listening
virou contagem de referência (ver core/voice_stt.py).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# MicGuard — mute inteligente (anti-echo)
# ---------------------------------------------------------------------------


class MicGuard:
    """Pausa o microfone enquanto a ZARA fala e retoma quando ela cala.

    Parâmetros injetáveis (todos opcionais):
    - pausar_mic(): chamado quando ela começa a falar;
    - retomar_mic(): chamado quando ela termina (após o settle);
    - falando(): True enquanto houver áudio dela no ar.

    Sem `falando`, a espera usa estimativa pela quantidade de texto
    (degradação honesta: melhor que retomar cedo demais).
    """

    def __init__(
        self,
        pausar_mic: Callable[[], None] | None = None,
        retomar_mic: Callable[[], None] | None = None,
        falando: Callable[[], bool] | None = None,
        *,
        settle_seconds: float = 0.4,
        max_wait_seconds: float = 25.0,
        chars_por_segundo: float = 14.0,
        intervalo_poll: float = 0.1,
        dormir: Callable[[float], Awaitable[None]] | None = None,
        relogio: Callable[[], float] | None = None,
    ) -> None:
        self._pausar_mic = pausar_mic
        self._retomar_mic = retomar_mic
        self._falando = falando
        self._settle_seconds = max(0.0, settle_seconds)
        self._max_wait_seconds = max(1.0, max_wait_seconds)
        self._chars_por_segundo = max(1.0, chars_por_segundo)
        self._intervalo_poll = max(0.01, intervalo_poll)
        self._dormir = dormir or asyncio.sleep
        self._relogio = relogio or time.monotonic
        self._profundidade = 0
        # Fim estimado de cada fala em voo. O _speaking_event do TTSManager é
        # um flag único: com peças sobrepostas, a thread que termina primeiro
        # o apaga enquanto a outra ainda fala. O disparo recente mantém o
        # "falando" verdadeiro até a estimativa expirar — o mic nunca volta
        # no meio da frase por causa desse pisca-pisca.
        self._disparos_ativos: list[float] = []

    @property
    def pausado(self) -> bool:
        """True se há pelo menos uma fala com o mic pausado."""
        return self._profundidade > 0

    async def falar_com_mute(
        self, texto: str, falar_fn: Callable[[str], Any] | None
    ) -> bool:
        """Pausa o mic, dispara a fala (fire-and-forget), espera calar, retoma.

        Devolve True se a fala foi disparada. Nunca levanta por causa do
        controle do mic: se pausar/retomar falhar, a fala acontece mesmo assim.
        """
        if not (texto or "").strip() or falar_fn is None:
            return False
        self._pausar()
        fim_estimado = self._relogio() + self._estimar_duracao(texto)
        self._disparos_ativos.append(fim_estimado)
        try:
            falar_fn(texto)  # fire-and-forget: nunca bloqueia a automação
            await self._esperar_calar(texto)
        finally:
            try:
                self._disparos_ativos.remove(fim_estimado)
            except ValueError:
                pass
            await self._retomar()
        return True

    # -- internos --------------------------------------------------------

    def _pausar(self) -> None:
        self._profundidade += 1
        if self._profundidade == 1:
            self._chamar(self._pausar_mic, "pausar o microfone")

    async def _retomar(self) -> None:
        if self._profundidade > 0:
            self._profundidade -= 1
        if self._profundidade == 0:
            # Settle: a cauda da voz dela não pode cair no STT.
            await self._dormir(self._settle_seconds)
            self._chamar(self._retomar_mic, "retomar o microfone")

    async def _esperar_calar(self, texto: str) -> None:
        estimativa = self._estimar_duracao(texto)
        espera_minima = min(estimativa, 2.0)
        inicio = self._relogio()
        while True:
            decorrido = self._relogio() - inicio
            quieto = not self._falando_agora() and decorrido >= espera_minima
            if quieto:
                return
            if decorrido >= self._max_wait_seconds:
                # Watchdog: voz travada ligada não pode mutar o mic p/ sempre.
                return
            await self._dormir(self._intervalo_poll)

    def _falando_agora(self) -> bool:
        """True se há fala em voo (dentro da estimativa) ou o observador diz."""
        agora = self._relogio()
        self._disparos_ativos = [f for f in self._disparos_ativos if f > agora]
        if self._disparos_ativos:
            return True
        if self._falando is not None:
            try:
                return bool(self._falando())
            except Exception:  # noqa: BLE001 - observador quebrou: segue o jogo
                return False
        return False

    def _estimar_duracao(self, texto: str) -> float:
        return max(1.0, len(texto or "") / self._chars_por_segundo + 0.5)

    @staticmethod
    def _chamar(fn: Callable[[], Any] | None, o_que: str) -> None:
        if fn is None:
            return
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - mic não pode quebrar a fala
            print(f"[MicGuard] falhou ao {o_que}: {exc}", flush=True)


# ---------------------------------------------------------------------------
# Frases — o que ela diz por ação
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FraseDeAcao:
    """Templates de narração para uma ação.

    `fala_alvo=False` = o valor do parâmetro NUNCA é falado (privacidade:
    texto digitado, clipboard, notificação podem ter dado sensível).
    """

    inicio: str
    ok: str
    falha: str
    chaves_alvo: tuple[str, ...] = (
        "target",
        "app",
        "query",
        "url",
        "folder",
        "profile",
        "nome",
        "name",
    )
    fala_alvo: bool = True


_FRASES_DE_ACAO: dict[str, FraseDeAcao] = {
    # abrir / fechar -----------------------------------------------------
    "os_app": FraseDeAcao(
        "abrindo {alvo}...", "pronto, abri {alvo}", "não consegui abrir {alvo}"
    ),
    "os_open": FraseDeAcao(
        "abrindo {alvo}...", "pronto, abri {alvo}", "não consegui abrir {alvo}"
    ),
    "os_close_safe_app": FraseDeAcao(
        "fechando {alvo}...", "pronto, fechei {alvo}", "não consegui fechar {alvo}"
    ),
    "browser_open_url": FraseDeAcao(
        "abrindo {alvo} no navegador...",
        "pronto, abri no navegador",
        "não consegui abrir no navegador",
    ),
    # busca / mídia ------------------------------------------------------
    "browser_search": FraseDeAcao(
        "pesquisando {alvo}...",
        "pronto, pesquisei {alvo}",
        "não consegui pesquisar {alvo}",
    ),
    "youtube_search": FraseDeAcao(
        "buscando {alvo} no YouTube...",
        "pronto, achei {alvo}",
        "não consegui buscar {alvo}",
    ),
    "youtube_play_by_name": FraseDeAcao(
        "tocando {alvo}...", "pronto, tocando {alvo}", "não consegui tocar {alvo}"
    ),
    "youtube_open": FraseDeAcao(
        "abrindo o YouTube...", "pronto, YouTube aberto", "não consegui abrir o YouTube",
        fala_alvo=False,
    ),
    "spotify_search": FraseDeAcao(
        "buscando {alvo} no Spotify...",
        "pronto, achei {alvo}",
        "não consegui buscar {alvo}",
    ),
    "media_play_pause": FraseDeAcao(
        "pausando...", "pronto", "não consegui pausar", fala_alvo=False
    ),
    "media_next": FraseDeAcao(
        "próxima faixa...", "pronto, próxima faixa", "não consegui pular a faixa",
        fala_alvo=False,
    ),
    "media_previous": FraseDeAcao(
        "voltando uma faixa...",
        "pronto, voltei uma faixa",
        "não consegui voltar a faixa",
        fala_alvo=False,
    ),
    # sistema ------------------------------------------------------------
    "os_volume": FraseDeAcao(
        "ajustando o volume...",
        "pronto, volume ajustado",
        "não consegui ajustar o volume",
        fala_alvo=False,
    ),
    "os_brightness": FraseDeAcao(
        "ajustando o brilho...",
        "pronto, brilho ajustado",
        "não consegui ajustar o brilho",
        fala_alvo=False,
    ),
    "os_brightness_up": FraseDeAcao(
        "aumentando o brilho...",
        "pronto, brilho aumentado",
        "não consegui aumentar o brilho",
        fala_alvo=False,
    ),
    "os_brightness_down": FraseDeAcao(
        "diminuindo o brilho...",
        "pronto, brilho diminuído",
        "não consegui diminuir o brilho",
        fala_alvo=False,
    ),
    "os_brightness_absolute": FraseDeAcao(
        "ajustando o brilho...",
        "pronto, brilho ajustado",
        "não consegui ajustar o brilho",
        fala_alvo=False,
    ),
    "audio_mute": FraseDeAcao(
        "mutando o áudio...", "pronto, áudio mutado", "não consegui mutar",
        fala_alvo=False,
    ),
    "audio_unmute": FraseDeAcao(
        "ativando o áudio...", "pronto, áudio ativado", "não consegui ativar o áudio",
        fala_alvo=False,
    ),
    "os_night_light_on": FraseDeAcao(
        "ligando o filtro de luz azul...",
        "pronto, filtro ligado",
        "não consegui ligar o filtro",
        fala_alvo=False,
    ),
    "os_night_light_off": FraseDeAcao(
        "desligando o filtro de luz azul...",
        "pronto, filtro desligado",
        "não consegui desligar o filtro",
        fala_alvo=False,
    ),
    # janelas ------------------------------------------------------------
    "window_minimize": FraseDeAcao(
        "minimizando a janela...",
        "pronto, janela minimizada",
        "não consegui minimizar",
        fala_alvo=False,
    ),
    "window_maximize": FraseDeAcao(
        "maximizando a janela...",
        "pronto, janela maximizada",
        "não consegui maximizar",
        fala_alvo=False,
    ),
    "window_restore": FraseDeAcao(
        "restaurando a janela...",
        "pronto, janela restaurada",
        "não consegui restaurar a janela",
        fala_alvo=False,
    ),
    "window_close": FraseDeAcao(
        "fechando a janela...",
        "pronto, fechei a janela",
        "não consegui fechar a janela",
        fala_alvo=False,
    ),
    "window_move": FraseDeAcao(
        "movendo a janela...", "pronto, janela movida", "não consegui mover a janela",
        fala_alvo=False,
    ),
    "window_resize_larger": FraseDeAcao(
        "aumentando a janela...",
        "pronto, janela maior",
        "não consegui aumentar a janela",
        fala_alvo=False,
    ),
    "window_focus_named": FraseDeAcao(
        "trazendo {alvo} para frente...",
        "pronto, {alvo} na frente",
        "não consegui trazer {alvo}",
    ),
    "window_switch": FraseDeAcao(
        "trocando de janela...", "pronto, troquei de janela", "não consegui trocar",
        fala_alvo=False,
    ),
    "window_switch_next": FraseDeAcao(
        "trocando de janela...", "pronto, troquei de janela", "não consegui trocar",
        fala_alvo=False,
    ),
    # entrada — NUNCA fala o valor (privacidade) --------------------------
    "input_type_text": FraseDeAcao(
        "digitando...", "pronto, digitei", "não consegui digitar", fala_alvo=False
    ),
    "input_hotkey": FraseDeAcao(
        "executando o atalho...",
        "pronto",
        "não consegui executar o atalho",
        fala_alvo=False,
    ),
    "os_clipboard": FraseDeAcao(
        "copiando...", "pronto, copiei", "não consegui copiar", fala_alvo=False
    ),
    "os_notify": FraseDeAcao(
        "mostrando o aviso...", "pronto", "não consegui mostrar o aviso",
        fala_alvo=False,
    ),
    # energia — risco ALTO: frase neutra, sem detalhe ---------------------
    "os_power": FraseDeAcao(
        "executando comando de energia...",
        "pronto",
        "não consegui executar",
        fala_alvo=False,
    ),
}


def _encurtar_alvo(texto: str, limite: int) -> str:
    """URL vira só o host; resto é cortado no limite com reticência."""
    texto = (texto or "").strip()
    if "://" in texto:
        try:
            host = urlsplit(texto).netloc or texto
        except Exception:  # noqa: BLE001 - URL estranha: usa crua
            host = texto
        host = re.sub(r"^www\.", "", host.casefold())
        return host[:limite] or texto[:limite]
    if len(texto) > limite:
        return texto[: max(0, limite - 1)].rstrip() + "…"
    return texto


# ---------------------------------------------------------------------------
# NarradorDeVoz
# ---------------------------------------------------------------------------


class NarradorDeVoz:
    """Anuncia o que a ZARA está fazendo enquanto a automação roda.

    Uso típico (caminho de voz):
        narrador = montar_narrador_para_ipc(ipc)
        asyncio.create_task(narrador.anunciar_inicio(action, params))
        resultado = await execute_action(action, **params)

    Ou o atalho `executar_narrada`, que faz os três passos.
    """

    FRASE_GENERICA_INICIO = "trabalhando nisso..."
    FRASE_GENERICA_OK = "pronto"
    FRASE_GENERICA_FALHA = "não consegui concluir"

    def __init__(
        self,
        falar: Callable[[str], Any] | None = None,
        mic_guard: MicGuard | None = None,
        falar_habilitado: Callable[[], bool] | None = None,
        limite_chars: int = 140,
    ) -> None:
        self._falar = falar
        self._mic_guard = mic_guard or MicGuard()
        self._falar_habilitado = falar_habilitado
        self._limite_chars = max(20, limite_chars)

    # -- frases ---------------------------------------------------------

    def frase_inicio(self, action_name: str | None, params: dict | None = None) -> str:
        """O que dizer ANTES da ação rodar. Nunca devolve vazio."""
        frase = _FRASES_DE_ACAO.get(action_name or "")
        if frase is None:
            return self.FRASE_GENERICA_INICIO
        alvo = self._extrair_alvo(params, frase)
        return self._render(frase.inicio, alvo)

    def frase_conclusao(
        self, action_name: str | None, params: dict | None = None, ok: bool = True
    ) -> str:
        """O que dizer DEPOIS. O sucesso normal já é falado pelo fluxo de
        resposta; este método cobre a falha e serve a outros chamadores."""
        frase = _FRASES_DE_ACAO.get(action_name or "")
        if frase is None:
            return self.FRASE_GENERICA_OK if ok else self.FRASE_GENERICA_FALHA
        alvo = self._extrair_alvo(params, frase)
        return self._render(frase.ok if ok else frase.falha, alvo)

    # -- fala -----------------------------------------------------------

    async def anunciar_inicio(
        self, action_name: str | None, params: dict | None = None
    ) -> bool:
        """Fala a frase de início com o mic mutado. Não atrasa a ação quando
        disparado como task (é o uso recomendado)."""
        return await self._anunciar(self.frase_inicio(action_name, params))

    async def anunciar_conclusao(
        self, action_name: str | None, params: dict | None = None, ok: bool = True
    ) -> bool:
        """Fala a frase de conclusão com o mic mutado."""
        return await self._anunciar(self.frase_conclusao(action_name, params, ok=ok))

    async def executar_narrada(
        self,
        action_name: str,
        params: dict | None,
        executar: Callable[..., Awaitable[Any]] | None = None,
    ) -> Any:
        """Anuncia o início em background (a ação roda em paralelo com o
        anúncio — é o "enquanto executa"), executa e, se falhar, anuncia a
        falha. Sincroniza com o anúncio antes de devolver: sem isso a próxima
        fala começaria com o anúncio ainda no ar (áudio sobreposto).
        Devolve o resultado da ação intacto; exceção da ação repropaga."""
        params = dict(params or {})
        if executar is None:  # pragma: no cover - produção; testes injetam
            from core.action_registry import execute_action as executar

        tarefa = asyncio.get_running_loop().create_task(
            self.anunciar_inicio(action_name, params)
        )
        tarefa.add_done_callback(_registrar_falha_de_narracao)
        try:
            resultado = await executar(action_name, **params)
        except Exception:
            await _esperar_narracao(tarefa)
            await self.anunciar_conclusao(action_name, params, ok=False)
            raise
        ok = bool(resultado is not None and getattr(resultado, "success", False))
        await _esperar_narracao(tarefa)
        if not ok:
            await self.anunciar_conclusao(action_name, params, ok=False)
        return resultado

    # -- internos -------------------------------------------------------

    async def _anunciar(self, frase: str) -> bool:
        if self._falar is None:
            return False
        if self._falar_habilitado is not None and not self._falar_habilitado():
            return False  # ex.: botão mudo do Alex — ela continua executando
        return await self._mic_guard.falar_com_mute(frase, self._falar)

    def _extrair_alvo(self, params: dict | None, frase: FraseDeAcao) -> str:
        if not frase.fala_alvo or not params:
            return ""
        for chave in frase.chaves_alvo:
            valor = params.get(chave)
            if valor:
                texto = str(valor).strip()
                if texto:
                    return _encurtar_alvo(texto, self._limite_chars)
        return ""

    @staticmethod
    def _render(template: str, alvo: str) -> str:
        if alvo:
            texto = template.replace("{alvo}", alvo)
        else:
            texto = template.replace(" {alvo}", "").replace("{alvo}", "")
        return re.sub(r"\s+", " ", texto).strip()


def _registrar_falha_de_narracao(tarefa: asyncio.Task) -> None:
    try:
        exc = tarefa.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        print(f"[Narrador] anúncio em background falhou: {exc!r}", flush=True)


async def _esperar_narracao(tarefa: asyncio.Task) -> None:
    """Sincroniza com o anúncio sem deixar o erro dele vazar (já logado)."""
    try:
        await tarefa
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - narração é acessória
        pass


# ---------------------------------------------------------------------------
# Fiação com o pipeline real
# ---------------------------------------------------------------------------


def montar_narrador_para_ipc(ipc: Any) -> NarradorDeVoz | None:
    """Monta o narrador a partir do IPCHandlers (ou objeto compatível).

    - falar: tts_manager.speak(texto, blocking=False) — o mesmo funil do
      handler zoe-voice-speak;
    - mic: voice_pipeline.pause/resume_listening (anti-echo);
    - falando: tts_manager.is_speaking() (observa o fim da fala);
    - falar_habilitado: respeita o botão mudo do Alex (_silenciada).
    Devolve None se não houver TTS (sem voz, sem narração).
    """
    tts = getattr(ipc, "tts_manager", None)
    if tts is None:
        return None
    pipeline = getattr(ipc, "voice_pipeline", None)

    def _falar(texto: str) -> None:
        tts.speak(texto, blocking=False)

    guard = MicGuard(
        pausar_mic=(lambda: pipeline.pause_listening()) if pipeline is not None else None,
        retomar_mic=(
            lambda: pipeline.resume_listening(require_wake_word=True)
        ) if pipeline is not None else None,
        falando=lambda: bool(tts.is_speaking()),
    )
    return NarradorDeVoz(
        falar=_falar,
        mic_guard=guard,
        falar_habilitado=lambda: not bool(getattr(ipc, "_silenciada", False)),
    )
