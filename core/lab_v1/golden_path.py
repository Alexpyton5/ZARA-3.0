"""One-touch, sandbox-only ZARA self-improvement using the existing controller.

The review target is an actual production function, copied without behavioral
changes. A real CEO plans, a distinct worker produces code, pinned Hermes writes
only the candidate, and an independent process verifies behavior. No promotion.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time

from core.lab_v1.autopilot import Autopilot, _resource
from core.lab_v1.domain import Artifact, Decision, Message, MessageKind, Task, new_id
from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation
from core.lab_v1.golden_check import AUTHORIZATION, CASES, check, validate_code
from core.lab_v1.hermes_executor import ActionRequest, HermesActionPorts
from core.lab_v1.mission_controller import MissionLimits, MissionStep, Receipt, Verification, TextProviderFailure
from core.lab_v1.runtime import _extract_json


class GoldenPath(Autopilot):
    def start(self, intent):
        import core.reply_status as production
        original = Path(production.__file__).with_suffix('.py').read_text(encoding='utf-8')
        observation = check(original)
        if observation['passed'] or any(production._jarvis_reply_status(text) != row['actual']
                for (text, _), row in zip(CASES, observation['checks'])):
            raise ValueError('NO_REPRODUCED_CLASSIFIER_GAP')
        result = super().start(intent)
        if not result.get('success'):
            return result
        sid = result['session_id']
        metrics = self.metrics(sid)
        folder = Path(metrics['sandbox'])
        baseline = folder / 'baseline.txt'
        baseline.write_text(original, encoding='utf-8')
        target = folder / 'reply_status.py'
        plan_task, worker_task = self.store.get_task(sid + ':plan'), self.store.get_task(sid + ':draft')
        lead, worker = self.store.get_agent(plan_task.assigned_agent_id), self.store.get_agent(worker_task.assigned_agent_id)
        if lead.id == worker.id:
            raise ScopeViolation('SELF_DELEGATION')
        plan_task.title = 'CEO audita o defeito e delega a correcao'
        worker_task.title = 'Builder implementa a candidata segura'
        self.store.save_task(plan_task); self.store.save_task(worker_task)
        self.store.save_task(Task(sid + ':test', sid, 'Verifier executa testes independentes',
            'Comparar baseline e candidata; nenhum arquivo de producao pode mudar.', lead.id,
            assigned_agent_id=worker.id, acceptance='Todos os casos independentes passam; baseline reproduz falhas.'))
        scope = ExecutionScope((str(folder), *sorted({_resource(a) for a in self.candidates(self.store.get_session(sid).team_id)})),
            ('model.text', 'files.write', 'tests.reply_status'), authorization_state='POLICY_AUTHORIZED', authorization_ref=AUTHORIZATION)
        steps = [MissionStep('plan', plan_task.id, 'INVOKE', (), 'model.text', (_resource(lead),)),
                 MissionStep('draft', worker_task.id, 'DELEGATE', ('plan',), 'model.text', (_resource(worker),)),
                 MissionStep('write', sid + ':write', 'ACTION', ('draft',), 'files.write', (str(target),)),
                 MissionStep('test', sid + ':test', 'ACTION', ('write',), 'tests.reply_status', (str(target),))]
        self.controller.plan(sid, steps, MissionLimits(max_turns=3, max_delegations=2, max_retries=1,
                                                      max_actions=2, timeout_s=420), scope=scope)
        self._metrics(sid, workflow='golden_reply_status_v1', target=str(target), baseline=str(baseline),
                      observation=observation, lead_id=lead.id, worker_id=worker.id,
                      production_modified=False, content_review='BEHAVIORAL_PENDING')
        self.store.save_artifact(Artifact(new_id('artifact'), sid, plan_task.id, 'BASELINE',
                                         'Defeito reproduzido na funcao real', body=json.dumps(observation)))
        self.store.add_message(Message(new_id('message'), sid, MessageKind.ZARA, 'ZARA',
            f'Missao criada. {lead.name} recebeu o objetivo, o defeito reproduzido e o escopo de copia segura. Producao nao sera alterada.'))
        return result

    def run(self, sid):
        metrics = self.metrics(sid)
        ports = GoldenPorts(self, sid, metrics)
        for _ in range(14):
            previous = self.controller.snapshot(sid)
            doc = self.controller.tick(sid, ports)
            if doc['state'] == 'BLOCKED' and metrics.get('workflow') != 'golden_reply_status_v1':
                failed = next((s for s in doc['steps'] if s['status'] == 'PROVIDER_FAILED'), None)
                if failed:
                    task = self.store.get_task(failed['task_id'])
                    old = self.store.get_agent(task.assigned_agent_id)
                    exclude = (old.id, task.created_by_agent_id) if failed['kind'] == 'DELEGATE' else (old.id,)
                    alternatives = self.candidates(self.store.get_session(sid).team_id, old.role, exclude=exclude)
                    if alternatives and self.controller.retry_text_with(sid, alternatives[0].id):
                        self._metrics(sid, recovery_automatic=True)
                        continue
            if doc['state'] in ('BLOCKED', 'FAILED', 'CANCELLED', 'COMPLETED') or doc == previous:
                break
        if doc['state'] == 'COMPLETED':
            self._metrics(sid, verification_automatic=True, final_report_automatic=True,
                          content_review='BEHAVIORAL_PASS')
            mid = 'golden-report:' + sid
            if not any(m.id == mid for m in self.store.list_messages(sid)):
                self.store.add_message(Message(mid, sid, MessageKind.ZARA, 'ZARA',
                    f'Correcao verificada na copia segura: falhas de execucao deixam de ser classificadas como sucesso. '
                    f'{len(CASES)}/{len(CASES)} casos passaram em processo independente. Hermes gravou a candidata em '
                    f'{metrics["target"]}. Nenhuma alteracao foi promovida a producao.'))
                self.store.save_decision(Decision('golden-learning:' + sid, sid, None,
                    'Falhas explicitas no readback precisam bloquear etapas dependentes.',
                    'Candidata verificada pelos artefatos desta missao; producao permanece inalterada.'))
        return {'success': doc['state'] == 'COMPLETED', 'state': doc['state'], 'session_id': sid,
                'mission': doc, 'autonomy': self.metrics(sid)}


class GoldenPorts:
    def __init__(self, engine, sid, metrics):
        self.engine, self.sid, self.metrics, self.store = engine, sid, metrics, engine.store
        self.executor = engine.executor_factory(Path(metrics['sandbox']))
        self.actions = HermesActionPorts(self.store, self.executor)

    def artifact(self, dispatch, kind, title, body):
        artifact = Artifact(new_id('artifact'), self.sid, dispatch.task_id, kind, title, body=body)
        self.store.save_artifact(artifact)
        return Receipt(artifact.id, body)

    def execute(self, dispatch):
        if dispatch.capability == 'files.write':
            code = _extract_json(self.store.get_task(self.sid + ':draft').result)['code']
            validate_code(code)
            target = Path(self.metrics['target'])
            before = None
            if target.exists():
                original = Path(self.metrics['baseline']).read_text(encoding='utf-8')
                if target.read_text(encoding='utf-8') != original:
                    raise ScopeViolation('Existing candidate differs from the preserved baseline')
                before = hashlib.sha256(target.read_bytes()).hexdigest()
            request = ActionRequest('golden-action:' + self.sid, self.sid, dispatch.task_id, dispatch.agent_id,
                'Gravar a correcao do Builder somente na candidata', 'files.write',
                {'path': self.metrics['target'], 'content': code, 'before_sha256': before}, dispatch.execution_scope, 'LOW',
                'POLICY_AUTHORIZED', 'Candidata gravada por Hermes', 'SHA256 exato e testes independentes',
                'Baseline preservada. Producao intocada; nenhuma exclusao automatica.')
            self.actions.prepare(request)
            return self.actions.execute(dispatch)
        if dispatch.capability == 'tests.reply_status':
            dispatch.execution_scope.require(dispatch.capability, (self.metrics['target'],), 'LOW')
            code = Path(self.metrics['target']).read_text(encoding='utf-8')
            validate_code(code)
            proc = subprocess.run([str(self.executor.python), '-I', str(Path(__file__).with_name('golden_check.py')),
                                   self.metrics['target']], capture_output=True, text=True, encoding='utf-8',
                                  timeout=max(1, min(20, dispatch.deadline - time.time())),
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            value = json.loads(proc.stdout)
            value['exit_code'] = proc.returncode
            return self.artifact(dispatch, 'BEHAVIORAL_TEST', 'Verifier independente', json.dumps(value))
        task, agent = self.store.get_task(dispatch.task_id), self.store.get_agent(dispatch.agent_id)
        adapter = self.engine.runtime.registry.get(agent.provider_id)
        if not getattr(adapter, 'controlled_text_only', False):
            raise ScopeViolation('Text-only adapter required')
        dispatch.execution_scope.require('model.text', (_resource(agent),), 'LOW')
        original = Path(self.metrics['baseline']).read_text(encoding='utf-8')
        prompt = dispatch.context.render() + '\nActual production function copied unchanged:\n' + original
        prompt += '\nIndependent observed baseline: ' + json.dumps(self.metrics['observation'])
        if dispatch.step_id == 'plan':
            worker = self.store.get_agent(self.metrics['worker_id'])
            prompt += '\nEligible distinct worker (router checked model health, owner policy and membership): ' + json.dumps(worker.to_dict())
            system = ('You are Astra, the real ZARA CEO. Audit this small failure-classification bug. '
                'Return only JSON {"title":str,"instruction":str,"acceptance":str,"worker_agent_id":str}. '
                'Decide the specific bounded correction and delegate to the eligible distinct worker. '
                'Do not include hidden reasoning. No tools. No production changes.')
        else:
            plan = self.store.get_task(self.sid + ':plan')
            prompt += '\nVerified CEO plan and delegation: ' + plan.result
            system = ('Implement the CEO repair in a COPY. Return only JSON {"code":str,"summary":str}. '
                'code must contain exactly one Python function _jarvis_reply_status(reply), preserving OK/FALHOU/PENDENTE. '
                'No imports, loops, comprehensions, decorators, helper functions, filesystem, private names or tools. '
                'Only str(), string strip/casefold/startswith, local assignment, if, boolean comparisons, tuples and return. '
                'Preserve successful and pending readbacks; reject explicit failure/error wording. No hidden reasoning.')
            self.engine._metrics(self.sid, delegation_automatic=True, context_transfer_automatic=True)
        self.artifact(dispatch, 'CONTEXT_PACKET', 'Contexto automatico da ZARA', prompt)
        run, result = self.engine.runtime._run_agent(self.store.get_session(self.sid), agent, prompt, system,
                                                    task, timeout_s=max(1, int(dispatch.deadline - time.time())))
        if not result.ok:
            raise TextProviderFailure(result.availability.value)
        self.store.add_message(Message(new_id('message'), self.sid, MessageKind.AGENT, agent.name,
                                       result.text, author_agent_id=agent.id, run_id=run.id))
        return self.artifact(dispatch, 'MODEL_RESULT', agent.name + ' · entrega real', result.text)

    def verify(self, dispatch, receipt):
        if dispatch.capability == 'files.write':
            verdict = self.actions.verify(dispatch, receipt)
            if verdict.verdict == 'PASS':
                self.store.add_message(Message('hermes-verified:' + self.sid, self.sid, MessageKind.SYSTEM, 'Hermes',
                    'Candidata gravada pela integracao instalada; hash confirmado. ' + verdict.evidence_ref))
            return verdict
        artifact = next((a for a in self.store.list_artifacts(self.sid) if a.id == receipt.artifact_ref), None)
        passed = bool(artifact and artifact.task_id == dispatch.task_id and artifact.body == receipt.summary)
        try:
            value = _extract_json(receipt.summary)
            if dispatch.step_id == 'plan':
                passed = passed and all(isinstance(value.get(k), str) and value[k].strip()
                                        for k in ('title', 'instruction', 'acceptance'))
                passed = passed and value.get('worker_agent_id') == self.metrics['worker_id'] != dispatch.agent_id
                if passed:
                    task = self.store.get_task(self.sid + ':draft')
                    task.title, task.instruction, task.acceptance = value['title'], value['instruction'], value['acceptance']
                    self.store.save_task(task)
                    self.artifact(dispatch, 'DELEGATION', 'Delegacao do CEO', json.dumps({
                        'source_agent_id': dispatch.agent_id, 'target_agent_id': task.assigned_agent_id,
                        'task_id': task.id, 'plan_artifact': receipt.artifact_ref}))
            elif dispatch.step_id == 'draft':
                validate_code(value['code'])
                passed = passed and isinstance(value.get('summary'), str) and bool(value['summary'])
            else:
                code = Path(self.metrics['target']).read_text(encoding='utf-8')
                passed = (passed and value.get('passed') is True and value.get('exit_code') == 0
                          and value.get('sha256') == hashlib.sha256(code.encode('utf-8')).hexdigest()
                          and self.metrics['observation']['passed'] is False)
        except (ValueError, KeyError, TypeError, SyntaxError):
            passed = False
        proof = self.artifact(dispatch, 'VERIFICATION', 'Evidencia independente',
                              json.dumps({'passed': bool(passed), 'source_artifact': receipt.artifact_ref}))
        if passed and dispatch.step_id == 'test':
            self.store.add_message(Message('verifier:' + self.sid, self.sid, MessageKind.SYSTEM, 'Verifier',
                f'{len(CASES)}/{len(CASES)} casos passaram; o defeito existia na baseline. Evidencia: ' + proof.artifact_ref))
        return Verification('PASS' if passed else 'FAIL', proof.artifact_ref)
