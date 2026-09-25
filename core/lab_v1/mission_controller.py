"""Opt-in, persistent sequential missions over existing Lab Sessions and Tasks.

No provider, executor, scheduler or UI is started here. One tick advances one
checkpoint through injected execution/verification ports. Ports must perform
one bounded operation, honour the deadline and persist real Runs themselves.
"""
from __future__ import annotations

import json
import math
import os
import re
import socket
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from core.lab_v1.domain import ContextPacket, Task, new_id
from core.lab_v1.store import LabStore
from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation, canonical_resource


def _process_started_at(pid):
    """Process start time, so a reused PID is never mistaken for the old owner."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a declared dependency
        return None
    try:
        return round(psutil.Process(pid).create_time(), 3)
    except Exception:
        return None


def process_identity():
    """Identity of this Lab process: host, pid and process start time."""
    pid = os.getpid()
    return {'host': socket.gethostname(), 'pid': pid, 'started_at': _process_started_at(pid)}


# A read that refused its own character budget is not an uncertain effect:
# nothing was executed. Collapsing both into 'UNCERTAIN_EFFECT' with no stored
# reason made a common deterministic error indistinguishable from a half-applied
# real action, so the engine could not tell itself what had actually happened.
_DETERMINISTIC_CONTEXT_CODES = frozenset({'CONTEXT_LIMIT'})

# The same reasoning for a draft the local executor refused. `apply_edits`
# validates the WHOLE candidate before performing its first write, so every code
# below fires with nothing written: the effect is known, and it is 'nothing'.
# Reading them as UNCERTAIN_EFFECT dead-ended the mission on what is really the
# executor telling the worker its draft broke a rule - feedback the worker can
# act on. Naming it does not relax any rule: the draft is still refused.
_DETERMINISTIC_DRAFT_REJECTION_CODES = frozenset({
    'SOURCE_CHANGE_REQUIRED', 'EDIT_LIMIT', 'EDIT_SCHEMA', 'EDIT_SIZE_LIMIT',
    'DUPLICATE_EDIT', 'PARTIAL_VIEW_CONTENT_FORBIDDEN', 'ANCHOR_NOT_FOUND',
    'ANCHOR_AMBIGUOUS', 'ANCHOR_EMPTY', 'ANCHOR_FILE_MISSING', 'ANCHOR_SIZE_LIMIT',
    'ANCHORED_EDIT_LIMIT', 'ANCHORED_EDIT_SCHEMA', 'ANCHORED_EDIT_SYNTAX',
    'ANCHORED_EDIT_UNSAFE',
})
_ERROR_CODE_RE = re.compile(r'[A-Z][A-Z0-9_]*')


def _error_code(exc):
    """Leading uppercase code of a Lab error, e.g. 'CONTEXT_LIMIT: detail'."""
    head = str(exc).split(':', 1)[0].strip()
    return head if head and _ERROR_CODE_RE.fullmatch(head) else ''


def classify_step_failure(exc):
    """Name a step failure instead of hiding it behind a generic blocker.

    ``CandidateSourceError('CONTEXT_LIMIT')`` comes from ``read_context``, which
    only reads the sandbox snapshot: when it fires, the step's real work never
    started. That is a deterministic context-budget failure, never an uncertain
    effect. ``apply_edits`` refusing a draft before its first write is the same
    kind of fact, reported as PATCH_DRAFT_REJECTED so the worker can be handed
    the refusal. Any other exception keeps the conservative unknown-effect reading.
    """
    try:
        from core.lab_v1.candidate_source import CandidateSourceError
    except ImportError:  # pragma: no cover - the Lab tool is always importable
        CandidateSourceError = ()
    code = _error_code(exc)
    lab_error = bool(CandidateSourceError) and isinstance(exc, CandidateSourceError)
    context_budget = lab_error and code in _DETERMINISTIC_CONTEXT_CODES
    draft_rejected = lab_error and code in _DETERMINISTIC_DRAFT_REJECTION_CODES
    known = context_budget or draft_rejected
    kind = ('CONTEXT_BUDGET_EXCEEDED' if context_budget
            else 'PATCH_DRAFT_REJECTED' if draft_rejected else 'UNCLASSIFIED_STEP_ERROR')
    return {
        'error_type': type(exc).__name__,
        'error_module': type(exc).__module__,
        'error_code': code or None,
        'message': str(exc)[:2000],
        'kind': kind,
        'deterministic': known,
        'effect': 'NONE_NOTHING_EXECUTED' if known else 'UNKNOWN',
        'uncertain_effect': not known,
        'blocker': kind if known else None,
    }


def owner_is_alive(owner):
    """True only with positive evidence that the recorded owner still runs.

    Anything unknown — another host, an unparseable record, or a pid whose start
    time cannot be read — counts as alive, so the lease is never stolen.
    """
    if not isinstance(owner, dict) or 'pid' not in owner:
        return True
    if owner.get('host') != socket.gethostname():
        return True
    current = process_identity()
    if owner['pid'] == current['pid'] and owner.get('started_at') == current['started_at']:
        return True
    started_at = _process_started_at(owner['pid'])
    if started_at is None:
        return False  # the pid does not exist any more
    if owner.get('started_at') is None:
        return True  # unknown original start time: assume the pid is the owner
    return started_at == owner['started_at']


@dataclass(frozen=True)
class MissionLimits:
    max_turns: int = 6
    max_delegations: int = 2
    max_retries: int = 1
    max_actions: int = 8
    timeout_s: int = 900

    def validate(self):
        for value in asdict(self).values():
            if type(value) is not int or value < 0:
                raise ValueError("Limits must be nonnegative integers")
        if self.timeout_s == 0:
            raise ValueError("A mission must have a deadline")


@dataclass(frozen=True)
class MissionStep:
    id: str
    task_id: str
    kind: str  # INVOKE, DELEGATE or ACTION; verification is a separate checkpoint
    depends_on: tuple[str, ...] = ()
    capability: str = ''
    resources: tuple[str, ...] = ()
    risk: str = 'LOW'


@dataclass(frozen=True)
class Dispatch:
    session_id: str
    step_id: str
    task_id: str
    agent_id: str
    attempt_id: str
    deadline: float
    context: ContextPacket
    execution_scope: ExecutionScope
    capability: str
    resources: tuple[str, ...]
    risk: str


@dataclass(frozen=True)
class Receipt:
    artifact_ref: str
    summary: str


@dataclass(frozen=True)
class Verification:
    verdict: str  # PASS, FAIL, INCONCLUSIVE
    evidence_ref: str


class MissionPorts(Protocol):
    def execute(self, dispatch: Dispatch) -> Receipt: ...
    def verify(self, dispatch: Dispatch, receipt: Receipt) -> Verification: ...


class LeaseLost(RuntimeError):
    pass


class TextProviderFailure(RuntimeError):
    """A text-only adapter returned failure; no computer action was requested."""
    def __init__(self, availability: str):
        self.availability = availability


_QUOTA_WAIT_STATES = frozenset({'QUOTA_EXHAUSTED', 'RATE_LIMITED'})
_QUOTA_BACKOFF_MAX_S = 3600


class MissionController:
    """State and lease mutations are atomic with Session/Task/event updates.

    The extension is migrated only on explicit construction. Existing V1
    startup and ordinary Session reads do not activate the controller.
    """

    def __init__(self, store: LabStore, *, clock: Callable[[], float] = time.time,
                 lease_s: int = 30):
        if not math.isfinite(lease_s) or lease_s <= 0:
            raise ValueError("Lease duration must be positive")
        self.store, self.clock, self.lease_s = store, clock, lease_s
        store.initialize()
        with self._transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS mission_controls (
                session_id TEXT PRIMARY KEY REFERENCES sessions(id),
                document TEXT NOT NULL, lease_token TEXT, lease_until REAL NOT NULL DEFAULT 0
            )""")
            columns = {row[1] for row in conn.execute('PRAGMA table_info(mission_controls)')}
            if 'lease_owner' not in columns:
                # Who holds the lease, so a restarted Lab can tell a dead owner
                # from a live one instead of waiting out the whole lease.
                conn.execute('ALTER TABLE mission_controls ADD COLUMN lease_owner TEXT')
            conn.execute("""CREATE TABLE IF NOT EXISTS mission_plans (
                session_id TEXT NOT NULL REFERENCES sessions(id), version INTEGER NOT NULL,
                document TEXT NOT NULL, PRIMARY KEY(session_id, version)
            )""")
            conn.execute("INSERT OR IGNORE INTO schema_meta(key,value) VALUES('mission_controller_version','1')")
            conn.execute("""CREATE TABLE IF NOT EXISTS mission_observations (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                step_id TEXT NOT NULL, attempt_id TEXT NOT NULL, kind TEXT NOT NULL,
                document TEXT NOT NULL, occurred_at REAL NOT NULL
            )""")
            conn.execute("UPDATE schema_meta SET value='2' WHERE key='mission_controller_version'")

    @contextmanager
    def _transaction(self):
        conn = self.store._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _load(self, conn, session_id):
        row = conn.execute("SELECT * FROM mission_controls WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("Session has no mission plan")
        return json.loads(row['document']), row

    def _save(self, conn, doc, event):
        sid, stamp = doc['session_id'], self.clock()
        doc['updated_at'] = stamp
        conn.execute("UPDATE mission_controls SET document=? WHERE session_id=?", (json.dumps(doc), sid))
        conn.execute("UPDATE sessions SET state=?, updated_at=?, revision=revision+1 WHERE id=?",
                     (doc['state'], stamp, sid))
        conn.execute("""INSERT INTO events(id,type,session_id,entity_id,payload,occurred_at)
                        VALUES(?,?,?,?,?,?)""",
                     (new_id('evt'), event, sid, sid,
                      json.dumps({'state': doc['state'], 'blocker': doc['blocker'],
                                  'plan_version': doc['plan_version']}), stamp))

    def _validate_plan(self, conn, session_id, steps):
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None:
            raise ValueError("Unknown session")
        if not steps or len(steps) > 32:
            raise ValueError("A sequential plan needs 1..32 steps")
        seen, task_ids = set(), set()
        for step in steps:
            if not step.id or step.id in seen or step.task_id in task_ids:
                raise ValueError("Step and Task IDs must be unique")
            if step.kind not in ('INVOKE', 'DELEGATE', 'ACTION'):
                raise ValueError("Unsupported step kind")
            if not set(step.depends_on) <= seen:
                raise ValueError("Dependencies must precede this step")
            task = conn.execute("SELECT * FROM tasks WHERE id=? AND session_id=?",
                                (step.task_id, session_id)).fetchone()
            if task is None or not task['acceptance'].strip():
                raise ValueError("Every step needs a Task in this Session and acceptance criteria")
            member = conn.execute("""SELECT a.id FROM agents a JOIN team_memberships m ON m.agent_id=a.id
                WHERE a.id=? AND a.archived=0 AND m.team_id=? AND m.left_at IS NULL""",
                (task['assigned_agent_id'], session['team_id'])).fetchone()
            if member is None:
                raise ValueError("Assigned agent must be an active team member")
            seen.add(step.id)
            task_ids.add(step.task_id)

    def blocking_mission(self, conn, *, except_session_id=None):
        """Return live work that must serialize before another work item can run.

        Paused missions remain persisted in the shared room. They do not hold
        the execution slot after their lease expires and their provider run is
        no longer STARTED.
        """
        query = 'SELECT session_id, document, lease_until FROM mission_controls'
        params = ()
        if except_session_id is not None:
            query += ' WHERE session_id<>?'
            params = (except_session_id,)
        for row in conn.execute(query, params):
            doc = json.loads(row['document'])
            state = doc.get('state')
            if state in ('COMPLETED', 'FAILED', 'CANCELLED'):
                continue
            if (state in ('BLOCKED', 'WAITING_RESOURCE', 'BLOCKED_NEEDS_OWNER')
                    and float(row['lease_until'] or 0) <= self.clock()
                    and not conn.execute(
                        "SELECT 1 FROM runs WHERE session_id=? AND state='STARTED' LIMIT 1",
                        (row['session_id'],),
                    ).fetchone()):
                continue
            return doc
        return None

    def plan(self, session_id: str, steps: list[MissionStep], limits: MissionLimits | None = None,
             *, scope: ExecutionScope, dynamic: bool = False):
        limits = limits or MissionLimits()
        limits.validate()
        scope.validate()
        scope = ExecutionScope(**{**asdict(scope), 'allowed_resources': tuple(
            canonical_resource(r) for r in scope.allowed_resources)})
        with self._transaction() as conn:
            self._validate_plan(conn, session_id, steps)
            authority = conn.execute('SELECT owner FROM session_authorities WHERE session_id=?',
                                     (session_id,)).fetchone()
            if authority and authority['owner'] != 'MISSION':
                raise ValueError('Session already belongs to V1')
            # Only live execution owns the slot. Paused room work is retained
            # and can be resumed later without blocking another work item.
            if self.blocking_mission(conn, except_session_id=session_id):
                raise ValueError('Another mission must finish or be safely cancelled first')
            existing = conn.execute("SELECT document FROM mission_controls WHERE session_id=?", (session_id,)).fetchone()
            if existing:
                old = json.loads(existing[0])
                if old['state'] != 'QUEUED' or any(old['used'].values()):
                    raise ValueError("Only an unstarted plan can be revised in V0")
                version, deadline = old['plan_version'] + 1, old['deadline']
            else:
                state = conn.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
                if state != 'QUEUED':
                    raise ValueError("Only a queued Session can enter Autopilot")
                version, deadline = 1, self.clock() + limits.timeout_s
            doc = {'session_id': session_id, 'plan_version': version, 'state': 'QUEUED',
                   'blocker': None, 'cancel_requested': False, 'deadline': deadline,
                   'resource_waiting': scope.authorization_ref.startswith('autopilot'),
                   'awaiting_expansion': dynamic,
                   'execution_scope': asdict(scope),
                   'limits': asdict(limits), 'used': {'turns': 0, 'delegations': 0, 'retries': 0, 'actions': 0},
                   'steps': [{**asdict(s), 'status': 'PENDING', 'attempt_id': None,
                              'receipt': None, 'verification': None} for s in steps]}
            conn.execute("INSERT INTO mission_plans VALUES(?,?,?)", (session_id, version, json.dumps([asdict(s) for s in steps])))
            conn.execute("INSERT OR IGNORE INTO mission_controls(session_id,document) VALUES(?,?)", (session_id, '{}'))
            conn.execute("INSERT OR IGNORE INTO session_authorities VALUES(?,'MISSION',NULL)", (session_id,))
            self._save(conn, doc, 'mission.planned')
        return self.snapshot(session_id)

    def expand_verified_plan(self, session_id, tasks: list[Task], steps: list[MissionStep], *, metadata: dict):
        """Commit planner-selected tasks and dependencies atomically after planner verification.

        The original limits, scope, history and deadline cannot expand here.
        A crash either leaves the verified planner pending expansion or the entire next version.
        """
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if not doc.get('awaiting_expansion'):
                return False
            if (doc['cancel_requested'] or row['lease_until'] > self.clock()
                    or not all(s['status'] == 'DONE' for s in doc['steps'])):
                return False
            scope = ExecutionScope(**doc['execution_scope'])
            for task in tasks:
                if task.session_id != session_id: raise ValueError('Cross-session task')
                conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                    task.id, task.session_id, task.title, task.instruction, task.created_by_agent_id,
                    task.assigned_agent_id, task.state.value, task.acceptance, task.result,
                    task.max_turns, task.budget_usd, task.created_at, task.updated_at))
            old = [MissionStep(**{key: s[key] for key in MissionStep.__dataclass_fields__}) for s in doc['steps']]
            self._validate_plan(conn, session_id, old + steps)
            for step in steps: scope.require(step.capability, step.resources, step.risk)
            doc['steps'] += [{**asdict(s), 'status': 'PENDING', 'attempt_id': None,
                              'receipt': None, 'verification': None} for s in steps]
            doc['plan_version'] += 1
            doc['planner_contract'] = metadata
            doc['awaiting_expansion'] = False
            # A verified source-inspection plan may intentionally contain no
            # follow-up tasks when the architect found no defensible change.
            # In that case every existing step is already DONE, so keeping the
            # mission RUNNING creates a permanent ghost mission that blocks the
            # next real Lab objective. Empty verified expansion is terminal.
            doc['state'], doc['blocker'] = ('COMPLETED' if not steps else 'RUNNING'), None
            conn.execute('INSERT INTO mission_plans VALUES(?,?,?)',
                (session_id, doc['plan_version'], json.dumps({'steps': doc['steps'], 'contract': metadata})))
            self._save(conn, doc, 'mission.plan_expanded')
            return True

    def snapshot(self, session_id):
        conn = self.store._connect()
        try:
            return self._load(conn, session_id)[0]
        finally:
            conn.close()

    def reconcile_verified_empty_plan(self, session_id: str) -> bool:
        """Close an old ghost mission created by the pre-fix empty-plan bug.

        This is intentionally strict: only a verified planner contract with
        zero follow-up tasks, a factual no-change reason, every persisted step
        DONE, no active model run and no live lease may be reconciled.
        """
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if doc['state'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
                return False
            contract = doc.get('planner_contract')
            if (doc.get('awaiting_expansion') or not isinstance(contract, dict)
                    or contract.get('tasks') != []
                    or not isinstance(contract.get('no_change_reason'), str)
                    or not contract['no_change_reason'].strip()
                    or not doc.get('steps')
                    or not all(step.get('status') == 'DONE' for step in doc['steps'])):
                return False
            if row['lease_token'] is not None and row['lease_until'] > self.clock():
                return False
            if conn.execute(
                "SELECT 1 FROM runs WHERE session_id=? AND state='STARTED' LIMIT 1",
                (session_id,),
            ).fetchone():
                return False
            doc['state'], doc['blocker'] = 'COMPLETED', None
            self._save(conn, doc, 'mission.no_change_reconciled')
            return True

    def fail_idle(self, session_id: str, reason: str):
        """Close a nonterminal mission only when no worker still owns its lease."""
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if doc['state'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
                return doc
            if row['lease_token'] is not None and row['lease_until'] > self.clock():
                raise LeaseLost('Active mission cannot be failed by another worker')
            doc['state'], doc['blocker'] = 'FAILED', reason
            conn.execute('UPDATE mission_controls SET lease_token=NULL, lease_until=0, lease_owner=NULL WHERE session_id=?',
                         (session_id,))
            self._save(conn, doc, 'mission.failed')
            return doc

    def _claim(self, session_id):
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if doc['state'] in ('COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED',
                                'WAITING_RESOURCE', 'BLOCKED_NEEDS_OWNER'):
                return None
            # One live operation across all missions in this Lab database.
            if conn.execute("SELECT 1 FROM mission_controls WHERE lease_token IS NOT NULL AND lease_until>?",
                            (self.clock(),)).fetchone():
                return None
            if self.blocking_mission(conn, except_session_id=session_id):
                return None
            token = new_id('lease')
            conn.execute("UPDATE mission_controls SET lease_token=?,lease_until=?,lease_owner=? WHERE session_id=?",
                         (token, self.clock() + self.lease_s, json.dumps(process_identity()), session_id))
            return token

    def release_dead_leases(self):
        """Restart hook: free leases whose owning process no longer exists.

        A live owner, another host or any unreadable owner record keeps its
        lease; only a proven-dead process is reclaimed. The old token is
        discarded, so a zombie worker can never commit over the new owner.
        """
        reclaimed = []
        with self._transaction() as conn:
            rows = conn.execute('SELECT session_id, lease_owner, lease_until FROM mission_controls '
                                'WHERE lease_token IS NOT NULL AND lease_until>?', (self.clock(),)).fetchall()
            for row in rows:
                try:
                    owner = json.loads(row['lease_owner']) if row['lease_owner'] else None
                except (TypeError, ValueError):
                    owner = None
                if owner_is_alive(owner):
                    continue
                doc, _ = self._load(conn, row['session_id'])
                doc.setdefault('restarts', []).append({
                    'reclaimed_lease_owner': owner, 'lease_had_left_s': row['lease_until'] - self.clock(),
                    'reclaimed_by': process_identity(), 'at': self.clock()})
                conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0,lease_owner=NULL '
                             'WHERE session_id=?', (row['session_id'],))
                self._save(conn, doc, 'mission.lease_reclaimed_after_restart')
                reclaimed.append({'session_id': row['session_id'], 'dead_owner': owner})
        return reclaimed

    def _owned(self, conn, session_id, token):
        doc, row = self._load(conn, session_id)
        if row['lease_token'] != token or row['lease_until'] <= self.clock():
            raise LeaseLost("Stale worker may not commit a checkpoint")
        return doc

    def renew(self, session_id, token):
        with self._transaction() as conn:
            self._owned(conn, session_id, token)
            conn.execute("UPDATE mission_controls SET lease_until=? WHERE session_id=?",
                         (self.clock() + self.lease_s, session_id))

    def _block(self, conn, doc, reason):
        resource_wait = doc.get('resource_waiting', False) and reason in (
            'PROVIDER_BUSY', 'PROVIDER_RATE_LIMITED', 'PROVIDER_QUOTA_EXHAUSTED',
            'PROVIDER_PROVIDER_ERROR', 'PROVIDER_OFFLINE', 'PROVIDER_ERROR')
        doc['state'] = 'WAITING_RESOURCE' if resource_wait else 'BLOCKED'
        doc['blocker'] = reason
        self._save(conn, doc, 'mission.blocked')

    def repair_step(self, session_id: str, *, reason: str) -> bool:
        """Authorize one bounded re-execution after failed verification.

        Only text generation and reversible mission-sandbox writes qualify.
        The rejected receipt and verification remain in observations/artifacts.
        """
        if not reason.strip():
            raise ValueError('Repair needs verifier evidence')
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if row['lease_token'] and row['lease_until'] > self.clock():
                return False
            step = next((s for s in doc['steps'] if s['status'] != 'DONE'), None)
            if (doc['state'] != 'BLOCKED' or doc['blocker'] not in
                    ('VERIFICATION_FAIL', 'VERIFICATION_INCONCLUSIVE') or step is None
                    or step['status'] != 'VERIFYING' or step['capability'] != 'model.text'
                    or len(step.get('repairs', [])) >= step.get('repair_budget', 1)
                    or doc['used']['retries'] >= doc['limits']['max_retries'] or doc['cancel_requested']
                    or self.clock() >= doc['deadline']):
                if doc['state'] == 'BLOCKED' and doc['blocker'] in ('VERIFICATION_FAIL', 'VERIFICATION_INCONCLUSIVE'):
                    doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', 'REPAIR_LIMIT'
                    self._save(conn, doc, 'mission.repair_exhausted')
                return False
            step.setdefault('repairs', []).append({
                'reason': reason, 'at': self.clock(), 'receipt': step['receipt'],
                'verification': step['verification'], 'attempt_id': step['attempt_id']})
            doc['used']['retries'] += 1
            step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
            doc['state'], doc['blocker'] = 'REPAIRING', None
            doc['plan_version'] += 1
            conn.execute('INSERT INTO mission_plans VALUES(?,?,?)',
                         (session_id, doc['plan_version'], json.dumps(doc['steps'])))
            conn.execute("UPDATE tasks SET state='CREATED',result=NULL,updated_at=? WHERE id=?",
                         (self.clock(), step['task_id']))
            self._save(conn, doc, 'mission.repair_authorized')
            return True

    def resume_due_resource(self, session_id):
        """Retry only a known failed text attempt after persisted backoff; never probe for proof."""
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if row['lease_until'] > self.clock() or doc['cancel_requested']:
                return False
            if doc['state'] not in ('WAITING_RESOURCE', 'RUNNING'):
                return False
            due = next((s for s in doc['steps'] if s['status'] == 'PROVIDER_FAILED'
                        and s.get('retry_at', float('inf')) <= self.clock()), None)
            if not due: return False
            # A quota failure pauses this attempt even if earlier provider
            # errors used the ordinary retry budget. The prior errors remain
            # recorded; they must not turn a later quota wait into exhaustion.
            waiting_on_quota = (doc.get('blocker') in
                                ('PROVIDER_QUOTA_EXHAUSTED', 'PROVIDER_RATE_LIMITED')
                                and due.get('quota_waits', 0) > 0)
            if not waiting_on_quota and (doc['used']['retries'] >= doc['limits']['max_retries']
                                         or due.get('resource_failures', 0) >= 3):
                doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', 'RESOURCE_RETRY_LIMIT'
                self._save(conn, doc, 'mission.resource_exhausted')
                return False
            if due['capability'] != 'model.text' or due['receipt']:
                return False
            if not waiting_on_quota:
                doc['used']['retries'] += 1
            if doc.get('waiting_since') is not None:
                doc['deadline'] += max(0, self.clock() - doc.pop('waiting_since'))
            due.update(status='PENDING', attempt_id=None)
            doc['state'], doc['blocker'] = 'RUNNING', None
            self._save(conn, doc, 'mission.resource_retry_due')
            return True

    def tick(self, session_id: str, ports: MissionPorts):
        token = self._claim(session_id)
        if token is None:
            return self.snapshot(session_id)
        try:
            with self._transaction() as conn:
                doc = self._owned(conn, session_id, token)
                completed = {s['id'] for s in doc['steps'] if s['status'] == 'DONE'}
                step = next((s for s in doc['steps'] if s['status'] in ('DISPATCHED', 'RECONCILE', 'VERIFYING')), None)
                if step is None:
                    step = next((s for s in doc['steps'] if s['status'] == 'PENDING'
                                 and set(s['depends_on']) <= completed), None)
                if step is None:
                    return doc
                if step['status'] in ('DISPATCHED', 'RECONCILE'):
                    step['status'] = 'RECONCILE'
                    self._block(conn, doc, 'UNCERTAIN_EFFECT')
                    return doc
                if doc['cancel_requested']:
                    doc['state'] = 'CANCELLED'
                    self._save(conn, doc, 'mission.cancelled')
                    return doc
                if self.clock() >= doc['deadline']:
                    self._block(conn, doc, 'TIME_LIMIT')
                    return doc
                completed = {s['id'] for s in doc['steps'] if s['status'] == 'DONE'}
                if not set(step['depends_on']) <= completed:
                    self._block(conn, doc, 'DEPENDENCY_UNSATISFIED')
                    return doc
                task = conn.execute("SELECT * FROM tasks WHERE id=?", (step['task_id'],)).fetchone()
                session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                member = conn.execute("""SELECT a.id FROM agents a JOIN team_memberships m ON m.agent_id=a.id
                    WHERE a.id=? AND a.archived=0 AND m.team_id=? AND m.left_at IS NULL""",
                    (task['assigned_agent_id'], session['team_id'])).fetchone()
                if member is None:
                    self._block(conn, doc, 'AGENT_UNAVAILABLE')
                    return doc
                try:
                    scope = ExecutionScope(**doc.get('execution_scope', {}))
                    scope.require(step.get('capability', ''), tuple(step.get('resources', ())),
                                  step.get('risk', 'HIGH'))
                except (ScopeViolation, TypeError):
                    self._block(conn, doc, 'SCOPE_REJECTED')
                    return doc
                context = ContextPacket(session['objective'], task['title'], task['instruction'],
                                        task['acceptance'], constraints=[json.dumps(asdict(scope))])
                if step.get('repairs'):
                    context.relevant_decisions.append('Repair the rejected result using verifier evidence: ' +
                                                       step['repairs'][-1]['reason'][:5000])
                for dep in doc['steps']:
                    if dep['id'] in step['depends_on'] and dep['receipt']:
                        context.relevant_decisions.append('Verified dependency ' + dep['id'] + ': ' +
                            json.dumps({'receipt': dep['receipt'], 'verification': dep['verification']})[:5000])
                verifying = step['status'] == 'VERIFYING'
                if not verifying:
                    charges = {'turns': int(step['kind'] in ('INVOKE','DELEGATE')),
                               'delegations': int(step['kind'] == 'DELEGATE'),
                               'actions': int(step['kind'] == 'ACTION')}
                    if any(doc['used'][k] + v > doc['limits']['max_' + k] for k, v in charges.items()):
                        self._block(conn, doc, 'BUDGET_LIMIT')
                        return doc
                    for k, v in charges.items():
                        doc['used'][k] += v
                    step['attempt_id'], step['status'] = new_id('attempt'), 'DISPATCHED'
                    doc['state'] = 'RUNNING'
                    conn.execute("UPDATE tasks SET state='RUNNING',updated_at=? WHERE id=?", (self.clock(), task['id']))
                    self._save(conn, doc, 'mission.dispatched')
                    if step['kind'] == 'DELEGATE':
                        conn.execute('INSERT INTO handoffs VALUES(?,?,?,?,?,?,?,?,?,?,?)', (
                            'handoff:' + step['attempt_id'], session_id, session['team_id'],
                            conn.execute('SELECT role FROM agents WHERE id=?', (task['assigned_agent_id'],)).fetchone()[0],
                            task['created_by_agent_id'], task['assigned_agent_id'], 'DEPENDENCY_READY',
                            context.render()[:12000], json.dumps([task['id']]), 'COMPLETED', self.clock()))
                dispatch = Dispatch(session_id, step['id'], step['task_id'], task['assigned_agent_id'],
                                    step['attempt_id'], min(doc['deadline'], self.clock() + self.lease_s), context,
                                    scope, step['capability'], tuple(step['resources']), step['risk'])
                receipt = Receipt(**step['receipt']) if verifying else None
            # Never hold a SQLite write lock during execution or verification.
            if not verifying:
                result = ports.execute(dispatch)
                if not isinstance(result, Receipt) or not result.artifact_ref:
                    raise ValueError("Execution must return an artifact receipt")
                self._observe(dispatch, 'RECEIPT', result)
                with self._transaction() as conn:
                    doc = self._owned(conn, session_id, token)
                    step = next(s for s in doc['steps'] if s['id'] == dispatch.step_id)
                    step['receipt'] = asdict(result)
                    if self.clock() >= dispatch.deadline:
                        step['status'] = 'RECONCILE'
                        self._block(conn, doc, 'LATE_EXECUTION')
                        return doc
                    step['status'] = 'VERIFYING'
                    doc['state'] = 'CANCELLING' if doc['cancel_requested'] else 'VERIFYING'
                    self._save(conn, doc, 'mission.result_received')
            else:
                result = ports.verify(dispatch, receipt)
                if not isinstance(result, Verification) or result.verdict not in ('PASS','FAIL','INCONCLUSIVE') or not result.evidence_ref:
                    raise ValueError("Verifier must provide a typed verdict and evidence")
                self._observe(dispatch, 'VERIFICATION', result)
                with self._transaction() as conn:
                    doc = self._owned(conn, session_id, token)
                    step = next(s for s in doc['steps'] if s['id'] == dispatch.step_id)
                    step['verification'] = asdict(result)
                    if self.clock() >= dispatch.deadline:
                        self._block(conn, doc, 'LATE_VERIFICATION')
                    elif result.verdict != 'PASS':
                        step['status'] = 'VERIFYING'
                        self._block(conn, doc, 'VERIFICATION_' + result.verdict)
                    else:
                        step['status'] = 'DONE'
                        conn.execute("UPDATE tasks SET state='COMPLETED', result=?,updated_at=? WHERE id=?",
                                     (receipt.summary, self.clock(), step['task_id']))
                        doc['state'] = 'CANCELLED' if doc['cancel_requested'] else (
                            ('PLANNING' if doc.get('awaiting_expansion') else 'COMPLETED')
                            if all(s['status'] == 'DONE' for s in doc['steps']) else 'RUNNING')
                        if doc['state'] == 'RUNNING' and all(s['status'] in ('DONE', 'PROVIDER_FAILED')
                                or (s['status'] == 'PENDING' and not set(s['depends_on']) <=
                                    {x['id'] for x in doc['steps'] if x['status'] == 'DONE'}) for s in doc['steps']):
                            doc['state'] = 'WAITING_RESOURCE'
                            doc.setdefault('waiting_since', self.clock())
                        self._save(conn, doc, 'mission.verified')
        except TextProviderFailure as exc:
            with self._transaction() as conn:
                try:
                    doc = self._owned(conn, session_id, token)
                except LeaseLost:
                    pass
                else:
                    step = next(s for s in doc['steps'] if s['id'] == dispatch.step_id)
                    step['status'] = 'PROVIDER_FAILED'
                    self._block(conn, doc, 'PROVIDER_' + exc.availability)
                    if doc.get('resource_waiting') and exc.availability in (
                            'BUSY', 'RATE_LIMITED', 'QUOTA_EXHAUSTED', 'PROVIDER_ERROR', 'OFFLINE', 'ERROR'):
                        # Cota esgotada nao e falha intermitente: e uma espera com hora
                        # para acabar (o plano do dono renova). Contar isso como tentativa
                        # queimada mata a missao muito antes da cota voltar. Entao ela
                        # espera mais e nao consome o orcamento de falha real.
                        if exc.availability in _QUOTA_WAIT_STATES:
                            step['quota_waits'] = step.get('quota_waits', 0) + 1
                            step['retry_at'] = self.clock() + min(
                                _QUOTA_BACKOFF_MAX_S, 300 * 2 ** (step['quota_waits'] - 1))
                        else:
                            step['resource_failures'] = step.get('resource_failures', 0) + 1
                            step['retry_at'] = self.clock() + min(900, 60 * 2 ** (step['resource_failures'] - 1))
                        complete = {s['id'] for s in doc['steps'] if s['status'] == 'DONE'}
                        ready = any(s['status'] == 'PENDING' and set(s['depends_on']) <= complete for s in doc['steps'])
                        doc['state'] = 'RUNNING' if ready else 'WAITING_RESOURCE'
                        if not ready: doc.setdefault('waiting_since', self.clock())
                        self._save(conn, doc, 'mission.resource_wait')
        except LeaseLost:
            # The new owner must reconcile; this stale result cannot overwrite it.
            pass
        except Exception as exc:
            failure = classify_step_failure(exc)
            with self._transaction() as conn:
                try:
                    doc = self._owned(conn, session_id, token)
                except LeaseLost:
                    pass
                else:
                    step = next(s for s in doc['steps'] if s['id'] == dispatch.step_id)
                    if step['status'] == 'DISPATCHED':
                        step['status'] = 'RECONCILE'
                    failure.update(step_id=step['id'], attempt_id=step.get('attempt_id'),
                                   step_status=step['status'], at=self.clock())
                    if failure['blocker'] is None:
                        failure['blocker'] = ('UNCERTAIN_EFFECT' if step['status'] == 'RECONCILE'
                                              else 'VERIFIER_ERROR')
                    else:
                        # The step status stays RECONCILE on purpose: only the
                        # failure record may assert that nothing ran. A diagnosis
                        # names the error, it never weakens the safe default.
                        failure['status_note'] = 'RECONCILE_KEPT_CONSERVATIVELY'
                    step['failure'] = failure
                    doc['last_failure'] = failure
                    self._block(conn, doc, failure['blocker'])
        finally:
            with self._transaction() as conn:
                conn.execute("UPDATE mission_controls SET lease_token=NULL,lease_until=0,lease_owner=NULL WHERE session_id=? AND lease_token=?",
                             (session_id, token))
        return self.snapshot(session_id)

    def _observe(self, dispatch, kind, result):
        # Evidence from a stale worker is append-only, never a completion or replay authorization.
        # Executors must additionally persist their own receipt before returning (process-loss window).
        with self._transaction() as conn:
            conn.execute('INSERT INTO mission_observations VALUES(?,?,?,?,?,?,?)',
                         (new_id('obs'), dispatch.session_id, dispatch.step_id, dispatch.attempt_id,
                          kind, json.dumps(asdict(result)), self.clock()))

    def observations(self, session_id):
        conn = self.store._connect()
        try:
            return [dict(row) for row in conn.execute(
                'SELECT * FROM mission_observations WHERE session_id=? ORDER BY occurred_at,id', (session_id,))]
        finally:
            conn.close()

    def resume_after_quota(self, session_id, *, proof_run_id: str):
        """Resume a known failed text attempt, never replay an uncertain effect.

        A fresh completed runtime probe must match the assigned agent/model/effort.
        Quota waiting pauses the deadline, not the turn/action/retry budgets.
        This method never creates a Mission, changes assignments or owner touches.
        """
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            stamp = self.clock()
            if (doc['state'] not in ('BLOCKED', 'WAITING_RESOURCE') or doc['blocker'] != 'PROVIDER_QUOTA_EXHAUSTED'
                    or doc['cancel_requested'] or doc['used']['retries'] >= doc['limits']['max_retries']
                    or conn.execute('SELECT 1 FROM mission_controls WHERE lease_token IS NOT NULL AND lease_until>?', (stamp,)).fetchone()):
                return False
            pending = [s for s in doc['steps'] if s['status'] != 'DONE']
            if not pending or pending[0]['status'] != 'PROVIDER_FAILED':
                return False
            step = pending[0]
            if (step['capability'] != 'model.text' or step['kind'] not in ('INVOKE', 'DELEGATE')
                    or any(s['status'] != 'PENDING' for s in pending[1:])
                    or step['receipt'] or step['verification']
                    or doc['used']['turns'] >= doc['limits']['max_turns']):
                return False
            agent = conn.execute('SELECT a.* FROM agents a JOIN tasks t ON t.assigned_agent_id=a.id '
                'JOIN sessions s ON s.id=t.session_id JOIN team_memberships m ON m.agent_id=a.id '
                'AND m.team_id=s.team_id WHERE t.id=? AND s.id=? AND a.archived=0 AND m.left_at IS NULL',
                (step['task_id'], session_id)).fetchone()
            proof = conn.execute('SELECT * FROM runs WHERE id=? AND session_id=?', (proof_run_id, session_id)).fetchone()
            if (agent is None or proof is None or proof['state'] != 'COMPLETED'
                    or proof['task_id'] is not None or not proof['provider_session_id'] or proof['error']
                    or any(proof[k] != agent[v] for k, v in [('agent_id', 'id'), ('provider_id', 'provider_id'), ('model', 'model'), ('effort', 'effort')])
                    or proof['started_at'] < doc['updated_at'] or proof['ended_at'] is None
                    or not 0 <= stamp - proof['ended_at'] <= 900):
                return False
            ExecutionScope(**doc['execution_scope']).require('model.text',
                ('provider:' + agent['provider_id'] + '/' + agent['model'],), 'LOW')
            remaining = doc['deadline'] - doc['updated_at']
            if remaining <= 0:
                return False
            doc.setdefault('provider_recoveries', []).append({'proof_run_id': proof_run_id,
                'previous_attempt_id': step['attempt_id'], 'previous_deadline': doc['deadline'],
                'agent_id': agent['id'], 'resumed_at': stamp})
            doc['deadline'] = stamp + remaining
            doc['used']['retries'] += 1
            step.update(status='PENDING', attempt_id=None)
            doc['state'], doc['blocker'] = 'QUEUED', None
            conn.execute("UPDATE tasks SET state='CREATED',updated_at=? WHERE id=?", (stamp, step['task_id']))
            conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0,lease_owner=NULL WHERE session_id=?', (session_id,))
            self._save(conn, doc, 'mission.provider_resumed')
            return True

    def retry_text_with(self, session_id, agent_id):
        """Controller-owned bounded handoff. Caller selects from compatible text-only agents."""
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if row['lease_token'] and row['lease_until'] > self.clock():
                return False
            step = next((s for s in doc['steps'] if s['status'] == 'PROVIDER_FAILED'), None)
            if (step is None or step['capability'] != 'model.text' or doc['cancel_requested']
                    or self.clock() >= doc['deadline'] or doc['used']['retries'] >= doc['limits']['max_retries']):
                return False
            session = conn.execute('SELECT team_id,objective FROM sessions WHERE id=?', (session_id,)).fetchone()
            agent = conn.execute('SELECT a.* FROM agents a JOIN team_memberships m ON m.agent_id=a.id '
                                 'WHERE a.id=? AND a.archived=0 AND m.team_id=? AND m.left_at IS NULL',
                                 (agent_id, session['team_id'])).fetchone()
            if agent is None:
                return False
            resource = 'provider:' + agent['provider_id'] + '/' + agent['model']
            ExecutionScope(**doc['execution_scope']).require('model.text', (resource,), 'LOW')
            previous = conn.execute('SELECT assigned_agent_id FROM tasks WHERE id=?', (step['task_id'],)).fetchone()[0]
            if previous == agent_id:
                return False
            conn.execute('UPDATE tasks SET assigned_agent_id=?,updated_at=? WHERE id=?',
                         (agent_id, self.clock(), step['task_id']))
            conn.execute('INSERT INTO handoffs(id,session_id,team_id,role,from_agent_id,to_agent_id,reason,'
                         'context_summary,unfinished_task_ids,outcome,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (new_id('handoff'), session_id, session['team_id'], agent['role'], previous, agent_id,
                          doc['blocker'], session['objective'], json.dumps([step['task_id']]), 'COMPLETED', self.clock()))
            step['resources'], step['status'] = [resource], 'PENDING'
            doc['used']['retries'] += 1
            doc['state'], doc['blocker'] = 'QUEUED', None
            self._save(conn, doc, 'mission.handoff')
            return True

    def recheck_verification(self, session_id, *, reason: str):
        """Trusted backend repair: recheck an existing receipt, never repeat execution or extend budgets."""
        if not reason.strip():
            raise ValueError('A verifier repair needs a reason')
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if row['lease_token'] and row['lease_until'] > self.clock():
                raise ValueError('Executor still owns its lease')
            if doc['cancel_requested'] or self.clock() >= doc['deadline']:
                raise ValueError('Mission cancelled or expired')
            step = next((s for s in doc['steps'] if s['status'] != 'DONE'), None)
            if (doc['state'] != 'BLOCKED' or doc['blocker'] not in ('VERIFICATION_FAIL', 'VERIFICATION_INCONCLUSIVE', 'VERIFIER_ERROR')
                    or step is None or step['status'] != 'VERIFYING' or not step['receipt']):
                raise ValueError('No failed verification with a retained receipt')
            step.setdefault('verification_rechecks', []).append({'reason': reason, 'at': self.clock(),
                                                                 'previous': step['verification']})
            doc['state'], doc['blocker'] = 'VERIFYING', None
            self._save(conn, doc, 'mission.verification_recheck')

    def cancel(self, session_id):
        with self._transaction() as conn:
            doc, _ = self._load(conn, session_id)
            if doc['state'] in ('COMPLETED', 'CANCELLED', 'FAILED'):
                return
            doc['cancel_requested'] = True
            uncertain = any(s['status'] in ('DISPATCHED', 'RECONCILE') for s in doc['steps'])
            doc['state'] = 'CANCELLING' if uncertain else 'CANCELLED'
            self._save(conn, doc, 'mission.cancel_requested')

    def reconcile(self, session_id, step_id, *, verdict: str, evidence_ref: str,
                  receipt: Receipt | None = None):
        """Trusted reconciliation port only: never infer NOT_APPLIED from silence.

        APPLIED requires subsequent independent verification. NOT_APPLIED may
        authorize one bounded retry; UNKNOWN stays blocked. No external action.
        """
        if verdict not in ('APPLIED','NOT_APPLIED','UNKNOWN') or not evidence_ref:
            raise ValueError("Reconciliation needs an explicit verdict and evidence")
        with self._transaction() as conn:
            doc, row = self._load(conn, session_id)
            if row['lease_token'] and row['lease_until'] > self.clock():
                raise ValueError("Executor still owns its lease")
            step = next((s for s in doc['steps'] if s['id'] == step_id), None)
            if step is None or step['status'] not in ('DISPATCHED','RECONCILE'):
                raise ValueError("Step is not awaiting reconciliation")
            step['reconciliation'] = {'verdict': verdict, 'evidence_ref': evidence_ref}
            if verdict == 'UNKNOWN':
                step['status'] = 'RECONCILE'
                self._block(conn, doc, 'UNCERTAIN_EFFECT')
            elif verdict == 'APPLIED':
                if not isinstance(receipt, Receipt) or not receipt.artifact_ref:
                    raise ValueError("Applied action needs a receipt")
                step['receipt'], step['status'] = asdict(receipt), 'VERIFYING'
                doc['blocker'] = None
                doc['state'] = 'CANCELLED' if doc['cancel_requested'] else 'VERIFYING'
                self._save(conn, doc, 'mission.reconciled')
            elif doc['cancel_requested']:
                step['status'], doc['state'], doc['blocker'] = 'PENDING', 'CANCELLED', None
                self._save(conn, doc, 'mission.cancelled')
            elif doc['used']['retries'] >= doc['limits']['max_retries']:
                self._block(conn, doc, 'RETRY_LIMIT')
            else:
                doc['used']['retries'] += 1
                step['status'], doc['state'], doc['blocker'] = 'PENDING', 'QUEUED', None
                self._save(conn, doc, 'mission.retry_authorized')
