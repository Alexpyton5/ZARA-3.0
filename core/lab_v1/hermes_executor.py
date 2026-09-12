"""Governed Hermes file capability with durable action receipts and independent verification."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation, canonical_resource
from core.lab_v1.mission_controller import Dispatch, Receipt, Verification
from core.lab_v1.store import LabStore
from core.tool_definition import ToolDefinition
from core.tool_execution_wrapper import ExecutionWrapper
from core.tool_router import ToolRequest, ToolRouter


@dataclass(frozen=True)
class ActionRequest:
    action_id: str
    mission_id: str
    task_id: str
    requested_by: str
    objective: str
    capability: str
    arguments: dict
    execution_scope: ExecutionScope
    risk: str
    authorization_state: str
    expected_result: str
    verification_criteria: str
    rollback_strategy: str


class _ActionRegistry:
    """Private allowlist fed into the existing ToolRouter; no global tools fallback."""
    def __init__(self, tool):
        self.tool = tool

    def get(self, name):
        return self.tool if name == self.tool.name else None

    def validate_schema(self, name, parameters):
        return (name == self.tool.name and not parameters, 'Unexpected tool arguments')


class HermesFileExecutor:
    def __init__(self, sandbox: Path, *, hermes_root: Path | None = None):
        self.sandbox = Path(canonical_resource(str(sandbox)))
        self.root = hermes_root or Path(os.environ.get('LOCALAPPDATA', '')) / 'hermes' / 'hermes-agent'
        self.python = self.root / 'venv' / 'Scripts' / 'python.exe'

    def execute(self, request: ActionRequest, deadline: float) -> dict:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError()
        path = canonical_resource(request.arguments['path'])
        request.execution_scope.require(request.capability, (path,), request.risk)
        if self.sandbox not in Path(path).parents:
            raise ScopeViolation('Only a file inside the mission sandbox is executable')
        if not self.python.is_file():
            raise RuntimeError('HERMES_NOT_INSTALLED')
        runtime_home = self.sandbox / '.hermes-runtime'
        runtime_home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k.upper() in
               ('SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')}
        env.update(HERMES_HOME=str(runtime_home), PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
        payload = {'hermes_root': str(self.root), 'sandbox': str(self.sandbox),
                   'timeout_s': max(1, int(remaining)), 'path': path,
                   'capability': request.capability, 'content': request.arguments.get('content', '')}
        proc = subprocess.Popen([str(self.python), '-I', str(Path(__file__).with_name('hermes_runner.py'))],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', cwd=self.sandbox, env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            output, _ = proc.communicate(json.dumps(payload), timeout=remaining)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            else:
                proc.kill()
            proc.communicate(timeout=10)
            raise TimeoutError('HERMES_TIMEOUT_EFFECT_UNCERTAIN')
        try:
            result = json.loads(output)
        except (ValueError, TypeError):
            result = {'ok': False, 'error': 'HERMES_INVALID_RESPONSE'}
        return {'success': proc.returncode == 0 and result.get('ok') is True, 'data': result}


class HermesActionPorts:
    """Requests are persisted before dispatch. Model-selected scope is never trusted."""
    def __init__(self, store: LabStore, executor: HermesFileExecutor):
        self.store, self.executor = store, executor
        with store._connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS mission_action_requests (
                    action_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id), document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mission_action_results (
                    attempt_id TEXT PRIMARY KEY, action_id TEXT NOT NULL REFERENCES mission_action_requests(action_id),
                    document TEXT NOT NULL);
            ''')
            conn.execute("INSERT OR IGNORE INTO schema_meta VALUES('mission_actions_version','1')")

    def prepare(self, request: ActionRequest):
        # Immutable request: a plan cannot change an already dispatched action's arguments.
        document = asdict(request)
        document['execution_scope']['allowed_resources'] = [
            canonical_resource(r) for r in request.execution_scope.allowed_resources]
        with self.store._connect() as conn:
            conn.execute('INSERT INTO mission_action_requests VALUES(?,?,?,?)',
                         (request.action_id, request.mission_id, request.task_id, json.dumps(document)))

    def _request(self, dispatch):
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM mission_action_requests WHERE task_id=? AND session_id=?',
                               (dispatch.task_id, dispatch.session_id)).fetchone()
        if row is None:
            raise ScopeViolation('No prepared action')
        data = json.loads(row[0])
        data['execution_scope'] = ExecutionScope(**data['execution_scope'])
        request = ActionRequest(**data)
        path = canonical_resource(request.arguments.get('path', ''))
        if (request.requested_by != dispatch.agent_id or request.capability != dispatch.capability
                or (path,) != tuple(canonical_resource(r) for r in dispatch.resources)
                or request.risk != dispatch.risk
                or json.dumps(asdict(request.execution_scope), sort_keys=True) !=
                    json.dumps(asdict(dispatch.execution_scope), sort_keys=True)):
            raise ScopeViolation('Action differs from authorized dispatch')
        dispatch.execution_scope.require(request.capability, (path,), request.risk)
        if request.authorization_state != dispatch.execution_scope.authorization_state:
            raise ScopeViolation('Action cannot change authorization')
        if request.capability not in ('files.write', 'files.delete') or request.risk != 'LOW':
            raise ScopeViolation('Only low-risk sandbox file operations are implemented')
        if Path(path).suffix.lower() not in ('.txt', '.md', '.json'):
            from core.lab_v1.golden_check import AUTHORIZATION, validate_code
            if dispatch.execution_scope.authorization_ref == AUTHORIZATION:
                if request.capability != 'files.write' or Path(path).name != 'reply_status.py':
                    raise ScopeViolation('Golden Path allows only its sandbox classifier')
                validate_code(request.arguments.get('content', ''))
            else:
                self._validate_reviewed_source(request, dispatch, path)
        if Path(path).name.startswith('.') or '.hermes-runtime' in Path(path).parts:
            raise ScopeViolation('Runtime configuration is not a task resource')
        if set(request.arguments) - {'path', 'content', 'before_sha256'}:
            raise ScopeViolation('Unknown action arguments')
        content = request.arguments.get('content', '')
        if not isinstance(content, str) or len(content.encode('utf-8')) > 16384:
            raise ScopeViolation('Content exceeds bounded file capability')
        if not request.expected_result or not request.verification_criteria or not request.rollback_strategy:
            raise ScopeViolation('Action requires expected outcome, verification and rollback policy')
        return request

    @staticmethod
    def _validate_reviewed_source(request, dispatch, path):
            from core.lab_v1.evolution_repairs import validate_change, candidate, reverse_candidate, digest
            source = Path(path).read_bytes().decode('utf-8') if Path(path).is_file() else ''
            content = request.arguments.get('content', '')
            if source == content:  # Verification runs after the effect. Reconstruct the uniquely permitted preimage.
                if dispatch.execution_scope.authorization_ref.startswith('evolution:rollback:'):
                    source = candidate(source)
                else:
                    source = reverse_candidate(source)
            if request.capability != 'files.write' or not validate_change(Path(path), source,
                    content, dispatch.execution_scope.authorization_ref) or digest(source) != request.arguments.get('before_sha256'):
                raise ScopeViolation('Source change is outside the reviewed repair catalog')

    def _save_result(self, attempt, action_id, data):
        with self.store._connect() as conn:
            conn.execute('INSERT INTO mission_action_results VALUES(?,?,?) ON CONFLICT(attempt_id) '
                         'DO UPDATE SET document=excluded.document', (attempt, action_id, json.dumps(data)))

    def execute(self, dispatch: Dispatch) -> Receipt:
        request = self._request(dispatch)
        path = Path(request.arguments['path'])
        before = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if before != request.arguments.get('before_sha256'):
            raise ScopeViolation('Resource changed since authorization')
        if request.capability == 'files.delete':
            # Deletion is rollback only: prove this mission created and verified these exact bytes.
            with self.store._connect() as conn:
                rows = conn.execute('SELECT r.document FROM mission_action_results r JOIN mission_action_requests q '
                                    'ON q.action_id=r.action_id WHERE q.session_id=?', (dispatch.session_id,)).fetchall()
            if not before or not any((d := json.loads(row[0])).get('verified_sha256') == before
                                     and d.get('path') == str(path) and d.get('created') is True for row in rows):
                raise ScopeViolation('Delete is only permitted for a verified file created by this mission')
        started = time.time()
        data = {'action_id': request.action_id, 'status': 'DISPATCHED', 'path': str(path),
                'before_sha256': before, 'created': before is None,
                'verification_status': 'NOT_VERIFIED', 'rollback_available': False,
                'started_at': started, 'changed_resources': [], 'evidence': None}
        with self.store._connect() as conn:
            # Unique attempt prevents re-execution even if called outside the controller.
            conn.execute('INSERT INTO mission_action_results VALUES(?,?,?)',
                         (dispatch.attempt_id, request.action_id, json.dumps(data)))
        wrapper = ExecutionWrapper(lambda: self.executor.execute(request, dispatch.deadline),
                                   name=request.capability, timeout_ms=max(1, int((dispatch.deadline - started) * 1000)))
        router = ToolRouter(_ActionRegistry(ToolDefinition(request.capability, request.objective, 'files',
                                                          executor=wrapper.execute)))
        router.set_permission_checker(lambda name, args: name == dispatch.capability and not args)
        result = router.route(ToolRequest(request.capability))
        data.update(status='RECEIVED' if result.success else 'UNCERTAIN_EFFECT', ended_at=time.time(),
                    receipt=result.data, error=None if result.success else 'EXECUTOR_FAILED')
        self._save_result(dispatch.attempt_id, request.action_id, data)
        if not result.success:
            raise RuntimeError('EXECUTOR_FAILED_EFFECT_UNCERTAIN')
        return Receipt('action:' + dispatch.attempt_id, request.expected_result)

    def verify(self, dispatch: Dispatch, receipt: Receipt) -> Verification:
        request = self._request(dispatch)
        if receipt.artifact_ref != 'action:' + dispatch.attempt_id:
            raise ScopeViolation('Receipt belongs to another action')
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM mission_action_results WHERE attempt_id=? AND action_id=?',
                               (dispatch.attempt_id, request.action_id)).fetchone()
        data = json.loads(row[0])
        path = Path(canonical_resource(request.arguments['path']))
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        expected = hashlib.sha256(request.arguments.get('content', '').encode('utf-8')).hexdigest()
        passed = digest == expected if request.capability == 'files.write' else not path.exists()
        data.update(verification_status='PASS' if passed else 'FAIL', verified_sha256=digest,
                    evidence={'method': 'independent_sha256_read' if request.capability == 'files.write' else 'independent_absence_check',
                              'expected_sha256': expected if request.capability == 'files.write' else None,
                              'observed_sha256': digest, 'checked_at': time.time()},
                    rollback_available=passed and request.capability == 'files.write' and data['created'],
                    changed_resources=[str(path)] if passed else [])
        self._save_result(dispatch.attempt_id, request.action_id, data)
        return Verification('PASS' if passed else 'FAIL', 'action-evidence:' + dispatch.attempt_id)
