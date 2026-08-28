"""Low-latency Gemini Live native-audio voice session for ZARA.

The API key stays in the Python sidecar. The Electron renderer only receives
state, levels and transcripts through the existing local IPC bridge.

Wake behavior (ZARA-VOICE-AUDICAO-001, substitui ZARA-VOICE-WAKE-GATE-001):

O gate Vosk local esta DESLIGADO por padrao. O microfone transmite continuamente
para o Gemini e o wake e decidido por TRANSCRICAO em
`ipc_handlers._on_gemini_live_turn` (`_WAKE_PREFIX_RE`).

Por que mudou: o gate local lia 1,2 s de audio para achar "zara" e descartava
esse buffer ao abrir. O inicio do comando ia junto, entao "que horas sao"
chegava mutilado ao Gemini e voltava como "oracao". O mesmo gate fechava
enquanto a Kore falava, o que tornava o barge-in impossivel, e adicionava uma
etapa de reconhecimento antes de qualquer coisa sair da maquina.

Consequencias do gate desligado:
- LISTENING permanente: a ZARA nunca fica surda.
- barge-in real: o microfone alcanca o Gemini durante a fala, entao o VAD do
  servidor enxerga a interrupcao.
- audio proprio volta pelo microfone; quem protege disso e o filtro de eco por
  conteudo em `ipc_handlers._looks_like_own_echo` (ZARA-VOICE-ECO-001), que
  descarta a repeticao da resposta sem bloquear um "pare" dito por cima.

O caminho antigo continua no codigo e volta com
`"wake_word_mode": "local"` em `api_keys.json`, sem rebuild.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
import unicodedata
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from core.personality import load_personality

AsyncCallback = Callable[..., Awaitable[None] | None]

_VOICE_ECHO_STOPWORDS = frozenset({
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos",
    "durante", "e", "em", "na", "nas", "no", "nos", "o", "os", "ou",
    "para", "pela", "pelas", "pelo", "pelos", "por", "um", "uma",
})


def _normalized_voice_tokens(text: str) -> list[str]:
    """Lowercase, accent-free word tokens shared by STT echo checks."""
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", value)


def is_explicit_human_barge_in(text: str) -> bool:
    """Short stop requests always outrank the self-echo filter."""
    words = _normalized_voice_tokens(text)
    if words[:1] in (["ei"], ["hey"]):
        words = words[1:]
    if words[:1] in (["zara"], ["sara"]):
        words = words[1:]
    if words[:2] == ["por", "favor"]:
        words = words[2:]
    return words in (
        ["pare"], ["para"], ["parar"], ["cancela"], ["cancelar"],
        ["interrompa"], ["interromper"], ["chega"],
    )


def looks_like_assistant_echo(heard: str, references: tuple[str, ...] | list[str]) -> bool:
    """Conservative content match for a temporally eligible STT candidate.

    Timing is deliberately enforced by the caller. Here we compare normalized
    token overlap plus token order, tolerating punctuation, accents, omitted
    words and small STT substitutions without doing broad semantic blocking.
    """
    if is_explicit_human_barge_in(heard):
        return False
    heard_words = _normalized_voice_tokens(heard)
    if len(heard_words) < 3:
        return False
    heard_counts = Counter(heard_words)
    heard_content = [word for word in heard_words if word not in _VOICE_ECHO_STOPWORDS]
    heard_content_counts = Counter(heard_content)
    for reference in references:
        reference_words = _normalized_voice_tokens(reference)
        if len(reference_words) < 3:
            continue
        shared = sum((heard_counts & Counter(reference_words)).values())
        heard_coverage = shared / len(heard_words)
        sequence = SequenceMatcher(None, heard_words, reference_words)
        ordered_coverage = sequence.find_longest_match().size / len(heard_words)
        sequence_ratio = sequence.ratio()
        if heard_coverage >= 0.80 and (ordered_coverage >= 0.60 or sequence_ratio >= 0.58):
            return True
        if heard_coverage >= 0.65 and sequence_ratio >= 0.78:
            return True
        reference_content = [
            word for word in reference_words if word not in _VOICE_ECHO_STOPWORDS
        ]
        if len(heard_content) < 4 or len(reference_content) < 4:
            continue
        content_shared = sum(
            (heard_content_counts & Counter(reference_content)).values()
        )
        heard_content_coverage = content_shared / len(heard_content)
        reference_content_coverage = content_shared / len(reference_content)
        content_order_ratio = SequenceMatcher(
            None, heard_content, reference_content
        ).ratio()
        if (
            content_shared >= 4
            and heard_content_coverage >= 0.80
            and reference_content_coverage >= 0.65
            and content_order_ratio >= 0.80
        ):
            return True
    return False


@dataclass(slots=True)
class GeminiLiveVoiceConfig:
    api_key: str
    model: str = "gemini-3.1-flash-live-preview"
    voice_name: str = "Kore"
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000
    block_ms: int = 40
    input_device: int | None = None
    output_device: int | None = None
    # ZARA-AEC-RENDERER-001. "local"    = microfone e alto-falante por PortAudio
    #                        "renderer" = audio entra e sai pelo Electron, que
    #                                     aplica o AEC do Chromium.
    # So o modo "renderer" cancela o eco: o AEC precisa que a fala da Kore saia
    # pelo mesmo processo que captura o microfone, senao nao existe referencia.
    # Reversivel sem rebuild: "audio_transport": "local" em api_keys.json.
    audio_transport: str = "local"
    # ZARA-VOICE-LATENCY-002 — quanto tempo o servidor espera para decidir que
    # Alex terminou de falar.
    #
    # A sessao nunca configurou isto, entao rodava no padrao de fabrica. Essa
    # espera acontece ANTES de qualquer coisa que a ZARA faca: o dispatcher dela
    # responde em centesimos de segundo (medido no historico), mas o turno so
    # comeca quando o servidor fecha a fala. Era ai que estava a lentidao que
    # Alex sentia.
    #
    # Curto demais corta a frase quando ele pausa para pensar; longo demais
    # parece que ela travou. Ajustavel sem rebuild por "vad_silencio_ms" em
    # api_keys.json.
    vad_silencio_ms: int = 300
    vad_padding_ms: int = 100
    vad_fim_sensivel: bool = True
    # ZARA-VOICE-AUDICAO-001
    # O gate Vosk local ficava LIGADO por padrao e era a causa de tres
    # problemas que Alex relatou como se fossem separados:
    #
    #  1. audicao ruim  — _check_wake_word acumula 1,2 s de audio, detecta
    #     "zara" e LIMPA o buffer. Esses chunks nunca chegam ao Gemini, entao
    #     o inicio do comando e cortado. "que horas sao" chega mutilado e o
    #     STT devolve "oracao".
    #  2. latencia      — uma etapa inteira de reconhecimento local antes de
    #     qualquer coisa ser enviada.
    #  3. barge-in      — o gate fecha enquanto a Kore fala, entao o microfone
    #     nao alcanca o Gemini e o VAD do servidor nunca ve a interrupcao.
    #
    # Com o gate DESLIGADO o audio flui continuo, o Gemini transcreve a frase
    # inteira (inclusive a palavra "Zara") e o wake passa a ser feito por
    # transcricao em ipc_handlers._on_gemini_live_turn (_WAKE_PREFIX_RE), que
    # ja existe e nao corta audio nenhum.
    #
    # Reversivel sem rebuild: "wake_word_mode": "local" em api_keys.json.
    wake_word_enabled: bool = False
    wake_words: tuple[str, ...] = ("zara", "sara")
    # ZARA-VOICE-LATENCY-001: sem gate local isto so atrasa o estado visual.
    wake_cooldown_seconds: float = 0.4
    # ZARA-VOICE-ECO-002. Quanto tempo depois do ultimo bloco de audio a ZARA
    # ainda e considerada "falando". O eco do alto-falante chega ao microfone
    # com atraso; sem essa cauda o fim da propria frase dela escaparia como se
    # fosse fala do Alex.
    # ZARA-VOICE-SELF-ECHO-001: cauda somente de CLASSIFICACAO. O microfone
    # continua fluindo para preservar barge-in humano imediato.
    echo_speech_tail_seconds: float = 0.8
    system_instruction: str = (
        # ZARA-PERSONALIDADE-2026-08-27: a abertura (quem a Zara e, o tom dela)
        # vem do mesmo arquivo que o caminho de texto usa
        # (PERSONALIDADE_DA_ZARA.txt via core/personality.py), pra nao ter duas
        # personalidades divergindo sem ninguem perceber. Tudo que vem depois
        # e regra especifica de voz — vocabulario de STT, brevidade de turno
        # falado, anti-invencao — e continua exatamente como estava, ajustado
        # com incidente real do Alex; nao mexi em nenhuma linha disso.
        load_personality() + " RESPONDA EM PORTUGUÊS DO BRASIL quando "
        "Alex falar em português. Fale naturalmente, com respostas úteis, objetivas e humanas. "
        "Você deve responder inequivocamente em português do Brasil. "
        # ZARA-VOCABULARIO-001
        # Alex reclamou que ela ouve "Cláudio" quando ele diz "Claude". Nome
        # próprio estrangeiro é onde todo reconhecimento de fala erra mais, e o
        # conserto é dizer ao modelo quais palavras existem neste mundo. Custa
        # nada e vale para transcrição e para resposta.
        "VOCABULÁRIO desta casa — ao transcrever a fala de Alex, prefira sempre estas "
        "grafias, mesmo que o som seja parecido com outra palavra: "
        "Claude (o assistente de programação; NUNCA escreva Cláudio, Cláudia ou Claudio), "
        "Claude Code, Codex, ChatGPT, ZARA, Kore, Gemini, Alex, Hermes, Graphify, "
        "Windows, YouTube, Spotify, Chrome. "
        # ZARA-VOICE-FLUIDEZ-001: agora esta voz sai direto em turno de
        # conversa, então o pedido de brevidade virou parte do produto — turno
        # longo destrói a sensação de conversa falada.
        "Converse em turnos curtos, como numa conversa falada de verdade: uma ou duas frases, "
        "sem listas e sem monólogo, a não ser que Alex peça detalhe. "
        # A regra de verdade da ZARA, dita ao modelo na forma mais dura
        # possível. O silenciamento do áudio em turno de ação é a garantia
        # real; esta instrução é a segunda camada.
        "NUNCA diga que abriu, fechou, mudou, ligou, desligou, aumentou ou diminuiu qualquer "
        "coisa no computador. Você não executa ações: quem executa é o sistema da ZARA, e ele "
        "mesmo anuncia o resultado verificado. Se Alex pedir uma ação, não descreva sucesso. "
        "Quando receber texto iniciado por FALE_EXATAMENTE:, pronuncie somente o texto "
        "depois dos dois-pontos, sem acrescentar nenhuma palavra. "
        # ZARA-SEM-INVENCAO-001
        #
        # Alex, depois de pegar ela inventando: *"tente deixar ela sem mentiras
        # e sem chutes ou invenções; se não souber, ela deve ser sempre
        # transparente... tem que ser o mais próximo de uma conversa entre
        # humanos em todos os sentidos"*.
        #
        # O que ele pegou: perguntou três vezes quanto ela demorava e recebeu
        # "2,01 segundos" nas três, um número que nunca foi medido. E perguntou
        # "você entendeu?" e ouviu "sim, entendi com certeza" — seguido de um
        # chute errado sobre o assunto.
        #
        # As duas falhas têm a mesma raiz: preencher o vazio com algo que soa
        # bem. Um número inventado é pior que "não sei", porque convence.
        "NUNCA invente número, medida, hora, duração, quantidade, estatística, data ou "
        "nome de arquivo. Se você não tem o dado, diga que não tem — isso é resposta "
        "completa e boa. Nunca diga 'aproximadamente' para disfarçar que está chutando. "
        "Se não entendeu o que Alex disse, diga que não entendeu e peça para ele repetir; "
        "nunca responda 'sim, entendi' sem conseguir dizer O QUE entendeu. "
        "Se ele fizer uma pergunta que você não sabe responder, diga que não sabe, com "
        "naturalidade, e ofereça o que você consegue fazer a respeito. "
        "Fale como uma pessoa falaria: sem fórmula pronta, sem repetir a mesma frase, sem "
        "encher linguiça para parecer prestativa. Alex prefere um 'não sei' curto a um "
        "parágrafo bonito que não responde nada."
    )


class GeminiLiveVoice:
    """Persistent microphone -> Gemini Live -> speaker audio bridge."""

    def __init__(
        self,
        config: GeminiLiveVoiceConfig,
        *,
        on_state: AsyncCallback | None = None,
        on_level: AsyncCallback | None = None,
        on_turn: AsyncCallback | None = None,
        can_answer_directly: Callable[[str], bool] | None = None,
        on_interrupt: AsyncCallback | None = None,
        on_error: AsyncCallback | None = None,
        on_output_audio: AsyncCallback | None = None,
    ) -> None:
        self.config = config
        self.on_state = on_state
        self.on_level = on_level
        self.on_turn = on_turn
        # ZARA-AEC-RENDERER-001. Quando o transporte de audio e "renderer", a
        # Kore nao toca por PortAudio: os bytes saem por aqui para o Electron
        # tocar via WebAudio. Isso e o que da ao AEC do Chromium um sinal de
        # referencia (far-end) e, com ele, o cancelamento do proprio
        # alto-falante. Medido em 2026-08-13: eco abaixo do ruido da sala, voz
        # do Alex +30 dB por cima, 0 interrupcoes do servidor no piso do eco.
        self.on_output_audio = on_output_audio
        # ZARA-VOICE-FLUIDEZ-001. Predicado SINCRONO injetado pelo dispatcher:
        # "este turno pode ser respondido direto pela voz do Live?". O
        # transporte nao conhece intents nem wake gate; ele so obedece. Sem o
        # predicado o comportamento e o antigo: nada sai direto.
        self.can_answer_directly = can_answer_directly
        self.on_interrupt = on_interrupt
        self.on_error = on_error

        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_queue: asyncio.Queue[bytes] | None = None
        # ZARA-VOICE-ORDEM-001: cada pedido de fala carrega o proprio evento de
        # conclusao. Antes todos compartilhavam self._speech_done, entao dois
        # turnos concorrentes sinalizavam um pelo outro.
        self._speech_queue: asyncio.Queue[tuple[str, asyncio.Event]] | None = None
        # --- Roteamento e ordem de turno (ZARA-VOICE-FLUIDEZ-001 / -ORDEM-001) ---
        self._turn_direct = False        # o audio deste turno pode tocar?
        self._turn_route_decided = False # ja decidimos o roteamento do turno?
        self._utterance_open = False     # Alex esta no meio de uma fala?
        self._routed_turn_task: asyncio.Task | None = None
        # --- Anti-loop de eco (ZARA-VOICE-ECO-002) ---
        self._audio_out_until = 0.0      # fim da janela curta pos-audio
        self._assistant_output_active = False
        self._assistant_output_text = ""
        self._recent_assistant_outputs: deque[tuple[str, float]] = deque(maxlen=3)
        self._turn_echo_suspect = False  # a fala atual comecou por cima da dela?
        self._turn_echo_references: tuple[str, ...] = ()
        self._turn_rejected_as_echo = False
        # ZARA-VOICE-LATENCY-001: tasks de cooldown que nao podem ser coletadas.
        self._cooldown_tasks: set[asyncio.Task] = set()
        self._speech_done: asyncio.Event | None = None
        self._play_generated_audio = False
        # ZARA-LATENCIA-SEGUNDA-VIAGEM-001 — marcos crus do caminho da fala.
        #
        # O cronometro que existia nascia dentro de _process_voice_message, ou
        # seja, DEPOIS de o turno do Alex ter fechado no servidor, e era lido
        # depois de speak() voltar — e speak() so volta no turn_complete, isto
        # e, quando a frase inteira ja foi gerada. O numero que ele produzia
        # ("6904 ms") nao era "quanto o Alex espera para ela COMECAR a falar";
        # era "quanto demora ate ela TERMINAR de falar". Sao coisas diferentes
        # e a queixa dele e a primeira.
        #
        # Estes quatro relogios existem para separar as duas. Sao perf_counter
        # crus; quem transforma em ms e quem le. Observabilidade apenas: nenhum
        # deles muda comportamento.
        self._t_fim_fala_usuario: float | None = None   # VAD do servidor fechou
        self._t_fala_pedida: float | None = None        # mandamos FALE_EXATAMENTE
        self._t_primeiro_byte_tts: float | None = None  # 1o audio da Kore chegou
        self._t_audio_entregue: float | None = None     # 1o audio foi para o player
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error: Exception | None = None
        self._input_stream: Any = None
        self._output_stream: Any = None
        self._session_handle: str | None = None
        self._input_text = ""
        self._output_text = ""
        self._connected = False
        self._last_state = "STANDBY"
        self._stream_generation = 0
        self._audio_frames_received = 0
        # --- Wake-gate state (ZARA-VOICE-WAKE-GATE-001) ---
        self._gate_open = False          # True only while LISTENING (mic -> Gemini)
        self._wake_detector: Any | None = None  # lazy Vosk grammar detector
        self._wake_grammar_json: str | None = None
        self._gate_until_idle = False    # suppress wake while ZARA is speaking
        self._last_wake_at = 0.0
        self._wake_rolling = b""         # rolling buffer for wake detection

    def _ensure_wake_detector(self) -> None:
        """Lazily build a Vosk recognizer with a grammar reduced to the wake word.

        Keeps memory footprint small and startup fast: the full Portuguese model
        is only loaded once the voice session actually starts. If Vosk or the
        model is missing, the gate degrades to always-streaming (old behavior).
        """
        if not self.config.wake_word_enabled:
            return
        if self._wake_detector is not None:
            return
        try:
            import vosk  # type: ignore

            from core.paths import user_data_dir

            model_dir = user_data_dir() / "models" / "vosk"
            pt = model_dir / "vosk-model-small-pt-0.3"
            en = model_dir / "vosk-model-small-en-us-0.15"
            model_path = pt if pt.exists() else (en if en.exists() else None)
            if model_path is None:
                print("[WakeGate] Vosk model not found; gate OFF (always stream)")
                return
            model = vosk.Model(str(model_path))
            rec = vosk.KaldiRecognizer(model, self.config.input_sample_rate)
            words = list(self.config.wake_words)
            self._wake_grammar_json = json.dumps(words)
            rec.SetGrammar(self._wake_grammar_json)
            self._wake_detector = rec
            print(f"[WakeGate] Vosk wake detector ready (words={words})")
        except Exception as exc:  # pragma: no cover - env dependent
            print(f"[WakeGate] detector init failed, gate OFF: {exc}")
            self._wake_detector = None

    def _check_wake_word(self, raw: bytes) -> bool:
        """Feed one mic chunk to the local wake detector.

        Returns True when the wake word appears in the streaming result.
        Uses a rolling partial buffer so short words are not lost.
        """
        rec = self._wake_detector
        if rec is None:
            return False
        try:
            # Accumulate into a small rolling buffer so "zara" is not split
            # across chunk boundaries, then test the partial result.
            self._wake_rolling += raw
            if len(self._wake_rolling) > self.config.input_sample_rate * 1.2:
                self._wake_rolling = self._wake_rolling[-self.config.input_sample_rate:]
            rec.AcceptWaveform(self._wake_rolling)
            partial = json.loads(rec.PartialResult()).get("partial", "").strip().lower()
            if not partial:
                return False
            for ww in self.config.wake_words:
                if ww.lower() in partial:
                    self._wake_rolling = b""
                    return True
            # reset the recognizer periodically so it does not accumulate
            if len(partial) > 24:
                rec.Reset()
                self._wake_rolling = b""
            return False
        except Exception:
            return False

    @property
    def gate_open(self) -> bool:
        """True when mic audio is being streamed to Gemini (LISTENING)."""
        return self._gate_open

    @property
    def usa_renderer(self) -> bool:
        """O audio entra e sai pelo Electron (AEC do Chromium)?"""
        return str(self.config.audio_transport or "").strip().lower() == "renderer"

    def push_mic_pcm(self, raw: bytes) -> None:
        """Recebe microfone JA LIMPO pelo AEC do Chromium. ZARA-AEC-RENDERER-001.

        Entra exatamente onde o callback do PortAudio entrava, para que todo o
        resto do pipeline — gate, fila, wake, roteamento — continue igual. A
        unica diferenca e a origem dos bytes.
        """
        if not raw or self._stop.is_set():
            return
        self._audio_frames_received += 1
        if self._audio_frames_received == 1:
            print(
                "[VOICE_TRACE] stage=AUDIO_FRAMES_RECEIVED result=PASS source=renderer",
                flush=True,
            )
        level = self._pcm_level(raw)
        loop = self._loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(self._queue_audio, raw, level)

    @property
    def speaking_now(self) -> bool:
        """A ZARA esta emitindo audio agora (ou acabou de emitir)."""
        return self._assistant_output_active or time.monotonic() < self._audio_out_until

    @property
    def assistant_output_active(self) -> bool:
        """True only while an assistant-owned audio response is in progress."""
        return self._assistant_output_active

    @property
    def turn_echo_suspect(self) -> bool:
        """A fala em curso comecou enquanto a ZARA falava. ZARA-VOICE-ECO-002.

        Este e o sinal que quebra o loop "ela fala e se responde". O eco do
        alto-falante, por definicao, comeca por cima da fala dela; uma pergunta
        de verdade do Alex comeca depois que ela para — ou por cima, mas ai ele
        diz "Zara", e o wake explicito continua passando.

        Comparar texto nao bastava: `_last_spoken_text` so e preenchido quando
        o turno termina, e o eco entra DURANTE a fala, quando a referencia
        ainda esta velha.
        """
        return self._turn_echo_suspect

    def _echo_reference_texts(self, now: float | None = None) -> tuple[str, ...]:
        moment = time.monotonic() if now is None else now
        references: list[str] = []
        current = self._assistant_output_text.strip()
        if current:
            references.append(current)
        references.extend(
            text for text, expires_at in self._recent_assistant_outputs
            if text and moment <= expires_at
        )
        return tuple(dict.fromkeys(references))

    def _mark_assistant_output_started(self, text: str = "") -> None:
        self._assistant_output_active = True
        value = str(text or "").strip()
        if value:
            self._assistant_output_text = value
        self._audio_out_until = max(
            self._audio_out_until,
            time.monotonic() + self.config.echo_speech_tail_seconds,
        )

    def _mark_assistant_output_finished(self) -> None:
        if not self._assistant_output_active and not self._assistant_output_text.strip():
            return
        now = time.monotonic()
        value = self._assistant_output_text.strip()
        expires_at = now + self.config.echo_speech_tail_seconds
        if value:
            self._recent_assistant_outputs.appendleft((value, expires_at))
        self._assistant_output_active = False
        self._assistant_output_text = ""
        self._audio_out_until = max(self._audio_out_until, expires_at)

    def is_self_echo_transcript(
        self,
        heard: str,
        *,
        references: tuple[str, ...] | None = None,
    ) -> bool:
        """Reject own speech only inside active-output/short-tail ownership."""
        if is_explicit_human_barge_in(heard):
            return False
        if references is None:
            if not (self.speaking_now or self._turn_echo_suspect):
                return False
            references = self._echo_reference_texts()
        return bool(references and looks_like_assistant_echo(heard, references))

    async def open_gate(self) -> None:
        """Open the mic gate (wake word detected) -> LISTENING."""
        if self._gate_open:
            return
        self._gate_open = True
        self._last_wake_at = time.time()
        await self._emit_state("LISTENING")

    async def close_gate(self) -> None:
        """Close the mic gate -> IDLE (waiting for wake word)."""
        if not self._gate_open:
            return
        self._gate_open = False
        await self._emit_state("IDLE")

    def pause_input(self) -> None:
        """Drop microphone frames while ZARA speaks through local TTS."""
        self._gate_until_idle = True
        queue = self._audio_queue
        if queue is not None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    def resume_input(self) -> None:
        self._gate_until_idle = False

    async def speak(self, text: str, timeout: float | None = None) -> bool:
        # ZARA-VOZ-UNICA-001. O limite fixo de 25 s era curto para texto longo:
        # ler um recado do Claude leva mais que isso, a espera estourava, a Kore
        # era dada como falha e a cascata caía na voz do Windows — que Alex não
        # suporta. Agora a paciência cresce com o tamanho da fala.
        if timeout is None:
            timeout = 25.0 + len(str(text or "")) / 8.0
        """Speak verified ZARA text with the configured Gemini Live voice."""
        value = str(text or "").strip()
        if not value or not self.active or self._speech_queue is None:
            return False
        # ZARA-VOICE-ORDEM-001: evento proprio deste pedido. Com o evento
        # compartilhado, o turn_complete de um turno liberava o await de outro
        # e a fala saia fora de ordem.
        done = asyncio.Event()
        # ZARA-LATENCIA-SEGUNDA-VIAGEM-001: folha limpa para os marcos desta
        # ida ao Google. A retentativa da cascata chama speak() de novo, entao
        # sem isto o segundo pedido herdaria o primeiro byte do primeiro.
        self._t_fala_pedida = None
        self._t_primeiro_byte_tts = None
        self._t_audio_entregue = None
        await self._speech_queue.put((value, done))
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
        finally:
            self._play_generated_audio = False

    # ZARA-LATENCIA-SEGUNDA-VIAGEM-001 — leitura dos marcos ---------------
    #
    # Os [VOICE_TRACE] morrem com o console e o console nao estava aberto na
    # hora em que o Alex achou lento. Quem grava em disco e o Cronometro, no
    # ipc_handlers. Estas duas funcoes existem so para entregar os numeros a
    # ele. Nao alteram estado e nunca levantam excecao.

    def ultimo_fim_de_fala(self) -> float | None:
        """perf_counter do instante em que o Alex parou de falar, ou None.

        None quer dizer honestamente "nao sei": turno vindo de texto, sessao
        recem-aberta, ou fala nova que ja zerou o marco.
        """
        return self._t_fim_fala_usuario

    def marcos_da_segunda_viagem(self) -> dict[str, int]:
        """Quanto custou a ida e volta ao Google para a Kore ler o resultado."""
        def _ms(inicio: float | None, fim: float | None) -> int | None:
            if inicio is None or fim is None:
                return None
            return round((fim - inicio) * 1000.0)

        bruto = {
            "tts_pedido_ate_primeiro_byte_ms": _ms(
                self._t_fala_pedida, self._t_primeiro_byte_tts
            ),
            "tts_primeiro_byte_ate_player_ms": _ms(
                self._t_primeiro_byte_tts, self._t_audio_entregue
            ),
            "tts_pedido_ate_player_ms": _ms(
                self._t_fala_pedida, self._t_audio_entregue
            ),
        }
        return {nome: valor for nome, valor in bruto.items() if valor is not None}

    def _schedule_idle_after_cooldown(self) -> None:
        """Volta ao estado IDLE apos o cooldown, sem bloquear o _receive_loop.

        ZARA-VOICE-LATENCY-001. A referencia da task e mantida em
        self._cooldown_tasks porque o asyncio so guarda referencia fraca e a
        task poderia ser coletada antes de terminar.
        """
        async def _later() -> None:
            try:
                await asyncio.sleep(self.config.wake_cooldown_seconds)
                if self._stop.is_set():
                    return
                # ZARA-VOICE-AUDICAO-001: sem gate local a ZARA nunca fica
                # surda, entao o estado honesto e LISTENING. Reportar IDLE
                # daria a impressao de que ela parou de ouvir.
                gate_local = bool(self.config.wake_word_enabled and self._wake_detector)
                await self._emit_state("IDLE" if gate_local else "LISTENING")
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_later(), name="zara-gemini-live-cooldown")
        self._cooldown_tasks.add(task)
        task.add_done_callback(self._cooldown_tasks.discard)

    async def interrupt_speech(self) -> None:
        """Stop only the current generated reply and keep the live session usable."""
        self._play_generated_audio = False
        await asyncio.to_thread(self._flush_output)
        self._mark_assistant_output_finished()
        if self._speech_done is not None:
            self._speech_done.set()
        await self._emit_level(0.0, False)
        await self._emit_state("LISTENING")

    @property
    def active(self) -> bool:
        return bool(self._task and not self._task.done())

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.active:
            return self.status()
        if not self.config.api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self._loop = asyncio.get_running_loop()
        self._audio_queue = asyncio.Queue(maxsize=64)
        self._speech_queue = asyncio.Queue(maxsize=8)
        self._speech_done = asyncio.Event()
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error = None
        self._stream_generation += 1
        generation = self._stream_generation
        self._audio_frames_received = 0
        self._task = asyncio.create_task(self._run(generation), name="zara-gemini-live")

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError as exc:
            self._stream_generation += 1
            self._stop.set()
            task = self._task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._task = None
            self._connected = False
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=TIMEOUT", flush=True)
            raise RuntimeError("VOICE_START_TIMEOUT") from exc
        if self._ready_error:
            await self.stop()
            raise RuntimeError(str(self._ready_error)) from self._ready_error
        return self.status()

    async def stop(self) -> None:
        self._stop.set()
        self._stream_generation += 1
        await asyncio.to_thread(self._close_input_stream)
        task = self._task
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=2.5)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._connected = False
        await asyncio.to_thread(self._close_output_stream)
        self._mark_assistant_output_finished()
        self._gate_open = False
        self._gate_until_idle = False
        self._wake_rolling = b""
        await self._emit_state("STANDBY")
        await self._emit_level(0.0, False)

    def status(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "connected": self._connected,
            "mode": "gemini_live",
            "model": self.config.model,
            "voice": self.config.voice_name,
            # ZARA-AEC-RENDERER-001: o renderer precisa saber se ele e o dono do
            # audio. Sem isto ele abriria o microfone tambem no modo local e a
            # maquina teria duas capturas concorrentes.
            "audio_transport": self.config.audio_transport,
            "input_sample_rate": self.config.input_sample_rate,
            "output_sample_rate": self.config.output_sample_rate,
            "block_ms": self.config.block_ms,
            "wake_word_enabled": self.config.wake_word_enabled,
            "gate_open": self._gate_open,
            "wake_detector_ready": self._wake_detector is not None,
            "session_state": self._last_state,
        }

    def _connect_session(self, genai_module: Any, types: Any):
        """Monta a config do Live e abre a conexao.

        Recebe o modulo `genai` (nao um client ja pronto) porque um client
        novo e barato de criar e isso mantem o metodo testavel sem precisar
        de um client real. `types` e o modulo `google.genai.types` — recebido
        por fora para que o teste possa simular tanto o SDK atual quanto um
        SDK antigo sem os tipos de deteccao de atividade (VAD).

        ZARA-VOICE-LATENCY-002: os tres valores de VAD (silencio, padding,
        sensibilidade de fim de fala) so sao aplicados quando o SDK instalado
        tem `RealtimeInputConfig`, `AutomaticActivityDetection` e
        `EndSensitivity`. Um SDK mais velho sem esses tipos ainda tem que
        conseguir abrir uma sessao — so fica sem o ajuste fino de VAD, em vez
        de quebrar a voz inteira.
        """
        client = genai_module.Client(api_key=self.config.api_key)

        kwargs: dict[str, Any] = {"response_modalities": ["AUDIO"]}

        if (
            hasattr(types, "SpeechConfig")
            and hasattr(types, "VoiceConfig")
            and hasattr(types, "PrebuiltVoiceConfig")
        ):
            kwargs["speech_config"] = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.config.voice_name
                    )
                )
            )
        if hasattr(types, "AudioTranscriptionConfig"):
            kwargs["input_audio_transcription"] = types.AudioTranscriptionConfig()
            kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
        if hasattr(types, "ContextWindowCompressionConfig") and hasattr(types, "SlidingWindow"):
            kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            )
        if hasattr(types, "SessionResumptionConfig"):
            kwargs["session_resumption"] = types.SessionResumptionConfig(
                handle=self._session_handle
            )
        if hasattr(types, "Content") and hasattr(types, "Part"):
            kwargs["system_instruction"] = types.Content(
                parts=[types.Part(text=self.config.system_instruction)]
            )

        # ZARA-VOICE-LATENCY-002: fecha o turno mais rapido depois que Alex
        # cala. Sem isto a sessao usava o padrao do servidor e a espera
        # aparecia como "ela e lenta".
        if (
            hasattr(types, "RealtimeInputConfig")
            and hasattr(types, "AutomaticActivityDetection")
            and hasattr(types, "EndSensitivity")
        ):
            kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    silence_duration_ms=self.config.vad_silencio_ms,
                    prefix_padding_ms=self.config.vad_padding_ms,
                    end_of_speech_sensitivity=(
                        types.EndSensitivity.END_SENSITIVITY_HIGH
                        if self.config.vad_fim_sensivel
                        else types.EndSensitivity.END_SENSITIVITY_LOW
                    ),
                ),
            )
            print(
                "[VOICE_TRACE] stage=VAD_CONFIG "
                f"silencio_ms={self.config.vad_silencio_ms} "
                f"padding_ms={self.config.vad_padding_ms} "
                f"fim_sensivel={self.config.vad_fim_sensivel}",
                flush=True,
            )
        else:
            print(
                "[VOICE_TRACE] stage=VAD_CONFIG result=SKIP "
                "reason=sdk_sem_activity_types",
                flush=True,
            )

        live_config = types.LiveConnectConfig(**kwargs)
        return client.aio.live.connect(model=self.config.model, config=live_config)

    async def _run(self, generation: int) -> None:
        try:
            # ZARA-VOICE-KORE-PACKAGING-001
            # Estes imports falham de formas MUITO diferentes: no source,
            # por pacote ausente; no EXE empacotado, por binario nativo que
            # o PyInstaller nao levou (o PortAudio do sounddevice). A mensagem
            # antiga era igual nos dois casos, entao a causa real ficava
            # invisivel e a ZARA so trocava de voz em silencio.
            # Cada import e isolado e o erro real e propagado.
            try:
                import sounddevice as sd
            except Exception as exc:  # pragma: no cover - environment dependent
                print(
                    f"[VOICE_TRACE] stage=LIVE_IMPORT result=FAIL module=sounddevice "
                    f"error_type={type(exc).__name__} error={exc}",
                    flush=True,
                )
                raise RuntimeError(
                    f"Gemini Live indisponivel: falha ao carregar sounddevice "
                    f"({type(exc).__name__}: {exc}). No app empacotado isso costuma "
                    f"ser o binario nativo do PortAudio ausente no build."
                ) from exc
            try:
                from google import genai
                from google.genai import types
            except Exception as exc:  # pragma: no cover - environment dependent
                print(
                    f"[VOICE_TRACE] stage=LIVE_IMPORT result=FAIL module=google.genai "
                    f"error_type={type(exc).__name__} error={exc}",
                    flush=True,
                )
                raise RuntimeError(
                    f"Gemini Live indisponivel: falha ao carregar google-genai "
                    f"({type(exc).__name__}: {exc})."
                ) from exc
            print("[VOICE_TRACE] stage=LIVE_IMPORT result=PASS", flush=True)

            print("[VOICE_TRACE] stage=MIC_DEVICE_ENUMERATION result=START", flush=True)
            opened = await asyncio.to_thread(self._open_streams, sd, generation)
            if not opened:
                return
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=PASS", flush=True)
            if self.config.wake_word_enabled:
                print("[VOICE_TRACE] stage=WAKE_ENGINE_LOAD result=START", flush=True)
                self._ensure_wake_detector()
            first_connection = True
            if self.config.wake_word_enabled and self._wake_detector is not None:
                await self._emit_state("IDLE")

            while not self._stop.is_set():
                try:
                    async with self._connect_session(genai, types) as session:
                        self._connected = True
                        # ZARA-VOZ-QUEDA-SILENCIOSA-001: voltou. Se ele foi
                        # avisado da queda, precisa ser avisado da volta — senão
                        # fica achando que a voz continua morta e não usa mais.
                        if getattr(self, "_quedas_seguidas", 0):
                            print(
                                f"[VOICE_TRACE] stage=LIVE_VOLTOU depois_de={self._quedas_seguidas}",
                                flush=True,
                            )
                            await self._emit_error(
                                RuntimeError("A voz voltou. Pode falar comigo de novo.")
                            )
                            self._quedas_seguidas = 0
                        if first_connection:
                            self._ready.set()
                            first_connection = False
                        await self._emit_state("LISTENING")

                        send_task = asyncio.create_task(
                            self._send_audio_loop(session, types),
                            name="zara-gemini-live-send",
                        )
                        receive_task = asyncio.create_task(
                            self._receive_loop(session, sd),
                            name="zara-gemini-live-receive",
                        )
                        speech_task = asyncio.create_task(
                            self._send_speech_loop(session, types),
                            name="zara-gemini-live-speech",
                        )
                        stop_task = asyncio.create_task(
                            self._stop.wait(),
                            name="zara-gemini-live-stop-wait",
                        )
                        done, pending = await asyncio.wait(
                            {send_task, receive_task, speech_task, stop_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for pending_task in pending:
                            pending_task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        for finished in done:
                            if finished is stop_task:
                                continue
                            exc = finished.exception()
                            if exc:
                                raise exc

                    self._connected = False
                    if not self._stop.is_set():
                        await asyncio.sleep(0.35)

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._connected = False
                    if first_connection:
                        self._ready_error = exc
                        self._ready.set()
                        return

                    # ZARA-VOZ-QUEDA-SILENCIOSA-001
                    #
                    # No histórico de 15/08, entre 08h40 e 09h01, a mesma queda
                    # apareceu doze vezes: "keepalive ping timeout",
                    # "1006 abnormal closure", "timed out during opening
                    # handshake". Cada uma virou uma linha de sistema na
                    # conversa do Alex — ele abriu o app e viu erro de websocket
                    # no meio do papo com a ZARA.
                    #
                    # Duas coisas estavam erradas, e nenhuma era a queda em si:
                    #
                    # 1. Recuo fixo de um segundo. Bater de segundo em segundo
                    #    numa conexão que está recusando não acelera a volta —
                    #    só multiplica o erro e queima cota.
                    # 2. Todo tentativa falha virava recado. A décima segunda
                    #    mensagem idêntica não informa nada; só faz ele parar de
                    #    ler os avisos, inclusive os que importam.
                    #
                    # Agora: recuo crescente, e ele é avisado UMA vez quando cai
                    # e uma vez quando volta. Quedas no meio ficam no log
                    # técnico, onde eu procuro, não na conversa dele.
                    self._quedas_seguidas = getattr(self, "_quedas_seguidas", 0) + 1
                    print(
                        f"[VOICE_TRACE] stage=LIVE_QUEDA n={self._quedas_seguidas} "
                        f"motivo={type(exc).__name__}: {str(exc)[:120]}",
                        flush=True,
                    )
                    if self._quedas_seguidas == 1:
                        await self._emit_error(exc)
                    await self._emit_state("PROCESSING")
                    if not self._stop.is_set():
                        # 1, 2, 4, 8, 16, 30, 30... — chega em meio minuto e fica.
                        espera = min(2 ** (self._quedas_seguidas - 1), 30)
                        await asyncio.sleep(espera)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self._ready.is_set():
                self._ready_error = exc
                self._ready.set()
            await self._emit_error(exc)
        finally:
            self._connected = False
            await asyncio.to_thread(self._close_input_stream)
            await asyncio.to_thread(self._close_output_stream)
            await self._emit_state("STANDBY")
            await self._emit_level(0.0, False)

    def _open_streams(self, sd: Any, generation: int) -> bool:
        if self._loop is None or self._audio_queue is None:
            raise RuntimeError("Voice loop não inicializado")

        blocksize = max(
            160,
            int(self.config.input_sample_rate * (self.config.block_ms / 1000.0)),
        )

        def mic_callback(indata: Any, _frames: int, _time: Any, status: Any) -> None:
            if status:
                # PortAudio status is informational unless the callback fails.
                pass
            raw = bytes(indata)
            self._audio_frames_received += 1
            if self._audio_frames_received == 1:
                print("[VOICE_TRACE] stage=AUDIO_FRAMES_RECEIVED result=PASS", flush=True)
            level = self._pcm_level(raw)
            loop = self._loop
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(self._queue_audio, raw, level)

        # ZARA-AEC-RENDERER-001: no modo renderer nao existe stream PortAudio.
        # O microfone chega por push_mic_pcm() e a Kore sai por on_output_audio.
        if self.usa_renderer:
            print(
                "[VOICE_TRACE] stage=AUDIO_TRANSPORT result=RENDERER "
                "aec=chromium",
                flush=True,
            )
            return True

        devices = sd.query_devices()
        default_devices = getattr(getattr(sd, "default", None), "device", (None, None))
        print(
            "[VOICE_TRACE] stage=SELECTED_INPUT_DEVICE "
            f"configured={self.config.input_device is not None} "
            f"default_index={default_devices[0] if default_devices else None} "
            f"device_count={len(devices)}",
            flush=True,
        )
        input_stream = None
        output_stream = None
        try:
            input_stream = sd.RawInputStream(
                samplerate=self.config.input_sample_rate,
                blocksize=blocksize,
                channels=1,
                dtype="int16",
                device=self.config.input_device,
                callback=mic_callback,
            )
            input_stream.start()
            if generation != self._stream_generation or self._stop.is_set():
                self._close_stream_pair(input_stream, output_stream)
                return False
            self._input_stream = input_stream
            self._output_stream = output_stream
            return True
        except Exception:
            self._close_stream_pair(input_stream, output_stream)
            raise

    @staticmethod
    def _close_stream_pair(input_stream: Any, output_stream: Any) -> None:
        for stream in (input_stream, output_stream):
            if stream is None:
                continue
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def _queue_audio(self, raw: bytes, level: float) -> None:
        queue = self._audio_queue
        if queue is None or self._stop.is_set():
            return

        if self._gate_until_idle:
            asyncio.create_task(self._emit_level(0.0, False))
            return

        # --- Wake-gate (ZARA-VOICE-WAKE-GATE-001) ---
        if self.config.wake_word_enabled and self._wake_detector is not None:
            if not self._gate_open:
                # IDLE: only run the local wake detector; nothing reaches Gemini.
                woke = self._check_wake_word(raw)
                if woke:
                    asyncio.create_task(self._open_gate_task())
                # Keep level animation responsive in IDLE too.
                asyncio.create_task(self._emit_level(level, False))
                return
        # LISTENING (or gate disabled -> legacy always-stream): enqueue for Gemini.
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(raw)
        except asyncio.QueueFull:
            pass
        asyncio.create_task(self._emit_level(level, False))

    async def _open_gate_task(self) -> None:
        """Wake word fired: open the gate so the next speech streams to Gemini."""
        await self.open_gate()

    async def _send_audio_loop(self, session: Any, types: Any) -> None:
        if self._audio_queue is None:
            return
        while not self._stop.is_set():
            chunk = await self._audio_queue.get()
            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type=f"audio/pcm;rate={self.config.input_sample_rate}",
                )
            )

    async def _send_speech_loop(self, session: Any, types: Any) -> None:
        if self._speech_queue is None:
            return
        while not self._stop.is_set():
            text, done = await self._speech_queue.get()
            # O turn_complete / interrupted que chegar a seguir libera ESTE
            # pedido, e nenhum outro (ZARA-VOICE-ORDEM-001).
            self._speech_done = done
            self._play_generated_audio = True
            self._mark_assistant_output_started(text)
            # ZARA-LATENCIA-SEGUNDA-VIAGEM-001: aqui comeca a ida e volta ao
            # Google. Tudo daqui ate _t_primeiro_byte_tts e rede + modelo.
            self._t_fala_pedida = time.perf_counter()
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=f"FALE_EXATAMENTE: {text}")],
                ),
                turn_complete=True,
            )

    async def _receive_loop(self, session: Any, sd: Any) -> None:
        while not self._stop.is_set():
            async for response in session.receive():
                if self._stop.is_set():
                    return

                update = getattr(response, "session_resumption_update", None)
                if update and getattr(update, "resumable", False):
                    new_handle = getattr(update, "new_handle", None)
                    if new_handle:
                        self._session_handle = str(new_handle)

                if getattr(response, "go_away", None) is not None:
                    return

                content = getattr(response, "server_content", None)
                if not content:
                    continue

                if getattr(content, "interrupted", False):
                    self._flush_output()
                    self._mark_assistant_output_finished()
                    self._input_text = ""
                    self._output_text = ""
                    # Barge-in encerra o turno corrente: o roteamento dele nao
                    # vale mais para o audio que vier depois.
                    self._reset_turn_state()
                    self._play_generated_audio = False
                    if self._speech_done is not None:
                        self._speech_done.set()
                    self._gate_until_idle = False
                    if self.config.wake_word_enabled and self._wake_detector is not None:
                        self._gate_open = False
                        await self._emit_state("IDLE")
                    else:
                        await self._emit_state("LISTENING")
                    await self._emit_level(0.0, False)
                    await self._call(self.on_interrupt)

                input_tx = getattr(content, "input_transcription", None)
                if input_tx and getattr(input_tx, "text", None):
                    if not self._utterance_open:
                        self._begin_utterance()
                    self._input_text = self._merge_fragment(
                        self._input_text, str(input_tx.text)
                    )

                output_tx = getattr(content, "output_transcription", None)
                if output_tx and getattr(output_tx, "text", None):
                    self._output_text = self._merge_fragment(
                        self._output_text, str(output_tx.text)
                    )
                    if self._assistant_output_active:
                        self._assistant_output_text = self._output_text

                model_turn = getattr(content, "model_turn", None)
                if model_turn:
                    # ZARA-VOICE-FLUIDEZ-001
                    # Ate 2026-08-13 o audio gerado era SEMPRE mudo: todo turno
                    # ia para o pipeline local e voltava numa segunda viagem ao
                    # Google so para a Kore ler o resultado. Isso custava dois
                    # round-trips por frase e era a origem do "ela pensa, ai
                    # volta e responde".
                    #
                    # Agora o audio toca direto em turno de CONVERSA e continua
                    # mudo em turno de ACAO, onde so o resultado verificado pelo
                    # executor pode ser falado.
                    #
                    # O primeiro audio do modelo e o ponto de decisao: se ele
                    # chegou, o VAD do servidor ja fechou a fala do Alex, entao
                    # self._input_text carrega a frase inteira e decidir aqui
                    # nao atrasa nada.
                    # ZARA-LATENCIA-SEGUNDA-VIAGEM-001 — FIM DA FALA DO ALEX.
                    #
                    # Este e o marco que faltava e sem o qual a queixa dele nao
                    # vira numero. O comentario acima ja afirma a premissa: se o
                    # primeiro audio do modelo chegou, o VAD do servidor ja
                    # fechou a fala do Alex. Entao este instante e o "ele calou
                    # a boca" mais cedo que o Python consegue observar.
                    #
                    # E aproximado por cima: o VAD fechou alguns tracos de
                    # segundo antes, o tempo de o servidor comecar a gerar. Isso
                    # e INFERIDO, nao medido, e por isso o numero que sai daqui
                    # e um PISO da espera real do Alex, nunca o total dela.
                    if not self._play_generated_audio and self._t_fim_fala_usuario is None:
                        self._t_fim_fala_usuario = time.perf_counter()
                        print(
                            "[VOICE_TRACE] stage=FIM_DA_FALA_DO_USUARIO "
                            "result=VAD_FECHOU_INFERIDO ms=0",
                            flush=True,
                        )
                    if not self._turn_route_decided and not self._play_generated_audio:
                        self._decide_turn_route()
                    for part in getattr(model_turn, "parts", []) or []:
                        inline = getattr(part, "inline_data", None)
                        audio_data = getattr(inline, "data", None) if inline else None
                        if audio_data and (self._play_generated_audio or self._turn_direct):
                            audio_bytes = bytes(audio_data)
                            # PRIMEIRO BYTE DE TTS: a Kore respondeu. O que
                            # existe entre o pedido e este instante e rede +
                            # modelo, e e o preco estrutural da segunda viagem.
                            if self._play_generated_audio and self._t_primeiro_byte_tts is None:
                                self._t_primeiro_byte_tts = time.perf_counter()
                                _base = self._t_fala_pedida or self._t_primeiro_byte_tts
                                print(
                                    "[VOICE_TRACE] stage=TTS_PRIMEIRO_BYTE result=PASS "
                                    f"ms={(self._t_primeiro_byte_tts - _base) * 1000:.0f}",
                                    flush=True,
                                )
                            self._mark_assistant_output_started(self._output_text)
                            await self._emit_state("SPEAKING")
                            await self._emit_level(self._pcm_level(audio_bytes), True)
                            if self.usa_renderer:
                                # ZARA-AEC-RENDERER-001: o Electron toca. Isso e
                                # o que cria o far-end que o AEC precisa.
                                await self._call(self.on_output_audio, audio_bytes)
                            else:
                                if self._output_stream is None:
                                    await asyncio.to_thread(self._ensure_output_stream, sd)
                                await asyncio.to_thread(self._output_stream.write, audio_bytes)
                            # INICIO DO AUDIO AUDIVEL — proxy, e o relatorio tem
                            # de dizer isso. No modo renderer o Python entrega os
                            # bytes ao Electron; quando o alto-falante realmente
                            # vibra e do outro lado do IPC e do WebAudio, e daqui
                            # nao da para ver. No modo PortAudio o write ja foi
                            # feito acima, entao o proxy e mais apertado.
                            if self._play_generated_audio and self._t_audio_entregue is None:
                                self._t_audio_entregue = time.perf_counter()
                                print(
                                    "[VOICE_TRACE] stage=AUDIO_AUDIVEL_INICIO "
                                    f"result={'PROXY_RENDERER' if self.usa_renderer else 'PORTAUDIO'} "
                                    f"ms={(self._t_audio_entregue - (self._t_primeiro_byte_tts or self._t_audio_entregue)) * 1000:.0f}",
                                    flush=True,
                                )

                if getattr(content, "turn_complete", False):
                    await self._finish_turn()
                    if self._play_generated_audio and self._speech_done is not None:
                        self._speech_done.set()
                    # Return to wake mode after a short cooldown so Alex can
                    # say "Zara" again without the previous turn bleeding in.
                    self._gate_open = False
                    # ZARA-VOICE-LATENCY-001
                    # Este cooldown ficava DENTRO do _receive_loop, entao por
                    # 1,5 s o loop parava de consumir respostas do servidor —
                    # inclusive as do turno seguinte, o que empurrava a fala da
                    # Kore para depois. O gate ja fechou na linha acima, que e
                    # o que de fato impede o turno anterior de sangrar; a
                    # espera so precisa atrasar o estado visual IDLE.
                    # Agora roda em paralelo e o loop continua livre.
                    self._schedule_idle_after_cooldown()

    def _begin_utterance(self) -> None:
        """Alex comecou a falar de novo. ZARA-VOICE-ORDEM-001.

        Cancela o turno anterior que ainda estiver em andamento. Era exatamente
        isto que fazia a ZARA responder uma pergunta antiga: o turno lento (LLM
        + executor) terminava DEPOIS da pergunta seguinte e falava assim mesmo,
        porque cada turno virava um create_task solto, sem ordem e sem dono.

        Cancelar aqui tambem e o que impede a resposta de cair por cima da fala
        do Alex: se ele voltou a falar, a resposta anterior perdeu a validade.
        """
        self._utterance_open = True
        self._turn_route_decided = False
        self._turn_direct = False
        self._turn_rejected_as_echo = False
        # ZARA-LATENCIA-SEGUNDA-VIAGEM-001: fala nova, relogio novo. Sem isto o
        # "fim da fala" ficaria preso no primeiro turno da sessao e todo turno
        # seguinte reportaria uma espera absurda e falsa.
        self._t_fim_fala_usuario = None
        # ZARA-VOICE-ECO-002: congela AQUI se esta fala nasceu por cima da voz
        # da ZARA. Congelar no inicio e o que torna o sinal confiavel — quando
        # o turno terminar ela ja parou de falar e a informacao teria sumido.
        self._turn_echo_suspect = self.speaking_now
        self._turn_echo_references = (
            self._echo_reference_texts() if self._turn_echo_suspect else ()
        )
        if self._turn_echo_suspect:
            print("[VOICE_TRACE] stage=ECHO_SUSPECT result=OVER_OWN_SPEECH", flush=True)
        # Fora de uma saida da assistente, a nova fala e humana e pode cancelar
        # o turno anterior imediatamente. Durante a saida, espera-se o texto:
        # eco jamais deve cancelar trabalho valido.
        if not self._turn_echo_suspect:
            self._cancel_superseded_routed_turn()

    def _cancel_superseded_routed_turn(self) -> None:
        task = self._routed_turn_task
        self._routed_turn_task = None
        if task is not None and not task.done():
            task.cancel()
            print("[VOICE_TRACE] stage=TURN_CANCELLED result=SUPERSEDED", flush=True)

    def _decide_turn_route(self) -> None:
        """CONVERSA (audio direto) ou ACAO (audio suprimido)? ZARA-VOICE-FLUIDEZ-001.

        Falha FECHADA. Sem predicado, sem transcricao, ou com erro dentro do
        predicado, o audio NAO toca e o turno segue para o executor. Deixar
        tocar por engano seria a ZARA declarando uma acao que ninguem executou,
        que e o falso sucesso que este projeto existe para impedir.
        """
        self._turn_route_decided = True
        self._turn_direct = False
        decider = self.can_answer_directly
        text = self._input_text.strip()
        if self.is_self_echo_transcript(
            text, references=self._turn_echo_references
        ):
            self._turn_rejected_as_echo = True
            print("[VOICE_TRACE] stage=SELF_ECHO result=DISCARDED_BEFORE_ROUTE", flush=True)
            return
        if decider is None or not text:
            print("[VOICE_TRACE] stage=TURN_ROUTE result=EXECUTOR reason=SEM_TRANSCRICAO",
                  flush=True)
            return
        try:
            self._turn_direct = bool(decider(text))
        except Exception:
            self._turn_direct = False
        print("[VOICE_TRACE] stage=TURN_ROUTE result="
              + ("DIRECT_CONVERSATION" if self._turn_direct else "EXECUTOR"), flush=True)

    def _reset_turn_state(self) -> None:
        self._utterance_open = False
        self._turn_route_decided = False
        self._turn_direct = False
        self._turn_echo_suspect = False
        self._turn_echo_references = ()
        self._turn_rejected_as_echo = False

    async def _finish_turn(self) -> None:
        user_text = self._input_text.strip()
        model_text = self._output_text.strip()
        direct = self._turn_direct
        echo_references = tuple(dict.fromkeys(
            (*self._turn_echo_references, *self._echo_reference_texts())
        ))
        rejected_as_echo = self._turn_rejected_as_echo or self.is_self_echo_transcript(
            user_text, references=echo_references
        )
        self._mark_assistant_output_finished()
        self._input_text = ""
        self._output_text = ""
        self._reset_turn_state()
        if rejected_as_echo:
            print(
                "[VOICE_TRACE] stage=SELF_ECHO result=DISCARDED "
                "wake_renewed=NO turn_created=NO intent_created=NO action_dispatched=NO",
                flush=True,
            )
            await self._emit_level(0.0, False)
            return
        if user_text or model_text:
            # Do not block the receive loop: deterministic action routing may
            # ask this same Live session to speak the verified result.
            #
            # ZARA-VOICE-ORDEM-001: a referencia agora e guardada. Sem dono, a
            # task nao podia ser cancelada quando Alex falava de novo.
            if user_text:
                self._cancel_superseded_routed_turn()
            task = asyncio.create_task(
                self._call(self.on_turn, user_text, model_text, direct),
                name="zara-gemini-live-routed-turn",
            )
            self._routed_turn_task = task
            task.add_done_callback(
                lambda t: setattr(self, "_routed_turn_task", None)
                if self._routed_turn_task is t else None
            )
        await self._emit_level(0.0, False)
        # With the wake gate the turn completes back into IDLE (cooldown is
        # applied by the caller); legacy mode keeps LISTENING.
        if self.config.wake_word_enabled and self._wake_detector is not None:
            await self._emit_state("IDLE")
        else:
            await self._emit_state("LISTENING")

    def _ensure_output_stream(self, sd: Any) -> None:
        if self._output_stream is not None:
            return
        stream = sd.RawOutputStream(
            samplerate=self.config.output_sample_rate,
            channels=1,
            dtype="int16",
            device=self.config.output_device,
        )
        stream.start()
        self._output_stream = stream

    def _flush_output(self) -> None:
        # ZARA-AEC-RENDERER-001: no modo renderer o audio esta enfileirado no
        # WebAudio, nao no PortAudio. Cortar de verdade exige avisar o Electron
        # — mudar so o estado visual deixaria a Kore falando por cima do Alex,
        # que e exatamente o que o barge-in existe para impedir.
        if self.usa_renderer:
            loop = self._loop
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(
                        self._call(self.on_output_audio, b""),
                        name="zara-aec-stop-output",
                    )
                )
            return

        stream = self._output_stream
        if stream is None:
            return
        try:
            stream.abort()
            stream.start()
        except Exception:
            pass

    def _close_input_stream(self) -> None:
        stream, self._input_stream = self._input_stream, None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    def _close_output_stream(self) -> None:
        stream, self._output_stream = self._output_stream, None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    @staticmethod
    def _merge_fragment(current: str, fragment: str) -> str:
        fragment = fragment or ""
        if not fragment:
            return current
        if not current:
            return fragment
        if fragment.startswith(current):
            return fragment
        if current.endswith(fragment):
            return current
        separator = "" if current.endswith((" ", "\n")) or fragment.startswith((" ", "\n", ".", ",", "!", "?", ":", ";")) else " "
        return current + separator + fragment

    @staticmethod
    def _pcm_level(raw: bytes) -> float:
        if len(raw) < 2:
            return 0.0
        try:
            import numpy as np
            values = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            if values.size == 0:
                return 0.0
            rms = float(np.sqrt(np.mean(values * values)))
        except Exception:
            # Small pure-Python fallback for environments where numpy import is delayed.
            count = len(raw) // 2
            if count <= 0:
                return 0.0
            total = 0.0
            for i in range(0, count * 2, 2):
                sample = int.from_bytes(raw[i:i + 2], "little", signed=True)
                total += float(sample * sample)
            rms = math.sqrt(total / count)
        # Around 6k RMS is already a strong close-mic signal. Soft knee keeps
        # the particle animation expressive without clipping constantly.
        return max(0.0, min(1.0, rms / 6000.0))

    async def _emit_state(self, state: str) -> None:
        if state == self._last_state:
            return
        self._last_state = state
        await self._call(self.on_state, state)

    async def _emit_level(self, level: float, speaking: bool) -> None:
        await self._call(self.on_level, max(0.0, min(1.0, float(level))), speaking)

    async def _emit_error(self, exc: Exception) -> None:
        await self._call(self.on_error, str(exc))

    @staticmethod
    async def _call(callback: AsyncCallback | None, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result
