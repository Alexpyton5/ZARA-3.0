"""Unit wiring only: deterministic model fixtures, genuine local subprocess tests.

These fixtures must never qualify as production autonomy proof.
"""
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.domain import AgentProfile, Availability, ProviderInfo, ProviderResult, RoleName, Team, TeamMembership
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy
from core.lab_v1.source_mission import SourceMission, _protected_baseline, _recheck_protected


class UnitReasoningFixture(ProviderAdapter):
    id = label = 'unit-only'
    controlled_text_only = True

    def probe(self):
        return ProviderInfo(self.id, self.label, 'test', Availability.AVAILABLE)

    def complete(self, **kwargs):
        model = kwargs['model']
        if model == 'planner':
            tasks = []
            for key, role, method in [('patch', 'BUILDER', 'source_changed'), ('tests', 'BUILDER', 'pytest'), ('review', 'REVIEWER', 'independent_review')]:
                tasks.append(dict(id=key, title=key, instruction='Investigate and verify the reported behavior.',
                    role=role, capability='source.' + key, path=key + '.json', risk='LOW', repair_budget=1,
                    depends_on=[] if not tasks else [tasks[-1]['id']], acceptance={'method': method}))
            result = {'mission': 'Repair reported behavior', 'plan_version': 1, 'tasks': tasks}
        elif model == 'builder':
            result = {'edits': [
                {'path': 'core/example.py', 'content': 'def twice(n):\n    return n * 2\n'},
                {'path': 'tests/test_zara_mission_regression.py', 'content':
                    'from core.example import twice\ndef test_behavior():\n    assert twice(3) == 6\n    assert twice(-2) == -4\n    assert twice(0) == 0\n'}],
                'summary': 'Unit fixture implementation, not a real autonomous contribution.'}
        else:
            prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message')
            refs = json.loads(prompt.split('EVIDENCE_REFERENCES: ', 1)[1])
            result = {'verdict': 'PASS', 'rationale': 'Unit fixture review, not independent production evidence.', 'evidence_refs': refs}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
            model_reported=model, provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)


@pytest.fixture
def source_engine(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    (workspace / 'core').mkdir(parents=True)
    (workspace / 'memory').mkdir()
    (workspace / 'core/__init__.py').touch()
    (workspace / 'core/example.py').write_text('def twice(n):\n    return n + 2\n')
    current = workspace / 'frontend/ZARA CURRENT BUILD/win-unpacked'
    (current / 'resources/backend').mkdir(parents=True)
    (current / 'BUILD_INFO.json').write_text(json.dumps({
        'BUILD_ID': 'unit-current', 'PREVIOUS_PACKAGE': None, 'ROLLBACK_JOURNAL': None}))
    (current / 'ZARA 3.0.exe').write_bytes(b'current-exe')
    (current / 'resources/app.asar').write_bytes(b'current-asar')
    (current / 'resources/backend/zara-backend.exe').write_bytes(b'current-backend')
    (workspace / 'ZARA_ACTIVE_BUILD.json').write_text(json.dumps({'BUILD_ID': 'unit-current'}))
    (workspace / 'ZARA_ACTIVE_BUILD.txt').write_text(str(current / 'ZARA 3.0.exe'))
    from core.lab_v1.candidate_source import CandidateSource
    real_init = CandidateSource.__init__
    def with_python(self, *args, **kwargs):
        kwargs['python_executable'] = Path(sys.executable)
        real_init(self, *args, **kwargs)
    monkeypatch.setattr(CandidateSource, '__init__', with_python)
    def unit_desktop_builder(workspace, sandbox, source_root, allowed_paths, review_evidence):
        package = Path(sandbox) / 'unit-desktop-package'
        unpacked = package / 'win-unpacked'
        resources = unpacked / 'resources'
        resources.mkdir(parents=True)
        exe = unpacked / 'ZARA 3.0.exe'
        asar = resources / 'app.asar'
        backend = resources / 'backend' / 'zara-backend.exe'
        backend.parent.mkdir()
        for path, body in ((exe, b'unit-exe'), (asar, b'unit-asar'), (backend, b'unit-backend')):
            path.write_bytes(body)
        canary_path = Path(sandbox) / 'desktop-canary' / 'VALIDATION.json'
        canary_path.parent.mkdir()
        canary = {'status': 'passed', 'live': False, 'runs': [], 'fixture': 'UNIT_ONLY'}
        canary_path.write_text(json.dumps(canary))
        digest = lambda path: __import__('hashlib').sha256(path.read_bytes()).hexdigest()
        return {
            'status': 'PACKAGED_RUNTIME_CANDIDATE', 'package': str(package),
            'candidate_status': 'VERIFIED_AWAITING_APPROVAL', 'desktop_package': True,
            'workspace': str(Path(sandbox) / 'desktop-workspace'),
            'source_sha256': '0' * 64,
            'overlay': [{'path': path, 'sha256': digest(Path(source_root) / path)} for path in allowed_paths],
            'review_evidence': review_evidence,
            'exe_path': str(exe), 'exe_sha256': digest(exe),
            'asar_path': str(asar), 'asar_sha256': digest(asar),
            'backend_path': str(backend), 'backend_sha256': digest(backend), 'build_id': 'UNIT-ONLY',
            'canary_report': str(canary_path), 'canary': canary,
            'activation': 'FORBIDDEN_UNTIL_CANONICAL_SOURCE_PROMOTION_AND_REBUILD',
            'evidence_level': 'TEST_ONLY',
        }
    monkeypatch.setattr('tools.build_source_candidate.build_candidate', unit_desktop_builder)
    registry = ProviderRegistry(tmp_path / 'health.json')
    registry.register(UnitReasoningFixture())
    store = LabStore(tmp_path / 'lab.db')
    runtime = LabRuntime(store, registry)
    store.save_team(Team('team', 'Unit only'))
    for model, role in [('planner', RoleName.CEO), ('builder', RoleName.BUILDER), ('reviewer', RoleName.REVIEWER)]:
        registry.record_result('unit-only', model, ProviderResult(True, availability=Availability.AVAILABLE))
        store.save_agent(AgentProfile(model, model, 'unit-only', model, role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership(model, 'team', model))
    policy = WorkforcePolicy({'workspace': str(workspace), 'authorized_models': ['unit-only/*'],
        'resource_classes': {'unit-only/*': 'OWNER_REPORTED_FREE'}})
    return Autopilot(runtime, root=tmp_path / 'missions', policy=policy)


def test_source_pipeline_reopens_candidate_and_runs_real_subprocesses(source_engine):
    started = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')
    sid = started['session_id']
    result = source_engine.run(sid)
    assert result['state'] == 'COMPLETED', [(a.kind, a.body) for a in source_engine.store.list_artifacts(sid) if a.kind in ('SOURCE_VERIFICATION', 'REAL_TESTS')]
    meta = source_engine.metrics(sid)['source_work']
    assert meta['test_evidence']['baseline']['exit_code'] == 1
    assert meta['test_evidence']['candidate']['exit_code'] == 0
    assert meta['change_evidence']['source_files_changed'] == 1
    assert meta['preservation_evidence']['status'] == 'NO_PROMOTION'
    assert meta['preservation_evidence']['matches'] is True
    assert meta['protection_baseline']['rollback_basis'] == 'CURRENT_RETAINED_NO_REFERENCED_PREVIOUS'
    assert (Path(meta['workspace']) / 'core/example.py').read_text().endswith('return n + 2\n')
    assert Path(meta['candidate_build']['exe_path']).is_file()
    assert meta['candidate_build']['status'] == 'PACKAGED_RUNTIME_CANDIDATE'
    assert meta['candidate_build']['canary']['status'] == 'passed'
    assert meta['candidate_build']['evidence_level'] == 'TEST_ONLY'
    proof = json.loads(Path(source_engine.metrics(sid)['proof_path']).read_text())
    assert proof['production_evidence'][0]['status'] == 'NOT_PROVEN'
    assert len(proof['participants']) == 3
    assert proof['owner_touches'] == 1


def test_source_inspection_no_change_gets_independent_visible_review(source_engine, monkeypatch):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete

    def complete(**kwargs):
        model = kwargs['model']
        system = kwargs.get('system', '')
        if model == 'planner':
            result = {
                'mission': 'Inspecionar o comportamento atual',
                'plan_version': 1,
                'tasks': [],
                'no_change_reason': ('A função observada é pequena e o comportamento atual não apresenta um '
                                     'contraexemplo factual que justifique alteração neste momento.'),
            }
            return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
                                  model_reported=model, provider_session_id='unit-no-change')
        if model == 'reviewer' and 'independent second reviewer' in system:
            result = {
                'verdict': 'NO_CHANGE_CONFIRMED',
                'rationale': ('Reli a função completa e não encontrei perda de comportamento, risco observável '
                              'ou caso factual que justifique uma correção agora.'),
                'evidence_refs': {'source_paths': ['core/example.py']},
            }
            return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
                                  model_reported=model, provider_session_id='unit-second-review')
        return original(**kwargs)

    monkeypatch.setattr(adapter, 'complete', complete)
    started = source_engine.start(
        'Inspecione core/example.py e procure somente uma melhoria justificável.',
        mission_kind='SELF_IMPROVEMENT', evidence={'observation_kind': 'SOURCE_INSPECTION'})
    sid = started['session_id']

    result = source_engine.run(sid)

    assert result['state'] == 'COMPLETED'
    meta = source_engine.metrics(sid)['source_work']
    assert meta['inspection_review']['verdict'] == 'NO_CHANGE_CONFIRMED'
    assert meta['inspection_reviewer_id'] != source_engine.metrics(sid)['planner_id']
    messages = source_engine.store.list_messages(sid)
    assert messages[0].author == 'ZARA'
    assert any('segunda revisão independente antes de encerrar' in message.content for message in messages)
    assert any('segunda revisão independente e concordo' in message.content for message in messages)
    assert not any('"mission"' in message.content or '"plan_version"' in message.content for message in messages)


def test_source_inspection_disagreement_replans_and_keeps_working(source_engine, monkeypatch):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    planner_calls = []

    def complete(**kwargs):
        model = kwargs['model']
        system = kwargs.get('system', '')
        prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message') or ''
        if model == 'planner':
            planner_calls.append(prompt)
            if 'INDEPENDENT_INSPECTION_COUNTEREXAMPLE' not in prompt:
                result = {
                    'mission': 'Inspecionar o comportamento atual',
                    'plan_version': 1,
                    'tasks': [],
                    'no_change_reason': ('A primeira leitura não encontrou um defeito concreto suficiente para '
                                         'autorizar uma alteração na fonte observada.'),
                }
                return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
                                      model_reported=model, provider_session_id='unit-no-change-first')
            return original(**kwargs)
        if model == 'reviewer' and 'independent second reviewer' in system:
            result = {
                'verdict': 'CHANGE_NEEDED',
                'rationale': ('A segunda leitura encontrou um contraexemplo concreto no cálculo: para entradas '
                              'negativas a função soma dois em vez de realmente duplicar o valor.'),
                'counterexample': ('Em core/example.py, twice(-2) devolve 0; o comportamento esperado pelo nome e '
                                   'pela operação é -4, portanto existe uma correção pequena e verificável.'),
                'evidence_refs': {'source_paths': ['core/example.py']},
            }
            return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
                                  model_reported=model, provider_session_id='unit-second-review-change')
        return original(**kwargs)

    monkeypatch.setattr(adapter, 'complete', complete)
    started = source_engine.start(
        'Inspecione core/example.py e procure somente uma melhoria justificável.',
        mission_kind='SELF_IMPROVEMENT', evidence={'observation_kind': 'SOURCE_INSPECTION'})
    sid = started['session_id']

    result = source_engine.run(sid)

    assert result['state'] == 'COMPLETED'
    meta = source_engine.metrics(sid)['source_work']
    assert meta['inspection_replans'] == 1
    assert meta['no_change_reason'] is None
    assert meta['change_evidence']['source_files_changed'] == 1
    assert len(planner_calls) == 2
    assert 'INDEPENDENT_INSPECTION_COUNTEREXAMPLE' in planner_calls[1]
    messages = source_engine.store.list_messages(sid)
    assert any('encontrei um ponto concreto que precisa de trabalho' in message.content for message in messages)
    assert any('Reorganizei o trabalho' in message.content for message in messages)
    assert any('Testes reais concluídos' in message.content for message in messages)
    assert not any('"mission"' in message.content or '"plan_version"' in message.content for message in messages)


def test_source_mission_waits_before_creating_session_without_independent_team(source_engine):
    source_engine.runtime.registry.record_result(
        'unit-only', 'planner',
        ProviderResult(False, availability=Availability.PROVIDER_ERROR, error='overloaded'),
    )
    with pytest.raises(ValueError, match='WAITING_RESOURCE'):
        source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')
    assert source_engine.store.list_sessions() == []


def test_feedback_source_mission_binds_existing_pipeline_tests_as_readonly(tmp_path):
    from core.lab_v1.source_mission import prepare_source

    workspace = tmp_path / 'workspace'
    source = workspace / 'core/lab_v1/feedback_inbox.py'
    source.parent.mkdir(parents=True)
    source.write_text('def looks_like_product_criticism(text): return True\n', encoding='utf-8')
    existing_tests = workspace / 'tests/test_lab_feedback_pipeline.py'
    existing_tests.parent.mkdir(parents=True)
    existing_tests.write_text('def test_existing_feedback_behavior(): assert True\n', encoding='utf-8')
    engine = SimpleNamespace(policy=SimpleNamespace(document={'workspace': str(workspace)}))

    meta = prepare_source(
        engine,
        tmp_path / 'sandbox',
        'Melhore core/lab_v1/feedback_inbox.py sem alterar nem promover produção.',
    )

    assert meta['readonly_test_paths'] == ['tests/test_lab_feedback_pipeline.py']
    assert 'tests/test_lab_feedback_pipeline.py' in meta['support_paths']
    assert 'tests/test_lab_feedback_pipeline.py' not in meta['allowed_paths']
    mission = object.__new__(SourceMission)
    mission.meta = meta
    mission.candidate = SimpleNamespace(objective_test_paths=())
    assert mission.test_nodeids() == [
        'tests/test_zara_mission_regression.py',
        'tests/test_lab_feedback_pipeline.py',
    ]


def test_public_start_defers_cold_snapshot_until_supervised_run(source_engine, monkeypatch):
    from core.lab_v1.candidate_source import CandidateSource
    original = CandidateSource.prepare
    calls = []
    def observed_prepare(self):
        calls.append(self.sandbox)
        return original(self)
    monkeypatch.setattr(CandidateSource, 'prepare', observed_prepare)

    started = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')

    assert started['state'] == 'QUEUED'
    assert calls == []
    assert source_engine.metrics(started['session_id'])['source_work']['snapshot_state'] == 'PENDING'
    steps = source_engine.controller.snapshot(started['session_id'])['steps']
    assert [(step['id'], step['depends_on']) for step in steps] == [
        ('source_prepare', []), ('plan', ['source_prepare'])]
    assert source_engine.run(started['session_id'])['state'] == 'COMPLETED'
    assert len(calls) == 1


def test_protected_manifest_detects_current_or_canonical_source_change(source_engine):
    workspace = Path(source_engine.policy.document['workspace'])
    baseline = _protected_baseline(workspace, ['core/example.py'])
    unchanged = _recheck_protected(baseline)
    assert unchanged['status'] == 'NO_PROMOTION'
    assert unchanged['matches'] is True

    pointer = workspace / 'ZARA_ACTIVE_BUILD.txt'
    pointer.write_text('changed-current-pointer')
    changed = _recheck_protected(baseline)
    assert changed['status'] == 'PROTECTED_STATE_CHANGED'
    assert changed['matches'] is False


def test_source_build_rejects_candidate_changed_after_review(source_engine, monkeypatch):
    from tools import build_source_candidate
    original_builder = build_source_candidate.build_candidate
    def stale_builder(workspace, sandbox, source_root, allowed_paths, review_evidence):
        result = original_builder(workspace, sandbox, source_root, allowed_paths, review_evidence)
        (Path(source_root) / 'core/example.py').write_text('def twice(n):\n    return 999\n')
        return result
    monkeypatch.setattr(build_source_candidate, 'build_candidate', stale_builder)
    started = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')
    sid = started['session_id']
    result = source_engine.run(sid)
    assert result['state'] != 'COMPLETED'
    failures = [json.loads(a.body) for a in source_engine.store.list_artifacts(sid)
                if a.kind == 'SOURCE_VERIFICATION']
    assert any('CANDIDATE_IDENTITY_CHANGED' in item.get('error', '') for item in failures)


def test_review_repair_is_single_and_retains_prior_receipts(source_engine, monkeypatch):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    reviews = {'count': 0}
    def reject_once(**kwargs):
        if kwargs['model'] != 'reviewer':
            return original(**kwargs)
        reviews['count'] += 1
        if reviews['count'] > 1:
            return original(**kwargs)
        prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message')
        refs = json.loads(prompt.split('EVIDENCE_REFERENCES: ', 1)[1])
        result = {'verdict': 'FAIL', 'rationale': 'First review requests one bounded repair.', 'evidence_refs': refs}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
            model_reported='reviewer', provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)
    monkeypatch.setattr(adapter, 'complete', reject_once)

    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    result = source_engine.run(sid)
    assert result['state'] == 'COMPLETED'
    assert source_engine.metrics(sid)['source_work']['repair_count'] == 1
    review_step = next(step for step in result['mission']['steps'] if step['id'] == 'review')
    assert len(review_step['repairs']) == 1
    assert review_step['repairs'][0]['receipt']
    assert review_step['repairs'][0]['verification']


def test_preservation_evidence_repair_does_not_rerun_builder(source_engine, monkeypatch):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    calls = {'builder': 0, 'reviewer': 0}
    def reject_missing_evidence_once(**kwargs):
        model = kwargs['model']
        if model == 'builder':
            calls['builder'] += 1
        if model != 'reviewer':
            return original(**kwargs)
        calls['reviewer'] += 1
        if calls['reviewer'] > 1:
            return original(**kwargs)
        prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message')
        refs = json.loads(prompt.split('EVIDENCE_REFERENCES: ', 1)[1])
        result = {'verdict': 'FAIL',
                  'rationale': 'Falta evidência verificável de preservação de produção, CURRENT e rollback.',
                  'failure_kind': 'EVIDENCE_ONLY',
                  'evidence_refs': refs}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
            model_reported='reviewer', provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)
    monkeypatch.setattr(adapter, 'complete', reject_missing_evidence_once)

    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    result = source_engine.run(sid)

    assert result['state'] == 'COMPLETED'
    assert calls == {'builder': 1, 'reviewer': 2}
    tests_step = next(step for step in result['mission']['steps'] if step['id'] == 'tests')
    patch_step = next(step for step in result['mission']['steps'] if step['id'] == 'patch:draft')
    assert len(tests_step['repairs']) == 1
    assert not patch_step.get('repairs')


def test_code_counterexamples_route_back_to_builder_even_when_rationale_mentions_receipt(source_engine, monkeypatch):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    calls = {'builder': 0, 'reviewer': 0}
    def reject_code_once(**kwargs):
        model = kwargs['model']
        if model == 'builder':
            calls['builder'] += 1
        if model != 'reviewer':
            return original(**kwargs)
        calls['reviewer'] += 1
        if calls['reviewer'] > 1:
            return original(**kwargs)
        prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message')
        refs = json.loads(prompt.split('EVIDENCE_REFERENCES: ', 1)[1])
        # Even a mislabelled EVIDENCE_ONLY verdict cannot hide concrete code counterexamples.
        result = {'verdict': 'FAIL', 'failure_kind': 'EVIDENCE_ONLY',
                  'rationale': ('O recibo de preservação foi aceito, mas há contraexemplos de código: '
                                '`A ZARA não está lenta ou ruim.` e `A ZARA não está lenta nem tem bug.`'),
                  'evidence_refs': refs}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
            model_reported='reviewer', provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)
    monkeypatch.setattr(adapter, 'complete', reject_code_once)

    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    result = source_engine.run(sid)

    assert result['state'] == 'COMPLETED'
    assert calls == {'builder': 2, 'reviewer': 2}
    patch_step = next(step for step in result['mission']['steps'] if step['id'] == 'patch:draft')
    assert len(patch_step['repairs']) == 1


def drive_reviewer_sequence(source_engine, monkeypatch, reject_count):
    adapter = source_engine.runtime.registry.get('unit-only')
    original = adapter.complete
    calls = {'builder': 0, 'reviewer': 0}
    def sequenced(**kwargs):
        model = kwargs['model']
        if model == 'builder':
            calls['builder'] += 1
        if model != 'reviewer':
            return original(**kwargs)
        calls['reviewer'] += 1
        if calls['reviewer'] > reject_count:
            return original(**kwargs)
        prompt = kwargs.get('prompt') or kwargs.get('user') or kwargs.get('message')
        refs = json.loads(prompt.split('EVIDENCE_REFERENCES: ', 1)[1])
        phrase = ('`Não há erro nem falha na ZARA.`' if calls['reviewer'] % 2
                  else '`Não há erro ou falha na ZARA.`')
        result = {'verdict': 'FAIL', 'failure_kind': 'CODE_OR_TEST',
                  'rationale': 'Contraexemplo de código ainda não coberto: ' + phrase,
                  'evidence_refs': refs}
        return ProviderResult(True, text=json.dumps(result), availability=Availability.AVAILABLE,
            model_reported='reviewer', provider_session_id='unit-fixture', input_tokens=1, output_tokens=1)
    monkeypatch.setattr(adapter, 'complete', sequenced)
    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    return sid, source_engine.run(sid), calls


def test_two_successive_code_repairs_reach_pass_with_persisted_counter(source_engine, monkeypatch):
    sid, result, calls = drive_reviewer_sequence(source_engine, monkeypatch, 2)

    assert result['state'] == 'COMPLETED'
    assert calls == {'builder': 3, 'reviewer': 3}
    assert source_engine.metrics(sid)['source_work']['repair_count'] == 2
    assert SourceMission(source_engine, sid).meta['repair_count'] == 2


def test_replan_after_three_code_rejections_preserves_history(source_engine, monkeypatch):
    sid, result, calls = drive_reviewer_sequence(source_engine, monkeypatch, 4)

    assert result['state'] == 'COMPLETED'
    assert calls == {'builder': 5, 'reviewer': 5}
    meta = source_engine.metrics(sid)['source_work']
    assert meta['repair_count'] == 4
    assert meta['repair_cycle_count'] == 0
    assert meta['repair_replans'] == 1
    assert len(meta['counterexamples']) == 4
    assert meta['replan_repair']['decision'] == 'CHANGE_APPROACH_AND_EXPAND_TESTS'
    assert meta['replan_repair']['from_plan_version'] < meta['replan_repair']['to_plan_version']


def test_replan_sequence_exhaustion_blocks_without_generic_retry(source_engine, monkeypatch):
    sid, result, calls = drive_reviewer_sequence(source_engine, monkeypatch, 8)
    if result['state'] == 'RUNNING':
        result = source_engine.run(sid)

    assert result['state'] == 'BLOCKED_NEEDS_OWNER'
    assert calls == {'builder': 8, 'reviewer': 8}
    meta = source_engine.metrics(sid)['source_work']
    assert meta['repair_count'] == 8
    assert meta['repair_cycle_count'] == 3
    assert meta['repair_replans'] == 1
    assert meta['replan_blocked'] is True
    assert len(meta['counterexamples']) == 8
    assert 'candidate_build' not in meta


def test_source_scope_failure_does_not_persist_orphan_session(source_engine):
    count = len(source_engine.store.list_sessions())
    with pytest.raises(ValueError, match='SOURCE_SCOPE_NOT_IDENTIFIED'):
        source_engine.start('Melhore a ZARA sem indicar assunto algum')
    assert len(source_engine.store.list_sessions()) == count


def test_real_planner_schema_mistake_gets_actionable_bounded_diagnostic(source_engine):
    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    erroneous = {'mission': 'Repair observed behavior', 'plan_version': 1, 'tasks': [
        {'id': 'source.patch', 'title': 'patch', 'instruction': 'Investigate and repair.',
         'role': 'BUILDER', 'capability': 'source.apply', 'path': 'patch.json', 'depends_on': [],
         'risk': 'LOW', 'repair_budget': 1, 'acceptance': {'method': 'source_changed'}},
        {'id': 'source.tests', 'title': 'tests', 'instruction': 'Run the regression.',
         'role': 'BUILDER', 'capability': 'source.tests', 'path': 'tests.json', 'depends_on': ['source.patch'],
         'risk': 'LOW', 'repair_budget': 1, 'acceptance': {'method': 'pytest'}},
        {'id': 'source.review', 'title': 'review', 'instruction': 'Review evidence independently.',
         'role': 'REVIEWER', 'capability': 'model.text', 'path': 'review.json', 'depends_on': ['source.tests'],
         'risk': 'LOW', 'repair_budget': 1, 'acceptance': {'method': 'independent_review'}},
    ]}
    with pytest.raises(ValueError, match='ids patch -> tests -> review; dots are forbidden'):
        SourceMission(source_engine, sid).validate_plan(erroneous)

    corrected_shape = json.loads(json.dumps(erroneous))
    for item, task_id in zip(corrected_shape['tasks'], ('patch', 'tests', 'review')):
        item['id'] = task_id
    corrected_shape['tasks'][1]['depends_on'] = ['patch']
    corrected_shape['tasks'][2]['depends_on'] = ['tests']
    with pytest.raises(ValueError, match='logical capabilities must be source.patch'):
        SourceMission(source_engine, sid).validate_plan(corrected_shape)


def test_interrupted_source_action_recovers_only_from_bound_durable_receipt(source_engine):
    sid = source_engine.start('Corrija a ZARA core/example.py: twice deve duplicar também negativos.')['session_id']
    assert source_engine.run(sid)['state'] == 'COMPLETED'
    with source_engine.controller._transaction() as conn:
        doc, _ = source_engine.controller._load(conn, sid)
        step = next(item for item in doc['steps'] if item['capability'] == 'source.apply')
        original_artifact = step['receipt']['artifact_ref']
        step.update(status='RECONCILE', receipt=None, verification=None)
        doc['state'], doc['blocker'] = 'BLOCKED', 'UNCERTAIN_EFFECT'
        conn.execute('UPDATE mission_controls SET lease_token=NULL,lease_until=0 WHERE session_id=?', (sid,))
        source_engine.controller._save(conn, doc, 'test.interrupted_source_action')

    source_engine._recover_interrupted(sid)

    recovered = next(item for item in source_engine.controller.snapshot(sid)['steps']
                     if item['capability'] == 'source.apply')
    assert recovered['status'] == 'VERIFYING'
    assert recovered['receipt']['artifact_ref'] == original_artifact
    assert recovered['reconciliation']['verdict'] == 'APPLIED'
