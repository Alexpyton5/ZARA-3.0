import json
import sqlite3
from pathlib import Path

import pytest

from tools.zoe_team import BridgeClient, read_operation, remote_request_id


def test_bridge_unavailable_is_not_success(tmp_path):
    result = BridgeClient(tmp_path / 'missing.json').send('status', {})
    assert result['success'] is False
    assert result['code'] == 'BRIDGE_UNAVAILABLE'


@pytest.mark.parametrize('changes', [
    {'host': 'example.com'}, {'port': True}, {'port': 0},
    {'token': 'g' * 64}, {'version': 2},
])
def test_invalid_connection_cannot_send_bearer_anywhere(tmp_path, changes):
    connection = tmp_path / 'connection.json'
    connection.write_text(json.dumps(dict(host='127.0.0.1', port=1234, token='a' * 64, version=1) | changes))
    assert BridgeClient(connection).send('status', {})['success'] is False


@pytest.mark.parametrize('value', [None, [], 42, 'connection'])
def test_connection_wrong_json_shape_always_returns_controlled_json(tmp_path, value):
    connection = tmp_path / 'connection.json'
    connection.write_text(json.dumps(value))
    assert BridgeClient(connection).send('status', {})['code'] == 'BRIDGE_UNAVAILABLE'


def test_missing_operation_db_is_not_created(tmp_path):
    db = tmp_path / 'lab.db'
    result = read_operation(db, 'op-1')
    assert result['success'] is False
    assert not db.exists()


def test_operation_launch_completion_is_not_mission_completion(tmp_path):
    db = tmp_path / 'lab.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('''
        CREATE TABLE lab_admitted_operations (operation_id TEXT, request_id TEXT, command TEXT);
        CREATE TABLE lab_operation_results (operation_id TEXT, state TEXT, result_json TEXT, finished_at REAL);
        ''')
        conn.execute('INSERT INTO lab_admitted_operations VALUES (?, ?, ?)', ('op-1', 'remote-1', 'lab.v1.submit'))
        conn.execute('INSERT INTO lab_operation_results VALUES (?, ?, ?, ?)',
                     ('op-1', 'COMPLETED', json.dumps({'success': True, 'session_id': 'session-1'}), 1.0))
    result = read_operation(db, 'op-1')
    assert result['state'] == 'DISPATCHED'
    assert result['session_id'] == 'session-1'
    assert result['mission_complete'] is False
    assert read_operation(db, 'another')['success'] is False


@pytest.mark.parametrize('command,result', [
    ('lab.v1.submit', {'success': True}),
    ('lab.v1.submit', {'success': True, 'session_id': 42}),
    ('lab.v1.cancel', {'success': True, 'session_id': 'existing'}),
])
def test_dispatch_requires_submit_receipt_with_real_session_id(tmp_path, command, result):
    db = tmp_path / 'lab.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('''
        CREATE TABLE lab_admitted_operations (operation_id TEXT, request_id TEXT, command TEXT);
        CREATE TABLE lab_operation_results (operation_id TEXT, state TEXT, result_json TEXT, finished_at REAL);
        ''')
        conn.execute('INSERT INTO lab_admitted_operations VALUES (?, ?, ?)', ('op', 'remote', command))
        conn.execute('INSERT INTO lab_operation_results VALUES (?, ?, ?, ?)',
                     ('op', 'COMPLETED', json.dumps(result), 1.0))
    assert read_operation(db, 'op').get('state') != 'DISPATCHED'


def test_stable_request_id_matches_node_contract():
    assert remote_request_id('whatsapp', 'wamid.owner-1') == 'zoe-team:3b048a0c79be254ba19ca988a87a793d9ba0f04ff2003df3cd7c0b4236887bf9'


def test_remote_request_is_deduplicated_by_real_lab_ledger(tmp_path):
    from core.lab_v1.operation_ledger import OperationLedger, IdempotencyConflict
    ledger = OperationLedger(tmp_path / 'lab.db')
    request_id = remote_request_id('whatsapp', 'owner-turn-1')
    first = ledger.admit(request_id, 'lab.v1.submit', {'objective': 'revisar'}, dispatch_authorized=False)
    duplicate = ledger.admit(request_id, 'lab.v1.submit', {'objective': 'revisar'}, dispatch_authorized=False)
    assert first.operation_id == duplicate.operation_id
    assert duplicate.newly_admitted is False
    assert ledger.claim(first.operation_id) is None
    with pytest.raises(IdempotencyConflict):
        ledger.admit(request_id, 'lab.v1.submit', {'objective': 'outro'}, dispatch_authorized=False)
    ledger.authorize_dispatch(first.operation_id)
    assert ledger.claim(first.operation_id) is not None
    assert ledger.claim(first.operation_id) is None
