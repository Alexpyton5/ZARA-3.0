"""Modo ditado universal v1 — ETAPA 1 (peca isolada, NAO plugada).

Origem: backlog em ~/workspace/zara-loop/PESQUISA-CONCORRENTES.md —
  item 1 (modo ditado universal: Rota AI / VoiceOS / Wispr Flow). O Alex ODEIA
  digitar: falar e o texto aparecer em qualquer campo onde o cursor estiver
  e a feature de maior valor por dia util que a ZARA pode ganhar.
  item 16 (whisper-local): pre-roll buffer + warmup — a primeira palavra nunca
  e cortada — e "fallback window": sem campo de texto focado, o transcript cai
  numa janelinha pronta para copiar.
  item 17 (localflow): guard de similaridade anti-alucinacao — reusado daqui:
  core/ditado_guard.aplicar_limpeza_com_guard (a IA nunca reescreve o que o
  Alex nao disse).

O que esta peca FAZ: a maquina de estados do push-to-talk + o pre-roll.
  - `PreRollBuffer`: ring de frames de audio (bytes) dos ultimos N ms. O loop
    de captura (Etapa 2) alimenta sem parar; quando a tecla e pressionada, o
    conteudo do buffer vira o COMECO da tomada — a primeira palavra nunca e
    cortada (o bug classico que faz o Alex descartar um ditado em 10 segundos).
  - `DitadoController`: ocioso -> (tecla pressionada) -> gravando ->
    (tecla solta) -> transcreve -> limpa com guard -> cola no cursor.
    Tudo injetavel (transcricao, limpeza, digitacao, foco, janela): nenhum
    teste toca microfone, alto-falante ou teclado de verdade.

O que esta peca NAO FAZ (Etapa 2, fiacao futura, atras de flag):
  atalho global de teclado, captura real via sounddevice, digitacao real
  (action input_type_text / SendInput), janela flutuante. Ponto de plugue:
  um loop que chame `alimentar_audio()` a cada chunk do mic, `tecla_pressionada()`
  no key-down, `tecla_solta()` no key-up, com
    transcrever_fn = faster-whisper/Vosk local,
    limpar_fn      = reescrita leve local (opcional),
    digitar_fn     = cola no cursor,
    tem_foco_fn    = ha campo de texto focado?,
    janela_fn      = fallback window do item 16.

Disciplina do projeto (a mesma de core/intent_classifier.py, Etapa 2):
peca isolada + testavel, SEM chamar em core/ipc_handlers.py. Nada importa
este modulo ainda — de proposito. Nao e peca de museu: tem consumidor
definido (a Etapa 2 acima) e o plugue do item 1 do backlog.

Fail-closed: excecao em qualquer funcao injetada vira motivo honesto no
ResultadoDitado (nunca levanta); transcricao vazia nunca e colada; a IA nunca
inventa palavra (o guard garante); sem foco e sem janela, o texto volta no
resultado em vez de sumir.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

#: Tamanho padrao do pre-roll: 500 ms (o valor do whisper-local, item 16).
PRE_ROLL_PADRAO_S = 0.5


class PreRollBuffer:
    """Ring de audio (bytes) dos ultimos N milissegundos.

    O loop de captura alimenta sem parar com `alimentar()`; na hora da tecla,
    `descarregar()` devolve tudo em ordem cronologica e esvazia o buffer.
    Frames antigos demais caem sozinhos — o buffer nunca cresce sem limite.
    """

    def __init__(self, capacidade_bytes: int) -> None:
        self._capacidade = max(1, int(capacidade_bytes))
        self._frames: deque[bytes] = deque()
        self._tamanho = 0

    @classmethod
    def para_taxa(
        cls,
        taxa_hz: int = 16000,
        bytes_por_amostra: int = 2,
        duracao_s: float = PRE_ROLL_PADRAO_S,
    ) -> "PreRollBuffer":
        """Cria o buffer dimensionado para `duracao_s` de audio."""
        return cls(int(taxa_hz * bytes_por_amostra * duracao_s))

    def __len__(self) -> int:
        return self._tamanho

    @property
    def capacidade(self) -> int:
        return self._capacidade

    def alimentar(self, frame: bytes | None) -> None:
        """Guarda um chunk de audio; o excedente mais antigo e descartado."""
        if not frame:
            return
        self._frames.append(bytes(frame))
        self._tamanho += len(frame)
        while self._tamanho > self._capacidade and self._frames:
            velho = self._frames.popleft()
            self._tamanho -= len(velho)

    def descarregar(self) -> bytes:
        """Devolve o audio guardado em ordem e esvazia o buffer."""
        audio = b"".join(self._frames)
        self.limpar()
        return audio

    def limpar(self) -> None:
        self._frames.clear()
        self._tamanho = 0


@dataclass(frozen=True)
class ResultadoDitado:
    """O veredito de uma tomada de ditado (tecla pressionada -> solta)."""

    texto_final: str  #: o que deve ser usado (limpo ou cru)
    colado: bool  #: True = foi colado no cursor (ou na janela)
    usou_guard: bool  #: True = a limpeza foi descartada, o cru venceu
    similaridade: float  #: 0..1 entre o cru e o limpo (1.0 = sem limpeza)
    motivo: str  #: codigo-maquina: "ok" | "transcricao_vazia" | "sem_gravacao"
    #: | "sem_foco" | "sem_foco_janela" | "falha_digitacao"
    #: | "transcricao_falhou" | "cancelado"
    mensagem: str  #: frase honesta em PT-BR, pronta p/ o narrador ("" se ok)


def _limpar_com_guard(
    cru: str, limpar_fn: Callable[[str], str | None] | None
) -> tuple[str, bool, float]:
    """Aplica a limpeza via core/ditado_guard. Fallback: usa o cru.

    O import e preguiçoso (padrao do projeto): se o modulo do guard nao
    estiver disponivel, o ditado continua funcionando com o texto cru —
    degradacao honesta, nunca quebra.
    """
    if limpar_fn is None:
        return (cru or "").strip(), False, 1.0
    try:
        from core.ditado_guard import aplicar_limpeza_com_guard
    except Exception:
        return (cru or "").strip(), False, 1.0
    resultado = aplicar_limpeza_com_guard(cru, limpar_fn)
    return resultado.final, resultado.usou_cru, resultado.similaridade


class DitadoController:
    """Maquina de estados do push-to-talk do ditado universal (v1).

    Injetaveis (todos os efeitos colaterais passam por aqui):
    - transcrever_fn(audio: bytes) -> str | None — STT local;
    - digitar_fn(texto: str) -> bool — cola o texto onde o cursor estiver;
    - limpar_fn(texto: str) -> str | None — reescrita leve (opcional);
    - tem_foco_fn() -> bool — ha campo de texto focado? (None = assume sim);
    - janela_fn(texto: str) -> None — fallback window do item 16 (opcional).

    Estados: "ocioso" -> "gravando" -> "ocioso". `alimentar_audio()` recebe
    cada chunk do mic; em "ocioso" ele so alimenta o pre-roll, em "gravando"
    ele acumula a tomada.
    """

    OCIOSO = "ocioso"
    GRAVANDO = "gravando"

    def __init__(
        self,
        *,
        transcrever_fn: Callable[[bytes], str | None],
        digitar_fn: Callable[[str], bool],
        limpar_fn: Callable[[str], str | None] | None = None,
        tem_foco_fn: Callable[[], bool] | None = None,
        janela_fn: Callable[[str], None] | None = None,
        pre_roll: PreRollBuffer | None = None,
    ) -> None:
        self._transcrever = transcrever_fn
        self._digitar = digitar_fn
        self._limpar = limpar_fn
        self._tem_foco = tem_foco_fn
        self._janela = janela_fn
        self._pre_roll = pre_roll or PreRollBuffer.para_taxa()
        self._estado = self.OCIOSO
        self._tomada = bytearray()

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def gravando(self) -> bool:
        return self._estado == self.GRAVANDO

    def alimentar_audio(self, frame: bytes | None) -> None:
        """Recebe um chunk do mic. Em ocioso alimenta so o pre-roll."""
        if self._estado == self.GRAVANDO:
            if frame:
                self._tomada += frame
        else:
            self._pre_roll.alimentar(frame)

    def tecla_pressionada(self) -> bool:
        """Key-down do push-to-talk. A tomada comeca com o pre-roll.

        Devolve False se ja estava gravando (o segundo pressionar e ignorado,
        nao reinicia a tomada no meio da fala).
        """
        if self._estado == self.GRAVANDO:
            return False
        self._tomada = bytearray(self._pre_roll.descarregar())
        self._estado = self.GRAVANDO
        return True

    def cancelar(self) -> None:
        """Descarta a tomada em andamento e volta ao ocioso."""
        self._tomada = bytearray()
        self._estado = self.OCIOSO

    def tecla_solta(self) -> ResultadoDitado:
        """Key-up: transcreve, limpa com guard e cola. Nunca levanta."""
        if self._estado != self.GRAVANDO:
            return ResultadoDitado(
                texto_final="",
                colado=False,
                usou_guard=False,
                similaridade=0.0,
                motivo="sem_gravacao",
                mensagem="Não havia ditado em andamento.",
            )
        audio = bytes(self._tomada)
        self._tomada = bytearray()
        self._estado = self.OCIOSO

        try:
            transcrito = self._transcrever(audio)
        except Exception:
            return ResultadoDitado(
                texto_final="",
                colado=False,
                usou_guard=False,
                similaridade=0.0,
                motivo="transcricao_falhou",
                mensagem="Não consegui transcrever o áudio.",
            )
        cru = (transcrito or "").strip()
        if not cru:
            return ResultadoDitado(
                texto_final="",
                colado=False,
                usou_guard=False,
                similaridade=0.0,
                motivo="transcricao_vazia",
                mensagem="Não entendi o que você disse.",
            )

        final, usou_guard, similaridade = _limpar_com_guard(cru, self._limpar)

        tem_foco = True
        if self._tem_foco is not None:
            try:
                tem_foco = bool(self._tem_foco())
            except Exception:
                tem_foco = False
        if not tem_foco:
            if self._janela is not None:
                try:
                    self._janela(final)
                except Exception:
                    pass
                return ResultadoDitado(
                    texto_final=final,
                    colado=False,
                    usou_guard=usou_guard,
                    similaridade=similaridade,
                    motivo="sem_foco_janela",
                    mensagem="Sem campo de texto focado — deixei o texto na janelinha para copiar.",
                )
            return ResultadoDitado(
                texto_final=final,
                colado=False,
                usou_guard=usou_guard,
                similaridade=similaridade,
                motivo="sem_foco",
                mensagem="Sem campo de texto focado — texto não colado.",
            )

        try:
            ok = bool(self._digitar(final))
        except Exception:
            ok = False
        if not ok:
            return ResultadoDitado(
                texto_final=final,
                colado=False,
                usou_guard=usou_guard,
                similaridade=similaridade,
                motivo="falha_digitacao",
                mensagem="Não consegui digitar no campo.",
            )
        return ResultadoDitado(
            texto_final=final,
            colado=True,
            usou_guard=usou_guard,
            similaridade=similaridade,
            motivo="ok",
            mensagem="",
        )
