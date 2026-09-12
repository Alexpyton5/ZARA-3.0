"""ZARA-VOICE-FLUIDEZ-001 / ZARA-VOICE-ORDEM-001.

Regra definida por Alex em 2026-08-13:

    CONVERSA -> a voz do Gemini Live pode responder direto (fluidez).
    ACAO     -> audio do Live suprimido; o executor decide e so o resultado
                verificado e falado.
    O LLM nunca declara sucesso de uma acao por conta propria.

Estes testes existem para que "fluidez" nunca vire porta de entrada para falso
sucesso, e para que a ordem dos turnos nao regrida de novo.
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import reminder_intent
from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
from core.ipc_handlers import IPCHandler


def _handler() -> IPCHandler:
    handler = IPCHandler(AsyncMock())
    handler._append_conversation_message = AsyncMock()
    handler.send_event = AsyncMock()
    handler._process_voice_message = AsyncMock()
    return handler


# --------------------------------------------------------------------------
# Classificacao CONVERSA vs ACAO
# --------------------------------------------------------------------------

@pytest.mark.parametrize("frase", [
    "Zara, me conta uma piada",
    "Zara, quem foi Einstein?",
    "Zara, tudo bem com voce?",
    "Zara, o que voce acha disso?",
    "Zara, obrigado",
])
def test_conversa_e_autorizada_sem_liberar_audio_do_gemini(frase):
    handler = _handler()
    assert handler._voice_is_authorized_conversation(frase) is True
    assert handler._voice_can_answer_directly(frase) is False


@pytest.mark.parametrize("frase", [
    "Zara, diminua o volume",
    "Zara, abaixa o volume",
    "Zara, abre o chrome",
    "Zara, coloca o volume em 30",
    "Zara, ativa o modo noturno",
    "Zara, minimiza essa janela",
    "Zara, abre o youtube",
    "Zara, tira uma captura de tela",
    "Zara, me lembra de tomar remedio as 8",
])
def test_acao_nunca_e_respondida_direto(frase):
    assert _handler()._voice_is_authorized_conversation(frase) is False


def test_acao_nao_reconhecida_nunca_vira_conversa_livre():
    """Comando nao reconhecido nunca cai em CONVERSA livre.

    Se a classificacao tratasse "abra o powershell" como conversa, o modelo
    ficaria livre para dizer que abriu sem executar nada.
    """
    handler = _handler()
    assert handler._voice_is_authorized_conversation("Zara, abra o powershell") is False
    assert handler._voice_is_authorized_conversation("Zara, abra o regedit") is False


def test_classificador_nao_cria_lembrete(monkeypatch):
    """O sniff de lembrete e regex de proposito.

    detect_reminder_intent CRIA o lembrete. Chamar isso no classificador
    agendaria lembrete so porque Alex pronunciou a palavra.
    """
    def explode(*_args, **_kwargs):
        raise AssertionError("classificador nao pode chamar detect_reminder_intent")

    monkeypatch.setattr(reminder_intent, "detect_reminder_intent", explode)
    handler = _handler()
    assert handler._voice_is_authorized_conversation("Zara, me lembra de ligar pro medico") is False


# --------------------------------------------------------------------------
# Wake gate continua valendo ANTES de qualquer som sair
# --------------------------------------------------------------------------

def test_sem_wake_nao_responde_nem_conversa():
    assert _handler()._voice_is_authorized_conversation("conversa ao fundo na sala") is False


def test_so_a_palavra_zara_nao_gera_resposta():
    assert _handler()._voice_is_authorized_conversation("Zara") is False


def test_pare_nunca_vira_conversa():
    assert _handler()._voice_is_authorized_conversation("Zara, pare") is False


def test_eco_da_propria_voz_nunca_vira_resposta_direta():
    """Sem isto a ZARA responde ao proprio alto-falante, em voz alta.

    Com resposta direta o audio sai ANTES de _on_gemini_live_turn rodar, entao
    o guarda de eco daquele ponto chegaria tarde demais.
    """
    handler = _handler()
    handler._begin_assistant_output(
        "O livro foi ao medico porque estava com as paginas amareladas"
    )
    eco = "o livro foi ao medico porque estava com as paginas amareladas"
    assert handler._voice_is_authorized_conversation(eco) is False


def test_pergunta_legitima_apos_resposta_nao_e_confundida_com_eco():
    handler = _handler()
    handler._last_spoken_text = "Agora sao vinte e duas horas"
    assert handler._voice_is_authorized_conversation("Zara, e amanha que horas eu acordo") is True


def test_classificador_nao_arma_nem_desarma_a_janela_de_continuacao():
    """A classificação local é leitura pura do estado de wake."""
    handler = _handler()
    handler._gemini_wake_armed_until = 0.0
    handler._voice_is_authorized_conversation("Zara, me conta uma piada")
    assert handler._gemini_wake_armed_until == 0.0


# --------------------------------------------------------------------------
# Roteamento do turno no dispatcher
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turno_de_conversa_ignora_resposta_gemini_e_usa_front_brain():
    handler = _handler()
    await handler._on_gemini_live_turn(
        "Zara, tudo bem?", "Tudo otimo, Alex.", direct=True
    )
    handler._process_voice_message.assert_awaited_once_with("tudo bem?")
    assert not any("Tudo otimo, Alex." in str(call) for call in handler._append_conversation_message.await_args_list)


@pytest.mark.asyncio
async def test_turno_de_acao_continua_indo_para_o_executor():
    handler = _handler()
    await handler._on_gemini_live_turn(
        "Zara, diminua o volume", "ja diminui pra voce", direct=False
    )
    handler._process_voice_message.assert_awaited_once_with("diminua o volume")


@pytest.mark.asyncio
async def test_executor_starts_before_discarded_gemini_draft_finishes():
    routed = asyncio.Event()
    release_turn_complete = asyncio.Event()

    async def on_turn(user_text, model_text, direct):
        assert user_text == "Zara, que dia é hoje?"
        assert model_text == ""
        assert direct is False
        routed.set()

    voice = _voice(lambda _text: False)
    voice.on_turn = on_turn

    class SlowDiscardedDraft:
        async def receive(self):
            yield SimpleNamespace(server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text="Zara, que dia é hoje?")
            ))
            yield SimpleNamespace(server_content=SimpleNamespace(
                model_turn=SimpleNamespace(parts=[])
            ))
            await release_turn_complete.wait()
            yield SimpleNamespace(server_content=SimpleNamespace(turn_complete=True))
            voice._stop.set()

    receive_task = asyncio.create_task(voice._receive_loop(SlowDiscardedDraft(), sd=None))
    await asyncio.wait_for(routed.wait(), timeout=0.2)
    assert receive_task.done() is False
    assert voice.ultimo_fim_de_fala() is not None
    assert voice.ultima_transcricao_pronta() is not None
    assert voice.ultima_transcricao_pronta() >= voice.ultimo_fim_de_fala()

    release_turn_complete.set()
    await asyncio.wait_for(receive_task, timeout=0.2)


@pytest.mark.asyncio
async def test_early_executor_route_is_not_duplicated_at_turn_complete():
    on_turn = AsyncMock()
    voice = _voice(lambda _text: False)
    voice.on_turn = on_turn
    voice._input_text = "Zara, que horas são?"
    voice._turn_route_decided = True

    voice._route_executor_early()
    await asyncio.sleep(0)
    await voice._finish_turn()
    await asyncio.sleep(0)

    on_turn.assert_awaited_once_with("Zara, que horas são?", "", False)


@pytest.mark.asyncio
async def test_rascunho_do_modelo_nunca_e_falado_em_turno_de_acao():
    """O texto remoto de um turno de acao nao pode entrar no historico."""
    handler = _handler()
    await handler._on_gemini_live_turn(
        "Zara, abra o chrome", "pronto, abri o Chrome", direct=False
    )
    for call in handler._append_conversation_message.await_args_list:
        assert "abri o Chrome" not in call.args


@pytest.mark.asyncio
async def test_resposta_gemini_suprimida_nao_alimenta_guarda_de_eco():
    handler = _handler()
    await handler._on_gemini_live_turn(
        "Zara, me conta uma piada", "Por que o livro foi ao medico?", direct=True
    )
    assert handler._last_spoken_text == ""


# --------------------------------------------------------------------------
# Transporte: quando o audio pode tocar
# --------------------------------------------------------------------------

def _voice(decider=None) -> GeminiLiveVoice:
    return GeminiLiveVoice(
        GeminiLiveVoiceConfig(api_key="test"), can_answer_directly=decider
    )


def test_audio_toca_em_turno_de_conversa():
    voice = _voice(lambda _text: True)
    voice._input_text = "me conta uma piada"
    voice._decide_turn_route()
    assert voice._turn_direct is True


def test_audio_fica_mudo_em_turno_de_acao():
    voice = _voice(lambda _text: False)
    voice._input_text = "diminua o volume"
    voice._decide_turn_route()
    assert voice._turn_direct is False


def test_sem_transcricao_falha_fechada():
    voice = _voice(lambda _text: True)
    voice._input_text = ""
    voice._decide_turn_route()
    assert voice._turn_direct is False


def test_sem_predicado_falha_fechada():
    voice = _voice(None)
    voice._input_text = "me conta uma piada"
    voice._decide_turn_route()
    assert voice._turn_direct is False


def test_erro_no_predicado_falha_fechada():
    def explode(_text):
        raise RuntimeError("classificador quebrou")

    voice = _voice(explode)
    voice._input_text = "me conta uma piada"
    voice._decide_turn_route()
    assert voice._turn_direct is False


# --------------------------------------------------------------------------
# Ordem dos turnos
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nova_fala_cancela_o_turno_anterior():
    """A causa de 'ela responde uma pergunta que eu fiz antes'."""
    voice = _voice(lambda _text: False)
    started = asyncio.Event()

    async def turno_lento():
        started.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(turno_lento())
    voice._routed_turn_task = task
    await started.wait()

    voice._begin_utterance()
    await asyncio.gather(task, return_exceptions=True)

    assert task.cancelled() is True
    assert voice._routed_turn_task is None


def test_nova_fala_zera_o_roteamento_do_turno_anterior():
    voice = _voice(lambda _text: True)
    voice._turn_direct = True
    voice._turn_route_decided = True

    voice._begin_utterance()

    assert voice._turn_direct is False
    assert voice._turn_route_decided is False


@pytest.mark.asyncio
async def test_cada_fala_espera_o_proprio_evento_de_conclusao():
    """Dois pedidos concorrentes nao podem liberar um ao outro."""
    voice = _voice()
    voice._speech_queue = asyncio.Queue(maxsize=8)
    voice._task = asyncio.create_task(asyncio.sleep(30))
    try:
        primeiro = asyncio.create_task(voice.speak("primeiro", timeout=5))
        segundo = asyncio.create_task(voice.speak("segundo", timeout=5))
        await asyncio.sleep(0)

        _texto_a, evento_a = await voice._speech_queue.get()
        _texto_b, evento_b = await voice._speech_queue.get()
        assert evento_a is not evento_b

        evento_a.set()
        assert await primeiro is True
        assert segundo.done() is False
        segundo.cancel()
        await asyncio.gather(segundo, return_exceptions=True)
    finally:
        voice._task.cancel()
        await asyncio.gather(voice._task, return_exceptions=True)


# --------------------------------------------------------------------------
# Anti-loop de eco (ZARA-VOICE-ECO-002): "ela fala e se responde"
# --------------------------------------------------------------------------

def _handler_com_eco(suspeito: bool) -> IPCHandler:
    handler = _handler()
    handler.gemini_live_voice = SimpleNamespace(
        active=True, turn_echo_suspect=suspeito, interrupt_speech=AsyncMock()
    )
    handler._gemini_wake_armed_until = time.monotonic() + 12.0
    return handler


def test_fala_humana_diferente_durante_saida_usa_continuacao():
    """Temporalidade so habilita comparacao; nao bloqueia todo barge-in."""
    handler = _handler_com_eco(True)
    assert handler._voice_is_authorized_conversation("nao, quero saber de sabado") is True


def test_seguimento_depois_que_ela_para_continua_valendo():
    handler = _handler_com_eco(False)
    assert handler._voice_is_authorized_conversation("e o que mais?") is True


def test_wake_explicito_atravessa_a_propria_fala():
    """Barge-in nao pode morrer junto com o anti-eco."""
    handler = _handler_com_eco(True)
    assert handler._voice_is_authorized_conversation("Zara, e o que voce acha disso") is True


@pytest.mark.asyncio
async def test_eco_nao_chega_ao_executor():
    handler = _handler_com_eco(True)
    handler._begin_assistant_output("e por isso que o ceu e azul")
    await handler._on_gemini_live_turn("e por isso que o ceu e azul", "", direct=False)
    handler._process_voice_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_zara_pare_por_cima_da_propria_fala_ainda_interrompe():
    handler = _handler_com_eco(True)
    await handler._on_gemini_live_turn("Zara, pare", "", direct=False)
    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()


@pytest.mark.asyncio
async def test_microfone_continua_chegando_ao_gemini_enquanto_ela_fala():
    """Barge-in exige microfone full-duplex durante a saida da Kore."""
    voice = _voice(lambda _text: True)
    voice._audio_queue = asyncio.Queue(maxsize=64)
    voice._audio_out_until = time.monotonic() + 5.0

    voice._queue_audio(b"\x00\x01" * 320, 0.4)

    assert voice._audio_queue.qsize() == 1


@pytest.mark.asyncio
async def test_microfone_volta_a_passar_quando_ela_cala():
    voice = _voice(lambda _text: True)
    voice._audio_queue = asyncio.Queue(maxsize=64)
    voice._audio_out_until = 0.0

    voice._queue_audio(b"\x00\x01" * 320, 0.4)

    assert voice._audio_queue.qsize() == 1


def test_transporte_marca_eco_quando_a_fala_nasce_durante_o_audio():
    voice = _voice(lambda _text: True)
    voice._audio_out_until = time.monotonic() + 5.0
    voice._begin_utterance()
    assert voice.turn_echo_suspect is True


def test_transporte_nao_marca_eco_quando_ela_esta_calada():
    voice = _voice(lambda _text: True)
    voice._audio_out_until = 0.0
    voice._begin_utterance()
    assert voice.turn_echo_suspect is False


@pytest.mark.asyncio
async def test_barge_in_zera_o_roteamento_do_turno():
    voice = _voice(lambda _text: True)
    voice._turn_direct = True
    voice._utterance_open = True

    voice._reset_turn_state()

    assert voice._turn_direct is False
    assert voice._utterance_open is False


# --------------------------------------------------------------------------
# Self-echo com ownership + conteudo + janela temporal (TASK ...-001)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voz_da_zara_repetida_no_stt_e_ignorada_sem_criar_turno():
    on_turn = AsyncMock()
    voice = _voice(lambda _text: True)
    voice.on_turn = on_turn
    voice._mark_assistant_output_started(
        "A previsao para amanha indica chuva forte durante a manha"
    )
    voice._begin_utterance()
    voice._input_text = "a previsao para amanha indica chuva forte durante a manha"

    await voice._finish_turn()
    await asyncio.sleep(0)

    on_turn.assert_not_awaited()
    assert voice._routed_turn_task is None


@pytest.mark.asyncio
async def test_parafrase_proxima_temporalmente_compativel_e_ignorada():
    on_turn = AsyncMock()
    voice = _voice(lambda _text: True)
    voice.on_turn = on_turn
    voice._mark_assistant_output_started(
        "A previsao para amanha indica chuva forte durante a manha"
    )
    voice._begin_utterance()
    voice._input_text = "a previsao de amanha indica chuva forte pela manha"

    await voice._finish_turn()
    await asyncio.sleep(0)

    on_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_pare_durante_fala_e_aceito_e_interrompe_saida():
    handler = _handler_com_eco(True)
    handler._begin_assistant_output("A previsao para amanha e de chuva")

    await handler._on_gemini_live_turn("Zara, pare", "", direct=False)

    handler.gemini_live_voice.interrupt_speech.assert_awaited_once()
    handler._process_voice_message.assert_not_awaited()


def test_frase_humana_diferente_durante_fala_e_aceita_imediatamente():
    handler = _handler_com_eco(True)
    handler._begin_assistant_output("A previsao para amanha e de chuva")

    assert handler._voice_is_authorized_conversation("nao quero saber de sabado") is True


@pytest.mark.asyncio
async def test_eco_nao_renova_janela_de_doze_segundos():
    handler = _handler()
    handler._gemini_wake_armed_until = 123.0
    handler._begin_assistant_output("A previsao para amanha e de chuva forte")

    await handler._on_gemini_live_turn(
        "a previsao para amanha e de chuva forte", "", direct=False
    )

    assert handler._gemini_wake_armed_until == 123.0
    handler._append_conversation_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_eco_nao_cria_acao_de_pc():
    handler = _handler()
    handler._gemini_wake_armed_until = time.monotonic() + 12.0
    handler._begin_assistant_output("Abra o Chrome agora para continuar")

    await handler._on_gemini_live_turn(
        "abra o chrome agora para continuar", "", direct=False
    )

    handler._process_voice_message.assert_not_awaited()


def test_apos_fala_usuario_normal_nao_espera_a_janela_de_protecao():
    handler = _handler()
    handler._gemini_wake_armed_until = time.monotonic() + 12.0
    handler._begin_assistant_output("A previsao para amanha e de chuva")
    handler._finish_assistant_output()
    assert time.monotonic() < handler._assistant_output_protect_until

    assert handler._voice_is_authorized_conversation("nao quero saber de sabado") is True


def test_mesmo_topico_com_intencao_humana_diferente_nao_e_overfilter():
    handler = _handler()
    handler._gemini_wake_armed_until = time.monotonic() + 12.0
    handler._begin_assistant_output(
        "A previsao de sabado indica chuva forte durante a manha"
    )

    assert handler._voice_is_authorized_conversation(
        "nao, eu perguntei se sabado faz sol"
    ) is True


def test_repeticao_identica_depois_da_janela_e_fala_humana():
    handler = _handler()
    handler._gemini_wake_armed_until = time.monotonic() + 12.0
    handler._begin_assistant_output("A previsao para sabado indica chuva forte")
    handler._finish_assistant_output()
    handler._assistant_output_protect_until = 0.0
    handler._recent_assistant_outputs.clear()

    assert handler._voice_is_authorized_conversation(
        "a previsao para sabado indica chuva forte"
    ) is True


def test_overlap_de_duas_palavras_nao_e_overfilter():
    handler = _handler()
    handler._begin_assistant_output("A previsao para sabado indica chuva forte")

    assert handler._looks_like_own_echo("por que a chuva ficou forte") is False


@pytest.mark.asyncio
async def test_eco_nao_cancela_turno_anterior_valido():
    voice = _voice(lambda _text: True)
    previous = asyncio.create_task(asyncio.sleep(30))
    voice._routed_turn_task = previous
    voice._mark_assistant_output_started("Agora sao vinte e duas horas")
    voice._begin_utterance()
    voice._input_text = "agora sao vinte e duas horas"

    await voice._finish_turn()

    assert previous.cancelled() is False
    previous.cancel()
    await asyncio.gather(previous, return_exceptions=True)
