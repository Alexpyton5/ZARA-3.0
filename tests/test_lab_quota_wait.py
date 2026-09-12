"""Cota esgotada e espera, nao morte da missao.

O plano mensal do dono renova em hora conhecida (horas de distancia). Tratar isso
como falha intermitente — tres tentativas com backoff de ate 15 min — matava toda
missao em ~45 min, muito antes da cota voltar. Estes testes travam o comportamento
correto: espera longa, sem consumir o orcamento de falha real.
"""
import pytest

from core.lab_v1.domain import AgentProfile, Session, Team, TeamMembership, Task
from core.lab_v1.mission_controller import (
    ExecutionScope, MissionController, MissionLimits, MissionStep, Receipt,
    TextProviderFailure, Verification,
)
from core.lab_v1.store import LabStore


class Clock:
    value = 1000.0

    def __call__(self):
        return self.value


class QuotaPorts:
    """Executor que sempre devolve cota esgotada, como o claude_cli faz."""

    def __init__(self, availability='QUOTA_EXHAUSTED'):
        self.availability = availability
        self.attempts = 0

    def execute(self, dispatch):
        self.attempts += 1
        raise TextProviderFailure(self.availability)

    def verify(self, dispatch, receipt):
        return Verification('PASS', 'evidence:test')


@pytest.fixture
def world(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.initialize()
    store.save_team(Team('team', 'Test Team'))
    store.save_agent(AgentProfile('agent', 'Worker', 'fake', 'fake'))
    store.save_membership(TeamMembership('member', 'team', 'agent'))
    store.save_session(Session('session', 'team', 'Fix a small module'))
    store.save_task(Task('task1', 'session', 'Small fix', 'Apply the patch',
                         'agent', assigned_agent_id='agent', acceptance='before fails; after passes'))
    clock = Clock()
    return store, MissionController(store, clock=clock), clock


SCOPE = ExecutionScope(("provider:fake/fake",), ("model.invoke", "model.text"),
                       authorization_state="POLICY_AUTHORIZED",
                       authorization_ref="autopilot:test")


def _plan(ctl):
    ctl.plan('session', [MissionStep('one', 'task1', 'INVOKE', capability='model.text', resources=('provider:fake/fake',))],
             MissionLimits(), scope=SCOPE)


def _step(ctl):
    return ctl.snapshot('session')  # snapshot exposto; estado detalhado lido abaixo


def _doc(ctl):
    with ctl._transaction() as conn:
        doc, _ = ctl._load(conn, 'session')
    return doc


def test_cota_esgotada_nao_mata_a_missao(world):
    store, ctl, clock = world
    _plan(ctl)
    ports = QuotaPorts()
    for _ in range(6):
        ctl.tick('session', ports)
        doc = _doc(ctl)
        if doc['state'] == 'WAITING_RESOURCE':
            clock.value += 4000  # deixa o backoff vencer
            ctl.resume_due_resource('session')
    doc = _doc(ctl)
    assert doc['blocker'] != 'RESOURCE_RETRY_LIMIT', (
        'cota esgotada nao pode matar a missao: ' + str(doc.get('blocker')))
    assert doc['state'] != 'BLOCKED_NEEDS_OWNER'


def test_cota_nao_consome_orcamento_de_falha_real(world):
    store, ctl, clock = world
    _plan(ctl)
    ports = QuotaPorts()
    ctl.tick('session', ports)
    doc = _doc(ctl)
    step = doc['steps'][0]
    assert step.get('quota_waits', 0) >= 1, 'espera de cota deve ter contador proprio'
    assert step.get('resource_failures', 0) == 0, 'cota nao pode contar como falha de recurso'
    assert doc['used']['retries'] == 0, 'cota nao pode consumir o orcamento de retry'


def test_espera_de_cota_e_longa_nao_quinze_minutos(world):
    store, ctl, clock = world
    _plan(ctl)
    ctl.tick('session', QuotaPorts())
    doc = _doc(ctl)
    espera = doc['steps'][0]['retry_at'] - clock.value
    assert espera >= 300, f'espera curta demais para cota: {espera}s'


def test_falha_real_de_provedor_continua_limitada(world):
    """Erro que nao e cota continua morrendo depois de poucas tentativas."""
    store, ctl, clock = world
    _plan(ctl)
    ports = QuotaPorts(availability='PROVIDER_ERROR')
    for _ in range(8):
        ctl.tick('session', ports)
        doc = _doc(ctl)
        if doc['state'] in ('WAITING_RESOURCE', 'RUNNING'):
            clock.value += 4000
            ctl.resume_due_resource('session')
        if doc['state'] == 'BLOCKED_NEEDS_OWNER':
            break
    doc = _doc(ctl)
    assert doc['steps'][0].get('resource_failures', 0) >= 1, (
        'erro real de provedor deve contar como falha de recurso')
