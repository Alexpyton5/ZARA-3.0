"""Durable local peer correspondence. Message text never executes code or grants authority."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / '.zara-dev' / 'zoe-wire' / 'coordination.db'
ROLES = {'codex', 'zoe'}
AUTHORITY = 'PEER_REFERENCE_ONLY'
APP_ID = 0x5A575231


class WireError(ValueError):
    """Safe error code only; never embed message text or credentials."""


def text(value, maximum, *, identifier=False):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WireError('INVALID_ARGUMENTS')
    if identifier and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', value) is None:
        raise WireError('INVALID_ARGUMENTS')
    return value


def shape(args, required, optional=()):
    if not isinstance(args, dict) or not set(required) <= set(args) or set(args) - set(required) - set(optional):
        raise WireError('INVALID_ARGUMENTS')


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class WireStore:
    def __init__(self, path=DEFAULT_DB, *, create=True):
        self.path = Path(path)
        if not create and not self.path.is_file():
            raise WireError('WIRE_NOT_CONFIGURED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if tables:
                if conn.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
                    raise WireError('WRONG_DATABASE')
                if conn.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise WireError('UNSUPPORTED_DATABASE')
            else:
                conn.execute('''CREATE TABLE messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL,
                    task_id TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
                    reply_to TEXT, fingerprint TEXT NOT NULL, created_at REAL NOT NULL,
                    acknowledged_at REAL,
                    FOREIGN KEY(reply_to) REFERENCES messages(id))''')
                conn.execute('CREATE INDEX pending_messages ON messages(recipient, acknowledged_at, sequence)')
                conn.execute('''CREATE TABLE team_requests (
                    source_ref TEXT PRIMARY KEY, message_id TEXT UNIQUE NOT NULL,
                    task_id TEXT NOT NULL, channel TEXT NOT NULL, objective TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, created_at REAL NOT NULL)''')
                conn.execute(f'PRAGMA application_id={APP_ID}')
                conn.execute('PRAGMA user_version=1')

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def message(row):
        return {key: row[key] for key in ('sequence', 'id', 'sender', 'recipient', 'task_id',
                'kind', 'body', 'reply_to', 'created_at', 'acknowledged_at')} | {'authority': AUTHORITY}

    def send(self, role, args):
        shape(args, ('message_id', 'recipient', 'task_id', 'kind', 'body'), ('reply_to',))
        client_id = text(args['message_id'], 120, identifier=True)
        task = text(args['task_id'], 128, identifier=True)
        recipient = args['recipient']
        if not isinstance(recipient, str) or recipient not in ROLES or recipient == role:
            raise WireError('INVALID_RECIPIENT')
        kind = args['kind']
        if not isinstance(kind, str) or kind not in {'question', 'answer', 'status', 'handoff'}:
            raise WireError('INVALID_KIND')
        body = text(args['body'], 4000)
        parent_id = text(args['reply_to'], 80, identifier=True) if 'reply_to' in args else None
        if kind == 'answer' and parent_id is None:
            raise WireError('INVALID_REPLY')
        message_id = 'wire:' + hashlib.sha256(compact([role, client_id]).encode('utf-8')).hexdigest()
        fingerprint = hashlib.sha256(compact(args).encode('utf-8')).hexdigest()
        with self.transaction() as conn:
            previous = conn.execute('SELECT * FROM messages WHERE id=?', (message_id,)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise WireError('ID_CONFLICT')
                return {'success': True, 'duplicate': True, 'message': self.message(previous)}
            if parent_id:
                parent = conn.execute('SELECT * FROM messages WHERE id=?', (parent_id,)).fetchone()
                if not parent or parent['recipient'] != role or parent['sender'] != recipient or parent['task_id'] != task:
                    raise WireError('INVALID_REPLY')
            if conn.execute('SELECT COUNT(*) FROM messages WHERE recipient=? AND acknowledged_at IS NULL', (recipient,)).fetchone()[0] >= 1000:
                raise WireError('QUEUE_FULL')
            conn.execute('''INSERT INTO messages
                (id,sender,recipient,task_id,kind,body,reply_to,fingerprint,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)''', (message_id,role,recipient,task,kind,body,parent_id,fingerprint,time.time()))
            row = conn.execute('SELECT * FROM messages WHERE id=?', (message_id,)).fetchone()
            return {'success': True, 'duplicate': False, 'message': self.message(row)}

    def read(self, role, args, history=False):
        shape(args, (), ('limit', 'task_id'))
        limit = args.get('limit', 10)
        if type(limit) is not int or not 1 <= limit <= 25:
            raise WireError('INVALID_ARGUMENTS')
        clause = '(sender=? OR recipient=?)' if history else 'recipient=? AND acknowledged_at IS NULL'
        params = [role, role] if history else [role]
        if 'task_id' in args:
            clause += ' AND task_id=?'; params.append(text(args['task_id'], 128, identifier=True))
        with self.transaction() as conn:
            rows = conn.execute(f'SELECT * FROM messages WHERE {clause} ORDER BY sequence {"DESC" if history else "ASC"} LIMIT ?', (*params, limit)).fetchall()
            return {'success': True, 'messages': [self.message(row) for row in rows]}

    def ack(self, role, args):
        shape(args, ('message_id',))
        message_id = text(args['message_id'], 80, identifier=True)
        with self.transaction() as conn:
            row = conn.execute('SELECT recipient FROM messages WHERE id=?', (message_id,)).fetchone()
            if not row:
                raise WireError('MESSAGE_NOT_FOUND')
            if row['recipient'] != role:
                raise WireError('WRONG_RECIPIENT')
            conn.execute('UPDATE messages SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?', (time.time(), message_id))
        return {'success': True, 'state': 'ACKNOWLEDGED', 'message_id': message_id}

    @staticmethod
    def request(row):
        from tools.zoe_team import remote_request_id
        return {'source_ref': row['source_ref'], 'task_id': row['task_id'], 'created_at': row['created_at'],
                'request_id': remote_request_id(row['channel'], row['message_id']),
                'envelope': {'message_id': row['message_id'], 'channel': row['channel'], 'objective': row['objective']}}

    def prepare_team(self, role, args):
        if role != 'zoe':
            raise WireError('WRONG_ROLE')
        shape(args, ('source_ref', 'task_id', 'channel', 'objective'))
        source = text(args['source_ref'], 120, identifier=True)
        task = text(args['task_id'], 128, identifier=True)
        objective = text(args['objective'], 4000)
        if not isinstance(args['channel'], str) or args['channel'] not in {'whatsapp', 'muse'}:
            raise WireError('INVALID_ARGUMENTS')
        fingerprint = hashlib.sha256(compact(args).encode('utf-8')).hexdigest()
        with self.transaction() as conn:
            row = conn.execute('SELECT * FROM team_requests WHERE source_ref=?', (source,)).fetchone()
            duplicate = row is not None
            if row and row['fingerprint'] != fingerprint:
                raise WireError('ID_CONFLICT')
            if not row:
                conn.execute('INSERT INTO team_requests VALUES (?,?,?,?,?,?,?)',
                    (source, 'wire-team:' + uuid.uuid4().hex, task, args['channel'], objective, fingerprint, time.time()))
                row = conn.execute('SELECT * FROM team_requests WHERE source_ref=?', (source,)).fetchone()
            return {'success': True, 'duplicate': duplicate, 'dispatched': False, **self.request(row)}

    def team_requests(self, role, args):
        shape(args, (), ('source_ref', 'task_id', 'limit'))
        limit = args.get('limit', 10)
        if type(limit) is not int or not 1 <= limit <= 25:
            raise WireError('INVALID_ARGUMENTS')
        clauses, values = [], []
        for key in ('source_ref', 'task_id'):
            if key in args:
                clauses.append(key + '=?'); values.append(text(args[key], 128 if key == 'task_id' else 120, identifier=True))
        query = 'SELECT * FROM team_requests' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY created_at DESC LIMIT ?'
        with self.transaction() as conn:
            return {'success': True, 'requests': [self.request(row) for row in conn.execute(query, (*values, limit))]}


def run_action(store, role, action, args):
    if not isinstance(role, str) or role not in ROLES:
        raise WireError('INVALID_ROLE')
    if action == 'send': result = store.send(role, args)
    elif action == 'receive': result = store.read(role, args)
    elif action == 'history': result = store.read(role, args, history=True)
    elif action == 'ack': result = store.ack(role, args)
    elif action == 'prepare_team': result = store.prepare_team(role, args)
    elif action == 'team_requests': result = store.team_requests(role, args)
    elif action in {'status', 'init'}:
        shape(args, ()); result = {'success': True, 'role': role, 'transport': 'local-durable-correspondence'}
    else: raise WireError('UNKNOWN_ACTION')
    return result | {'human_authorization_verified': False, 'peer_messages_are_reference_only': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--role', choices=sorted(ROLES), required=True)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('send', 'prepare-team'):
        subs.add_parser(name).add_argument('--stdin', action='store_true', required=True)
    for name in ('receive', 'history', 'team-requests'):
        sub = subs.add_parser(name); sub.add_argument('--limit', type=int, default=10); sub.add_argument('--task-id')
        if name == 'team-requests': sub.add_argument('--source-ref')
    subs.add_parser('ack').add_argument('--message-id', required=True)
    subs.add_parser('status')
    subs.add_parser('init')
    args = parser.parse_args()
    try:
        if args.command in ('send', 'prepare-team'):
            incoming = sys.stdin.buffer.read(65537)
            if len(incoming) > 65536: raise WireError('INPUT_TOO_LARGE')
            try: payload = json.loads(incoming.decode('utf-8'))
            except (ValueError, RecursionError): raise WireError('INVALID_JSON') from None
        elif args.command == 'ack': payload = {'message_id': args.message_id}
        elif args.command in ('status', 'init'): payload = {}
        else: payload = {key: value for key, value in vars(args).items() if key in {'limit', 'task_id', 'source_ref'} and value is not None}
        store = WireStore(args.db, create=args.command in ('init', 'send', 'prepare-team'))
        result = run_action(store, args.role, args.command.replace('-', '_'), payload)
    except WireError as error:
        result = {'success': False, 'code': str(error)}
    except (OSError, sqlite3.Error, ValueError):
        result = {'success': False, 'code': 'WIRE_UNAVAILABLE'}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
