"""Item 4 — "responder enquanto executa" + feedback falado + mute inteligente
(FRENTE 2, 2026-09-29).

Cobre:
- MicGuard: pausa o mic enquanto ela fala, retoma quando cala, contagem de
  referência p/ falas simultâneas, watchdog se a voz travar ligada;
- NarradorDeVoz: frases curtas por ação (início + conclusão), privacidade
  (nunca fala valor de texto digitado/clipboard/notificação), ação
  desconhecida tem frase genérica;
- executar_narrada: anuncia o início sem atrasar a ação, anuncia a falha;
- montar_narrador_para_ipc: fiação com o pipeline real;
- VoicePipeline.pause/resume_listening com contagem de referência (o
  _speak_response e o narrador pausam pelo mesmo funil sem brigar).

Tudo com fakes injetáveis — nenhum teste toca microfone ou alto-falante.
"""
from __future__ import annotations

import asyncio

from core.voice_stt import VoiceConfig, VoicePipeline
from core.voz_narrador import (
    MicGuard,
    NarradorDeVoz,
    montar_narrador_para_ipc,
)


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class RelogioFake:
    """Relógio + sleep controlados: o tempo só anda quando o teste manda."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    async def dormir(self, segundos):
        self.t += segundos
        await asyncio.sleep(0)  # cede ao loop: tarefas concorrentes intercalam


class MicFake:
    def __init__(self):
        self.pausas = 0
        self.retomadas = 0

    def pausar(self):
        self.pausas += 1

    def retomar(self):
        self.retomadas += 1


class FalanteFake:
    """falar() registra; falando() segue o relógio fake (voz de N segundos)."""

    def __init__(self, relogio, duracao_fala=3.0):
        self.relogio = relogio
        self.duracao_fala = duracao_fala
        self.falas = []
        self._inicio_ultima_fala = None

    def falar(self, texto):
        self.falas.append(texto)
        self._inicio_ultima_fala = self.relogio()

    def falando(self):
        if self._inicio_ultima_fala is None:
            return False
        return (self.relogio() - self._inicio_ultima_fala) < self.duracao_fala


class ResultadoFake:
    def __init__(self, success, output=""):
        self.success = success
        self.output = output


def fazer_guard(mic=None, falante=None, relogio=None, **kwargs):
    relogio = relogio or RelogioFake()
    mic = mic or MicFake()
    falante = falante or FalanteFake(relogio)
    guard = MicGuard(
        pausar_mic=mic.pausar,
        retomar_mic=mic.retomar,
        falando=falante.falando,
        dormir=relogio.dormir,
        relogio=relogio,
        settle_seconds=0.4,
        **kwargs,
    )
    return guard, mic, falante, relogio


# ---------------------------------------------------------------------------
# MicGuard
# ---------------------------------------------------------------------------


def test_falar_com_mute_pausa_fala_e_retoma():
    guard, mic, falante, relogio = fazer_guard()
    ok = asyncio.run(guard.falar_com_mute("abrindo o Excel...", falante.falar))
    assert ok is True
    assert falante.falas == ["abrindo o Excel..."]
    assert mic.pausas == 1
    assert mic.retomadas == 1
    assert not guard.pausado
    # esperou a fala terminar (+ settle) antes de retomar
    assert relogio.t >= 3.0


def test_texto_vazio_nao_fala_nem_pausa():
    guard, mic, falante, _ = fazer_guard()
    assert asyncio.run(guard.falar_com_mute("   ", falante.falar)) is False
    assert asyncio.run(guard.falar_com_mute("oi", None)) is False
    assert falante.falas == []
    assert mic.pausas == 0


def test_falas_simultaneas_nao_retomam_cedo():
    # Duas falas sobrepostas: o mic só volta quando AMBAS terminarem.
    guard, mic, falante, relogio = fazer_guard()

    async def duas_falas():
        t1 = asyncio.create_task(guard.falar_com_mute("uma", falante.falar))
        t2 = asyncio.create_task(guard.falar_com_mute("duas", falante.falar))
        await asyncio.gather(t1, t2)

    asyncio.run(duas_falas())
    assert mic.pausas == 1  # segunda pausa aproveita o mute já ativo
    assert mic.retomadas == 1
    assert not guard.pausado


def test_evento_pisca_nao_retoma_no_meio_da_fala():
    # Cenário real: duas peças sobrepostas; a thread da 1ª apaga o
    # _speaking_event enquanto a 2ª ainda fala. O disparo recente segura o
    # mute até a estimativa da 2ª peça expirar.
    relogio = RelogioFake()
    mic = MicFake()
    evento = {"ligado": False}

    guard = MicGuard(
        pausar_mic=mic.pausar,
        retomar_mic=mic.retomar,
        falando=lambda: evento["ligado"],
        dormir=relogio.dormir,
        relogio=relogio,
        chars_por_segundo=10.0,  # estimativa: 10 chars -> 1.5s
    )

    async def cenario():
        t1 = asyncio.create_task(guard.falar_com_mute("1234567890", lambda t: None))
        await asyncio.sleep(0)
        # a 2ª peça dispara 0.5s depois (dentro da 1ª)
        relogio.t += 0.5
        evento["ligado"] = True  # a 1ª ainda "fala"
        t2 = asyncio.create_task(guard.falar_com_mute("1234567890", lambda t: None))
        await asyncio.sleep(0)
        # a thread da 1ª termina e APAGA o evento com a 2ª no ar
        relogio.t += 0.5
        evento["ligado"] = False
        await asyncio.gather(t1, t2)

    asyncio.run(cenario())
    # A 2ª peça foi disparada em t=0.5 com estimativa de 1.5s: o mic só pode
    # voltar em t>=2.0. Sem o tracking, voltaria em t~1.0 (no meio da fala).
    assert relogio.t >= 2.0
    assert mic.pausas == 1
    assert mic.retomadas == 1


def test_watchdog_retoma_mesmo_com_voz_travada_ligada():
    # falando() nunca volta a False: o teto salva o mic.
    relogio = RelogioFake()
    mic = MicFake()
    guard = MicGuard(
        pausar_mic=mic.pausar,
        retomar_mic=mic.retomar,
        falando=lambda: True,
        dormir=relogio.dormir,
        relogio=relogio,
        max_wait_seconds=5.0,
    )
    asyncio.run(guard.falar_com_mute("teste", lambda t: None))
    assert mic.pausas == 1
    assert mic.retomadas == 1
    assert relogio.t >= 5.0


def test_sem_falando_usa_estimativa_de_duracao():
    # Sem observabilidade, espera pelo tamanho do texto e retoma.
    relogio = RelogioFake()
    mic = MicFake()
    falas = []
    guard = MicGuard(
        pausar_mic=mic.pausar,
        retomar_mic=mic.retomar,
        falando=None,
        dormir=relogio.dormir,
        relogio=relogio,
        chars_por_segundo=10.0,
    )
    asyncio.run(guard.falar_com_mute("x" * 100, falas.append))
    assert falas == ["x" * 100]
    assert mic.retomadas == 1
    assert relogio.t >= 10.0  # 100 chars / 10 cps


def test_falha_no_controle_do_mic_nao_cala_a_zara():
    def pausar_quebrado():
        raise RuntimeError("driver de áudio sumiu")

    relogio = RelogioFake()
    falas = []
    guard = MicGuard(
        pausar_mic=pausar_quebrado,
        retomar_mic=None,
        falando=lambda: False,
        dormir=relogio.dormir,
        relogio=relogio,
    )
    assert asyncio.run(guard.falar_com_mute("oi", falas.append)) is True
    assert falas == ["oi"]


# ---------------------------------------------------------------------------
# NarradorDeVoz — frases
# ---------------------------------------------------------------------------


def test_frase_inicio_os_app():
    n = NarradorDeVoz()
    assert n.frase_inicio("os_app", {"app": "Excel"}) == "abrindo Excel..."


def test_frase_conclusao_falha_os_app():
    n = NarradorDeVoz()
    assert (
        n.frase_conclusao("os_app", {"app": "Excel"}, ok=False)
        == "não consegui abrir Excel"
    )


def test_frase_conclusao_sucesso():
    n = NarradorDeVoz()
    assert n.frase_conclusao("os_app", {"app": "Excel"}, ok=True) == "pronto, abri Excel"


def test_acao_desconhecida_tem_frase_generica():
    n = NarradorDeVoz()
    assert n.frase_inicio("acao_que_nao_existe") == "trabalhando nisso..."
    assert n.frase_conclusao("acao_que_nao_existe", ok=True) == "pronto"
    assert n.frase_conclusao("acao_que_nao_existe", ok=False) == "não consegui concluir"


def test_privacidade_texto_digitado_nunca_e_falado():
    n = NarradorDeVoz()
    inicio = n.frase_inicio("input_type_text", {"text": "senha123"})
    conclusao = n.frase_conclusao("input_type_text", {"text": "senha123"}, ok=True)
    assert "senha123" not in inicio
    assert "senha123" not in conclusao
    assert inicio == "digitando..."


def test_privacidade_clipboard_e_notificacao():
    n = NarradorDeVoz()
    assert "segredo" not in n.frase_inicio("os_clipboard", {"text": "segredo"})
    assert "segredo" not in n.frase_inicio(
        "os_notify", {"title": "t", "message": "segredo"}
    )


def test_url_vira_host_curto():
    n = NarradorDeVoz()
    frase = n.frase_inicio(
        "browser_open_url", {"url": "https://www.youtube.com/watch?v=abc123"}
    )
    assert frase == "abrindo youtube.com no navegador..."
    assert "watch?v=" not in frase


def test_alvo_longo_e_cortado():
    n = NarradorDeVoz(limite_chars=20)
    frase = n.frase_inicio("browser_search", {"query": "x" * 100})
    assert len(frase) <= len("pesquisando  ...") + 20 + 5  # folga p/ template


def test_busca_fala_a_query():
    n = NarradorDeVoz()
    assert (
        n.frase_inicio("browser_search", {"query": "receita de bolo"})
        == "pesquisando receita de bolo..."
    )


# ---------------------------------------------------------------------------
# NarradorDeVoz — fala
# ---------------------------------------------------------------------------


def test_anunciar_inicio_fala_com_mic_mutado():
    relogio = RelogioFake()
    mic = MicFake()
    falante = FalanteFake(relogio)
    guard, _, _, _ = fazer_guard(mic=mic, falante=falante, relogio=relogio)
    n = NarradorDeVoz(falar=falante.falar, mic_guard=guard)
    ok = asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"}))
    assert ok is True
    assert falante.falas == ["abrindo Excel..."]
    assert mic.pausas == 1 and mic.retomadas == 1


def test_botao_mudo_silencia_o_narrador_mas_nao_o_teste():
    # _silenciada: ela continua executando, só não fala.
    falas = []
    n = NarradorDeVoz(falar=falas.append, falar_habilitado=lambda: False)
    assert asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"})) is False
    assert falas == []


def test_sem_canal_de_fala_nao_faz_nada():
    n = NarradorDeVoz()
    assert asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"})) is False


# ---------------------------------------------------------------------------
# executar_narrada — orquestração
# ---------------------------------------------------------------------------


def test_executar_narrada_anuncia_e_devolve_resultado():
    relogio = RelogioFake()
    mic = MicFake()
    falante = FalanteFake(relogio)
    guard, _, _, _ = fazer_guard(mic=mic, falante=falante, relogio=relogio)
    n = NarradorDeVoz(falar=falante.falar, mic_guard=guard)
    chamadas = []

    async def executar(action_name, **params):
        chamadas.append((action_name, params))
        return ResultadoFake(success=True, output="ok")

    resultado = asyncio.run(
        n.executar_narrada("os_app", {"app": "Excel"}, executar=executar)
    )
    assert resultado.success is True
    assert chamadas == [("os_app", {"app": "Excel"})]
    assert falante.falas and falante.falas[0] == "abrindo Excel..."
    # sucesso: sem anúncio extra de conclusão (a resposta falada cobre)
    assert len(falante.falas) == 1


def test_executar_narrada_falha_anuncia_falha():
    relogio = RelogioFake()
    mic = MicFake()
    falante = FalanteFake(relogio)
    guard, _, _, _ = fazer_guard(mic=mic, falante=falante, relogio=relogio)
    n = NarradorDeVoz(falar=falante.falar, mic_guard=guard)

    async def executar(action_name, **params):
        return ResultadoFake(success=False, output="")

    resultado = asyncio.run(
        n.executar_narrada("os_app", {"app": "Excel"}, executar=executar)
    )
    assert resultado.success is False
    assert falante.falas[-1] == "não consegui abrir Excel"


def test_executar_narrada_excecao_repropaga_e_anuncia():
    relogio = RelogioFake()
    mic = MicFake()
    falante = FalanteFake(relogio)
    guard, _, _, _ = fazer_guard(mic=mic, falante=falante, relogio=relogio)
    n = NarradorDeVoz(falar=falante.falar, mic_guard=guard)

    async def executar(action_name, **params):
        raise RuntimeError("ação explodiu")

    try:
        asyncio.run(n.executar_narrada("os_app", {"app": "Excel"}, executar=executar))
        assert False, "devia ter repropagado"
    except RuntimeError as exc:
        assert str(exc) == "ação explodiu"
    assert falante.falas[-1] == "não consegui abrir Excel"


# ---------------------------------------------------------------------------
# fiação com o pipeline real
# ---------------------------------------------------------------------------


class IPCHandlersFake:
    """Sósia mínimo do IPCHandlers p/ testar a fiação, sem importar o módulo."""

    def __init__(self, com_tts=True, com_pipeline=True, silenciada=False):
        self._silenciada = silenciada
        self.tts_manager = TTSFake() if com_tts else None
        self.voice_pipeline = PipelineFake() if com_pipeline else None


class TTSFake:
    def __init__(self):
        self.falas = []
        self._falando = False

    def speak(self, texto, blocking=True):
        self.falas.append((texto, blocking))

    def is_speaking(self):
        return self._falando


class PipelineFake:
    def __init__(self):
        self.pausas = 0
        self.retomadas = 0

    def pause_listening(self):
        self.pausas += 1

    def resume_listening(self, require_wake_word=False):
        self.retomadas += 1


def test_montar_narrador_sem_tts_devolve_none():
    assert montar_narrador_para_ipc(IPCHandlersFake(com_tts=False)) is None


def test_montar_narrador_fia_fala_mic_e_mudo():
    ipc = IPCHandlersFake()
    n = montar_narrador_para_ipc(ipc)
    assert n is not None
    asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"}))
    assert ipc.tts_manager.falas == [("abrindo Excel...", False)]
    assert ipc.voice_pipeline.pausas == 1
    assert ipc.voice_pipeline.retomadas == 1


def test_montar_narrador_respeita_silenciada():
    ipc = IPCHandlersFake(silenciada=True)
    n = montar_narrador_para_ipc(ipc)
    assert asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"})) is False
    assert ipc.tts_manager.falas == []


def test_montar_narrador_sem_pipeline_ainda_fala():
    ipc = IPCHandlersFake(com_pipeline=False)
    n = montar_narrador_para_ipc(ipc)
    assert asyncio.run(n.anunciar_inicio("os_app", {"app": "Excel"})) is True
    assert ipc.tts_manager.falas == [("abrindo Excel...", False)]


# ---------------------------------------------------------------------------
# VoicePipeline — pause/resume com contagem de referência
# ---------------------------------------------------------------------------


def _pipeline_sem_hardware():
    async def _noop(*args):
        return None

    pipe = VoicePipeline(VoiceConfig(), on_wake=_noop, on_speech=_noop)
    pipe._running = True  # sem initialize(): sem Vosk, sem microfone
    return pipe


def test_pause_resume_aninhado_nao_reabre_cedo():
    pipe = _pipeline_sem_hardware()
    pipe.pause_listening()  # narrador anuncia
    pipe.pause_listening()  # _speak_response começa junto
    assert pipe.state == "PAUSED"
    pipe.resume_listening()  # narrador terminou...
    assert pipe.state == "PAUSED"  # ...mas a resposta ainda fala
    pipe.resume_listening()  # resposta terminou
    assert pipe.state == "LISTENING"


def test_pause_sem_running_nao_faz_nada():
    pipe = VoicePipeline(VoiceConfig(), on_wake=None, on_speech=None)
    pipe.pause_listening()
    assert pipe.state == "SLEEPING"  # estado inicial, intocado
    pipe.resume_listening()
    assert pipe.state == "SLEEPING"
