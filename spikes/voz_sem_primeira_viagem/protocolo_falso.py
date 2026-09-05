"""Servidor Gemini Live FALSO e deterministico. ZARA-VOICE-SEM-PRIMEIRA-VIAGEM-001.

Por que este arquivo existe
---------------------------
A primeira viagem descartada custa 6.702 ms medianos (docs/LATENCIA-VOZ.md).
Para consertar isso alguem precisa provar, antes de tocar em producao, o que o
transporte de voz FAZ hoje quando o protocolo chega. Prova nao pode depender de
rede, de cota, nem da sorte do dia: tem que dar o mesmo numero toda vez.

Entao aqui o servidor e falso, o relogio e virtual e o roteiro e fixo. O que NAO
e falso e o formato: as respostas sao construidas com os tipos REAIS de
`google.genai.types`. Se o SDK renomear `interim_input_transcription` ou mudar
`LiveServerContent`, este arquivo explode na hora, em vez de continuar
"passando" contra um dublê que so existe na nossa cabeca. Um fake que mente e
pior que nenhum teste.

O que este arquivo NAO prova
----------------------------
Nada sobre o comportamento do servidor do Google. Ele reproduz o roteiro que a
producao ja observou e mediu; nao descobre roteiro novo. Toda conclusao sobre
"o servidor faria X" continua sendo SUPOSICAO ate ser medida contra a API real,
e esta rotulada como tal em docs/ARQUITETURA-VOZ-DECISOES.md.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

# --- Roteiro medido em producao (docs/LATENCIA-VOZ.md) -----------------------
#
# Os numeros abaixo nao foram escolhidos: sao o turno de ACAO mediano do
# arquivo de latencia do Alex, reencenado marco a marco.

FALA_COMECA_MS = 0
INTERIM_MS = (240, 520, 760)          # transcricao parcial ENQUANTO ele fala
FIM_DA_FALA_MS = 800                  # VAD do servidor fecha o turno
PRIMEIRO_AUDIO_DO_MODELO_MS = 900     # o lixo comeca a ser gerado
INTERVALO_ENTRE_CHUNKS_MS = 100
CHUNKS_DE_AUDIO = 67                  # 6.700 ms de fala completa da Kore
GENERATION_COMPLETE_MS = PRIMEIRO_AUDIO_DO_MODELO_MS + CHUNKS_DE_AUDIO * INTERVALO_ENTRE_CHUNKS_MS
TURN_COMPLETE_MS = GENERATION_COMPLETE_MS + 20

COMANDO_DE_ACAO = "Zara, abaixa o volume"
PARCIAIS_DE_ACAO = ("Zara,", "Zara, abaixa", "Zara, abaixa o volume")

COMANDO_DE_CONVERSA = "Zara, me conta uma piada"
PARCIAIS_DE_CONVERSA = ("Zara,", "Zara, me conta", "Zara, me conta uma piada")


class RelogioVirtual:
    """Relogio injetavel. Nenhum sleep real, nenhum teste lento, nenhum flake.

    Substitui o modulo `time` dentro de core.gemini_live_voice durante o spike.
    Precisa expor perf_counter (marcos de latencia) e monotonic (janelas de eco),
    que sao as duas leituras que o transporte faz.
    """

    def __init__(self) -> None:
        self._agora_s = 0.0

    def avancar_ms(self, ms: float) -> None:
        self._agora_s += float(ms) / 1000.0

    def ir_para_ms(self, ms: float) -> None:
        alvo = float(ms) / 1000.0
        if alvo < self._agora_s:
            raise AssertionError(
                f"relogio virtual nao anda para tras ({self.agora_ms:.0f} ms -> {ms:.0f} ms)"
            )
        self._agora_s = alvo

    @property
    def agora_ms(self) -> float:
        return self._agora_s * 1000.0

    def perf_counter(self) -> float:
        return self._agora_s

    def monotonic(self) -> float:
        return self._agora_s


def _resposta(**campos: Any) -> types.LiveServerMessage:
    """Uma mensagem do servidor, montada com o tipo real do SDK."""
    return types.LiveServerMessage(server_content=types.LiveServerContent(**campos))


def _chunk_de_audio(indice: int) -> types.LiveServerMessage:
    """Um pedaco de PCM da Kore, no mesmo formato que a producao le."""
    amostra = (indice % 97).to_bytes(1, "little") + b"\x10"
    return _resposta(
        model_turn=types.Content(
            role="model",
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        data=amostra * 480,  # 20 ms a 24 kHz, int16
                        mime_type="audio/pcm;rate=24000",
                    )
                )
            ],
        )
    )


@dataclass
class EventoDoRoteiro:
    ms: float
    resposta: types.LiveServerMessage
    rotulo: str


@dataclass
class SessaoLiveFalsa:
    """Emula `client.aio.live.connect(...)` o suficiente para o _receive_loop real.

    Guarda tudo que o cliente MANDOU, para que o spike possa responder a pergunta
    que interessa: em que instante a ZARA pediu a fala do resultado verificado?
    """

    relogio: RelogioVirtual
    roteiro: list[EventoDoRoteiro]
    parar_ao_fim: asyncio.Event | None = None

    audio_emitido: int = 0
    enviados: list[dict[str, Any]] = field(default_factory=list)
    _esgotada: bool = False

    # --- lado servidor -> cliente -------------------------------------------
    async def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        if self._esgotada:
            # O _receive_loop real reabre o `async for` num while. Sem isto ele
            # giraria para sempre; a producao so sai dali por _stop ou go_away.
            if self.parar_ao_fim is not None:
                self.parar_ao_fim.set()
            return
        self._esgotada = True
        for evento in self.roteiro:
            self.relogio.ir_para_ms(evento.ms)
            if evento.rotulo == "audio":
                self.audio_emitido += 1
            yield evento.resposta
            # Devolve o controle ao loop: tasks que a producao criou (executor,
            # cooldown) precisam poder rodar entre uma resposta e outra.
            await asyncio.sleep(0)
        if self.parar_ao_fim is not None:
            self.parar_ao_fim.set()

    # --- lado cliente -> servidor -------------------------------------------
    async def send_realtime_input(self, **kwargs: Any) -> None:
        self.enviados.append({"tipo": "realtime_input", "ms": self.relogio.agora_ms, **kwargs})

    async def send_client_content(self, *, turns: Any = None, turn_complete: bool = True) -> None:
        texto = ""
        try:
            texto = "".join(
                str(getattr(parte, "text", "") or "") for parte in (turns.parts or [])
            )
        except Exception:
            texto = str(turns)
        self.enviados.append(
            {
                "tipo": "client_content",
                "ms": self.relogio.agora_ms,
                "texto": texto,
                "turn_complete": turn_complete,
            }
        )

    def primeiro_envio_de_fala_ms(self) -> float | None:
        for enviado in self.enviados:
            if enviado["tipo"] == "client_content" and "FALE_EXATAMENTE" in enviado.get("texto", ""):
                return float(enviado["ms"])
        return None


def montar_roteiro(
    *,
    frase_final: str = COMANDO_DE_ACAO,
    parciais: tuple[str, ...] = PARCIAIS_DE_ACAO,
    com_interim: bool = True,
) -> list[EventoDoRoteiro]:
    """O turno de ACAO mediano, marco a marco.

    `com_interim=False` reproduz o mundo em que o servidor so manda a
    transcricao no fim — o pior caso para qualquer desenho que dependa de
    decidir cedo. O desenho tem que sobreviver a isso sem falar falso sucesso.
    """
    eventos: list[EventoDoRoteiro] = []

    if com_interim:
        for ms, parcial in zip(INTERIM_MS, parciais, strict=True):
            eventos.append(
                EventoDoRoteiro(
                    ms=ms,
                    rotulo="interim",
                    resposta=_resposta(
                        interim_input_transcription=types.Transcription(
                            text=parcial, finished=False
                        )
                    ),
                )
            )

    # Fim da fala: a transcricao final. Este e o instante mais cedo em que o
    # cliente PODERIA saber que o turno e de acao.
    eventos.append(
        EventoDoRoteiro(
            ms=FIM_DA_FALA_MS,
            rotulo="transcricao_final",
            resposta=_resposta(
                input_transcription=types.Transcription(text=frase_final, finished=True)
            ),
        )
    )

    for indice in range(CHUNKS_DE_AUDIO):
        eventos.append(
            EventoDoRoteiro(
                ms=PRIMEIRO_AUDIO_DO_MODELO_MS + indice * INTERVALO_ENTRE_CHUNKS_MS,
                rotulo="audio",
                resposta=_chunk_de_audio(indice),
            )
        )

    eventos.append(
        EventoDoRoteiro(
            ms=GENERATION_COMPLETE_MS,
            rotulo="generation_complete",
            resposta=_resposta(generation_complete=True),
        )
    )
    eventos.append(
        EventoDoRoteiro(
            ms=TURN_COMPLETE_MS,
            rotulo="turn_complete",
            resposta=_resposta(turn_complete=True),
        )
    )
    return eventos
