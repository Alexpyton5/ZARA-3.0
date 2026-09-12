"""One real, isolated Hermes file write/readback/rollback mission. No model calls."""
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lab_v1.domain import AgentProfile, Session, Task, Team, TeamMembership
from core.lab_v1.execution_scope import ExecutionScope
from core.lab_v1.hermes_executor import ActionRequest, HermesActionPorts, HermesFileExecutor
from core.lab_v1.mission_controller import MissionController, MissionLimits, MissionStep
from core.lab_v1.store import LabStore


def main():
    target = ROOT / 'artifacts' / 'autonomy-one-shot' / ('hermes-proof-' + str(time.time_ns()))
    sandbox = target / 'sandbox'
    sandbox.mkdir(parents=True)
    store = LabStore(target / 'lab.db')
    store.initialize()
    store.save_team(Team('proof-team', 'Isolated Hermes executor proof'))
    # Executor identity is not a fake language-model agent. It cannot invoke a provider.
    store.save_agent(AgentProfile('proof-executor', 'Hermes file executor', 'hermes_tool', 'NONE',
                                  capabilities=['files.write', 'files.delete']))
    store.save_membership(TeamMembership('member', 'proof-team', 'proof-executor'))
    store.save_session(Session('proof-mission', 'proof-team', 'Write, verify and remove a sandbox proof file'))
    path, content = sandbox / 'proof.txt', 'ZARA_HERMES_OK'
    scope = ExecutionScope((str(sandbox),), ('files.write', 'files.delete'),
                           authorization_state='POLICY_AUTHORIZED', authorization_ref='Alex:one-shot:stage2:sandbox-proof')
    ports = HermesActionPorts(store, HermesFileExecutor(sandbox))
    steps = []
    for kind in ('write', 'delete'):
        store.save_task(Task(kind, 'proof-mission', kind, 'Bounded sandbox proof', 'proof-executor',
                             assigned_agent_id='proof-executor', acceptance='Exact bytes' if kind == 'write' else 'File absent'))
        args = {'path': str(path), 'content': content} if kind == 'write' else {
            'path': str(path), 'before_sha256': hashlib.sha256(content.encode()).hexdigest()}
        ports.prepare(ActionRequest(kind, 'proof-mission', kind, 'proof-executor', kind, 'files.' + kind,
                                    args, scope, 'LOW', scope.authorization_state, 'Exact bytes' if kind == 'write' else 'File absent',
                                    'Independent readback', 'Remove only the file created by this mission'))
        steps.append(MissionStep(kind, kind, 'ACTION', () if kind == 'write' else ('write',), 'files.' + kind, (str(path),)))
    ctl = MissionController(store, lease_s=90)
    ctl.plan('proof-mission', steps, MissionLimits(max_turns=0, max_delegations=0, max_actions=2, timeout_s=240), scope=scope)
    for _ in range(4):
        result = ctl.tick('proof-mission', ports)
        if result['state'] in ('BLOCKED', 'FAILED', 'CANCELLED'):
            break
    with store._connect() as conn:
        actions = [json.loads(row[0]) for row in conn.execute('SELECT document FROM mission_action_results')]
    report = {'state': result['state'], 'blocker': result['blocker'], 'mission': result,
              'actions': actions, 'provider_calls': 0, 'owner_touches_during_execution': 0,
              'rollback_absence_verified': not path.exists(), 'database': str(store.db_path)}
    (target / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'state': result['state'], 'blocker': result['blocker'], 'report': str(target / 'result.json')}))
    return 0 if result['state'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
