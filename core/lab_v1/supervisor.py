"""Persistent opt-in supervisor. Sequential ticks resume work and inspect reviewed improvements."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from core.lab_v1.autopilot import Autopilot, WORKFLOW
from core.lab_v1.evolution import EvolutionEngine
from core.lab_v1.workforce_policy import WorkforcePolicy
from core.lab_v1.scout import TechnologyScout
from core.lab_v1.feedback_inbox import FeedbackInbox
from core.lab_v1.mission_controller import MissionController


def _default_workspace(executable=None):
    """Find the source checkout for packaged runs launched from a candidate."""
    configured = os.environ.get('ZARA_LAB_WORKSPACE')
    if configured:
        target = Path(configured).resolve()
        if (target / 'core' / 'lab_v1').is_dir() and (target / 'tools' / 'build_candidate.py').is_file():
            return target

    executable = Path(executable or sys.executable).resolve()
    for parent in executable.parents:
        marker = parent / 'ZARA_ACTIVE_BUILD.json'
        if (marker.is_file() and (parent / 'core' / 'lab_v1').is_dir()
                and (parent / 'tools' / 'build_candidate.py').is_file()):
            try:
                active = json.loads(marker.read_text(encoding='utf-8'))
                active_exe = Path(active.get('EXE_PATH', '')).resolve()
                if active_exe.is_file() and active_exe.is_relative_to(parent.resolve()):
                    return parent.resolve()
            except (OSError, ValueError, TypeError):
                continue
    return Path(__file__).resolve().parents[2]


class AutonomySupervisor:
    SUPPORTED_WORKFLOWS = frozenset({WORKFLOW})

    def __init__(self, runtime, *, autopilot=None):
        self.runtime, self.store = runtime, runtime.store
        self.autopilot = autopilot
        self.lock = threading.Lock()
        with self.store._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS lab_autonomy_policy(id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
            defaults = WorkforcePolicy.default_document() | {
                'enabled': True, 'workspace': str(_default_workspace()),
                'last_tick': None, 'last_state': 'READY',
                'next_evolution_check': 0, 'cadence_seconds': 60, 'evolution_cadence_seconds': 86400,
                'max_new_evolution_missions_per_day': 1, 'daily_date': None, 'daily_missions': 0,
                'stale_legacy_sessions': [], 'source_observer': None,
                # Alex explicitly asked on 2026-09-23 for Lab to start bounded
                # self-improvement on app launch. A saved False remains a pause.
                'scheduler_enabled': True}
            conn.execute('INSERT OR IGNORE INTO lab_autonomy_policy VALUES(1,?)', (json.dumps(defaults),))
            current = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
            merged = defaults | current
            configured_workspace = Path(merged.get('workspace') or '').resolve()
            if not ((configured_workspace / 'core' / 'lab_v1').is_dir()
                    and (configured_workspace / 'tools' / 'build_candidate.py').is_file()):
                merged['workspace'] = defaults['workspace']
            conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1', (json.dumps(merged),))

    def set_autopilot(self, autopilot):
        if self.autopilot is not None and self.autopilot is not autopilot:
            raise ValueError('Supervisor already owns a different Autopilot')
        self.autopilot = autopilot

    def _engine(self, workforce=None):
        if self.autopilot is None:
            self.autopilot = Autopilot(self.runtime, policy=workforce or WorkforcePolicy(self.policy()))
        return self.autopilot

    def record_background_error(self, detail):
        return self._save(last_state='FAILED', error='BACKGROUND_TASK_EXCEPTION', error_detail=str(detail))

    def policy(self):
        with self.store._connect() as conn:
            return json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])

    def _save(self, **changes):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            value = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
            value.update(changes)
            conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1', (json.dumps(value),))
        return value

    def configure(self, *, enabled, workspace=None):
        if type(enabled) is not bool: raise ValueError('enabled must be boolean')
        saved = self.policy()
        target = Path(workspace or saved.get('workspace') or '').resolve()
        if enabled and not (target / 'tools/build_current.py').is_file():
            raise ValueError('Workspace de manutencao nao configurado')
        return self._save(enabled=enabled, workspace=str(target) if enabled else saved.get('workspace'),
            last_state='READY' if enabled else 'MONITORING', background_enabled=True,
            scheduler_enabled=enabled)

    def ensure_team(self):
        # Autopilot provisions only policy-authorized Codex profiles.
        return self._engine(WorkforcePolicy(self.policy()))._team()[0]

    @staticmethod
    def _feedback_source_path(text):
        value = str(text or '').casefold()
        voice = ('voz', 'áudio', 'audio', 'microfone', 'wake word', 'kore')
        latency = ('latência', 'latencia', 'lento', 'lenta', 'demora')
        if any(word in value for word in voice):
            return 'core/gemini_live_voice.py'
        choices = (
            (latency, 'core/model_router.py'),
            (('feedback', 'elogio', 'elogios', 'classificador', 'triagem'),
             'core/lab_v1/feedback_inbox.py'),
            (('supervisor', 'autonomia', 'automática', 'automatica'), 'core/lab_v1/supervisor.py'),
            (('serviço', 'servico', 'interface', 'envio'), 'core/lab_v1/service.py'),
        )
        return next((path for words, path in choices if any(word in value for word in words)), None)

    @staticmethod
    def _proposal_only(text):
        value = str(text or '').casefold()
        return any(word in value for word in (
            'proposta', 'sugestão', 'sugestao', 'ideia', 'avalie', 'estude', 'pesquise'))

    def tick(self):
        if not self.lock.acquire(blocking=False): return {'state': 'BUSY'}
        try:
            policy = self.policy()
            workforce = WorkforcePolicy(policy)
            if not workforce.background_enabled:
                return {'state': 'DISABLED'}
            now = time.time()
            self._save(last_tick=now, last_heartbeat=now, last_state='CHECKING', error=None, error_detail=None)
            evolution = EvolutionEngine(self.runtime, policy['workspace'], policy=workforce,
                                        autopilot=self.autopilot)
            inventory = evolution.observe_local()
            self._save(source_observer=evolution.observer_snapshot())
            with self.store._connect() as conn:
                has_missions = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mission_controls'"
                ).fetchone()
                pending = ([json.loads(r[0]) for r in conn.execute('SELECT document FROM mission_controls')
                            if json.loads(r[0])['state'] not in ('COMPLETED', 'CANCELLED', 'FAILED')]
                           if has_missions else [])
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
            day = time.strftime('%Y-%m-%d')
            count = policy['daily_missions'] if policy.get('daily_date') == day else 0
            if now >= policy.get('next_evolution_check', 0) and count < policy['max_new_evolution_missions_per_day']:
                self._save(next_evolution_check=now + policy['evolution_cadence_seconds'])
                self.ensure_team()
                evolution.autopilot = self._engine(workforce)
                # Old unresolved feedback remains in history, but cannot
                # displace today's autonomous source inspection indefinitely.
                feedback = FeedbackInbox(self.store).next_received(max_age_seconds=86400)
                if feedback:
                    source_path = self._feedback_source_path(feedback['text'])
                    proposal_only = self._proposal_only(feedback['text']) or source_path is None
                    evidence = {'feedback_text': feedback['text'],
                                'evidence_sha256': feedback['evidence_sha256'],
                                'source_channel': feedback['channel'],
                                'observed_at': feedback['observed_at'],
                                'intent_mode': 'PROPOSAL_ONLY' if proposal_only else 'SOURCE_IMPROVEMENT'}
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
                        FeedbackInbox(self.store).link(feedback['id'], started['session_id'])
                        self._save(daily_date=day, daily_missions=count + 1,
                                   active_session=started['session_id'])
                        result = self._engine(workforce).run(started['session_id'])
                        FeedbackInbox(self.store).finish(feedback['id'],
                            completed=result.get('state') == 'COMPLETED')
                        self._save(last_state=result.get('state', 'UNKNOWN'))
                        return result
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
                    objective = (
                        'Avalie como líder esta oportunidade para a ZARA, escolha somente os papéis necessários e '
                        'produza um relatório proposal.md verificável para o owner aprovar. Não instale, não promova '
                        'e não altere o source atual. Oportunidade: ' + opportunity['opportunity'] +
                        '. Fonte observada: ' + opportunity['source'])
                    evidence = {'source': opportunity['source'], 'evidence_sha256': opportunity['evidence_sha256'],
                                'evidence_excerpt': opportunity['evidence_excerpt'],
                                'observed_at': opportunity['observed_at']}
                    objective += ('. SOURCE_URL: ' + evidence['source'] +
                                  '. EVIDENCE_SHA256: ' + evidence['evidence_sha256'] +
                                  '. EVIDENCE_EXCERPT: ' + evidence['evidence_excerpt'])
                    started = self._engine(workforce).start(objective,
                        mission_kind='DAILY_OPPORTUNITY_REVIEW', evidence=evidence)
                    if started.get('success'):
                        scout.link_review(opportunity['id'], started['session_id'])
                        self._save(daily_date=day, daily_missions=count + 1,
                                   active_session=started['session_id'])
                        result = self._engine(workforce).run(started['session_id'])
                        verification = scout.verify_review(opportunity['id'])
                        scout.finish_review(opportunity['id'], accepted=verification['passed'])
                        self._save(last_state=result.get('state', 'UNKNOWN'))
                        return result
            self._save(last_state='MONITORING')
            return {'state': 'MONITORING'}
        except Exception as exc:
            self._save(last_state='FAILED', error='SUPERVISOR_NEEDS_RECONCILIATION',
                       error_detail=f'{type(exc).__name__}: {exc}')
            return {'state': 'FAILED', 'error': 'SUPERVISOR_NEEDS_RECONCILIATION'}
        finally:
            self.lock.release()
