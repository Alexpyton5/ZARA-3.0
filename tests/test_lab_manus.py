from core.lab_v1.manus import ManusWorkCell
from core.lab_v1.store import LabStore
from core.lab_v1.domain import Team, Session


def store(tmp_path):
    item = LabStore(tmp_path / 'lab.db'); item.initialize()
    item.save_team(Team('team', 'Team', 'Goal')); item.save_session(Session('session', 'team', 'Goal'))
    return item


def test_missing_credential_never_calls_remote(tmp_path):
    calls = []
    item = ManusWorkCell(store(tmp_path), credential='', transport=lambda *a: calls.append(a))
    assert item.start('session', 'Hello', cell_id='cell')['state'] == 'AUTH_REQUIRED'
    assert not calls and item.status()['models'] == []


def test_uncertain_create_is_not_replayed(tmp_path):
    calls = []
    def transport(*args):
        calls.append(args); raise TimeoutError()
    item = ManusWorkCell(store(tmp_path), credential='test-key', transport=transport)
    assert item.start('session', 'Hello', cell_id='cell')['state'] == 'UNCERTAIN'
    assert item.start('session', 'Hello', cell_id='cell')['state'] == 'UNCERTAIN'
    assert len(calls) == 1


def test_remote_stopped_and_profile_are_not_fake_completion_or_model(tmp_path):
    replies = iter([{'ok': True, 'task_id': 'remote', 'request_id': 'r1'},
        {'ok': True, 'task': {'id': 'remote', 'status': 'stopped', 'agent_profile': 'manus-1.6-lite', 'credit_usage': 4}},
        {'ok': True, 'messages': [{'type': 'assistant_message', 'assistant_message': {'content': 'Result'}},
            {'type': 'status_update', 'status_update': {'description': 'Do not persist'}}]}])
    item = ManusWorkCell(store(tmp_path), credential='test-key', transport=lambda *a: next(replies))
    item.start('session', 'Hello', cell_id='cell')
    result = item.poll('cell')
    assert result['state'] == 'STOPPED_UNVERIFIED' and result['model_reported'] is None
    assert result['profile_reported'] == 'manus-1.6-lite' and result['cost_usd'] is None
    assert result['outputs'] == ['Result']
