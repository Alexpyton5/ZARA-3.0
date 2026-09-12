from types import SimpleNamespace
import asyncio
import json
import pytest
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor, WORKFLOW
from core.lab_v1.mission_controller import MissionController
import core.lab_v1.supervisor as module


def test_service_snapshot_does_not_advertise_hermes_workcell(tmp_path):
    from core.lab_v1.service import LabV1Service
    store = LabStore(tmp_path / 'service.db'); store.initialize()

    class Runtime:
        def __init__(self, value): self.store = value
        def snapshot(self, *args): return {}

    service = LabV1Service()
    service._runtime = Runtime(store); service._store = store
    result = asyncio.run(service.snapshot())
    assert result['success'] is True
    assert [cell['id'] for cell in result['workcells']] == ['manus']
    assert result['autonomy_policy']['background_task_state'] == 'STOPPED'
    assert result['autonomy_policy']['max_new_evolution_missions_per_day'] == 1


def test_service_persists_only_typed_factual_capability_failure(tmp_path):
    from core.lab_v1.service import LabV1Service
    store = LabStore(tmp_path / 'service.db'); store.initialize()
    service = LabV1Service(); service._store = store
    service._runtime = SimpleNamespace(store=store)
    result = asyncio.run(service.capture_runtime_failure(
        'browser_open_url', source_path='core/actions/browser.py', stage='executor', status='POSTCONDITION_FAILED',
        reason='window did not open', channel='voice', run_id='run-1'))
    assert result['success'] is True and result['captured'] is True
    gap = store.list_capability_gaps()[0]
    assert gap.required == 'runtime.action.browser_open_url'
    evidence = json.loads(gap.detail)
    assert evidence['observation_kind'] == 'RUNTIME_CAPABILITY_FAILURE'
    assert evidence['status'] == 'POSTCONDITION_FAILED'
    assert evidence['source_path'] == 'core/actions/browser.py'
    rejected = asyncio.run(service.capture_runtime_failure(
        'browser_open_url', source_path='core/actions/browser.py', stage='intent', status='REFUSED', reason='policy', channel='text'))
    assert rejected['success'] is False
    assert len(store.list_capability_gaps()) == 1


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    MissionController(store)
    runtime = SimpleNamespace(store=store)
    autopilot = SimpleNamespace(run=lambda sid: {'success': True, 'state': 'COMPLETED', 'session_id': sid})
    supervisor = AutonomySupervisor(runtime, autopilot=autopilot)
    monkeypatch.setattr(supervisor, 'ensure_team', lambda: None)
    monkeypatch.setattr(module, 'EvolutionEngine', lambda *args, **kwargs: SimpleNamespace(
        snapshot=lambda *args: None,
        observe_local=lambda: [],
        observer_snapshot=lambda: {'inventory_count': 0, 'provider_calls': 0},
        observe_and_plan=lambda **kwargs: {'state': 'NO_REVIEWED_REPAIR'}))
    monkeypatch.setattr(module, 'TechnologyScout', lambda *args, **kwargs: SimpleNamespace(
        run_due=lambda: {'state': 'NOT_DUE', 'new': 0}, next_unreviewed=lambda: None))
    (tmp_path / 'tools').mkdir(); (tmp_path / 'tools/build_current.py').touch()
    return supervisor, tmp_path


def test_default_on_and_pause_persists_workspace(supervisor):
    s, root = supervisor
    assert s.tick()['state'] == 'MONITORING'
    s.configure(enabled=True, workspace=root)
    s.configure(enabled=False)
    assert s.policy()['workspace'] == str(root.resolve())
    assert s.policy()['enabled'] is False
    assert s.policy()['background_enabled'] is True
    assert s.tick()['state'] == 'MONITORING'
    with pytest.raises(ValueError): s.configure(enabled='true')


def test_tick_writes_visible_heartbeat(supervisor):
    s, _ = supervisor
    assert s.tick()['state'] == 'MONITORING'
    assert s.policy()['last_heartbeat'] == s.policy()['last_tick']


def test_feedback_source_selection_is_specific_and_has_no_blind_fallback(supervisor):
    s, _ = supervisor
    assert s._feedback_source_path('A resposta está lenta e demora') == 'core/model_router.py'
    assert s._feedback_source_path('A voz Kore falhou no microfone') == 'core/gemini_live_voice.py'
    assert s._feedback_source_path('A voz está lenta e demora para responder') == 'core/gemini_live_voice.py'
    assert s._feedback_source_path('O feedback marcou uma crítica errada') is None
    assert s._feedback_source_path('Algo deveria ficar melhor') is None
    assert s._proposal_only('Tenho uma sugestão para avaliar') is True


def test_blocked_mission_prevents_new_work(supervisor, monkeypatch):
    s, root = supervisor
    s.configure(enabled=True, workspace=root)
    # Controller table requires a real Session FK.
    from core.lab_v1.domain import Session, Team
    s.store.save_team(Team('team', 'Test'))
    s.store.save_session(Session('blocked', 'team', objective='Await resolution'))
    with s.store._connect() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS mission_autonomy(
                session_id TEXT PRIMARY KEY REFERENCES sessions(id), document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS autonomy_gaps(
                gap_id TEXT PRIMARY KEY, session_id TEXT, stage TEXT, reason TEXT,
                owner_action_required TEXT, candidate_automation TEXT, risk TEXT,
                occurrences INTEGER, created_at REAL);
        ''')
        conn.execute('INSERT INTO mission_controls(session_id,document) VALUES(?,?)',
            ('blocked', json.dumps({'session_id': 'blocked', 'state': 'BLOCKED'})))
        conn.execute('INSERT INTO mission_autonomy(session_id,document) VALUES(?,?)',
            ('blocked', json.dumps({'workflow': WORKFLOW})))
    assert s.tick()['state'] == 'BLOCKED'


def test_failed_internal_review_is_closed_without_owner(supervisor):
    s, root = supervisor
    s.configure(enabled=True, workspace=root)
    from core.lab_v1.domain import Session, Team
    s.store.save_team(Team('team', 'Test'))
    s.store.save_session(Session('daily-blocked', 'team', objective='Internal review'))
    with s.store._connect() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS mission_autonomy(
                session_id TEXT PRIMARY KEY REFERENCES sessions(id), document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS autonomy_gaps(
                gap_id TEXT PRIMARY KEY, session_id TEXT, stage TEXT, reason TEXT,
                owner_action_required TEXT, candidate_automation TEXT, risk TEXT,
                occurrences INTEGER, created_at REAL);
        ''')
        doc = {'session_id': 'daily-blocked', 'plan_version': 1,
               'state': 'BLOCKED_NEEDS_OWNER', 'blocker': 'REPAIR_LIMIT'}
        conn.execute('INSERT INTO mission_controls(session_id,document) VALUES(?,?)',
                     ('daily-blocked', json.dumps(doc)))
        conn.execute('INSERT INTO mission_autonomy(session_id,document) VALUES(?,?)',
                     ('daily-blocked', json.dumps({
                         'workflow': WORKFLOW, 'mission_kind': 'DAILY_OPPORTUNITY_REVIEW'})))
    result = s.tick()
    assert result['state'] == 'FAILED'
    assert MissionController(s.store).snapshot('daily-blocked')['state'] == 'FAILED'


def test_only_canonical_workflow_uses_injected_autopilot(supervisor):
    s, _ = supervisor
    calls = []
    s.autopilot = SimpleNamespace(run=lambda sid: calls.append(sid) or {
        'success': True, 'state': 'COMPLETED', 'session_id': sid})
    from core.lab_v1.domain import Session, Team
    s.store.save_team(Team('team', 'Test'))
    s.store.save_session(Session('mission', 'team', objective='Continue'))
    with s.store._connect() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS mission_autonomy(
                session_id TEXT PRIMARY KEY REFERENCES sessions(id), document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS autonomy_gaps(
                gap_id TEXT PRIMARY KEY, session_id TEXT, stage TEXT, reason TEXT,
                owner_action_required TEXT, candidate_automation TEXT, risk TEXT,
                occurrences INTEGER, created_at REAL);
        ''')
        conn.execute('INSERT INTO mission_controls(session_id,document) VALUES(?,?)',
            ('mission', json.dumps({'session_id': 'mission', 'state': 'RUNNING'})))
        conn.execute('INSERT INTO mission_autonomy(session_id,document) VALUES(?,?)',
            ('mission', json.dumps({'workflow': WORKFLOW})))
    assert s.tick()['state'] == 'COMPLETED'
    assert calls == ['mission']


def test_unsupported_legacy_workflow_is_preserved_without_deadlocking_new_work(supervisor):
    s, _ = supervisor
    calls = []
    s.autopilot = SimpleNamespace(run=lambda sid: calls.append(sid))
    from core.lab_v1.domain import Session, Team
    s.store.save_team(Team('team', 'Test'))
    s.store.save_session(Session('legacy', 'team', objective='Old flow'))
    with s.store._connect() as conn:
        conn.execute('INSERT INTO mission_controls(session_id,document) VALUES(?,?)',
            ('legacy', json.dumps({'session_id': 'legacy', 'state': 'RUNNING'})))
    result = s.tick()
    assert result['state'] == 'MONITORING'
    assert s.store.get_session('legacy') is not None
    assert s.policy()['stale_legacy_sessions'] == ['legacy']
    assert calls == []


def test_daily_opportunity_is_led_verified_and_left_for_owner(supervisor, monkeypatch):
    s, root = supervisor
    s.configure(enabled=True, workspace=root)
    calls = []
    s.autopilot = SimpleNamespace(
        start=lambda objective, **kwargs: calls.append(('start', objective, kwargs)) or {
            'success': True, 'session_id': 'review', 'state': 'QUEUED'},
        run=lambda sid: calls.append(('run', sid)) or {
            'success': True, 'session_id': sid, 'state': 'COMPLETED'})
    scout = SimpleNamespace(
        run_due=lambda: calls.append(('scout',)),
        next_unreviewed=lambda: {'id': 'opp', 'opportunity': 'Codex release', 'source': 'https://github.com/openai/codex/releases/tag/v1',
                                 'evidence_sha256': 'abc123', 'evidence_excerpt': 'fix agent api', 'observed_at': 1},
        link_review=lambda oid, sid: calls.append(('link', oid, sid)),
        verify_review=lambda oid: {'passed': True},
        finish_review=lambda oid, accepted: calls.append(('finish', oid, accepted)))
    monkeypatch.setattr(module, 'TechnologyScout', lambda store: scout)
    result = s.tick()
    assert result['state'] == 'COMPLETED'
    assert ('run', 'review') in calls and ('finish', 'opp', True) in calls
    started = next(item for item in calls if item[0] == 'start')
    assert 'owner aprovar' in started[1]
    assert started[2]['mission_kind'] == 'DAILY_OPPORTUNITY_REVIEW'


def test_product_criticism_reaches_architect_before_external_scout(supervisor, monkeypatch):
    s, root = supervisor
    s.configure(enabled=True, workspace=root)
    calls = []
    s.autopilot = SimpleNamespace(
        start=lambda objective, **kwargs: calls.append(('start', objective, kwargs)) or {
            'success': True, 'session_id': 'criticism-plan', 'state': 'QUEUED'},
        run=lambda sid: calls.append(('run', sid)) or {
            'success': True, 'session_id': sid, 'state': 'COMPLETED'})
    feedback = {'id': 'feedback:1', 'text': 'O envio não funciona.', 'channel': 'text',
                'evidence_sha256': 'deadbeef', 'observed_at': 1}
    inbox = SimpleNamespace(
        next_received=lambda: feedback,
        link=lambda fid, sid: calls.append(('link', fid, sid)),
        finish=lambda fid, completed: calls.append(('finish', fid, completed)))
    monkeypatch.setattr(module, 'FeedbackInbox', lambda store: inbox)
    result = s.tick()
    assert result['state'] == 'COMPLETED'
    started = next(item for item in calls if item[0] == 'start')
    assert started[2]['mission_kind'] == 'SELF_IMPROVEMENT'
    assert 'Como arquiteto da ZARA' in started[1]
    assert 'core/lab_v1/service.py' in started[1]
    assert started[2]['evidence']['source_path'] == 'core/lab_v1/service.py'
    assert ('link', 'feedback:1', 'criticism-plan') in calls
    assert ('finish', 'feedback:1', True) in calls


def test_proposal_feedback_does_not_authorize_source_change(supervisor, monkeypatch):
    s, root = supervisor
    s.configure(enabled=True, workspace=root)
    calls = []
    s.autopilot = SimpleNamespace(
        start=lambda objective, **kwargs: calls.append(('start', objective, kwargs)) or {
            'success': True, 'session_id': 'proposal', 'state': 'QUEUED'},
        run=lambda sid: {'success': True, 'session_id': sid, 'state': 'COMPLETED'})
    feedback = {'id': 'feedback:proposal',
                'text': 'Tenho uma sugestão: a ZARA deveria avaliar uma ideia melhor.',
                'channel': 'text', 'evidence_sha256': 'proposal-sha', 'observed_at': 1}
    inbox = SimpleNamespace(next_received=lambda: feedback, link=lambda *args: None,
                            finish=lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'FeedbackInbox', lambda store: inbox)
    result = s.tick()
    assert result['state'] == 'COMPLETED'
    _, objective, kwargs = calls[0]
    assert kwargs['mission_kind'] == 'PRODUCT_CRITICISM_REVIEW'
    assert kwargs['evidence']['intent_mode'] == 'PROPOSAL_ONLY'
    assert 'Não implemente' in objective
    assert 'source_path' not in kwargs['evidence']
