"""Persistent opt-in supervisor. Sequential ticks resume work and inspect reviewed improvements."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from core.lab_v1.autopilot import (Autopilot, WORKFLOW, _is_transient_extraction,
    resolve_lab_source_checkout)
from core.lab_v1.evolution import EvolutionEngine
from core.lab_v1.workforce_policy import WorkforcePolicy
from core.lab_v1.scout import TechnologyScout
from core.lab_v1.feedback_inbox import FeedbackInbox
from core.lab_v1.mission_controller import MissionController
from core.lab_v1.research_pipeline import ResearchPipeline


_PROCESS_INSTANCE = uuid.uuid4().hex


def _pid_is_alive(pid):
    """Best-effort liveness check used only to reclaim a crashed gate owner."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        # On Windows ``os.kill(pid, 0)`` is not a harmless existence probe: it
        # can terminate the target process. Query the process handle instead.
        import ctypes
        from ctypes import wintypes
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                        and exit_code.value == still_active)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class _CrossProcessGate:
    """A non-reentrant scheduler gate persisted atomically in the Lab DB.

    The previous ``threading.Lock`` prevented overlap only inside one Python
    process.  Desktop restarts and duplicate packaged processes use the same
    database, so ownership must be visible there as well.  A crashed owner is
    reclaimed by PID; the per-process nonce also handles PID reuse.
    """

    _NAME = 'autonomy_scheduler'

    def __init__(self, store):
        self.store = store
        self._token = None
        self._state_lock = threading.Lock()
        with self.store._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS lab_supervisor_gate(
                name TEXT PRIMARY KEY, owner_pid INTEGER NOT NULL,
                owner_token TEXT NOT NULL, acquired_at REAL NOT NULL)''')

    @staticmethod
    def _belongs_to_this_process(token, pid):
        return str(token).startswith(f'{pid}:{_PROCESS_INSTANCE}:')

    def acquire(self, blocking=True, timeout=-1):
        deadline = None if timeout is None or timeout < 0 else time.monotonic() + timeout
        while True:
            pid = os.getpid()
            token = f'{pid}:{_PROCESS_INSTANCE}:{uuid.uuid4().hex}'
            acquired = False
            with self._state_lock:
                if self._token is None:
                    with self.store._connect() as conn:
                        conn.execute('BEGIN IMMEDIATE')
                        row = conn.execute(
                            'SELECT owner_pid,owner_token FROM lab_supervisor_gate WHERE name=?',
                            (self._NAME,)).fetchone()
                        stale = (row is not None and (
                            not _pid_is_alive(int(row['owner_pid']))
                            or (int(row['owner_pid']) == pid
                                and not self._belongs_to_this_process(row['owner_token'], pid))))
                        if stale:
                            conn.execute('DELETE FROM lab_supervisor_gate WHERE name=?',
                                         (self._NAME,))
                            row = None
                        if row is None:
                            conn.execute('INSERT INTO lab_supervisor_gate VALUES(?,?,?,?)',
                                         (self._NAME, pid, token, time.time()))
                            self._token = token
                            acquired = True
            if acquired:
                return True
            if not blocking or (deadline is not None and time.monotonic() >= deadline):
                return False
            time.sleep(0.01)

    def release(self):
        with self._state_lock:
            token = self._token
            if token is None:
                raise RuntimeError('release unlocked supervisor gate')
            with self.store._connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                deleted = conn.execute(
                    'DELETE FROM lab_supervisor_gate WHERE name=? AND owner_token=?',
                    (self._NAME, token)).rowcount
            self._token = None
            if deleted != 1:
                raise RuntimeError('supervisor gate ownership was lost')

    def locked(self):
        with self.store._connect() as conn:
            row = conn.execute(
                'SELECT owner_pid,owner_token FROM lab_supervisor_gate WHERE name=?',
                (self._NAME,)).fetchone()
        if row is None:
            return False
        pid = int(row['owner_pid'])
        return (_pid_is_alive(pid)
                and not (pid == os.getpid()
                         and not self._belongs_to_this_process(row['owner_token'], pid)))


class AutonomySupervisor:
    SUPPORTED_WORKFLOWS = frozenset({WORKFLOW})

    def __init__(self, runtime, *, autopilot=None):
        self.runtime, self.store = runtime, runtime.store
        self.autopilot = autopilot
        # One resident observer/one canonical Autopilot per supervisor.  A
        # background resume reuses these objects; it never starts a parallel
        # mission engine merely because the timer was restarted.
        self._evolution = None
        # The resident supervisor reads mission state even before the first
        # owner mission exists.  Run the canonical, idempotent controller
        # migration here so a clean database and an older database both expose
        # the schema that ``tick`` consumes.
        self.controller = MissionController(self.store)
        self.lock = _CrossProcessGate(self.store)
        with self.store._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS lab_autonomy_policy(id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
            defaults = WorkforcePolicy.default_document() | {
                'enabled': True, 'workspace': str(Path(__file__).resolve().parents[2]),
                'last_tick': None, 'last_state': 'READY',
                'next_evolution_check': 0, 'cadence_seconds': 60, 'evolution_cadence_seconds': 86400,
                'max_new_evolution_missions_per_day': 1, 'daily_date': None, 'daily_missions': 0,
                'stale_legacy_sessions': [], 'source_observer': None,
                'research_daily_budget': 2,
                'evidence_validity_seconds': 604800.0,
                'daily_operation_backoff_base_seconds': 900.0,
                'daily_operation_backoff_max_seconds': 21600.0}
            conn.execute('INSERT OR IGNORE INTO lab_autonomy_policy VALUES(1,?)', (json.dumps(defaults),))
            current = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
            merged = self._normalize_workspace(defaults | current)
            conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1', (json.dumps(merged),))
            conn.execute('''CREATE TABLE IF NOT EXISTS lab_autonomy_operations(
                id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('ADMITTED','SUPERSEDED')),
                document TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL)''')

    def set_autopilot(self, autopilot):
        if self.autopilot is not None and self.autopilot is not autopilot:
            raise ValueError('Supervisor already owns a different Autopilot')
        self.autopilot = autopilot

    def _engine(self, workforce=None):
        if self.autopilot is None:
            self.autopilot = Autopilot(self.runtime, policy=workforce or WorkforcePolicy(self.policy()))
        return self.autopilot

    def _evolution_engine(self, workforce, workspace):
        target = Path(workspace).resolve()
        current = getattr(self._evolution, 'workspace', target) if self._evolution is not None else None
        if self._evolution is None or current != target:
            self._evolution = EvolutionEngine(self.runtime, workspace, policy=workforce,
                                               autopilot=self.autopilot)
        elif getattr(self._evolution, 'autopilot', None) is None and self.autopilot is not None:
            self._evolution.autopilot = self.autopilot
        return self._evolution

    def record_background_error(self, detail):
        return self._save(last_state='FAILED', error='BACKGROUND_TASK_EXCEPTION', error_detail=str(detail))

    @staticmethod
    def _normalize_workspace(value):
        """Migrate only transient extraction paths, retaining owner policy fields."""
        configured = value.get('workspace')
        source = resolve_lab_source_checkout(configured)
        if source is None:
            value['last_state'] = 'WORKSPACE_NOT_CONFIGURED'
            value['error'] = 'WORKSPACE_NOT_CONFIGURED'
            value['error_detail'] = 'Persistent ZARA source checkout unavailable'
        else:
            if configured and _is_transient_extraction(Path(configured)):
                value['workspace'] = str(source)
            if value.get('error') == 'WORKSPACE_NOT_CONFIGURED':
                value['error'] = None
                value['error_detail'] = None
                if value.get('last_state') == 'WORKSPACE_NOT_CONFIGURED':
                    value['last_state'] = 'READY'
        return value

    def policy(self):
        with self.store._connect() as conn:
            value = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
            normalized = self._normalize_workspace(dict(value))
            if normalized != value:
                conn.execute('BEGIN IMMEDIATE')
                value = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
                normalized = self._normalize_workspace(dict(value))
                if normalized != value:
                    conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1',
                                 (json.dumps(normalized),))
            return normalized

    def _save(self, **changes):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            value = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
            value.update(changes)
            self._normalize_workspace(value)
            conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1', (json.dumps(value),))
        return value

    def _ledger_event(self, event_id, event_type, *, operation_id=None,
                      session_id=None, payload=None):
        """Append one replay-safe audit event to the existing Lab stream."""
        with self.store._connect() as conn:
            existing = conn.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone()
        if existing:
            return False
        from core.lab_v1.domain import LabEvent, now
        target = session_id or operation_id or event_id
        try:
            self.store.append_event(LabEvent(
                event_id, 0, event_type, target, operation_id,
                dict(payload or {}), now()))
        except Exception:
            with self.store._connect() as conn:
                existing = conn.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone()
            if existing:
                return False
            raise
        return True

    @staticmethod
    def _ledger_id(prefix, value):
        digest = hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:24]
        return f'{prefix}:{digest}'

    def _record_admission(self, state, evidence_id, source, *, operation=None,
                          detail=None):
        operation_id = (operation or {}).get('id')
        identity = f'{evidence_id}|{source}|{state}|{operation_id or "none"}'
        event_id = self._ledger_id('autonomy-admission', identity)
        self._ledger_event(event_id, 'autonomy.admission', operation_id=operation_id,
                           session_id=(operation or {}).get('session_id'), payload={
                               'state': state, 'evidence_id': evidence_id,
                               'evidence_source': source, 'operation_id': operation_id,
                               'detail': detail or {},
                           })
        return event_id

    def _record_operation_stage(self, operation, stage, *, state, payload=None):
        operation_id = operation.get('id')
        session_id = operation.get('session_id') or operation.get('mission_id')
        event_id = self._ledger_id('autonomy-stage', f'{operation_id}|{stage}|{state}')
        self._ledger_event(event_id, f'autonomy.{stage}', operation_id=operation_id,
                           session_id=session_id, payload={
                               'operation_id': operation_id, 'session_id': session_id,
                               'mission_id': operation.get('mission_id') or session_id,
                               'team_id': operation.get('team_id'), 'state': state,
                               **(payload or {}),
                           })
        return event_id

    def configure(self, *, enabled, workspace=None):
        if type(enabled) is not bool: raise ValueError('enabled must be boolean')
        saved = self.policy()
        configured = workspace or saved.get('workspace')
        source = resolve_lab_source_checkout(configured)
        if enabled and source is None:
            raise ValueError('WORKSPACE_NOT_CONFIGURED')
        target = source or Path(configured or '').resolve()
        if enabled and not (target / 'tools/build_current.py').is_file():
            raise ValueError('Workspace de manutencao nao configurado')
        return self._save(enabled=enabled, workspace=str(target) if enabled else saved.get('workspace'),
            last_state='READY' if enabled else 'MONITORING', background_enabled=True)

    def ensure_team(self):
        # A clean Lab database has no team yet.  The runtime owns the canonical
        # idempotent bootstrap; selection below must never mistake that empty
        # initial state for an unavailable workforce.
        self.runtime.ensure_core_team()
        return self._engine(WorkforcePolicy(self.policy()))._team()[0]

    def queue_research_event(self, question, *, event_id=None, observed_at=None):
        """Accept an event research request through this supervisor only.

        Admission is local and persistent; it deliberately does not invoke an
        agent, web tool, or provider.
        """
        policy = self.policy()
        if not bool(policy.get('background_enabled', True)):
            result = {'state': 'PAUSED', 'queued': False, 'event_id': event_id}
            self._ledger_event(
                self._ledger_id('research-admission', event_id or question),
                'autonomy.admission', payload={
                    'kind': 'RESEARCH_EVENT', 'event_id': event_id,
                    'state': 'PAUSED', 'queued': False,
                })
            return result
        pipeline = ResearchPipeline(self.store)
        # An event id is the admission identity.  A retried event may carry a
        # revised question, but it must never fork a second intake or spend a
        # second daily slot.  The pipeline's question hash remains the
        # canonical content dedup for callers that have no event id.
        if event_id:
            with self.store._connect() as conn:
                rows = conn.execute(
                    'SELECT id,document FROM lab_research_intakes ORDER BY created_at ASC'
                ).fetchall()
            for row in rows:
                try:
                    document = json.loads(row['document'])
                except (TypeError, ValueError):
                    continue
                if document.get('event_id') == str(event_id).strip():
                    existing = pipeline.get_intake(row['id']) or {}
                    result = {**existing, 'state': 'DUPLICATE',
                              'deduplicated_by': 'EVENT_ID', 'event_id': event_id}
                    self._ledger_event(
                        self._ledger_id('research-admission', event_id),
                        'autonomy.admission', operation_id=existing.get('id'),
                        payload={'kind': 'RESEARCH_EVENT', 'event_id': event_id,
                                 'state': 'DUPLICATE', 'queued': False})
                    return result
        result = pipeline.admit_intake(
            question, trigger='EVENT', event_id=event_id, observed_at=observed_at,
            daily_budget=policy['research_daily_budget'])
        self._ledger_event(
            self._ledger_id('research-admission', event_id or result.get('id') or question),
            'autonomy.admission', operation_id=result.get('id'), payload={
                'kind': 'RESEARCH_EVENT', 'event_id': event_id,
                'state': result.get('state'), 'queued': result.get('state') == 'QUEUED',
            })
        return result

    @staticmethod
    def _feedback_source_path(text):
        value = str(text or '').casefold()
        voice = ('voz', 'áudio', 'audio', 'microfone', 'wake word', 'kore')
        latency = ('latência', 'latencia', 'lento', 'lenta', 'demora')
        if any(word in value for word in voice):
            return 'core/gemini_live_voice.py'
        choices = (
            (latency, 'core/model_router.py'),
            (('supervisor', 'autonomia', 'automática', 'automatica'), 'core/lab_v1/supervisor.py'),
            (('serviço', 'servico', 'interface', 'envio'), 'core/lab_v1/service.py'),
        )
        return next((path for words, path in choices if any(word in value for word in words)), None)

    @staticmethod
    def _proposal_only(text):
        value = str(text or '').casefold()
        return any(word in value for word in (
            'proposta', 'sugestão', 'sugestao', 'ideia', 'avalie', 'estude', 'pesquise'))

    # ------------------------------------------------------------------
    # Daily autonomy operations (Astra Fase 8): dedup, owner priority,
    # backoff, evidence validity and the persistent budget are ONE
    # admission layer over the existing supervisor/ledger path. Every
    # daily event (feedback, failure, research request, change
    # opportunity) is admitted here and deduplicated by its evidence
    # identity; the budget it spends is persisted with the operation, so
    # a restart resumes the same budget instead of spending twice. This
    # layer never reaches an agent, a web tool or a provider.
    # ------------------------------------------------------------------

    _OPERATIONS_TABLE = 'lab_autonomy_operations'
    _DEFAULT_EVIDENCE_VALIDITY_SECONDS = 604800.0
    _DEFAULT_BACKOFF_BASE_SECONDS = 900.0
    _DEFAULT_BACKOFF_MAX_SECONDS = 21600.0

    @staticmethod
    def _operation_id(evidence_id, cycle):
        digest = hashlib.sha256(f'{evidence_id}:{cycle}'.encode('utf-8')).hexdigest()[:20]
        return f'daily-op:{digest}'

    @staticmethod
    def _operation_identity(evidence):
        # Stable identity of one daily event: its evidence id plus source.
        if not isinstance(evidence, dict):
            raise ValueError('EVIDENCE_MUST_BE_DICT')
        evidence_id = str(evidence.get('id') or evidence.get('event_id') or '').strip()
        if not evidence_id:
            content = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            evidence_id = 'content:' + hashlib.sha256(content.encode('utf-8')).hexdigest()[:20]
        source = str(evidence.get('source') or evidence.get('source_path')
                     or evidence.get('channel') or '').strip()
        return evidence_id, (source or 'unattributed')

    def _operation_document(self, evidence, evidence_id, source, cycle, linked_to, stamp, policy):
        day = time.strftime('%Y-%m-%d', time.localtime(stamp))
        return {
            'evidence_id': evidence_id, 'evidence_source': source,
            'kind': str(evidence.get('kind') or 'DAILY_OPPORTUNITY'),
            'evidence_sha256': str(evidence.get('evidence_sha256') or '') or None,
            'cycle': int(cycle), 'linked_to': linked_to,
            'justification': 'EVIDENCE_VALIDITY_EXPIRED' if linked_to else 'DAILY_CADENCE',
            'valid_until': stamp + float(policy.get('evidence_validity_seconds')
                                          or self._DEFAULT_EVIDENCE_VALIDITY_SECONDS),
            'admitted_at': stamp, 'session_id': None,
            'mission_id': None, 'team_id': None,
            'execution': {'state': 'NOT_STARTED', 'session_id': None},
            'review': {'state': 'NOT_REQUESTED'}, 'outcome': None,
            'budget': {'day': day, 'cap': int(policy.get('research_daily_budget') or 1),
                       'spent': 0},
            'backoff_until': 0.0, 'failures': 0, 'useful': None,
        }

    @staticmethod
    def _normalize_operation_document(document):
        """Additive read compatibility for operation rows written by older builds."""
        document = dict(document or {})
        document.setdefault('session_id', None)
        document.setdefault('mission_id', document.get('session_id'))
        document.setdefault('team_id', None)
        document.setdefault('execution', {'state': 'NOT_STARTED',
                                          'session_id': document.get('session_id')})
        document.setdefault('review', {'state': 'NOT_REQUESTED'})
        document.setdefault('outcome', None)
        document.setdefault('admission', {})
        return document

    def _update_operation_document(self, operation_id, *, now=None, **changes):
        stamp = time.time() if now is None else float(now)
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                f'SELECT document FROM {self._OPERATIONS_TABLE} WHERE id=?',
                (operation_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown daily operation')
            document = self._normalize_operation_document(json.loads(row['document']))
            for key, value in changes.items():
                if isinstance(value, dict) and isinstance(document.get(key), dict):
                    merged = dict(document[key]); merged.update(value); document[key] = merged
                else:
                    document[key] = value
            conn.execute(
                f'UPDATE {self._OPERATIONS_TABLE} SET document=?, updated_at=? WHERE id=?',
                (json.dumps(document, ensure_ascii=False), stamp, operation_id))
        return document

    def _owner_blocked_sessions(self):
        # Sessions of supported missions standing by for the owner. Internal
        # work may wait, but may never queue ahead of an owner-blocked mission.
        with self.store._connect() as conn:
            if not conn.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' '
                                'AND name=\'mission_controls\'').fetchone():
                return []
            rows = conn.execute('SELECT document FROM mission_controls').fetchall()
        blocked = []
        for row in rows:
            mission = json.loads(row[0])
            if mission.get('state') != 'BLOCKED_NEEDS_OWNER':
                continue
            try:
                autonomy = self.store.autonomy_snapshot(mission['session_id'])
            except Exception:
                autonomy = None
            if (autonomy or {}).get('workflow') in self.SUPPORTED_WORKFLOWS:
                blocked.append(mission['session_id'])
        return blocked

    def daily_budget_remaining(self, *, now=None):
        # Budget left today, computed from what the operations themselves
        # persisted. A restart reads the same spent value from the same rows.
        stamp = time.time() if now is None else float(now)
        day = time.strftime('%Y-%m-%d', time.localtime(stamp))
        cap = int(self.policy().get('research_daily_budget') or 1)
        spent = 0
        with self.store._connect() as conn:
            for row in conn.execute(f'SELECT document FROM {self._OPERATIONS_TABLE}'):
                budget = (json.loads(row[0]).get('budget') or {})
                if budget.get('day') == day:
                    spent += int(budget.get('spent') or 0)
        return max(0, cap - spent)

    def admit_daily_operation(self, evidence, *, now=None):
        # Admit one daily event: duplicate evidence inside its validity window
        # returns the operation it already owns (one logical operation per
        # event); expired validity returns a justified new cycle linked to the
        # previous one; a failure arms a persisted, exponential backoff; the
        # paused and owner-blocked states refuse admission before anything
        # else. Local and persistent only: nothing reaches a provider here.
        stamp = time.time() if now is None else float(now)
        policy = self.policy()
        evidence_id, source = self._operation_identity(evidence)

        def refused(state, **detail):
            result = {'state': state, 'dispatched': False, 'operation': None}
            if detail:
                result['detail'] = detail
            result['admission_event_id'] = self._record_admission(
                state, evidence_id, source, detail=detail)
            return result

        if not bool(policy.get('background_enabled', True)):
            return refused('PAUSED')
        blocked = self._owner_blocked_sessions()
        if blocked:
            return refused('OWNER_PRIORITY', blocked_sessions=blocked)

        result = None
        # The budget and latest event are read under the same SQLite write
        # transaction as the insert.  This closes the two-instance admission
        # race without introducing another queue or scheduler.
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            day = time.strftime('%Y-%m-%d', time.localtime(stamp))
            cap = int(policy.get('research_daily_budget') or 1)
            spent = sum(
                int((document.get('budget') or {}).get('spent') or 0)
                for item in conn.execute(f'SELECT document FROM {self._OPERATIONS_TABLE}')
                for document in (json.loads(item['document']),)
                if (document.get('budget') or {}).get('day') == day
            )
            remaining = max(0, cap - spent)
            row = conn.execute(
                f'SELECT * FROM {self._OPERATIONS_TABLE} '
                'WHERE evidence_id=? AND evidence_source=? '
                'ORDER BY created_at DESC, id DESC LIMIT 1',
                (evidence_id, source)).fetchone()
            if row is not None:
                document = self._normalize_operation_document(json.loads(row['document']))
                backoff_until = float(document.get('backoff_until') or 0.0)
                if stamp < backoff_until:
                    result = {'state': 'BACKOFF', 'dispatched': False,
                              'operation': document, 'retry_at': backoff_until}
                else:
                    valid_until = float(document.get('valid_until') or 0.0)
                    failures = int(document.get('failures') or 0)
                    if stamp < valid_until and failures <= 0:
                        result = {'state': 'DUPLICATE', 'dispatched': False,
                                  'operation': document}
                    elif remaining <= 0:
                        result = {'state': 'DAILY_BUDGET_EXHAUSTED',
                                  'dispatched': False, 'operation': None}
                    else:
                        cycle = int(document.get('cycle') or 1) + 1
                        new_document = self._operation_document(
                            evidence, evidence_id, source, cycle, row['id'], stamp, policy)
                        new_document['failures'] = failures
                        if stamp < valid_until:
                            new_document['justification'] = 'FAILURE_BACKOFF_ELAPSED'
                        new_document['id'] = self._operation_id(evidence_id, cycle)
                        conn.execute(
                            f'INSERT INTO {self._OPERATIONS_TABLE} VALUES(?,?,?,?,?,?,?)',
                            (new_document['id'], evidence_id, source, 'ADMITTED',
                             json.dumps(new_document, ensure_ascii=False), stamp, stamp))
                        conn.execute(
                            f'UPDATE {self._OPERATIONS_TABLE} SET state=\'SUPERSEDED\', updated_at=? '
                            'WHERE id=?', (stamp, row['id']))
                        result = {'state': 'RESEARCH_CYCLE', 'dispatched': False,
                                  'operation': new_document}
            elif remaining <= 0:
                result = {'state': 'DAILY_BUDGET_EXHAUSTED', 'dispatched': False,
                          'operation': None}
            else:
                new_document = self._operation_document(
                    evidence, evidence_id, source, 1, None, stamp, policy)
                new_document['id'] = self._operation_id(evidence_id, 1)
                conn.execute(
                    f'INSERT INTO {self._OPERATIONS_TABLE} VALUES(?,?,?,?,?,?,?)',
                    (new_document['id'], evidence_id, source, 'ADMITTED',
                     json.dumps(new_document, ensure_ascii=False), stamp, stamp))
                result = {'state': 'ADMITTED', 'dispatched': False,
                          'operation': new_document}

        operation = result.get('operation') if result else None
        result['admission_event_id'] = self._record_admission(
            result['state'], evidence_id, source, operation=operation)
        return result

    def daily_operation(self, operation_id):
        with self.store._connect() as conn:
            row = conn.execute(
                f'SELECT document FROM {self._OPERATIONS_TABLE} WHERE id=?',
                (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def link_daily_operation(self, operation_id, session_id, *, now=None):
        # Spend the persisted budget with the operation that earned it.
        stamp = time.time() if now is None else float(now)
        cap = int(self.policy().get('research_daily_budget') or 1)
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                f'SELECT document FROM {self._OPERATIONS_TABLE} WHERE id=?',
                (operation_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown daily operation')
            document = json.loads(row[0])
            document['session_id'] = session_id
            document['budget'] = {'day': time.strftime('%Y-%m-%d', time.localtime(stamp)),
                                  'cap': cap, 'spent': 1}
            conn.execute(f'UPDATE {self._OPERATIONS_TABLE} SET document=?, updated_at=? WHERE id=?',
                         (json.dumps(document, ensure_ascii=False), stamp, operation_id))
        return document

    def record_daily_operation_outcome(self, operation_id, *, useful=None,
                                       failure=False, now=None):
        # Persist one outcome; failures arm an exponential backoff that a
        # restart also reads, so a failing evidence source is retried with
        # growing caution, never in a tight loop.
        stamp = time.time() if now is None else float(now)
        base = float(self.policy().get('daily_operation_backoff_base_seconds')
                     or self._DEFAULT_BACKOFF_BASE_SECONDS)
        ceiling = float(self.policy().get('daily_operation_backoff_max_seconds')
                        or self._DEFAULT_BACKOFF_MAX_SECONDS)
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                f'SELECT document FROM {self._OPERATIONS_TABLE} WHERE id=?',
                (operation_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown daily operation')
            document = json.loads(row[0])
            document['useful'] = bool(useful) if useful is not None else (not failure)
            if failure:
                failures = int(document.get('failures') or 0) + 1
                document['failures'] = failures
                document['backoff_until'] = stamp + min(ceiling, base * (2 ** (failures - 1)))
            conn.execute(f'UPDATE {self._OPERATIONS_TABLE} SET document=?, updated_at=? WHERE id=?',
                         (json.dumps(document, ensure_ascii=False), stamp, operation_id))
        return document

    def research_question_for_cycle(self, base_question, operation=None, **_ignored):
        # The research pipeline dedups a question permanently by its hash. A
        # later cycle is therefore asked with its justification attached, which
        # both forks a NEW intake (not blocked by the permanent dedup) and
        # carries the linkage in the persisted record itself.
        cycle = int((operation or {}).get('cycle') or 1)
        if cycle <= 1:
            return base_question
        linked = str((operation or {}).get('linked_to') or '')
        return base_question + f' [ciclo {cycle} - EVIDENCE_VALIDITY_EXPIRED:{linked}]'

    def pause_background(self):
        # Pause interrupts new admissions immediately (admit_daily_operation
        # refuses PAUSED before anything else); the already-paused tick path
        # stays exactly as it was.
        return self._save(background_enabled=False)

    def resume_background(self):
        return self._save(background_enabled=True)

    def daily_digest(self, *, now=None):
        # Only items useful to the owner: completed internal reviews, product
        # feedback ready for the owner and daily opportunities accepted by the
        # independent review. Failed or rejected work is excluded from items.
        stamp = time.time() if now is None else float(now)
        items, excluded = [], 0
        owner_present = False
        internal_kinds = ('DAILY_OPPORTUNITY_REVIEW', 'PRODUCT_CRITICISM_REVIEW',
                          'SELF_IMPROVEMENT')
        terminal = ('COMPLETED', 'CANCELLED', 'FAILED')
        with self.store._connect() as conn:
            tables = {row[0] for row in conn.execute(
                'SELECT name FROM sqlite_master WHERE type=\'table\'')}
            if 'mission_controls' in tables:
                missions = [json.loads(row[0]) for row in
                            conn.execute('SELECT document FROM mission_controls')]
                autonomy = {}
                if 'mission_autonomy' in tables:
                    for row in conn.execute('SELECT document FROM mission_autonomy'):
                        document = json.loads(row[0])
                        autonomy[document.get('session_id')] = document
                for mission in missions:
                    document = autonomy.get(mission.get('session_id')) or {}
                    kind = document.get('mission_kind')
                    state = mission.get('state')
                    nonterminal = state not in terminal
                    if kind not in internal_kinds:
                        # A mission without a recorded autonomy kind may be the
                        # owner's; the machine never claims the owner is absent
                        # while such a mission is alive.
                        owner_present = owner_present or nonterminal
                        continue
                    if state == 'COMPLETED':
                        items.append({'kind': 'INTERNAL_REVIEW',
                                      'id': mission['session_id'],
                                      'session_id': mission['session_id'],
                                      'state': state, 'useful': True,
                                      'summary': 'Revisao interna concluida aguardando decisao do owner.'})
                    else:
                        excluded += 1
            if 'lab_product_feedback' in tables:
                for row in conn.execute('SELECT id, status, document FROM lab_product_feedback'):
                    document = json.loads(row['document'])
                    if row['status'] == 'READY_FOR_OWNER':
                        items.append({'kind': 'PRODUCT_FEEDBACK', 'id': row['id'],
                                      'state': row['status'], 'useful': True,
                                      'summary': str(document.get('text') or '')[:200]})
                    elif row['status'] in ('REVIEW_FAILED',):
                        excluded += 1
            if 'lab_opportunities' in tables:
                for row in conn.execute('SELECT id, document FROM lab_opportunities'):
                    document = json.loads(row['document'])
                    if document.get('state') == 'READY_FOR_OWNER':
                        items.append({'kind': 'DAILY_OPPORTUNITY', 'id': row['id'],
                                      'state': document.get('state'), 'useful': True,
                                      'summary': str(document.get('opportunity') or '')[:200]})
                    elif document.get('state') in ('REJECTED_BY_TEAM',):
                        excluded += 1
        return {'generated_at': stamp, 'owner_absent': not owner_present,
                'items': items, 'useful': len(items), 'excluded': excluded}

    def _provider_wait_state(self, workforce):
        """Return a cheap, truthful wait state for autonomous admissions.

        The desktop must remain usable when the OpenAI allowance is exhausted.
        Existing missions are still handed to the mission controller, which
        preserves their quota-wait checkpoint.  This gate only prevents the
        improvement loop from creating a fresh mission that cannot start.
        """
        registry = getattr(self.runtime, 'registry', None)
        if registry is None:
            return None
        try:
            info = next((item for item in registry.list_providers()
                         if item.id == 'codex_cli'), None)
        except Exception as exc:
            return {'state': 'WAITING_PROVIDER', 'provider': 'codex_cli',
                    'reason': 'PROBE_FAILED', 'detail': type(exc).__name__}
        if info is None or info.availability.can_work:
            return None
        candidates = getattr(self._engine(workforce), 'candidates', None)
        if callable(candidates) and candidates():
            return None
        reason = info.availability.value
        return {'state': 'WAITING_PROVIDER', 'provider': 'codex_cli',
                'reason': reason, 'detail': info.detail,
                'retry_after_seconds': 300}

    def tick(self):
        if not self.lock.acquire(blocking=False): return {'state': 'BUSY'}
        try:
            policy = self.policy()
            workforce = WorkforcePolicy(policy)
            if not workforce.background_enabled:
                return {'state': 'DISABLED'}
            now = time.time()
            if policy.get('last_state') == 'WORKSPACE_NOT_CONFIGURED':
                self._save(last_tick=now, last_heartbeat=now)
                return {'state': 'WORKSPACE_NOT_CONFIGURED',
                        'error': 'WORKSPACE_NOT_CONFIGURED'}
            self._save(last_tick=now, last_heartbeat=now, last_state='CHECKING', error=None, error_detail=None)
            evolution = self._evolution_engine(workforce, policy['workspace'])
            inventory = evolution.observe_local()
            self._save(source_observer=evolution.observer_snapshot())
            with self.store._connect() as conn:
                pending = [json.loads(r[0]) for r in conn.execute('SELECT document FROM mission_controls')
                    if json.loads(r[0])['state'] not in ('COMPLETED', 'CANCELLED', 'FAILED')]
            supported, legacy = [], []
            for mission in pending:
                autonomy = self.store.autonomy_snapshot(mission['session_id'])
                (supported if (autonomy or {}).get('workflow') in self.SUPPORTED_WORKFLOWS
                 else legacy).append(mission)
            self._save(stale_legacy_sessions=[item['session_id'] for item in legacy])
            if supported:
                mission = supported[0]
                sid = mission['session_id']
                autonomy = self.store.autonomy_snapshot(sid)
                if mission['state'] == 'BLOCKED_NEEDS_OWNER':
                    if (autonomy or {}).get('mission_kind') in (
                            'DAILY_OPPORTUNITY_REVIEW', 'PRODUCT_CRITICISM_REVIEW',
                            'SELF_IMPROVEMENT'):
                        MissionController(self.store).fail_idle(
                            sid, 'INTERNAL_REVIEW_FAILED:' + str(mission.get('blocker') or 'UNKNOWN'))
                        self._save(last_state='FAILED', active_session=sid,
                                   error='INTERNAL_REVIEW_FAILED')
                        return {'state': 'FAILED', 'session_id': sid,
                                'blocker': 'INTERNAL_REVIEW_FAILED'}
                    self._save(last_state='BLOCKED_NEEDS_OWNER', active_session=sid)
                    return {'state': 'BLOCKED_NEEDS_OWNER', 'session_id': sid,
                            'blocker': mission.get('blocker')}
                if mission['state'] == 'BLOCKED' and mission.get('blocker') not in (
                        'PROVIDER_BUSY', 'PROVIDER_RATE_LIMITED', 'PROVIDER_QUOTA_EXHAUSTED',
                        'PROVIDER_PROVIDER_ERROR', 'PROVIDER_ERROR', 'PROVIDER_OFFLINE'):
                    self._save(last_state='BLOCKED', active_session=sid)
                    return {'state': 'BLOCKED', 'session_id': sid}
                result = self._engine(workforce).run(sid)
                self._save(last_state=result.get('state', 'UNKNOWN'), active_session=sid)
                return result
            if not policy.get('enabled'):
                self._save(last_state='MONITORING')
                return {'state': 'MONITORING'}
            provider_wait = self._provider_wait_state(workforce)
            if provider_wait:
                self._save(last_state='WAITING_PROVIDER', provider_wait=provider_wait)
                return provider_wait
            day = time.strftime('%Y-%m-%d')
            count = policy['daily_missions'] if policy.get('daily_date') == day else 0
            if now >= policy.get('next_evolution_check', 0) and count < policy['max_new_evolution_missions_per_day']:
                self._save(next_evolution_check=now + policy['evolution_cadence_seconds'])
                evolution.autopilot = self._engine(workforce)
                feedback = FeedbackInbox(self.store).next_received()
                if feedback:
                    source_path = self._feedback_source_path(feedback['text'])
                    proposal_only = self._proposal_only(feedback['text']) or source_path is None
                    evidence = {'feedback_text': feedback['text'],
                                'evidence_sha256': feedback['evidence_sha256'],
                                 'source_channel': feedback['channel'],
                                 'observed_at': feedback['observed_at'],
                                 'intent_mode': 'PROPOSAL_ONLY' if proposal_only else 'SOURCE_IMPROVEMENT'}
                    admission = self.admit_daily_operation({
                        'id': feedback['id'], 'source': source_path or feedback['channel'],
                        'kind': 'FEEDBACK', 'text': feedback['text'],
                        'evidence_sha256': feedback['evidence_sha256'],
                        'observed_at': feedback['observed_at']})
                    if admission['state'] not in ('ADMITTED', 'RESEARCH_CYCLE'):
                        self._save(last_state='MONITORING', daily_operation_state=admission['state'])
                        return {'state': 'MONITORING', 'daily_operation_state': admission['state']}
                    operation = admission['operation']
                    evidence['daily_operation_id'] = operation['id']
                    evidence['research_cycle'] = operation['cycle']
                    if operation.get('linked_to'):
                        evidence['linked_operation'] = operation['linked_to']
                    intake = self.queue_research_event(
                        self.research_question_for_cycle(
                            'Pesquisa sobre feedback: ' + feedback['text'], operation),
                        event_id=feedback['id'], observed_at=feedback['observed_at'])
                    if intake['state'] != 'QUEUED':
                        self._save(last_state='MONITORING', research_intake_state=intake['state'])
                        return {'state': 'MONITORING', 'research_intake_state': intake['state']}
                    evidence['research_intake_id'] = intake['id']
                    # VALUE > ACTIVITY: the team is woken only when there is work.
                    self.ensure_team()
                    if source_path:
                        evidence['source_path'] = source_path
                    if proposal_only:
                        objective = ('Como arquiteto da ZARA, avalie esta crítica e produza somente uma proposta '
                            'verificável para o owner. Não implemente, não altere source e não promova produção. '
                            'CRÍTICA OBSERVADA: ' + feedback['text'] + '. EVIDENCE_SHA256: '
                            + feedback['evidence_sha256'])
                        mission_kind = 'PRODUCT_CRITICISM_REVIEW'
                    else:
                        objective = ('Como arquiteto da ZARA, melhore o código-fonte de ' + source_path +
                            ' no sandbox para resolver esta crítica registrada. Preserve os comportamentos válidos, '
                            'execute testes focados e faça revisão independente. Nenhuma promoção de produção é '
                            'permitida antes da aprovação do owner. CRÍTICA OBSERVADA: ' + feedback['text'] +
                            '. EVIDENCE_SHA256: ' + feedback['evidence_sha256'])
                        mission_kind = 'SELF_IMPROVEMENT'
                    started = self._engine(workforce).start(objective,
                        mission_kind=mission_kind, evidence=evidence)
                    if started.get('success'):
                        self.link_daily_operation(operation['id'], started['session_id'])
                        FeedbackInbox(self.store).link(feedback['id'], started['session_id'])
                        self._save(daily_date=day, daily_missions=count + 1,
                                   active_session=started['session_id'])
                        result = self._engine(workforce).run(started['session_id'])
                        completed = result.get('state') == 'COMPLETED'
                        FeedbackInbox(self.store).finish(feedback['id'], completed=completed)
                        self.record_daily_operation_outcome(operation['id'],
                            useful=completed, failure=not completed)
                        self._save(last_state=result.get('state', 'UNKNOWN'))
                        return result
                    self.record_daily_operation_outcome(operation['id'], failure=True)
                planned = evolution.observe_and_plan(inventory=inventory)
                if planned.get('session_id') and not planned.get('existing'):
                    self._save(daily_date=day, daily_missions=count + 1, active_session=planned['session_id'])
                    result = evolution.run(planned['session_id'])
                    self._save(last_state=result.get('state', 'UNKNOWN'))
                    return result
                # External scouting is due only after local owner evidence and
                # source inspection have no mission to dispatch.
                scout = TechnologyScout(self.store)
                scout.run_due()
                opportunity = scout.next_unreviewed()
                if opportunity:
                    admission = self.admit_daily_operation({
                        'id': opportunity['id'], 'source': opportunity['source'],
                        'kind': 'DAILY_OPPORTUNITY',
                        'evidence_sha256': opportunity['evidence_sha256'],
                        'observed_at': opportunity['observed_at']})
                    if admission['state'] not in ('ADMITTED', 'RESEARCH_CYCLE'):
                        self._save(last_state='MONITORING', daily_operation_state=admission['state'])
                        return {'state': 'MONITORING', 'daily_operation_state': admission['state']}
                    operation = admission['operation']
                    intake = ResearchPipeline(self.store).admit_intake(
                        self.research_question_for_cycle(
                            'Pesquisa diária: ' + opportunity['opportunity'],
                            operation),
                        trigger='DAILY',
                        event_id=opportunity['id'], observed_at=opportunity['observed_at'],
                        daily_budget=policy['research_daily_budget'])
                    if intake['state'] != 'QUEUED':
                        self._save(last_state='MONITORING', research_intake_state=intake['state'])
                        return {'state': 'MONITORING', 'research_intake_state': intake['state']}
                    objective = (
                        'Avalie como líder esta oportunidade para a ZARA, escolha somente os papéis necessários e '
                        'produza um relatório proposal.md verificável para o owner aprovar. Não instale, não promova '
                        'e não altere o source atual. Oportunidade: ' + opportunity['opportunity'] +
                        '. Fonte observada: ' + opportunity['source'])
                    evidence = {'source': opportunity['source'], 'evidence_sha256': opportunity['evidence_sha256'],
                                'evidence_excerpt': opportunity['evidence_excerpt'],
                                'observed_at': opportunity['observed_at'],
                                'daily_operation_id': operation['id'],
                                'research_cycle': operation['cycle'],
                                'research_intake_id': intake['id']}
                    objective += ('. SOURCE_URL: ' + evidence['source'] +
                                  '. EVIDENCE_SHA256: ' + evidence['evidence_sha256'] +
                                  '. EVIDENCE_EXCERPT: ' + evidence['evidence_excerpt'])
                    self.ensure_team()
                    started = self._engine(workforce).start(objective,
                        mission_kind='DAILY_OPPORTUNITY_REVIEW', evidence=evidence)
                    if started.get('success'):
                        self.link_daily_operation(operation['id'], started['session_id'])
                        scout.link_review(opportunity['id'], started['session_id'])
                        self._save(daily_date=day, daily_missions=count + 1,
                                   active_session=started['session_id'])
                        result = self._engine(workforce).run(started['session_id'])
                        verification = scout.verify_review(opportunity['id'])
                        accepted = bool(verification.get('passed')) and result.get('state') == 'COMPLETED'
                        scout.finish_review(opportunity['id'], accepted=verification['passed'])
                        self.record_daily_operation_outcome(operation['id'],
                            useful=accepted, failure=not accepted)
                        self._save(last_state=result.get('state', 'UNKNOWN'))
                        return result
                    self.record_daily_operation_outcome(operation['id'], failure=True)
            self._save(last_state='MONITORING')
            # VALUE > ACTIVITY: the empty queue stood down having spent zero
            # tokens (no team provisioning, no research admission, no model call).
            return {'state': 'MONITORING', 'token_spend': 0}
        except Exception as exc:
            detail = f'{type(exc).__name__}: {exc}'
            self._save(last_state='FAILED', error='SUPERVISOR_NEEDS_RECONCILIATION',
                       error_detail=detail)
            return {'state': 'FAILED', 'error': 'SUPERVISOR_NEEDS_RECONCILIATION',
                    'error_detail': detail}
        finally:
            self.lock.release()
