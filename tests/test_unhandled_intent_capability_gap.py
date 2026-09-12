"""NIGHT-07: a recusa honesta vira CapabilityGap -- com freio, e igual nos dois canais.

O que este arquivo prova, e o que ele NAO prova
-----------------------------------------------
Prova: que `_looks_like_unhandled_local_action` disparando em VOZ
(`_process_voice_message`) e em TEXTO (`handle_send_message`) alimenta o Lab
pelo mesmo `_remember_action_failure` que ja existia, que a MESMA frase pelos
dois canais gera UM gap so, e que o teto de gasto documentado e respeitado.

Nao prova: que o comando funciona por voz no EXE do Alex. Isto e nivel TEST.

Seguranca: nenhuma action e executada. A cadeia deterministica e neutralizada
com `AsyncMock(return_value=None)` -- o mesmo padrao de
`tests/test_unified_zara_channel_capability.py` -- e o primeiro teste prova,
com o detector REAL (`detect()` e pura deteccao, nao executa nada), que a
frase escolhida de fato nao casa com nenhum padrao. Sem esse cuidado um teste
de intent nao reconhecido pode acabar mexendo no brilho da maquina do dono:
"escurece a tela do notebook secundario" casa com `os_brightness_down` e foi
descartada por isso.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.ipc_handlers import (
    UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY,
    UNHANDLED_INTENT_MAX_NEW_GAPS_PER_DAY,
    UNHANDLED_INTENT_MISSION_THRESHOLD,
    UNHANDLED_INTENT_SOURCE_PATH,
    IPCHandler,
    IPCMessage,
    _looks_like_unhandled_local_action,
)
from core.lab_v1.evolution import EvolutionEngine
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore
from core.pc_voice_intent import RESPOSTA_NAO_SEI

# A mesma lacuna, dita e digitada. Caixa e ponto final diferentes de proposito:
# e assim que STT e teclado divergem na vida real.
VOICE_PHRASE = 'minimize todas as janelas menos o chrome'
TEXT_PHRASE = 'Minimize todas as janelas menos o Chrome.'
EXPECTED_REQUIRED = 'runtime.action.unhandled_intent:' + VOICE_PHRASE


def _lab(tmp_path):
    """Servico real do Lab sobre um banco temporario. Nunca o banco do dono."""
    from core.lab_v1.providers.registry import ProviderRegistry
    from core.lab_v1.runtime import LabRuntime

    tmp_path.mkdir(parents=True, exist_ok=True)
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    runtime = LabRuntime(store, ProviderRegistry(tmp_path / 'health.json'))
    service = LabV1Service()
    service._runtime, service._store = runtime, store
    return store, service


def _handler(tmp_path):
    sent = []

    async def send(message):
        sent.append(message)

    handler = IPCHandler(send)
    handler._append_conversation_message = AsyncMock()
    handler._marcar_canal = Mock()
    handler._speak_response = AsyncMock()
    handler._enrich_with_memory = AsyncMock(side_effect=lambda text: text)
    handler._front_conversation_reply = AsyncMock(
        side_effect=AssertionError('o guarda honesto nao pode cair no modelo'))
    for name in (
        '_try_jarvis_multi_action', '_try_reminder_intent',
        '_try_operational_memory_intent', '_try_self_knowledge',
        '_try_file_intent', '_try_compound_pc_intent', '_try_pc_intent',
    ):
        setattr(handler, name, AsyncMock(return_value=None))
    store, service = _lab(tmp_path)
    handler.lab_v1 = service
    return handler, store, sent


async def _drain(handler):
    """A captura e background por contrato; o teste espera ela terminar."""
    for _ in range(20):
        pending = [task for task in handler._lab_v1_background_tasks if not task.done()]
        if not pending:
            return
        await asyncio.gather(*pending)


def _only_gap(store):
    gaps = store.list_capability_gaps()
    assert len(gaps) == 1, [gap.required for gap in gaps]
    return gaps[0], json.loads(gaps[0].detail)


# -- 0. a frase e mesmo uma lacuna real, provada no detector de producao ------

def test_the_chosen_phrase_is_really_unhandled_by_the_real_detector():
    from core.pc_voice_intent import PcVoiceIntentDetector

    result = PcVoiceIntentDetector().detect(VOICE_PHRASE)

    assert result.is_pc_intent is False, f'a frase virou {result.action}; trocar de frase'
    assert _looks_like_unhandled_local_action(VOICE_PHRASE) is True
    assert _looks_like_unhandled_local_action(TEXT_PHRASE) is True


# -- 1. paridade voz/texto ---------------------------------------------------

@pytest.mark.asyncio
async def test_text_alone_records_the_same_gap_that_voice_alone_records(tmp_path):
    """A prova dura de paridade: cada canal SOZINHO produz a mesma lacuna.

    Bancos separados de proposito. Se o teste rodasse os dois canais no mesmo
    banco, o segundo canal poderia estar mudo e o teste ainda passaria, olhando
    para a linha que o primeiro escreveu.
    """
    voice_handler, voice_store, _ = _handler(tmp_path / 'so-voz')
    text_handler, text_store, sent = _handler(tmp_path / 'so-texto')

    await voice_handler._process_voice_message(VOICE_PHRASE)
    await _drain(voice_handler)
    await text_handler.handle_send_message(IPCMessage(
        type='send-message', request_id='texto', payload={'message': TEXT_PHRASE}))
    await _drain(text_handler)

    voice_gap, voice_detail = _only_gap(voice_store)
    text_gap, text_detail = _only_gap(text_store)

    # Mesma identidade e mesmo tipo de lacuna, apesar da caixa e do ponto final.
    assert text_gap.id == voice_gap.id
    assert text_gap.required == voice_gap.required == EXPECTED_REQUIRED
    assert text_detail['stage'] == voice_detail['stage'] == 'unhandled_intent'
    assert text_detail['status'] == voice_detail['status'] == 'CAPABILITY_MISSING'
    assert text_detail['observation_kind'] == voice_detail['observation_kind']
    assert text_detail['source_path'] == voice_detail['source_path'] == ''
    # O canal continua sendo registrado como fato, e e a unica diferenca.
    assert voice_detail['channel'] == 'voice'
    assert str(voice_detail['run_id']).startswith('voice:')
    assert text_detail['channel'] == 'conversation' and text_detail['run_id'] is None
    # A resposta ao Alex continua sendo a recusa honesta, nos dois canais.
    assert voice_handler._speak_response.await_args_list[0].args[0] == RESPOSTA_NAO_SEI
    typed = next(frame.response for frame in sent if frame.request_id == 'texto')
    assert typed['response'] == RESPOSTA_NAO_SEI
    assert typed['engine'] == 'local_action_guard'
    voice_handler._front_conversation_reply.assert_not_awaited()
    text_handler._front_conversation_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_same_phrase_by_both_channels_is_one_gap_not_two(tmp_path):
    handler, store, _ = _handler(tmp_path)

    await handler._process_voice_message(VOICE_PHRASE)
    await _drain(handler)
    first, _detail = _only_gap(store)
    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='texto', payload={'message': TEXT_PHRASE}))
    await _drain(handler)

    second, detail = _only_gap(store)
    assert second.id == first.id and second.required == EXPECTED_REQUIRED
    # A segunda ocorrencia nem reescreve o gap: nada de estado mudou.
    assert detail['channel'] == 'voice'


@pytest.mark.asyncio
async def test_a_recognised_phrase_never_becomes_a_gap(tmp_path):
    """Contraprova: so a recusa vira lacuna. Acao que rodou nao e lacuna."""
    handler, store, _ = _handler(tmp_path)
    handler._try_pc_intent = AsyncMock(return_value='Volume em 30%.')

    await handler._process_voice_message('diminua o volume')
    await handler.handle_send_message(IPCMessage(
        type='send-message', request_id='ok', payload={'message': 'diminua o volume'}))
    await _drain(handler)

    assert store.list_capability_gaps() == []


# -- 2. anti-spam ------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeating_the_phrase_never_creates_a_second_gap(tmp_path):
    handler, store, _ = _handler(tmp_path)

    for _ in range(6):
        await handler._process_voice_message(VOICE_PHRASE)
    await _drain(handler)

    gap, _detail = _only_gap(store)
    assert gap.required == EXPECTED_REQUIRED


@pytest.mark.asyncio
async def test_the_gap_stays_inert_until_the_threshold(tmp_path):
    """Sem `source_path` o gap nao vira missao dirigida. Esse e o freio."""
    handler, store, _ = _handler(tmp_path)

    for occurrence in range(1, UNHANDLED_INTENT_MISSION_THRESHOLD):
        await handler._process_voice_message(VOICE_PHRASE)
        await _drain(handler)
        _gap, detail = _only_gap(store)
        assert detail['source_path'] == '', f'escalou cedo demais na ocorrencia {occurrence}'

    await handler._process_voice_message(VOICE_PHRASE)
    await _drain(handler)

    _gap, detail = _only_gap(store)
    assert detail['source_path'] == UNHANDLED_INTENT_SOURCE_PATH


def test_the_daily_escalation_ceiling_is_respected(tmp_path):
    handler, store, _ = _handler(tmp_path)

    async def drive():
        for index in range(UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY + 2):
            for _ in range(UNHANDLED_INTENT_MISSION_THRESHOLD):
                # Um drain por frase falada: cada turno da ZARA e um turno.
                handler._remember_unhandled_intent(f'ajuste o parametro numero {index}')
                await _drain(handler)

    asyncio.run(drive())

    escalated = [gap for gap in store.list_capability_gaps()
                 if json.loads(gap.detail)['source_path']]
    assert len(store.list_capability_gaps()) == UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY + 2
    assert len(escalated) == UNHANDLED_INTENT_MAX_ESCALATIONS_PER_DAY


def test_the_daily_new_gap_ceiling_is_respected(tmp_path):
    handler, store, _ = _handler(tmp_path)

    async def drive():
        for index in range(UNHANDLED_INTENT_MAX_NEW_GAPS_PER_DAY + 5):
            handler._remember_unhandled_intent(f'organize a janela numero {index}')
        await _drain(handler)

    asyncio.run(drive())

    assert len(store.list_capability_gaps()) == UNHANDLED_INTENT_MAX_NEW_GAPS_PER_DAY


def test_an_empty_phrase_is_not_a_gap(tmp_path):
    handler, store, _ = _handler(tmp_path)

    async def drive():
        handler._remember_unhandled_intent('   ...   ')
        await _drain(handler)

    asyncio.run(drive())
    assert store.list_capability_gaps() == []


# -- 3. o que o EvolutionEngine faz com o gap: no maximo UMA missao ----------

class _CountingAutopilot:
    """Conta missoes. Nenhum provider e chamado -- e esse o ponto do teste."""

    def __init__(self, store):
        from core.lab_v1.domain import Session
        self.store, self.starts, self._Session = store, [], Session

    def start(self, objective, **kwargs):
        self.starts.append((objective, kwargs))
        sid = f'mission-{len(self.starts)}'
        if self.store.get_session(sid) is None:
            self.store.save_session(self._Session(sid, 'team', objective=objective))
        return {'success': True, 'session_id': sid, 'state': 'QUEUED'}

    def run(self, sid):
        return {'success': True, 'session_id': sid, 'state': 'COMPLETED'}


def _evolution_workspace(tmp_path):
    workspace = tmp_path / 'workspace'
    target = workspace / UNHANDLED_INTENT_SOURCE_PATH
    target.parent.mkdir(parents=True)
    target.write_text('PATTERNS = []\n', encoding='utf-8')
    (workspace / 'memory').mkdir()
    return workspace


def _runtime_missions(autopilot):
    return [kwargs for _objective, kwargs in autopilot.starts
            if kwargs['evidence'].get('observation_kind') == 'RUNTIME_CAPABILITY_FAILURE']


def test_the_inert_gap_starts_no_mission_and_escalation_starts_exactly_one(tmp_path):
    from core.lab_v1.domain import Team

    handler, store, _ = _handler(tmp_path)
    store.save_team(Team('team', 'Internal'))
    workspace = _evolution_workspace(tmp_path)
    autopilot = _CountingAutopilot(store)
    engine = EvolutionEngine(SimpleNamespace(store=store), workspace,
                             autopilot=autopilot, checker=lambda source: {'conclusive': False})

    async def say(times):
        for _ in range(times):
            handler._remember_unhandled_intent(VOICE_PHRASE)
            await _drain(handler)

    # Abaixo do limiar: o gap existe, mas nenhuma missao olha para ele.
    asyncio.run(say(UNHANDLED_INTENT_MISSION_THRESHOLD - 1))
    engine.observe_and_plan()
    assert _runtime_missions(autopilot) == []

    # Cruzou o limiar: exatamente UMA missao dirigida ao arquivo do intent.
    asyncio.run(say(1))
    engine.observe_and_plan()
    missions = _runtime_missions(autopilot)
    assert len(missions) == 1
    evidence = missions[0]['evidence']
    assert missions[0]['mission_kind'] == 'SELF_IMPROVEMENT'
    assert [item['source_path'] for item in evidence['sources']] == [UNHANDLED_INTENT_SOURCE_PATH]
    assert evidence['capability_gaps'][0]['required'] == EXPECTED_REQUIRED

    # Repetir a frase depois de escalonar nao pode reabrir a missao: o
    # `observation_id` e hash do conteudo do gap, e o gap para de mudar.
    asyncio.run(say(5))
    for _ in range(3):
        engine.observe_and_plan()
    assert len(_runtime_missions(autopilot)) == 1
