"""Manus API v2 cloud work cells. An agent profile is not a reported model ID.

Official contract: https://open.manus.ai/docs/v2/task.create
Remote execution is asynchronous. An uncertain create is never automatically replayed.
"""
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from core.paths import api_keys_path
from core.lab_v1.domain import CapabilityGap, new_id


class ManusWorkCell:
    def __init__(self, store, *, credential=None, transport=None):
        self.store = store
        if credential is None:
            try: configured = json.loads(api_keys_path().read_text(encoding='utf-8-sig')).get('manus_api_key', '')
            except (OSError, ValueError): configured = ''
            credential = os.environ.get('MANUS_API_KEY') or configured
        self._credential = credential
        self.transport = transport or self._http
        with store._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS lab_workcells (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), document TEXT NOT NULL)')

    def status(self):
        return {'id': 'manus', 'name': 'Manus', 'kind': 'cloud_workcell',
            'availability': 'UNKNOWN' if self._credential else 'AUTH_REQUIRED',
            'detail': 'API v2 configurada; execucao ainda precisa de prova.' if self._credential else 'Configure MANUS_API_KEY no backend para habilitar tarefas Manus.',
            'models': [], 'profiles': ['lite', 'standard', 'max']}

    def _http(self, method, route, payload=None):
        request = urllib.request.Request('https://api.manus.ai/v2/' + route,
            data=json.dumps(payload).encode() if payload is not None else None, method=method,
            headers={'x-manus-api-key': self._credential, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read(1_000_000))
        except urllib.error.HTTPError as exc:
            return {'ok': False, 'error': {'code': 'AUTH_REQUIRED' if exc.code in (401, 403) else 'HTTP_' + str(exc.code)}}

    def _save(self, doc):
        with self.store._connect() as conn:
            conn.execute('UPDATE lab_workcells SET document=? WHERE id=?', (json.dumps(doc), doc['id']))

    def read(self, cell_id):
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM lab_workcells WHERE id=?', (cell_id,)).fetchone()
        if not row: raise ValueError('Unknown work cell')
        return json.loads(row[0])

    def start(self, session_id, intent, *, cell_id, profile='lite'):
        if profile not in ('lite', 'standard', 'max') or not isinstance(intent, str) or not 1 <= len(intent.strip()) <= 12000:
            raise ValueError('Invalid work-cell request')
        if not self.store.get_session(session_id): raise ValueError('Unknown session')
        if not self._credential:
            self.store.save_capability_gap(CapabilityGap(new_id('gap'), session_id, 'manus.cloud_task',
                detail='MANUS_API_KEY ausente; nenhuma chamada externa realizada.'))
            return {'success': False, 'state': 'AUTH_REQUIRED', 'provider': 'manus'}
        doc = {'id': cell_id, 'session_id': session_id, 'provider': 'manus', 'state': 'DISPATCHED',
            'profile_requested': profile, 'profile_reported': None, 'model_requested': None, 'model_reported': None,
            'created_at': time.time(), 'remote_task_id': None, 'request_id': None, 'cost_basis': 'UNKNOWN', 'cost_usd': None}
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT document FROM lab_workcells WHERE id=?', (cell_id,)).fetchone()
            if old:
                prior = json.loads(old[0])
                if prior['session_id'] != session_id: raise ValueError('Work cell belongs to another session')
                return prior
            conn.execute('INSERT INTO lab_workcells VALUES(?,?,?)', (cell_id, session_id, json.dumps(doc)))
        try:
            reply = self.transport('POST', 'task.create', {'message': {'content': intent, 'connectors': [],
                'enable_skills': [], 'force_skills': []}, 'agent_profile': profile, 'share_visibility': 'private'})
            doc['request_id'] = reply.get('request_id')
            if reply.get('ok') is True and isinstance(reply.get('task_id'), str):
                doc.update(state='RUNNING', remote_task_id=reply['task_id'])
            else:
                doc.update(state='BLOCKED', error='MANUS_CREATE_REJECTED')
        except Exception:
            doc.update(state='UNCERTAIN', error='MANUS_CREATE_UNCERTAIN_NO_REPLAY')
        self._save(doc)
        return doc

    def poll(self, cell_id):
        doc = self.read(cell_id)
        if not self._credential or not doc.get('remote_task_id') or doc['state'] in ('COMPLETED', 'FAILED'):
            return doc
        if time.time() - doc.get('last_polled_at', 0) < 10: return doc
        doc['last_polled_at'] = time.time()
        self._save(doc)
        try:
            query = urllib.parse.urlencode({'task_id': doc['remote_task_id']})
            reply = self.transport('GET', 'task.detail?' + query)
            if not reply.get('ok'): raise ValueError('Detail unavailable')
            task = reply.get('task', {})
            if task.get('id') != doc['remote_task_id']: raise ValueError('Task identity mismatch')
            doc.update(profile_reported=task.get('agent_profile'), credit_usage=task.get('credit_usage'),
                last_request_id=reply.get('request_id'), remote_status=task.get('status'))
            state = task.get('status')
            doc['state'] = {'running': 'RUNNING', 'waiting': 'WAITING_USER', 'error': 'FAILED', 'stopped': 'STOPPED_UNVERIFIED'}.get(state, 'UNKNOWN')
            if state == 'stopped':
                messages = self.transport('GET', 'task.listMessages?' + query + '&order=desc&limit=20')
                if messages.get('ok'):
                    # Save user-facing deliverables only, excluding reasoning/tool/status event bodies.
                    doc['outputs'] = [m['assistant_message']['content'] for m in messages.get('messages', [])
                        if m.get('type') == 'assistant_message' and isinstance(m.get('assistant_message', {}).get('content'), str)]
                    doc['has_more_messages'] = bool(messages.get('has_more'))
                # Provider stopped does not independently prove the user's acceptance criterion.
            doc.pop('error', None)
        except Exception:
            doc['error'] = 'MANUS_POLL_UNAVAILABLE'
        self._save(doc)
        return doc
