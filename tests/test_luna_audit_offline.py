from core.lab_v1.audit_contract import (
    build_luna_audit_task,
    is_luna_audit_intent, normalize_audit_result, quota_wait_state,
    resolve_luna_agent, resume_preserves_owner_touch, summarize_for_owner,
)
from core.lab_v1.domain import Availability, AgentProfile, RoleName


def test_natural_luna_audit_resolves_without_technical_selection():
    text = 'ZARA, peça para o Luna fazer uma auditoria em você e me explique tudo de forma simples.'
    assert is_luna_audit_intent(text)
    agent = AgentProfile('agent-luna', 'Luna', 'codex_cli', 'gpt-5.6-luna',
                         role=RoleName.MEMBER, effort='medium', capabilities=['model.text'])
    resolved = resolve_luna_agent([agent])
    assert resolved == {
        'agent_id': 'agent-luna', 'name': 'Luna', 'provider_id': 'codex_cli',
        'model': 'gpt-5.6-luna', 'effort': 'medium', 'availability': 'UNPROVEN',
    }


def test_natural_luna_resolution_does_not_infer_availability():
    assert resolve_luna_agent([{
        'id': 'luna', 'name': 'Luna', 'provider_id': 'codex_cli',
        'model': 'gpt-5.6-luna', 'archived': False,
    }])['availability'] == 'UNPROVEN'
    assert not is_luna_audit_intent('audite a ZARA')


def test_luna_audit_task_is_prepared_without_persisting_or_calling_provider():
    task = build_luna_audit_task('session-offline', {
        'agent_id': 'agent-luna', 'model': 'gpt-5.6-luna', 'effort': 'medium',
    })
    assert task['id'] == 'session-offline:luna-audit'
    assert task['assigned_agent_id'] == 'agent-luna'
    assert task['acceptance'] and task['provider_id'] == 'codex_cli'


def test_audit_result_contract_and_owner_summary_are_plain_language():
    report = normalize_audit_result({
        'areas': [
            {'area': 'mission_controller', 'status': 'WORKING', 'evidence': 'Controller offline passou nos testes.'},
            {'area': 'voice', 'status': 'NOT_PROVEN', 'evidence': 'Nao houve prova fisica nesta execucao.'},
        ],
        'main_blocker': 'A cota do provedor impede a chamada interna.',
        'can_do_today': 'Receber objetivos e preservar sessoes verificadas.',
    })
    summary = summarize_for_owner(report)
    assert 'Alex, o Luna terminou' in summary
    assert 'cota do provedor' in summary
    assert 'mission_controller' not in summary and 'SQLite' not in summary


def test_quota_is_resumable_and_owner_touch_is_preserved():
    assert quota_wait_state(Availability.QUOTA_EXHAUSTED) == 'WAITING_PROVIDER'
    assert quota_wait_state('RATE_LIMITED') == 'WAITING_PROVIDER'
    assert resume_preserves_owner_touch({'session_id': 'session_c2c62a4b0e6e', 'owner_touches': 1})
    assert not resume_preserves_owner_touch({'session_id': 'new', 'owner_touches': 0, 'create_new_mission': True})
