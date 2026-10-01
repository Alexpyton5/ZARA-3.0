"""Zoe forwards Alex's original WhatsApp request to the existing durable Lab.

CLI/stdin JSON only: never interpolate a WhatsApp message into a shell command.
The receiver authenticates the existing Zoe bridge, not the WhatsApp sender.
Zoe must verify that the original request is from Alex before calling start.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


def runtime_directory() -> Path:
    return Path(os.environ.get('ZARA3_HOME') or
                Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'ZARA3')


def remote_request_id(channel: str, message_id: str) -> str:
    content = json.dumps([channel, message_id], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return 'zoe-team:' + hashlib.sha256(content).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BridgeClient:
    def __init__(self, connection: Path | None = None):
        self.connection = connection or runtime_directory() / 'zoe_bridge' / 'connection.json'

    def send(self, kind: str, payload: dict) -> dict:
        try:
            connection = json.loads(self.connection.read_text(encoding='utf-8'))
            if not isinstance(connection, dict):
                raise ValueError('invalid bridge connection')
            port, token = connection.get('port'), connection.get('token')
            if (connection.get('host') != '127.0.0.1' or connection.get('version') != 1
                    or type(port) is not int or not 1 <= port <= 65535
                    or not isinstance(token, str) or re.fullmatch('[0-9a-f]{64}', token) is None):
                raise ValueError('invalid bridge connection')
            body = json.dumps({'type': kind, 'payload': payload}, ensure_ascii=False).encode('utf-8')
            if len(body) > 32 * 1024:
                raise ValueError('request too large')
            request = Request(f'http://127.0.0.1:{port}/v1/command', data=body,
                              headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=200) as response:
                result = json.loads(response.read(4 * 1024 * 1024).decode('utf-8'))
            if not isinstance(result, dict):
                raise ValueError('invalid bridge reply')
            return result
        except (OSError, ValueError, URLError, HTTPError, KeyError):
            # Never include token, network exception text, or untrusted payload.
            return {'success': False, 'code': 'BRIDGE_UNAVAILABLE',
                    'error': 'Ponte indisponível; a ordem não foi confirmada. Use o mesmo ID ao tentar novamente.'}


def read_operation(db: Path, operation_id: str | None = None, *, request_id: str | None = None) -> dict:
    """Read a persisted receipt without opening/creating/migrating a writable DB."""
    try:
        identity = operation_id if operation_id is not None else request_id
        if (not db.is_file() or (operation_id is not None and request_id is not None)
                or not isinstance(identity, str) or not identity or len(identity) > 160):
            raise ValueError('missing receipt')
        column = 'operation_id' if operation_id is not None else 'request_id'
        with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('''SELECT a.operation_id, a.request_id, a.command,
                r.state, r.result_json, r.finished_at
                FROM lab_admitted_operations a
                LEFT JOIN lab_operation_results r ON r.operation_id=a.operation_id
                WHERE a.''' + column + '=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('missing receipt')
        result = json.loads(row['result_json']) if row['result_json'] else None
        state = original_state = row['state'] or 'PENDING'
        session_id = None
        if isinstance(result, dict):
            session_id = result.get('session_id') or (result.get('mission') or {}).get('session_id')
        launch_succeeded = (row['command'] == 'lab.v1.submit' and state == 'COMPLETED'
                            and isinstance(result, dict) and result.get('success') is True
                            and isinstance(session_id, str) and bool(session_id.strip()))
        if not launch_succeeded and state == 'COMPLETED':
            state = 'OUTCOME_UNVERIFIED'
        return {'success': True, 'operation_id': row['operation_id'], 'request_id': row['request_id'],
                'state': 'DISPATCHED' if launch_succeeded else state, 'operation_state': original_state,
                'session_id': session_id, 'result': result, 'finished_at': row['finished_at'],
                'mission_complete': False,
                'hint': 'DISPATCHED confirma início. Consulte snapshot da sessão para execução/entrega.'}
    except (OSError, ValueError, sqlite3.Error, TypeError, AttributeError):
        return {'success': False, 'code': 'RECEIPT_NOT_AVAILABLE', 'mission_complete': False}


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    start.add_argument('--stdin', action='store_true', required=True, help='JSON: message_id, channel, objective')
    receipt = sub.add_parser('receipt')
    identity = receipt.add_mutually_exclusive_group(required=True)
    identity.add_argument('--operation-id')
    identity.add_argument('--request-id', help='Recupere o recibo mesmo se o ACK HTTP se perdeu.')
    receipt.add_argument('--db', type=Path)
    snapshot = sub.add_parser('snapshot')
    snapshot.add_argument('--session-id')
    sub.add_parser('status')
    args = parser.parse_args()
    client = BridgeClient(args.connection)
    if args.command == 'start':
        try:
            payload = json.loads(sys.stdin.read(32 * 1024 + 1))
            if not isinstance(payload, dict) or set(payload) != {'message_id', 'channel', 'objective'}:
                raise ValueError('invalid mission envelope')
            result = client.send('zoe-remote-command', dict(payload, kind='team-mission'))
        except (ValueError, TypeError):
            result = {'success': False, 'code': 'INVALID_REMOTE_MISSION'}
    elif args.command == 'receipt':
        result = read_operation(args.db or runtime_directory() / 'data' / 'lab' / 'zara_lab_v1.db', args.operation_id, request_id=args.request_id)
    else:
        payload = {'session_id': args.session_id} if args.command == 'snapshot' and args.session_id else {}
        result = client.send('lab-v1-snapshot' if args.command == 'snapshot' else 'status', payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('success') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
