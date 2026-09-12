"""Internal, bounded file actions for ZARA Lab mission sandboxes."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation, canonical_resource
from core.lab_v1.mission_controller import Dispatch, Receipt, Verification
from core.tool_definition import ToolDefinition
from core.tool_execution_wrapper import ExecutionWrapper
from core.tool_router import ToolRouter, ToolRequest


@dataclass(frozen=True)
class SandboxActionRequest:
    action_id: str
    mission_id: str
    task_id: str
    requested_by: str
    capability: str
    path: str
    content: str
    execution_scope: ExecutionScope
    risk: str = 'LOW'


class SandboxFileExecutor:
    def __init__(self, sandbox: Path):
        self.sandbox = Path(canonical_resource(str(sandbox)))

    def execute(self, request: SandboxActionRequest, deadline: float) -> dict:
        if time.time() >= deadline:
            raise TimeoutError()
        path = Path(canonical_resource(request.path))
        if self.sandbox != path.parent and self.sandbox not in path.parents:
            raise ScopeViolation('Only mission sandbox files are allowed')
        request.execution_scope.require(request.capability, (str(path),), request.risk)
        path.parent.mkdir(parents=True, exist_ok=True)
        canonical_resource(str(path))
        # A mission may create a new artifact; overwriting pre-existing bytes is
        # not an implicit side effect of a retry or a filename from the planner.
        with path.open('xb') as stream:
            stream.write(request.content.encode('utf-8'))
            stream.flush()
        return {'success': True, 'data': {'bytes': len(request.content.encode('utf-8'))}}


class SandboxActionPorts:
    """Persist an immutable request and idempotent attempt receipt before effects."""
    def __init__(self, store, executor):
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

    def prepare(self, request: SandboxActionRequest):
        document = asdict(request)
        with self.store._connect() as conn:
            old = conn.execute('SELECT document FROM mission_action_requests WHERE task_id=?', (request.task_id,)).fetchone()
            if old:
                if json.loads(old[0]) != json.loads(json.dumps(document)): raise ScopeViolation('Immutable action request changed')
                return
            conn.execute('INSERT INTO mission_action_requests VALUES(?,?,?,?)',
                         (request.action_id, request.mission_id, request.task_id, json.dumps(document)))

    def _request(self, dispatch: Dispatch) -> SandboxActionRequest:
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM mission_action_requests WHERE task_id=? AND session_id=?',
                               (dispatch.task_id, dispatch.session_id)).fetchone()
        if row is None:
            raise ScopeViolation('No prepared sandbox action')
        data = json.loads(row[0]); data['execution_scope'] = ExecutionScope(**data['execution_scope'])
        request = SandboxActionRequest(**data)
        path = canonical_resource(request.path)
        if (request.requested_by != dispatch.agent_id or request.capability != 'files.write'
                or dispatch.capability != request.capability
                or (path,) != tuple(canonical_resource(r) for r in dispatch.resources)
                or request.risk != dispatch.risk or request.mission_id != dispatch.session_id
                or json.dumps(asdict(request.execution_scope), sort_keys=True) != json.dumps(asdict(dispatch.execution_scope), sort_keys=True)):
            raise ScopeViolation('Action differs from Mission Controller dispatch')
        dispatch.execution_scope.require('files.write', (path,), 'LOW')
        if not isinstance(request.content, str) or len(request.content.encode('utf-8')) > 32768:
            raise ScopeViolation('Sandbox artifact exceeds bounded file limit')
        return request

    def execute(self, dispatch: Dispatch) -> Receipt:
        request = self._request(dispatch)
        path = Path(request.path)
        before = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if path.exists(): raise ScopeViolation('Sandbox output already exists')
        record = {'status': 'DISPATCHED', 'path': str(path), 'before_sha256': before,
                  'created': before is None, 'verification_status': 'NOT_VERIFIED'}
        with self.store._connect() as conn:
            conn.execute('INSERT INTO mission_action_results VALUES(?,?,?)',
                         (dispatch.attempt_id, request.action_id, json.dumps(record)))
        class Registry:
            def __init__(self, tool): self.tool = tool
            def get(self, name): return self.tool if name == self.tool.name else None
            def validate_schema(self, name, parameters): return (name == self.tool.name and not parameters, 'Arguments forbidden')
        wrapper = ExecutionWrapper(lambda: self.executor.execute(request, dispatch.deadline), name='files.write',
            timeout_ms=max(1, int((dispatch.deadline - time.time()) * 1000)))
        router = ToolRouter(Registry(ToolDefinition('files.write', 'Create mission sandbox artifact', 'files', executor=wrapper.execute)))
        router.set_permission_checker(lambda name, args: name == dispatch.capability and not args)
        result = router.route(ToolRequest('files.write'))
        if result.success is not True:
            raise RuntimeError('SANDBOX_EFFECT_UNCERTAIN')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record.update(status='RECEIVED', sha256=digest, bytes=path.stat().st_size)
        with self.store._connect() as conn:
            conn.execute('UPDATE mission_action_results SET document=? WHERE attempt_id=?',
                         (json.dumps(record), dispatch.attempt_id))
        return Receipt('sandbox-action:' + dispatch.attempt_id, f'{path.name} gravado; sha256={digest}')

    def verify(self, dispatch: Dispatch, receipt: Receipt) -> Verification:
        request = self._request(dispatch); path = Path(request.path)
        if receipt.artifact_ref != 'sandbox-action:' + dispatch.attempt_id:
            raise ScopeViolation('Receipt from another attempt')
        canonical_resource(str(path))
        passed = path.is_file() and path.read_bytes() == request.content.encode('utf-8')
        if passed and path.suffix.lower() == '.py':
            try:
                compile(request.content, str(path), 'exec')
            except SyntaxError:
                passed = False
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM mission_action_results WHERE attempt_id=? AND action_id=?',
                               (dispatch.attempt_id, request.action_id)).fetchone()
            record = json.loads(row[0]) if row else {}
            passed = passed and bool(row) and record.get('status') == 'RECEIVED'
            record['verification_status'] = 'PASS' if passed else 'FAIL'
            conn.execute('UPDATE mission_action_results SET document=? WHERE attempt_id=?',
                         (json.dumps(record), dispatch.attempt_id))
        return Verification('PASS' if passed else 'FAIL', 'sandbox-evidence:' + dispatch.attempt_id)
