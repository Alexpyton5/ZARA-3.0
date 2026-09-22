"""Front conversation policy against real Lab persistence and fake text transport."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.front_brain import FrontBrain, BRAINS, DEFAULT_BRAIN


class FrontFake(ProviderAdapter):
    id = 'codex_cli'
    label = 'fixture'
    controlled_text_only = True
    declared_models = tuple(ModelDescriptor('codex_cli', model, name, supports_effort=True,
                                           effort_levels=('low', 'high')) for model, name in BRAINS.items())

    def __init__(self):
        self.calls = []
        self.answer = ProviderResult(True, text='Resposta real do transporte de teste', availability=Availability.AVAILABLE)
        self.hold = None
        self.entered = threading.Event()

    def probe(self):
        return ProviderInfo(self.id, self.label, 'fixture', Availability.AVAILABLE)

    def complete(self, **kwargs):
        return self.complete_with_options(**kwargs)

    def complete_with_options(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        if self.hold:
            assert self.hold.wait(10)
        return self.answer


@pytest.fixture
def front(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    adapter = FrontFake()
    registry = ProviderRegistry(health_path=tmp_path / 'health.json')
    registry.register(adapter)
    for model, name in BRAINS.items():
        registry.record_result(adapter.id, model, adapter.answer)
        store.save_agent(AgentProfile('front-test-' + name, name, adapter.id, model,
                                     role=RoleName.MEMBER, capabilities=['model.text'], effort='low'))
    runtime = LabRuntime(store, registry)
    return FrontBrain(runtime), runtime, adapter


def test_default_and_selection_survive_restart_without_new_session(front):
    brain, runtime, adapter = front
    assert brain.snapshot()['current'] == DEFAULT_BRAIN
    first = brain.reply('Meu projeto se chama Horizonte.')
    assert first['success'] and adapter.calls[-1]['model'] == DEFAULT_BRAIN
    assert brain.select('gpt-6-astra')['success']
    restarted = FrontBrain(LabRuntime(runtime.store, runtime.registry))
    assert restarted.snapshot()['current'] == 'gpt-6-astra'
    second = restarted.reply('Qual e o nome do projeto?')
    assert second['session_id'] == first['session_id']
    assert 'Horizonte' in adapter.calls[-1]['prompt']
    assert adapter.calls[-1]['model'] == 'gpt-6-astra'
    assert len(runtime.store.list_runs(first['session_id'])) == 2


def test_discovered_authenticated_model_can_make_its_first_proving_call(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    adapter = FrontFake()
    registry = ProviderRegistry(health_path=tmp_path / 'health.json')
    registry.register(adapter)
    store.save_agent(AgentProfile('front-first', 'Luna', adapter.id, DEFAULT_BRAIN,
                                  role=RoleName.MEMBER, capabilities=['model.text'], effort='low'))
    brain = FrontBrain(LabRuntime(store, registry))

    # No prior provider result exists, so the generic evidence projection is
    # DISCOVERED_UNPROVEN. The front channel must still allow the first real
    # invocation, whose receipt becomes the proof.
    assert registry.model_status(adapter.id, DEFAULT_BRAIN)['availability'] == 'DISCOVERED_UNPROVEN'
    assert brain.snapshot()['engines'][0]['status'] == 'AVAILABLE'
    result = brain.reply('Oi')
    assert result['success'] is True
    assert len(adapter.calls) == 1


def test_home_history_supplements_instead_of_replacing_persistent_history(front):
    brain, _, adapter = front
    assert brain.reply('Marcador persistente LAB-HISTORY')['success']
    assert brain.reply('Continue', history=[
        {'role': 'user', 'content': 'Marcador local HOME-HISTORY'},
    ])['success']
    prompt = adapter.calls[-1]['prompt']
    assert 'LAB-HISTORY' in prompt
    assert 'HOME-HISTORY' in prompt


def test_success_returns_factual_run_provenance_without_inventing_reported_model(front):
    brain, runtime, _ = front
    result = brain.reply('Ola')
    run = runtime.store.list_runs(result['session_id'])[-1]
    assert result['success']
    assert result['run_id'] == run.id
    assert result['model_requested'] == run.model == DEFAULT_BRAIN
    assert result['model_reported'] is None
    assert result['provider'] == run.provider_id == 'codex_cli'
    assert result['provenance_status'] == 'UNREPORTED'


def test_reported_model_and_mismatch_remain_factual(front):
    brain, runtime, adapter = front
    adapter.answer = ProviderResult(True, text='Astra respondeu', availability=Availability.AVAILABLE,
                                    model_reported='gpt-6-astra')
    assert brain.select('gpt-6-astra')['success']
    matched = brain.reply('Ola Astra')
    assert matched['model_requested'] == matched['model_reported'] == 'gpt-6-astra'
    assert matched['provenance_status'] == 'MATCHED'

    adapter.answer = ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE,
                                    error='CODEX_MODEL_MISMATCH', model_reported='gpt-5.6-sol')
    mismatch = brain.reply('Nao aceite reroute')
    persisted = runtime.store.list_runs(mismatch['session_id'])[-1]
    assert mismatch['success'] is False and mismatch['code'] == 'CODEX_MODEL_MISMATCH'
    assert mismatch['run_id'] == persisted.id
    assert mismatch['model_requested'] == persisted.model == 'gpt-6-astra'
    assert mismatch['model_reported'] == persisted.model_reported == 'gpt-5.6-sol'
    assert mismatch['provenance_status'] == 'MISMATCH_REJECTED'


def test_payload_cannot_silently_select_premium(front):
    brain, _, adapter = front
    result = brain.reply('Ola', requested_model='gpt-6-astra')
    assert not result['success'] and result['code'] == 'FRONT_SELECTION_CHANGED'
    assert adapter.calls == []
    assert brain.snapshot()['current'] == DEFAULT_BRAIN


def test_unavailable_and_quota_never_fall_back(front):
    brain, runtime, adapter = front
    adapter.answer = ProviderResult(False, availability=Availability.QUOTA_EXHAUSTED, error='limit')
    assert not brain.reply('Ola')['success']
    assert len(adapter.calls) == 1
    assert brain.snapshot()['current'] == DEFAULT_BRAIN
    assert not brain.reply('Tente outra vez')['success']
    assert len(adapter.calls) == 1
    assert not brain.select('gpt-6-astra')['success']
    assert not brain.select('claude')['success']


def test_selection_and_concurrent_turn_cannot_cross_inflight_turn(front):
    brain, runtime, adapter = front
    adapter.hold = threading.Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(brain.reply, 'Primeira')
        assert adapter.entered.wait(10)
        other = FrontBrain(LabRuntime(runtime.store, runtime.registry))
        try:
            assert not other.reply('Segunda')['success']
            assert not other.select('gpt-6-astra')['success']
            assert len(adapter.calls) == 1
        finally:
            adapter.hold.set()
        assert future.result()['success']


def test_interrupted_authority_does_not_replay(front):
    brain, runtime, adapter = front
    session_id = brain.reply('Primeira')['session_id']
    assert runtime.store.claim_v1(session_id, 'interrupted-token') is None
    restarted = FrontBrain(LabRuntime(runtime.store, runtime.registry))
    assert not restarted.reply('Nao repetir')['success']
    assert len(adapter.calls) == 1


def test_context_uses_recent_turns_and_size_is_bounded(front):
    brain, _, adapter = front
    for i in range(24):
        assert brain.reply(f'MARCADOR_{i:03d} ' + ('x' * 1800))['success']
    assert brain.reply('Qual foi o mais recente?')['success']
    prompt = adapter.calls[-1]['prompt']
    assert 'MARCADOR_023' in prompt and 'MARCADOR_000' not in prompt
    assert len(prompt) <= 40000
    assert not brain.reply('x' * 12001)['success']
