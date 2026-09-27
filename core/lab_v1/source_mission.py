"""Real source work ports on the canonical MissionController.

Models plan, implement and review. Local tools apply their output to an isolated
copy, run actual pytest and build a hashed source candidate. No fixed repair.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path

from core.lab_v1.domain import Artifact, Message, MessageKind, RoleName, Task
from core.lab_v1.execution_scope import ScopeViolation
from core.lab_v1.mission_controller import MissionStep, Receipt, Verification
from core.lab_v1.real_work_contract import (
    REVIEW_RATIONALE_LIMIT,
    ReviewResponseContractError,
    factual_participant_report,
    reject_planner_solution_material,
    validate_planner_task,
    validate_production_proof,
    validate_reviewer_result,
)
from core.lab_v1.runtime import _extract_json

_MAX_SOURCE_REPAIRS = 3


def profile_permission_allows(agent, permission: str) -> bool:
    """Enforce owner-configured permissions without breaking legacy agents.

    Profiles created before this feature have no marker and retain their
    established behavior. Once the owner saves permissions, absence becomes
    an explicit denial for source-work actions.
    """
    capabilities = set(getattr(agent, 'capabilities', ()) or ())
    if 'profile.permissions.configured' not in capabilities:
        return True
    return f'permission:{permission}' in capabilities


def _dict(value):
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    return json.loads(json.dumps(asdict(value) if is_dataclass(value) else value, default=str))


def _file_identity(path):
    path = Path(path).resolve(strict=False)
    return {'path': str(path), 'exists': path.is_file(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def _protected_baseline(workspace, source_paths):
    """Capture only explicit canonical source/build identities; never scan builds."""
    workspace = Path(workspace).resolve()
    current = workspace / 'frontend' / 'ZARA CURRENT BUILD'
    info_path = current / 'win-unpacked' / 'BUILD_INFO.json'
    try:
        info = json.loads(info_path.read_text(encoding='utf-8')) if info_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        info = {}
    paths = [workspace / relative for relative in source_paths]
    paths += [workspace / 'ZARA_ACTIVE_BUILD.json', workspace / 'ZARA_ACTIVE_BUILD.txt', info_path,
              current / 'win-unpacked' / 'ZARA 3.0.exe',
              current / 'win-unpacked' / 'resources' / 'app.asar',
              current / 'win-unpacked' / 'resources' / 'backend' / 'zara-backend.exe']
    previous = info.get('PREVIOUS_PACKAGE')
    journal = info.get('ROLLBACK_JOURNAL')
    referenced = []
    if isinstance(journal, str) and journal.strip():
        referenced.append(Path(journal))
    if isinstance(previous, str) and previous.strip():
        prior = Path(previous)
        referenced += [prior / 'win-unpacked' / 'BUILD_INFO.json',
                       prior / 'win-unpacked' / 'ZARA 3.0.exe',
                       prior / 'win-unpacked' / 'resources' / 'app.asar',
                       prior / 'win-unpacked' / 'resources' / 'backend' / 'zara-backend.exe']
    paths += referenced
    entries = [_file_identity(path) for path in dict.fromkeys(paths)]
    return {'version': 1, 'entries': entries, 'current_path': str(current.resolve(strict=False)),
            'current_build_id': info.get('BUILD_ID'),
            'previous_package': previous if isinstance(previous, str) and previous.strip() else None,
            'rollback_journal': journal if isinstance(journal, str) and journal.strip() else None,
            'rollback_basis': ('REFERENCED_PREVIOUS_CAPTURED' if referenced
                               else 'CURRENT_RETAINED_NO_REFERENCED_PREVIOUS')}


def _recheck_protected(baseline):
    after = [_file_identity(item['path']) for item in baseline['entries']]
    return {'status': 'NO_PROMOTION' if after == baseline['entries'] else 'PROTECTED_STATE_CHANGED',
            'before': baseline, 'after': after, 'matches': after == baseline['entries']}


def source_requested(intent, kind):
    if kind == 'SELF_IMPROVEMENT':
        return True
    if re.search(r'\b(propostas?|pesquis[ae]|estud[ae])\b', intent, re.I) and not re.search(r'\b(implement[ae]|corrij[ae]|aplique)\b', intent, re.I):
        return False
    # Alex can ask the team to work toward a concrete voice-latency outcome
    # without using an implementation verb such as "melhore" or "corrija".
    if (re.search(r'\btrabalh\w*\b', intent, re.I)
            and re.search(r'\btempo\s+de\s+resposta\b', intent, re.I)
            and re.search(r'\bvoz\b', intent, re.I)
            and re.search(r'\bquase\s+instant[aâ]ne', intent, re.I)):
        return True
    return bool(re.search(r'(?:corrij|consert|implement|melhor|auto.?melhor|resolv|mudem|aprend|mais r[aá]pid|mais discret)', intent, re.I)
                and re.search(r'(?:zara|voz|anima[çc][aã]o|interface|\blab\b|\bcore/|\.py\b|c[oó]digo|\bopen\s*code\b)', intent, re.I))


def prepare_source(engine, sandbox, intent):
    workspace = Path(engine.policy.document.get('workspace') or Path(__file__).resolve().parents[2]).resolve()
    from core.lab_v1.source_scope import SCOPE_NOT_IDENTIFIED_MESSAGE, select_source_scope
    paths = select_source_scope(workspace, intent)
    if not paths:
        # Prefix kept for the existing regression assertion
        # (tests/test_lab_source_mission.py::test_source_scope_failure_does_not_persist_orphan_session
        # matches on the 'SOURCE_SCOPE_NOT_IDENTIFIED' substring); the text after
        # it is what the owner actually sees, since he is not a programmer and
        # the previous message ("a concrete observed module is required") was not.
        raise ValueError('SOURCE_SCOPE_NOT_IDENTIFIED: ' + SCOPE_NOT_IDENTIFIED_MESSAGE)
    paths = list(dict.fromkeys(paths))[:8]
    for path in paths:
        if 'hermes' in path.casefold() or not (workspace / path).is_file():
            raise ScopeViolation('Only existing internal ZARA source is authorized')
    tests = ['tests/test_zara_mission_regression.py']
    meta = {'workspace': str(workspace), 'sandbox': str(sandbox),
            'allowed_paths': paths + tests, 'source_paths': paths, 'test_paths': tests,
            'support_paths': ['core', 'memory'] + (['frontend/src'] if any(p.startswith('frontend/') for p in paths) else []), 'repair_count': 0,
            'repair_cycle_count': 0, 'repair_limit': _MAX_SOURCE_REPAIRS,
            'repair_replans': 0, 'counterexamples': [], 'review_count': 0,
            'snapshot_state': 'PENDING'}
    return meta


class SourceMission:
    def __init__(self, engine, sid):
        from core.lab_v1.candidate_source import CandidateSource
        self.engine, self.store, self.sid = engine, engine.store, sid
        self.metrics = engine.metrics(sid)
        self.meta = self.metrics['source_work']
        self.candidate = CandidateSource(Path(self.meta['workspace']), Path(self.meta['sandbox']),
            self.meta['allowed_paths'], support_paths=self.meta['support_paths'],
            runtime_drift_paths=self.meta.get('runtime_drift_paths', ()),
            # What the mission is about, from the scope selection - not from the
            # worker. The executor needs it to tell a legitimate test-fix mission
            # apart from a worker dodging production code with a test-only edit.
            objective_paths=self.meta.get('source_paths', ()))
        if self.meta.get('snapshot_state') == 'READY':
            self.candidate.resume()

    def save_meta(self, **changes):
        self.meta.update(changes)
        self.engine._metrics(self.sid, source_work=self.meta)

    def validate_plan(self, plan):
        reject_planner_solution_material(plan)
        if (isinstance(plan, dict) and set(plan) == {'mission', 'plan_version', 'tasks', 'no_change_reason'}
                and self.metrics.get('evidence', {}).get('observation_kind') == 'SOURCE_INSPECTION'
                and plan['tasks'] == [] and plan['plan_version'] == 1
                and isinstance(plan['mission'], str)
                and isinstance(plan['no_change_reason'], str) and 30 <= len(plan['no_change_reason']) <= 3000):
            return plan
        if (not isinstance(plan, dict) or set(plan) != {'mission', 'plan_version', 'tasks'}
                or plan['plan_version'] != 1 or not isinstance(plan['mission'], str)):
            raise ValueError('SOURCE_PLAN_SCHEMA')
        tasks = plan['tasks']
        if not isinstance(tasks, list) or len(tasks) != 3:
            raise ValueError('SOURCE_PLAN_SCHEMA_EXPECTED: exactly 3 tasks with ids patch,tests,review')
        for i, capability in enumerate(('source.patch', 'source.tests', 'source.review')):
            raw = tasks[i]
            if not isinstance(raw, dict):
                raise ValueError(f'SOURCE_PLAN_TASK_{i + 1}_EXPECTED_OBJECT')
            if raw.get('id') != ('patch', 'tests', 'review')[i]:
                raise ValueError('SOURCE_PLAN_SCHEMA_EXPECTED: ids patch -> tests -> review; dots are forbidden')
            if raw.get('capability') != capability:
                raise ValueError('SOURCE_PLAN_SCHEMA_EXPECTED: logical capabilities must be source.patch -> '
                                 'source.tests -> source.review; source.apply, source.build and model.text are '
                                 'internal execution capabilities and forbidden in planner output')
            item = validate_planner_task(tasks[i])
            if (item.get('risk') != 'LOW' or type(item.get('repair_budget')) is not int
                    or not 0 <= item['repair_budget'] <= 1):
                raise ValueError('SOURCE_TASK_SCHEMA')
            if item.get('depends_on') != ([] if i == 0 else [tasks[i-1]['id']]):
                raise ValueError('REAL_HANDOFF_CHAIN_REQUIRED')
            RoleName(item['role'])
        if len({t['id'] for t in tasks}) != 3 or tasks[2]['role'] != 'REVIEWER':
            raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
        return plan

    def expand(self):
        plan = self.validate_plan(_extract_json(self.store.get_task(self.sid + ':plan').result))
        if plan.get('no_change_reason'):
            if self.engine.controller.expand_verified_plan(self.sid, [], [], metadata=plan):
                self.save_meta(no_change_reason=plan['no_change_reason'])
            return
        team = self.store.get_session(self.sid).team_id
        planner = self.store.get_agent(self.metrics['planner_id'])
        patch, tests, review = plan['tasks']
        builders = self.engine.candidates(team, RoleName(patch['role']), exclude=(planner.id,))
        if not builders:
            self.engine._block(self.sid, 'REAL_BUILDER_UNAVAILABLE'); return
        builder = builders[0]
        if (not profile_permission_allows(builder, 'write_sandbox')
                or not profile_permission_allows(builder, 'run_tests')):
            self.engine._block(self.sid, 'AGENT_PERMISSION_DENIED')
            return
        reviewers = [a for a in self.engine.candidates(team, RoleName.REVIEWER)
                     if a.id not in (planner.id, builder.id)
                     and (a.provider_id, a.model) not in ((planner.provider_id, planner.model), (builder.provider_id, builder.model))]
        if not reviewers:
            self.engine._block(self.sid, 'INDEPENDENT_REVIEWER_UNAVAILABLE'); return
        reviewer = reviewers[0]
        if not profile_permission_allows(reviewer, 'read_workspace'):
            self.engine._block(self.sid, 'AGENT_PERMISSION_DENIED')
            return
        definitions = [
            (patch['id'] + ':draft', patch, builder, 'DELEGATE', 'model.text', ('plan',)),
            (patch['id'] + ':apply', patch, builder, 'ACTION', 'source.apply', (patch['id'] + ':draft',)),
            (tests['id'], tests, builder, 'ACTION', 'source.tests', (patch['id'] + ':apply',)),
            (review['id'], review, reviewer, 'DELEGATE', 'model.text', (tests['id'],)),
            ('candidate_build', review, reviewer, 'ACTION', 'source.build', (review['id'],)),
        ]
        tasks, steps = [], []
        for step_id, item, agent, kind, capability, deps in definitions:
            task = Task(self.sid + ':' + step_id, self.sid, item['title'], item['instruction'],
                        planner.id, assigned_agent_id=agent.id, acceptance=json.dumps(item), max_turns=1)
            tasks.append(task)
            resource = 'provider:' + agent.provider_id + '/' + agent.model if capability == 'model.text' else self.meta['sandbox']
            steps.append(MissionStep(step_id, task.id, kind, deps, capability, (resource,)))
        if self.engine.controller.expand_verified_plan(self.sid, tasks, steps, metadata=plan):
            self.save_meta(builder_id=builder.id, reviewer_id=reviewer.id,
                patch_step=patch['id'] + ':draft', review_step=review['id'], test_step=tests['id'])
            self.engine._metrics(self.sid, task_creation_automatic=True, plan_version=2)

    def context_focus(self, *extra):
        """Real mission evidence used to choose which source regions to spend
        the context budget on. Never invented: only observed gap evidence,
        rejected counterexamples and the actual diff."""
        parts = [json.dumps(self.metrics.get('evidence', {}), ensure_ascii=False)]
        parts += [json.dumps(item, ensure_ascii=False) for item in extra if item]
        return ' '.join(parts)[:8000]

    def model_input(self, dispatch):
        prompt = dispatch.context.render()
        prompt += '\nOBSERVATION_EVIDENCE: ' + json.dumps(self.metrics.get('evidence', {}), ensure_ascii=False)[:16000]
        if dispatch.step_id == 'plan':
            members = [{'id': a.id, 'role': a.role.value, 'model': a.model}
                       for a in self.engine.candidates(self.store.get_session(self.sid).team_id)]
            prompt += '\nEXISTING INTERNAL WORKERS: ' + json.dumps(members)
            if self.meta.get('plan_rejections'):
                # Why the previous plan was refused, so the schema error is not
                # simply repeated. It carries the verifier's words, never a plan.
                prompt += '\nREJECTED_PLAN_EVIDENCE: ' + json.dumps(
                    self.meta['plan_rejections'], ensure_ascii=False)[-8000:]
            prompt += '\nOBSERVED SOURCE: ' + json.dumps(self.candidate.read_context(
                self.meta['source_paths'], max_chars=24000,
                on_overflow='outline', focus=self.context_focus()), ensure_ascii=False)
            system = ('You are the architect planning real ZARA source improvement. Return JSON only with '
                'exactly the top-level keys mission, plan_version:1, tasks. tasks contains exactly these 3 logical '
                'task records in order: (1) id="patch", role="BUILDER", capability="source.patch", path="patch.json", '
                'depends_on=[], acceptance={"method":"source_changed"}; (2) id="tests", role="BUILDER", '
                'capability="source.tests", path="tests.json", depends_on=["patch"], acceptance={"method":"pytest"}; '
                '(3) id="review", role="REVIEWER", capability="source.review", path="review.json", '
                'depends_on=["tests"], acceptance={"method":"independent_review"}. Each task also has bounded '
                'non-empty title and instruction, risk="LOW", repair_budget=1. These are logical planning capabilities: '
                'never output internal execution capabilities source.apply, source.build or model.text. '
                'Assign implementation to the existing BUILDER role, '
                'distinct from the planning agent. Testing is a local deterministic executor, '
                'do not invent a QA model Run for it. Reviewer is a real independent resource. '
                'Define strategy and measurable postconditions only. No final source, code snippets, solutions, '
                'test implementations, exact artifact answers or hidden metadata. Workers must solve the task. '
                'Only a sandbox copy changes. No production modification or claims of work already done.')
            if self.metrics.get('evidence', {}).get('observation_kind') == 'SOURCE_INSPECTION':
                system += (' This is an inspection, not a proven bug. If the actual source does not justify a concrete '
                    'bounded correction, return {mission,plan_version:1,tasks:[],no_change_reason:"factual explanation"}. '
                    'Never manufacture a defect to produce a change. Otherwise define the observed counterexample '
                    'and its measurable intended behavior in the task plan without writing the implementation.')
        elif dispatch.step_id == 'replan_repair':
            prompt += '\nREJECTED_COUNTEREXAMPLES: ' + json.dumps(self.meta.get('counterexamples', []), ensure_ascii=False)[-24000:]
            prompt += '\nCURRENT_SOURCE: ' + json.dumps(self.candidate.read_context(
                self.meta['allowed_paths'], max_chars=36000, on_overflow='outline',
                focus=self.context_focus(self.meta.get('counterexamples'))), ensure_ascii=False)
            system = ('You are the architect replanning after three unsuccessful code/test repairs. '
                'Study the real counterexamples and current source. Return JSON only with decision '
                '(CHANGE_APPROACH, SPLIT_TASK, CHANGE_WORKER, EXPAND_TESTS or CORRECT_ACCEPTANCE), '
                'rationale, and instruction. Specify a substantively different bounded approach and '
                'measurable acceptance. Do not write solution code or weaken acceptance to hide a defect. '
                'Existing permissions and total repair budget cannot increase.')
        elif dispatch.step_id == self.meta['patch_step']:
            from core.lab_v1.candidate_source import is_partial_view
            observed = self.candidate.read_context(
                self.meta['source_paths'], max_chars=42000, on_overflow='outline',
                focus=self.context_focus(self.meta.get('replan_result'),
                                         self.meta.get('counterexamples')))
            partial_paths = sorted(path for path, text in observed.items() if is_partial_view(text))
            self.save_meta(partial_view_paths=partial_paths)
            prompt += '\nSOURCE_FILES: ' + json.dumps(observed, ensure_ascii=False)
            prompt += '\nALLOWED_EDIT_PATHS: ' + json.dumps(self.meta['allowed_paths'])
            prompt += '\nPARTIAL_VIEW_PATHS: ' + json.dumps(partial_paths)
            if self.meta.get('replan_result'):
                prompt += '\nARCHITECT_REPLAN: ' + json.dumps(self.meta['replan_result'], ensure_ascii=False)
            rejected = self.meta.get('counterexamples') or self.meta.get('repair_evidence')
            if rejected:
                prompt += '\nREJECTED_ATTEMPT_EVIDENCE: ' + json.dumps(rejected, ensure_ascii=False)[-14000:]
            system = ('You are the actual implementation worker. Independently find the root cause in the supplied '
                'real ZARA source. Return JSON only {"edits":[<edit>,...],"summary":"what changed and why"}. '
                'An edit is EITHER {"path":"relative.py","content":"complete file"} - allowed only for a file you '
                'received in full - OR {"path":"relative.py","anchored_edits":[{"find":"exact current source text",'
                '"replace":"new text"}]}. PARTIAL_VIEW_PATHS lists the files you did NOT receive in full: for those, '
                '"content" is refused by the local executor and anchored_edits is mandatory. Each "find" must be '
                'copied verbatim from the source you were shown and must occur EXACTLY ONCE in the file; if it could '
                'match more than one place, extend it with surrounding lines until it is unique. Everything outside '
                'your anchors is preserved byte for byte, so never try to reproduce ranges marked OMITTED. '
                'Change the real source module and create the allowed pytest '
                'regression file. Tests must cover failures on original source, positive controls, mixed cases and '
                'preserve correct behavior; do not weaken tests or encode implementation internals. No fake providers, '
                'no mocks for the behavior under repair, no shell/network/tools/production writes. The local executor '
                'writes your content to the candidate and runs the tests. Imports may use standard Python and the '
                'copied core. Preserve unrelated behavior. No predetermined answer has been provided; implement it.')
            self.engine._metrics(self.sid, delegation_automatic=True, context_transfer_automatic=True)
        else:
            changes = self.meta['change_evidence']
            hashes = self.current_hashes()
            preservation = _recheck_protected(self.meta['protection_baseline'])
            preservation_id = 'LOCAL_PRESERVATION_REVIEW_INPUT:' + dispatch.attempt_id
            if not any(item.id == preservation_id for item in self.store.list_artifacts(self.sid)):
                self.store.save_artifact(Artifact(preservation_id, self.sid, dispatch.task_id,
                    'LOCAL_PRESERVATION', 'Protected state immediately before review',
                    body=json.dumps(preservation, ensure_ascii=False)))
            self.save_meta(review_preservation_evidence=preservation,
                           review_preservation_receipt_id=preservation_id)
            from core.lab_v1.review_evidence_packet import (
                build_review_evidence_packet, persist_review_evidence_packet)
            packet, packet_sha256 = build_review_evidence_packet(
                store=self.store, controller=self.engine.controller, session_id=self.sid,
                review_attempt_id=dispatch.attempt_id, patch_step_id=self.meta['patch_step'],
                test_step_id=self.meta['test_step'], review_task_id=dispatch.task_id,
                change_evidence=changes, review_preservation_id=preservation_id,
                source_identity=self.source_identity(), candidate_identity=self.current_identity())
            packet_artifact = persist_review_evidence_packet(
                self.store, session_id=self.sid, task_id=dispatch.task_id,
                packet=packet, packet_sha256=packet_sha256)
            self.save_meta(review_evidence_packet_id=packet_artifact.id,
                           review_evidence_packet_sha256=packet_sha256,
                           review_evidence_packet_attempt_id=dispatch.attempt_id)
            prompt += '\nACTUAL_FILES: ' + json.dumps(self.candidate.read_context(
                self.meta['allowed_paths'], max_chars=46000, on_overflow='outline',
                focus=self.context_focus(changes.get('diff') if isinstance(changes, dict) else None)),
                ensure_ascii=False)
            prompt += '\nREVIEW_EVIDENCE_PACKET: ' + json.dumps(packet, ensure_ascii=False, sort_keys=True)
            prompt += '\nEVIDENCE_REFERENCES: ' + json.dumps(
                {'artifact_hashes': hashes,
                 'test_receipt_ids': [self.meta['test_receipt_id'], self.meta['preservation_receipt_id'],
                                      preservation_id],
                 'packet_id': packet_artifact.id, 'packet_sha256': packet_sha256})
            system = ('You are the independent reviewer. Inspect the objective, actual diff/source/tests and '
                'actual subprocess results plus the deterministic local before/after preservation receipt. '
                'The future desktop candidate build is a later gate; review only source, tests, and the factual '
                'NO_PROMOTION proof at this stage. Reject superficial fixes, weakened tests, fabricated work, unrelated '
                'modifications, missed negation scopes, negative statements hiding real complaints, or fake evidence. '
                'You are a distinct model/Run from planner and builder. No expected solution is supplied. '
                'Return JSON only. Copy every supplied EVIDENCE_REFERENCES value exactly; partial references fail. '
                'PASS schema: {"verdict":"PASS","rationale":"concrete findings",'
                '"evidence_refs":{"artifact_hashes":["all reviewed hashes"],"test_receipt_ids":["all reviewed receipts"],'
                '"packet_id":"reviewed packet id","packet_sha256":"reviewed packet hash"}}. '
                'FAIL schema: {"verdict":"FAIL","failure_kind":"CODE_OR_TEST","rationale":"concrete findings",'
                '"evidence_refs":{"artifact_hashes":["all reviewed hashes"],"test_receipt_ids":["all reviewed receipts"],'
                '"packet_id":"reviewed packet id","packet_sha256":"reviewed packet hash"}}. '
                'For FAIL, failure_kind must be exactly CODE_OR_TEST or EVIDENCE_ONLY. '
                'Use CODE_OR_TEST for any source logic, behavioral counterexample, regression-test weakness, or '
                'implementation concern. Use EVIDENCE_ONLY only when source and tests are acceptable and the sole '
                'defect is a missing/invalid receipt; never label a behavioral counterexample EVIDENCE_ONLY. '
                'Do not say PASS solely because tests passed. Request repair with concrete counterexamples if needed. '
                'rationale is validated as bounded text: keep it under ' + str(REVIEW_RATIONALE_LIMIT) +
                ' characters, or the verdict is refused as a malformed answer no matter what it says.')
        return system, prompt

    def test_nodeids(self):
        """Which test files the ``tests`` step actually executes.

        The fixed regression test in ``test_paths`` is always mandatory and is
        never replaced. When the mission's own objective IS a test file - a
        flaky-test repair, where ``source_paths`` holds a file under ``tests/`` -
        that file has to run too, or the step proves nothing about the very test
        the mission was asked to fix.

        Observed 2026-09-11 (LAB-15, session_bddba03ea7c4): the builder repaired
        tests/test_lab_policy_facade.py, the tests step reported a real
        before-fail/after-pass, and the independent reviewer still refused the
        mission - correctly - because the repaired test had never been executed a
        single time. Only the fixed regression file was in the pytest nodeids.

        ``CandidateSource.objective_test_paths`` is the single project definition
        of "an objective path that is a test file" (``_is_test_path``); no new
        pattern is invented here.
        """
        nodeids = list(self.meta['test_paths'])
        for path in getattr(self.candidate, 'objective_test_paths', ()):
            if path not in nodeids:
                nodeids.append(path)
        return nodeids

    def current_hashes(self):
        return [hashlib.sha256((Path(self.meta['sandbox']) / 'source' / p).read_bytes()).hexdigest()
                for p in self.meta['allowed_paths'] if (Path(self.meta['sandbox']) / 'source' / p).is_file()]

    def current_identity(self):
        return {p: hashlib.sha256((Path(self.meta['sandbox']) / 'source' / p).read_bytes()).hexdigest()
                for p in self.meta['allowed_paths'] if (Path(self.meta['sandbox']) / 'source' / p).is_file()}

    def source_identity(self):
        manifest = json.loads(Path(self.meta['snapshot']['manifest_path']).read_text(encoding='utf-8'))
        return {item['path']: item['before_sha256'] for item in manifest['files']
                if item['path'] in self.meta['allowed_paths']}

    def artifact(self, dispatch, kind, value):
        body = json.dumps(_dict(value), ensure_ascii=False)
        artifact = Artifact(kind + ':' + dispatch.attempt_id, self.sid, dispatch.task_id, kind, kind, body=body)
        self.store.save_artifact(artifact)
        return Receipt(artifact.id, body)

    def recover_receipt(self, step):
        """Return only an exact durable source-action receipt after a crash."""
        kinds = {'source.prepare': ('SOURCE_SNAPSHOT', 'snapshot_receipt'),
                 'source.apply': ('SOURCE_DIFF', 'change_evidence'),
                 'source.tests': ('REAL_TESTS', 'test_evidence'),
                 'source.build': ('SOURCE_BUILD', 'candidate_build')}
        binding = kinds.get(step.get('capability'))
        if not binding or not step.get('attempt_id'):
            return None
        kind, meta_key = binding
        artifact_id = kind + ':' + step['attempt_id']
        artifact = next((item for item in self.store.list_artifacts(self.sid)
                         if item.id == artifact_id and item.kind == kind
                         and item.task_id == step['task_id']), None)
        if not artifact:
            return None
        try:
            value = _extract_json(artifact.body)
            if value != self.meta.get(meta_key):
                return None
            current = self.current_hashes()
            if step['capability'] == 'source.prepare':
                if self.meta.get('snapshot_state') != 'READY':
                    return None
                self.candidate.resume()
            elif step['capability'] == 'source.apply':
                changed = value.get('hashes', {})
                observed = [changed[path]['after_sha256'] for path in self.meta['allowed_paths']
                            if path in changed]
                # A mission whose objective is a test file legitimately changes
                # zero production files; its real work shows up as
                # objective_files_changed. Either one proves the apply happened.
                real_work = max(value.get('source_files_changed', 0),
                                value.get('objective_files_changed', 0))
                if real_work < 1 or any(item not in current for item in observed):
                    return None
            elif step['capability'] == 'source.tests' and value.get('source_hashes') != current:
                return None
            elif step['capability'] == 'source.build':
                overlay = value.get('overlay', [])
                if [item.get('sha256') for item in overlay] != current:
                    return None
        except (ValueError, KeyError, TypeError):
            return None
        return Receipt(artifact.id, artifact.body)

    def execute(self, dispatch):
        dispatch.execution_scope.require(dispatch.capability, dispatch.resources, 'LOW')
        if dispatch.capability == 'source.prepare':
            snapshot = _dict(self.candidate.prepare())
            protected = _protected_baseline(self.meta['workspace'], self.meta['source_paths'])
            payload = {'snapshot': snapshot, 'protection_baseline': protected}
            self.save_meta(snapshot=snapshot, snapshot_receipt=payload, snapshot_state='READY',
                           protection_baseline=protected)
            return self.artifact(dispatch, 'SOURCE_SNAPSHOT', payload)
        if dispatch.capability == 'source.apply':
            task = self.store.get_task(self.sid + ':' + self.meta['patch_step'])
            if task.state.value != 'COMPLETED': raise ScopeViolation('UNVERIFIED_SOURCE_DRAFT')
            proposal = _extract_json(task.result)
            changed = _dict(self.candidate.apply_edits(proposal['edits']))
            self.save_meta(change_evidence=changed)
            return self.artifact(dispatch, 'SOURCE_DIFF', changed)
        if dispatch.capability == 'source.tests':
            nodeids = self.test_nodeids()
            baseline = _dict(self.candidate.run_pytest_baseline(nodeids, timeout_seconds=90))
            tested = _dict(self.candidate.run_pytest(nodeids, timeout_seconds=90))
            preservation = _recheck_protected(self.meta['protection_baseline'])
            preservation_receipt = self.artifact(dispatch, 'LOCAL_PRESERVATION', preservation)
            evidence = {'baseline': baseline, 'candidate': tested, 'source_hashes': self.current_hashes(),
                        'executed_test_paths': nodeids,
                        'preservation': preservation,
                        'preservation_receipt_id': preservation_receipt.artifact_ref}
            receipt = self.artifact(dispatch, 'REAL_TESTS', evidence)
            self.save_meta(test_evidence=evidence, test_receipt_id=receipt.artifact_ref,
                           preservation_evidence=preservation,
                           preservation_receipt_id=preservation_receipt.artifact_ref)
            return receipt
        if dispatch.capability == 'source.build':
            from tools.build_source_candidate import build_candidate
            review = self.meta.get('independent_review')
            if not review or review.get('verdict') != 'PASS':
                raise ScopeViolation('VERIFIED_INDEPENDENT_REVIEW_REQUIRED')
            args = (Path(self.meta['workspace']), Path(self.meta['sandbox']),
                    Path(self.meta['sandbox']) / 'source', self.meta['allowed_paths'], review)
            drift_paths = self.meta.get('runtime_drift_paths', ())
            # Keep the executor seam compatible with the lightweight test
            # builder while passing drift paths for real package recovery.
            result = (build_candidate(*args, runtime_drift_paths=drift_paths)
                      if drift_paths else build_candidate(*args))
            self.save_meta(candidate_build=result)
            return self.artifact(dispatch, 'SOURCE_BUILD', result)
        raise ScopeViolation('UNSUPPORTED_SOURCE_ACTION')

    def verify(self, dispatch, receipt):
        evidence = {'passed': False, 'receipt': receipt.artifact_ref}
        artifact = next((a for a in self.store.list_artifacts(self.sid)
                         if a.id == receipt.artifact_ref and a.task_id == dispatch.task_id
                         and a.body == receipt.summary), None)
        try:
            if not artifact: raise ValueError('UNBOUND_SOURCE_RECEIPT')
            value = _extract_json(artifact.body)
            if dispatch.step_id == 'plan':
                self.validate_plan(value)
            elif dispatch.step_id == 'replan_repair':
                if (not isinstance(value, dict) or set(value) != {'decision', 'rationale', 'instruction'}
                        or value['decision'] not in ('CHANGE_APPROACH', 'SPLIT_TASK', 'CHANGE_WORKER', 'EXPAND_TESTS', 'CORRECT_ACCEPTANCE')
                        or any(not isinstance(value[k], str) or not 20 <= len(value[k]) <= 6000 for k in ('rationale', 'instruction'))):
                    raise ValueError('REPLAN_REPAIR_SCHEMA')
                reject_planner_solution_material(value)
                self.save_meta(replan_result=value)
            elif dispatch.capability == 'source.prepare':
                if value != self.meta.get('snapshot_receipt') or self.meta.get('snapshot_state') != 'READY':
                    raise ValueError('SOURCE_SNAPSHOT_NOT_BOUND')
                self.candidate.resume()
            elif dispatch.capability == 'source.apply':
                if not self.current_hashes() or not value: raise ValueError('NO_SOURCE_CHANGE')
            elif dispatch.capability == 'source.tests':
                before, after = value['baseline'], value['candidate']
                before_counts, after_counts = before['counts'], after['counts']
                excluded = ('errors', 'skipped', 'xfailed', 'xpassed')
                if (after['exit_code'] != 0 or before['exit_code'] != 1
                        or before_counts['collected'] < 1 or before_counts['failed'] < 1
                        or before_counts['passed'] + before_counts['failed'] != before_counts['collected']
                        or any(before_counts[key] for key in excluded)
                        or after_counts['passed'] != after_counts['collected']
                        or after_counts['collected'] != before_counts['collected']
                        or after_counts['failed'] or any(after_counts[key] for key in excluded)
                        or before['test_hashes'] != after['test_hashes']
                        or value.get('preservation', {}).get('status') != 'NO_PROMOTION'
                        or value.get('preservation', {}).get('matches') is not True
                        or value.get('preservation_receipt_id') != self.meta.get('preservation_receipt_id')
                        or value['source_hashes'] != self.current_hashes()):
                    raise ValueError('REAL_BEFORE_FAIL_AFTER_PASS_REQUIRED')
            elif dispatch.capability == 'source.build':
                current = self.current_hashes()
                review = self.meta.get('independent_review', {})
                refs = review.get('evidence_refs', {})
                overlay = value.get('overlay')
                overlay_by_path = ({item.get('path'): item.get('sha256') for item in overlay}
                                   if isinstance(overlay, list) and all(isinstance(item, dict) for item in overlay) else {})
                expected_overlay = {
                    path: hashlib.sha256((Path(self.meta['sandbox']) / 'source' / path).read_bytes()).hexdigest()
                    for path in self.meta['allowed_paths']
                }
                canary_path = Path(value.get('canary_report', ''))
                canary = value.get('canary')
                binaries = (
                    ('exe_path', 'exe_sha256'),
                    ('package', None),
                )
                if refs.get('artifact_hashes') != current or overlay_by_path != expected_overlay:
                    raise ValueError('CANDIDATE_IDENTITY_CHANGED')
                if (value.get('status') != 'PACKAGED_RUNTIME_CANDIDATE'
                        or value.get('candidate_status') != 'VERIFIED_AWAITING_APPROVAL'
                        or value.get('desktop_package') is not True
                        or value.get('activation') != 'FORBIDDEN_UNTIL_CANONICAL_SOURCE_PROMOTION_AND_REBUILD'
                        or value.get('review_evidence') != review
                        or not isinstance(canary, dict) or canary.get('status') != 'passed'
                        or canary.get('live') is not False or canary.get('runs', []) != []
                        or not canary_path.is_file()
                        or json.loads(canary_path.read_text(encoding='utf-8')) != canary
                        or any(not Path(value.get(path_key, '')).exists() for path_key, _ in binaries)):
                    raise ValueError('DESKTOP_CANDIDATE_EVIDENCE_INVALID')
                for path_key, hash_key in (('exe_path', 'exe_sha256'),
                                           ('asar_path', 'asar_sha256'),
                                           ('backend_path', 'backend_sha256')):
                    if hashlib.sha256(Path(value[path_key]).read_bytes()).hexdigest() != value.get(hash_key):
                        raise ValueError('CANDIDATE_IDENTITY_CHANGED')
            elif dispatch.step_id == self.meta['patch_step']:
                if not isinstance(value, dict) or set(value) != {'edits', 'summary'}:
                    raise ValueError('PATCH_SCHEMA')
                if not isinstance(value['edits'], list) or not 1 <= len(value['edits']) <= len(self.meta['allowed_paths']):
                    raise ValueError('PATCH_EDIT_LIMIT')
                paths = []
                partial = set(self.meta.get('partial_view_paths') or ())
                for edit in value['edits']:
                    if (not isinstance(edit, dict) or 'path' not in edit
                            or edit['path'] not in self.meta['allowed_paths']):
                        raise ValueError('PATCH_PATH_OR_CONTENT')
                    path = edit['path']
                    if set(edit) == {'path', 'content'}:
                        if not isinstance(edit['content'], str) or not edit['content'].strip():
                            raise ValueError('PATCH_PATH_OR_CONTENT')
                        if path in partial:
                            # The worker never saw this file whole. Rejecting here
                            # gives it a repair cycle with the real reason instead
                            # of letting the executor refuse the same thing later.
                            raise ValueError('PARTIAL_VIEW_CONTENT_FORBIDDEN: ' + path +
                                ' was delivered as a partial view; send anchored_edits '
                                '({"find","replace"} against the exact current source) instead of a full file')
                        if path.endswith('.py'):
                            compile(edit['content'], path, 'exec')
                    elif set(edit) == {'path', 'anchored_edits'}:
                        operations = edit['anchored_edits']
                        if not isinstance(operations, list) or not operations:
                            raise ValueError('PATCH_ANCHORED_EDITS_EMPTY: ' + path)
                        for operation in operations:
                            if (not isinstance(operation, dict) or set(operation) != {'find', 'replace'}
                                    or not isinstance(operation['find'], str)
                                    or not isinstance(operation['replace'], str)
                                    or not operation['find'].strip()):
                                raise ValueError('PATCH_ANCHORED_EDIT_SCHEMA: ' + path +
                                    ' needs [{"find":"exact current source","replace":"new text"}]')
                    else:
                        raise ValueError('PATCH_PATH_OR_CONTENT')
                    paths.append(path)
                if len(set(paths)) != len(paths) or not set(self.meta['test_paths']) <= set(paths):
                    raise ValueError('REAL_REGRESSION_TEST_REQUIRED')
                if not set(paths) & set(self.meta['source_paths']): raise ValueError('REAL_SOURCE_REQUIRED')
            else:
                from core.lab_v1.review_evidence_packet import (
                    _bound_response_run,
                    validate_persisted_review_evidence_packet,
                )
                after_review = _recheck_protected(self.meta['protection_baseline'])
                if after_review.get('status') != 'NO_PROMOTION' or after_review.get('matches') is not True:
                    raise ValueError('PROTECTED_STATE_CHANGED_DURING_REVIEW')
                runs = self.store.list_runs(self.sid)
                artifacts = self.store.list_artifacts(self.sid)
                indexed = {item.id: item for item in artifacts}
                if len(indexed) != len(artifacts):
                    raise ValueError('MODEL_RESPONSE_BINDING_DUPLICATE_ARTIFACT')
                reviewer = _bound_response_run(
                    self.store, indexed, session_id=self.sid, task_id=dispatch.task_id,
                    attempt_id=dispatch.attempt_id, response=artifact)
                snapshot = self.engine.controller.snapshot(self.sid)
                plan_step = next(step for step in snapshot['steps'] if step['id'] == 'plan')
                plan_attempt_id = plan_step.get('attempt_id')
                plan_artifact = indexed.get('response:' + str(plan_attempt_id))
                if not plan_attempt_id or plan_artifact is None:
                    raise ValueError('MODEL_RESPONSE_BINDING_PLANNER_RESPONSE_MISSING')
                planner = _bound_response_run(
                    self.store, indexed, session_id=self.sid, task_id=plan_step['task_id'],
                    attempt_id=plan_attempt_id, response=plan_artifact)
                builders = [r for r in runs if r.task_id == self.sid + ':' + self.meta['patch_step'] and r.state.value == 'COMPLETED']
                failure_kind = 'CODE_OR_TEST'
                # Defensive default: legacy, malformed or ambiguous FAIL output
                # can only authorize a full code/test repair.
                normalized_review = value
                # Two different defects can refuse this step: the reviewed WORK,
                # or the reviewer's own answer envelope. Only the first says
                # anything about the patch, so record which one happened and let
                # repair() restart the worker that actually failed.
                self.save_meta(review_response_defect=None)
                try:
                    packet_id = self.meta['review_evidence_packet_id']
                    packet_sha256 = self.meta['review_evidence_packet_sha256']
                    validate_persisted_review_evidence_packet(
                        self.store, session_id=self.sid, packet_id=packet_id,
                        packet_sha256=packet_sha256, review_attempt_id=dispatch.attempt_id)
                    if isinstance(value, dict) and value.get('verdict') == 'FAIL':
                        if set(value) != {'verdict', 'rationale', 'evidence_refs', 'failure_kind'}:
                            raise ReviewResponseContractError('REVIEW_FAIL_SCHEMA_REQUIRES_FAILURE_KIND')
                        failure_kind = value.get('failure_kind')
                        if failure_kind not in ('CODE_OR_TEST', 'EVIDENCE_ONLY'):
                            raise ReviewResponseContractError('REVIEW_FAILURE_KIND_INVALID')
                        rationale_folded = str(value.get('rationale', '')).casefold()
                        code_counterexample = ('contraexempl' in rationale_folded or '`' in str(value.get('rationale', ''))
                            or any(word in rationale_folded for word in
                                   ('lógica', 'logica', 'comportamento', 'código', 'codigo', 'teste', '.py')))
                        if failure_kind == 'EVIDENCE_ONLY' and code_counterexample:
                            failure_kind = 'CODE_OR_TEST'
                        normalized_review = {key: value[key] for key in ('verdict', 'rationale', 'evidence_refs')}
                    elif isinstance(value, dict) and value.get('verdict') == 'PASS' and 'failure_kind' in value:
                        raise ReviewResponseContractError('REVIEW_PASS_FORBIDS_FAILURE_KIND')
                    self.save_meta(review_failure_kind=failure_kind,
                                   review_count=self.meta.get('review_count', 0) + 1)
                    verified = validate_reviewer_result(normalized_review, reviewer_run=reviewer, planner_run=planner,
                        builder_runs=builders, artifact_hashes=self.current_hashes(),
                        test_receipt_ids=[self.meta['test_receipt_id'], self.meta['preservation_receipt_id'],
                                          self.meta['review_preservation_receipt_id']],
                        expected_packet_id=packet_id, expected_packet_sha256=packet_sha256)
                except ReviewResponseContractError as exc:
                    self.save_meta(review_response_defect=str(exc))
                    raise
                self.save_meta(independent_review=verified)
                if verified['verdict'] != 'PASS':
                    counterexample = {
                        'review_count': self.meta.get('review_count', 0),
                        'failure_kind': failure_kind,
                        'rationale': verified.get('rationale', ''),
                        'evidence_refs': verified.get('evidence_refs', {}),
                    }
                    prior = list(self.meta.get('counterexamples', []))
                    prior.append(counterexample)
                    self.save_meta(counterexamples=prior,
                                   repair_evidence=counterexample)
                    raise ValueError('REVIEW_REJECTED[' + failure_kind + ']: ' + verified['rationale'])
            evidence['passed'] = True
        except (ValueError, KeyError, TypeError, SyntaxError) as exc:
            evidence['error'] = str(exc)[:2000]
        saved = self.artifact(dispatch, 'SOURCE_VERIFICATION', evidence)
        return Verification('PASS' if evidence['passed'] else 'FAIL', saved.artifact_ref)

    def repair_rejected_plan(self, reason):
        """One bounded replan after the local verifier refused the plan itself.

        The plan step is a ``model.text`` step whose artifact failed deterministic
        schema validation, so nothing was executed from it and the verifier error
        names exactly what was wrong. Handing that back to the architect is the
        same bounded recovery the review step already has: it spends the SAME
        repair counter and never relaxes the plan schema.
        """
        reason = str(reason).strip()
        if not reason:
            raise ValueError('A replan needs the verifier evidence')
        cycle_count = self.meta.get('repair_cycle_count', self.meta.get('repair_count', 0))
        with self.engine.controller._transaction() as conn:
            doc, row = self.engine.controller._load(conn, self.sid)
            plan_step = next((step for step in doc['steps'] if step['id'] == 'plan'), None)
            if (doc['state'] != 'BLOCKED'
                    or doc['blocker'] not in ('VERIFICATION_FAIL', 'VERIFICATION_INCONCLUSIVE')
                    or doc['cancel_requested'] or plan_step is None
                    or plan_step['status'] != 'VERIFYING'
                    or row['lease_until'] > self.engine.controller.clock()
                    or self.engine.controller.clock() >= doc['deadline']):
                return False
            if (cycle_count >= self.meta.get('repair_limit', _MAX_SOURCE_REPAIRS)
                    or doc['used']['retries'] >= doc['limits']['max_retries']):
                doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', 'PLAN_REJECTION_LIMIT'
                self.engine.controller._save(conn, doc, 'mission.plan_rejection_exhausted')
                return False
            # The rejected attempt stays on the step; only the frontier is reset.
            plan_step.setdefault('repairs', []).append({
                'reason': reason, 'verification': plan_step.get('verification'),
                'attempt_id': plan_step.get('attempt_id')})
            plan_step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
            conn.execute("UPDATE tasks SET state='CREATED',result=NULL WHERE id=?", (plan_step['task_id'],))
            doc['used']['retries'] += 1
            doc['state'], doc['blocker'] = 'REPAIRING', None
            self.engine.controller._save(conn, doc, 'mission.plan_replan_authorized')
        rejections = list(self.meta.get('plan_rejections', []))
        rejections.append(reason)
        self.save_meta(plan_rejections=rejections,
                       repair_count=self.meta.get('repair_count', 0) + 1,
                       repair_cycle_count=cycle_count + 1)
        self.engine._metrics(self.sid, recovery_automatic=True)
        return True

    def repair_rejected_draft(self, reason):
        """One bounded redraft after the local executor refused the draft.

        ``apply_edits`` evaluates the complete candidate before its first write,
        so a refusal means nothing landed. The honest recovery is to hand the
        worker the refusal and let it draft again - never to relax the rule it
        broke. Permissions do not change and the repair budget is the SAME
        counter the review repair spends, so total bounded work does not grow.
        """
        reason = str(reason).strip()
        if not reason:
            raise ValueError('A redraft needs the executor refusal')
        patch_step = self.meta.get('patch_step')
        cycle_count = self.meta.get('repair_cycle_count', self.meta.get('repair_count', 0))
        with self.engine.controller._transaction() as conn:
            doc, row = self.engine.controller._load(conn, self.sid)
            if (doc['state'] != 'BLOCKED' or doc['blocker'] != 'PATCH_DRAFT_REJECTED'
                    or doc['cancel_requested'] or patch_step is None
                    or row['lease_until'] > self.engine.controller.clock()
                    or self.engine.controller.clock() >= doc['deadline']):
                return False
            if (cycle_count >= self.meta.get('repair_limit', _MAX_SOURCE_REPAIRS)
                    or doc['used']['retries'] >= doc['limits']['max_retries']):
                doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', 'DRAFT_REJECTION_LIMIT'
                self.engine.controller._save(conn, doc, 'mission.draft_rejection_exhausted')
                return False
            reset_ids, frontier = set(), {patch_step}
            while frontier:
                step_id = frontier.pop()
                if step_id in reset_ids:
                    continue
                reset_ids.add(step_id)
                frontier.update(step['id'] for step in doc['steps'] if step_id in step.get('depends_on', []))
            for step in doc['steps']:
                if step['id'] not in reset_ids:
                    continue
                if step.get('attempt_id') or step.get('receipt') or step.get('verification'):
                    step.setdefault('repairs', []).append({'reason': reason, 'receipt': step.get('receipt'),
                        'verification': step.get('verification'), 'attempt_id': step.get('attempt_id')})
                step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
                conn.execute("UPDATE tasks SET state='CREATED',result=NULL WHERE id=?", (step['task_id'],))
            doc['used']['retries'] += 1
            doc['state'], doc['blocker'] = 'REPAIRING', None
            doc['plan_version'] += 1
            conn.execute('INSERT INTO mission_plans VALUES(?,?,?)',
                         (self.sid, doc['plan_version'], json.dumps(doc['steps'])))
            self.engine.controller._save(conn, doc, 'mission.draft_redraft_authorized')
        rejections = list(self.meta.get('draft_rejections', []))
        rejections.append(reason)
        # Reuses the channel the patch prompt already reads as
        # REJECTED_ATTEMPT_EVIDENCE, so the next draft sees why it was refused.
        self.save_meta(draft_rejections=rejections,
                       repair_count=self.meta.get('repair_count', 0) + 1,
                       repair_cycle_count=cycle_count + 1,
                       repair_evidence={'executor_refused_draft': reason})
        self.engine._metrics(self.sid, recovery_automatic=True)
        return True

    def repair(self, reason):
        replan_meta = None
        exhausted_after_replan = False
        with self.engine.controller._transaction() as conn:
            doc, row = self.engine.controller._load(conn, self.sid)
            if (doc['state'] != 'BLOCKED' or doc['cancel_requested'] or row['lease_until'] > self.engine.controller.clock()
                    or self.engine.controller.clock() >= doc['deadline']):
                return False
            failed = next((step for step in doc['steps'] if step['status'] == 'VERIFYING'), None)
            plan_step = next((step for step in doc['steps'] if step['id'] == 'plan'), None)
            if plan_step is None or plan_step['status'] != 'DONE' or failed is None:
                return False
            # Which refused steps one more bounded draft can actually answer.
            # All three are local verifications of MODEL output: the reviewer's
            # verdict, the draft's own schema check, and the deterministic
            # before-fail/after-pass postcondition. In every case the verifier
            # names the defect and nothing was promoted, so handing it back is
            # the same recovery repair_rejected_plan/repair_rejected_draft give
            # - on the SAME repair counter, with no rule relaxed.
            #
            # Observed 2026-09-10 (LAB-12, session_8ed4613ef1eb): the draft was
            # refused with REAL_REGRESSION_TEST_REQUIRED and the mission died
            # here, because only the review step had a way back.
            #
            # The real-effect ACTION steps stay out on purpose: source.apply and
            # source.build already wrote/packaged bytes, so their verification
            # failure is not "the model said something wrong" and must not be
            # answered by silently doing it again.
            if failed['id'] not in {self.meta.get('review_step'), self.meta.get('patch_step'),
                                    self.meta.get('test_step')}:
                return False
            cycle_count = self.meta.get('repair_cycle_count', self.meta.get('repair_count', 0))
            repair_limit = self.meta.get('repair_limit', _MAX_SOURCE_REPAIRS)
            if cycle_count >= repair_limit:
                total_count = self.meta.get('repair_count', 0) + 1
                # One bounded replan is allowed after the first repair sequence.
                # It preserves all receipts and counterexamples while changing the
                # approach metadata before another limited sequence begins.
                if self.meta.get('repair_replans', 0) >= 1:
                    doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', 'REPAIR_LIMIT_AFTER_REPLAN'
                    self.engine.controller._save(conn, doc, 'mission.repair_exhausted')
                    exhausted_after_replan = True
                    exhausted_total_count = total_count
                else:
                    replan_meta = {
                        'sequence': self.meta.get('repair_replans', 0) + 1,
                        'reason': 'Three CODE_OR_TEST reviews were rejected; preserve evidence and change approach.',
                        'decision': 'CHANGE_APPROACH_AND_EXPAND_TESTS',
                        'counterexamples': list(self.meta.get('counterexamples', [])),
                        'from_plan_version': doc['plan_version'],
                        'to_plan_version': doc['plan_version'] + 1,
                    }
                    # Start the new approach from a clean task frontier while
                    # retaining every prior receipt on the step itself.
                    reset_ids = {self.meta['patch_step'], self.meta['test_step'], self.meta['review_step']}
                    for step in doc['steps']:
                        if step['id'] not in reset_ids:
                            continue
                        if step.get('attempt_id') or step.get('receipt') or step.get('verification'):
                            step.setdefault('repairs', []).append({'reason': reason, 'receipt': step.get('receipt'),
                                'verification': step.get('verification'), 'attempt_id': step.get('attempt_id')})
                        step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
                        conn.execute("UPDATE tasks SET state='CREATED',result=NULL WHERE id=?", (step['task_id'],))
                    doc['used']['retries'] += 1
                    doc['plan_version'] += 1
                    doc.setdefault('repair_replans', []).append(replan_meta)
                    doc['state'], doc['blocker'] = 'REPAIRING', None
                    conn.execute('INSERT INTO mission_plans VALUES(?,?,?)',
                                 (self.sid, doc['plan_version'], json.dumps(doc['steps'])))
                    self.engine.controller._save(conn, doc, 'mission.replan_repair')

            if cycle_count < repair_limit:
                reset_ids = set()
                # EVIDENCE_ONLY is a statement about a REVIEW, so it may only
                # narrow the restart when the review is what was refused. A
                # stale verdict from an earlier cycle must never shrink the
                # frontier for a refused draft or a failed test postcondition:
                # re-running the tests over unchanged source repeats the same
                # deterministic result and burns the budget for nothing.
                evidence_only = (failed['id'] == self.meta.get('review_step')
                                 and self.meta.get('review_failure_kind') == 'EVIDENCE_ONLY')
                # A malformed reviewer ANSWER is not a statement about the patch.
                # Observed 2026-09-11 (LAB-13, session_ff9f6c94874e): three real
                # Opus reviews - one of them a genuine PASS - were refused by the
                # rationale bound, and every refusal sent the BUILDER back to
                # redesign code the reviewer had just approved. The patch, the
                # applied diff and the test receipts are all still valid here, so
                # the only step that must run again is the review itself.
                review_response_defect = (failed['id'] == self.meta.get('review_step')
                                          and bool(self.meta.get('review_response_defect')))
                if review_response_defect:
                    frontier = {self.meta['review_step']}
                else:
                    frontier = {self.meta['test_step'] if evidence_only else self.meta['patch_step']}
                while frontier:
                    step_id = frontier.pop()
                    if step_id in reset_ids:
                        continue
                    reset_ids.add(step_id)
                    frontier.update(step['id'] for step in doc['steps'] if step_id in step.get('depends_on', []))
                for step in doc['steps']:
                    if step['id'] not in reset_ids:
                        continue
                    if step.get('attempt_id') or step.get('receipt') or step.get('verification'):
                        step.setdefault('repairs', []).append({'reason': reason, 'receipt': step.get('receipt'),
                            'verification': step.get('verification'), 'attempt_id': step.get('attempt_id')})
                    step.update(status='PENDING', attempt_id=None, receipt=None, verification=None)
                    conn.execute("UPDATE tasks SET state='CREATED',result=NULL WHERE id=?", (step['task_id'],))
                doc['used']['retries'] += 1
                doc['state'], doc['blocker'] = 'REPAIRING', None
                doc['plan_version'] += 1
                conn.execute('INSERT INTO mission_plans VALUES(?,?,?)', (self.sid, doc['plan_version'], json.dumps(doc['steps'])))
                self.engine.controller._save(conn, doc, 'mission.source_repair_authorized')
        if exhausted_after_replan:
            self.save_meta(repair_count=exhausted_total_count, replan_blocked=True)
            return False
        if replan_meta is not None:
            self.save_meta(repair_count=total_count, repair_replans=1, repair_cycle_count=0,
                           replan_repair=replan_meta, plan_version=replan_meta['to_plan_version'])
            self.engine._metrics(self.sid, recovery_automatic=True)
            return True
        self.save_meta(repair_count=self.meta.get('repair_count', 0) + 1,
                       repair_cycle_count=cycle_count + 1,
                       repair_evidence=reason)
        self.engine._metrics(self.sid, recovery_automatic=True)
        return True

    def promotion_gate(self):
        """State the candidate hands to the release gate; never promotes here."""
        from core.lab_v1.release import promotion_readiness
        candidate_build = self.meta.get('candidate_build')
        if not candidate_build:
            return {'state': 'NOT_APPLICABLE', 'reason': 'NO_DESKTOP_CANDIDATE',
                    'desktop_promoted': False}
        try:
            plan = _extract_json(self.store.get_task(self.sid + ':plan').result)
            risks = {task.get('risk') for task in plan.get('tasks', [])} or {'UNKNOWN'}
        except (ValueError, KeyError, TypeError, AttributeError):
            risks = {'UNKNOWN'}
        candidate = dict(candidate_build, risk='LOW' if risks == {'LOW'} else 'NOT_LOW')
        readiness = promotion_readiness(candidate, self.meta['workspace'])
        return {'state': 'ELIGIBLE' if readiness['eligible'] else 'NOT_ELIGIBLE',
                'gate': 'core.lab_v1.release.ReleaseQueue.schedule_source_candidate',
                'readiness': readiness, 'candidate': candidate, 'desktop_promoted': False}

    def report(self):
        runs = self.store.list_runs(self.sid)
        factual = factual_participant_report(runs, self.store.list_agents())
        production = []
        try:
            for provider_id in {r.provider_id for r in runs}:
                chosen = [r for r in runs if r.provider_id == provider_id and r.state.value == 'COMPLETED']
                production.append(validate_production_proof({'run_ids': [r.id for r in chosen]},
                    runs=chosen, adapter=self.engine.runtime.registry.get(provider_id)))
        except ValueError as exc:
            production = [{'status': 'NOT_PROVEN', 'reason': str(exc)}]
        promotion = self.promotion_gate()
        self.save_meta(promotion_gate=promotion)
        result = {'mission_id': self.sid, 'owner_touches': self.metrics['owner_touches'],
                  'participants': factual['participants'], 'provider_calls': len(runs),
                  'production_evidence': production, 'source_work': self.meta,
                  'hermes_calls': 0, 'desktop_promoted': False, 'promotion': promotion}
        path = Path(self.meta['sandbox']) / 'REAL_WORK_PROOF.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        mid = 'autopilot-report:' + self.sid
        if not any(m.id == mid for m in self.store.list_messages(self.sid)):
            outcome = ('Inspeção concluída; nenhuma mudança justificada: ' + self.meta['no_change_reason']
                       if self.meta.get('no_change_reason') else
                       'Código alterado na candidata isolada. Testes reais executados antes/depois, revisão independente '
                       'e candidata desktop com canário somente leitura concluídos.')
            candidate_note = ('' if self.meta.get('no_change_reason') else
                ' Candidata desktop: ' + str(self.meta['candidate_build']['package']) + '.')
            self.store.add_message(Message(mid, self.sid, MessageKind.ZARA, 'ZARA',
                outcome + ' '
                'Participantes com Runs: ' + ', '.join(sorted({p['agent_name'] or p['agent_id'] for p in factual['participants']})) +
                '. Evidências: ' + str(path) + '.' + candidate_note + ' Promoção: pendente.'))
        self.engine._metrics(self.sid, verification_automatic=True, final_report_automatic=True,
                             content_review='NO_CHANGE_JUSTIFIED' if self.meta.get('no_change_reason') else 'INDEPENDENT_REVIEW_PASSED', proof_path=str(path))
