"""Canonical internal Lab mission entry and bounded planner/execution ports.

MissionController owns every transition. Model output supplies a validated DAG,
never permissions, arbitrary shell commands or a second task database.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading
import time
import tomllib
from dataclasses import replace

from core.lab_v1.domain import (Artifact, Availability, CapabilityGap, EventType, LabEvent, Lifecycle,
    Message, MessageKind, RoleName, Session, Task, TeamMembership, new_id, now, RunState)
from core.lab_v1.execution_scope import ExecutionScope, ScopeViolation, canonical_resource
from core.lab_v1.mission_controller import MissionController, MissionLimits, MissionStep, Receipt, Verification, TextProviderFailure, LeaseLost
from core.lab_v1.runtime import _extract_json
from core.lab_v1.sandbox_actions import SandboxActionPorts, SandboxActionRequest, SandboxFileExecutor
from core.lab_v1.workforce_policy import WorkforcePolicy
from core.lab_v1.artifact_verifier import ArtifactVerifier, validate_acceptance
from core.lab_v1.agent_continuity import AgentContinuity, StaleCheckpoint
from core.tool_verifier import VerificationState
from core.lab_v1.scout import review_evidence_bound

WORKFLOW = 'internal_dynamic_v1'
_TRANSIENT = {'BUSY', 'RATE_LIMITED', 'QUOTA_EXHAUSTED', 'PROVIDER_ERROR', 'OFFLINE', 'ERROR'}


class WorkspaceNotConfigured(ValueError):
    """No persistent source checkout is available for a packaged Lab."""


def _is_transient_extraction(path: Path) -> bool:
    return any(part.upper().startswith('_MEI') for part in path.parts)


def _persistent_checkout_candidates():
    # The source tree itself is valid during development. The second location
    # is this PC's known checkout, used only when PyInstaller runs from _MEI.
    return (Path(__file__).resolve().parents[2],
            Path.home() / 'Downloads' / 'ZARA 3.0 CLEAN 002')


def _verified_source_checkout(path: Path) -> bool:
    if _is_transient_extraction(path):
        return False
    git_marker = path / '.git'
    if git_marker.is_dir():
        git_valid = (git_marker / 'HEAD').is_file()
    elif git_marker.is_file():
        git_valid = git_marker.read_text(encoding='utf-8', errors='replace').startswith('gitdir:')
    else:
        git_valid = False
    if not git_valid or not all((path / name).is_file() for name in (
            'pyproject.toml', 'tools/build_current.py',
            'core/lab_v1/autopilot.py', 'core/lab_v1/evolution.py')):
        return False
    try:
        with (path / 'pyproject.toml').open('rb') as stream:
            return tomllib.load(stream).get('project', {}).get('name') == 'zara-3.0'
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return False


def resolve_lab_source_checkout(configured) -> Path | None:
    """Reject missing explicit paths; replace _MEI with a verified source tree."""
    if not configured:
        return None
    target = Path(configured).expanduser().resolve()
    if not _is_transient_extraction(target):
        # An existing empty directory can be an intentional no-work fixture.
        # A moved/deleted checkout must not silently look like that fixture.
        return target if target.is_dir() else None
    for candidate in _persistent_checkout_candidates():
        source = Path(candidate).expanduser().resolve()
        if _verified_source_checkout(source):
            return source
    return None


def _resource(agent):
    return 'provider:' + agent.provider_id + '/' + agent.model


class Autopilot:
    def __init__(self, runtime, *, root: Path | None = None, executor_factory=SandboxFileExecutor, policy=None):
        self.runtime, self.store = runtime, runtime.store
        self.root = root or self.store.db_path.parent / 'missions'
        # Desktop candidate packaging is one bounded action and can legitimately
        # take most of the 30-minute source-mission deadline on Windows.
        self.controller = MissionController(self.store, lease_s=1800)
        self.executor_factory = executor_factory
        self.policy = policy or WorkforcePolicy(WorkforcePolicy.default_document())
        workspace = self.policy.document.get('workspace')
        if workspace and _is_transient_extraction(Path(workspace)):
            source = resolve_lab_source_checkout(workspace)
            if source is not None:
                self.policy.document['workspace'] = str(source)
        self._continuity = None
        self.lock = threading.Lock()
        with self.store._connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS mission_autonomy (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id), document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS autonomy_gaps (
                    gap_id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id), stage TEXT NOT NULL,
                    reason TEXT NOT NULL, owner_action_required TEXT NOT NULL, candidate_automation TEXT NOT NULL,
                    risk TEXT NOT NULL, occurrences INTEGER NOT NULL, created_at REAL NOT NULL,
                    UNIQUE(session_id,stage,reason));
            ''')

    def _get_continuity(self):
        if self._continuity is None:
            # Continuity must read the SAME UserMemoryCore the memory adapter
            # promotes into; otherwise facts promoted by a completed mission
            # would be invisible to the recovery context of the next one.
            adapter = self.runtime.memory_adapter
            memory = getattr(adapter, 'memory', None) if adapter is not None else None
            self._continuity = AgentContinuity(self.store, memory)
        return self._continuity

    def _sync_agent_continuity(self, sid):
        """Advance each agent only from receipts accepted by MissionController."""
        doc = self.controller.snapshot(sid)
        artifacts = {item.id: item for item in self.store.list_artifacts(sid)}
        latest_by_agent = {}
        for step in doc.get('steps', []):
            if step.get('status') not in ('VERIFYING', 'DONE'):
                continue
            attempt_id = step.get('attempt_id')
            receipt = step.get('receipt') or {}
            artifact_ref = receipt.get('artifact_ref')
            if not attempt_id or not str(artifact_ref or '').endswith(':' + attempt_id):
                continue
            artifact = artifacts.get(artifact_ref)
            task = self.store.get_task(step.get('task_id'))
            if task is None:
                continue
            if artifact is not None and artifact.task_id != task.id:
                continue
            if artifact is None and not str(artifact_ref or '').startswith('sandbox-action:'):
                # A verified ACTION keeps its receipt ref as durable evidence
                # even though the sandbox write has no Artifact row.
                continue
            if not task.assigned_agent_id:
                continue
            evidence_ref = artifact.id if artifact is not None else artifact_ref
            latest_by_agent[task.assigned_agent_id] = (step, task, evidence_ref)

        continuity = self._get_continuity()
        for agent_id, (step, task, artifact_ref) in latest_by_agent.items():
            current = continuity.load_checkpoint(sid, agent_id)
            if current and current.state.get('attempt_id') == step['attempt_id']:
                continue
            state = {
                'artifact_ref': artifact_ref,
                'attempt_id': step['attempt_id'],
                'step_id': step['id'],
                'task_id': task.id,
            }
            handoff = self._handoff_baton(sid, agent_id, step, artifact_ref, current)
            if handoff is not None:
                # One durable row carries both the plain cursor and the stage
                # baton: a failover resumes with the artifact AND the formal
                # handoff checkpoint, never one without the other.
                state['handoff'] = handoff
            try:
                continuity.save_checkpoint(
                    sid,
                    agent_id,
                    cursor=step['id'],
                    summary=f'Artefato duravel produzido para a tarefa {task.id}.',
                    state=state,
                    expected_revision=current.revision if current else None,
                )
            except StaleCheckpoint:
                # Another restart worker may have synchronized the same receipt
                # after our read. Never turn that harmless race into mission
                # failure, and never overwrite a different newer checkpoint.
                raced = continuity.load_checkpoint(sid, agent_id)
                if raced and raced.state.get('attempt_id') == step['attempt_id']:
                    continue

    @staticmethod
    def _handoff_baton(sid, agent_id, step, artifact_ref, current):
        """Map a controller-verified step onto the STRATEGIST→MAESTRO baton.

        Only steps whose verification the controller already accepted advance
        the baton, and it must advance exactly one stage like
        `AgentContinuity.save_handoff_checkpoint` enforces. Anything that does
        not fit returns None and the plain checkpoint is kept unchanged.
        """
        if step['id'] == 'plan':
            stage = 'STRATEGIST'
        elif step['kind'] == 'DELEGATE':
            stage = 'EXECUTOR'
        elif step['kind'] == 'ACTION':
            stage = 'REVIEWER'
        else:
            return None
        prior = (current.state.get('handoff') or {}).get('stage') if current else None
        if prior is not None:
            stages = ('STRATEGIST', 'EXECUTOR', 'REVIEWER', 'MAESTRO')
            if stages.index(stage) != stages.index(str(prior)) + 1:
                return None
        verification = step.get('verification') or {}
        evidence_ref = str(verification.get('evidence_ref') or artifact_ref)
        return {
            'stage': stage,
            'artifact_ref': str(artifact_ref),
            'evidence_refs': [evidence_ref],
            'provenance': {'session': sid, 'agent': agent_id, 'step': step['id']},
        }

    def _decision(self, agent, *, retry=False, team_id=None, _providers=None, _health=None):
        choice = self.policy.effective_resource(agent)
        # Worker selection must not block behind unrelated adapters (for
        # example a Codex CLI probe) when this particular agent is assigned to
        # NVIDIA or another provider.  The UI can still inspect every provider;
        # the execution path only needs the resource it is about to authorize.
        if _providers is None:
            adapter = self.runtime.registry.get(choice.provider_id)
            providers = [adapter.probe()] if adapter is not None else []
        else:
            providers = _providers
        info = next((p for p in providers if p.id == choice.provider_id), None)
        status = (_health if _health is not None else self.runtime.registry.health_snapshot()).get(f'model:{choice.provider_id}:{choice.model_id}', {})
        available = status.get('availability') == 'AVAILABLE'
        from dataclasses import replace as _replace
        _candidate = _replace(agent, provider_id=choice.provider_id, model=choice.model_id)
        if retry and status.get('availability') in _TRANSIENT:
            available = True
            if info is not None and info.availability.value in _TRANSIENT:
                info = _replace(info, availability=Availability.AVAILABLE)
        return self.policy.authorize(_candidate, info, model_available=available, team_id=team_id)

    def candidates(self, team_id=None, role=None, exclude=(), *, retry=False):
        result = []
        team_agents = self.store.list_agents(team_id=team_id)
        provider_ids = {
            self.policy.effective_resource(agent).provider_id
            for agent in team_agents
            if not agent.archived
        }
        providers = [adapter.probe() for provider_id in provider_ids
                     if (adapter := self.runtime.registry.get(provider_id)) is not None]
        health = self.runtime.registry.health_snapshot()
        for agent in team_agents:
            choice = self.policy.effective_resource(agent)
            adapter = self.runtime.registry.get(choice.provider_id)
            if (agent.archived or agent.id in exclude or (role is not None and agent.role != role)
                    or 'model.text' not in agent.capabilities or not getattr(adapter, 'controlled_text_only', False)):
                continue
            if self._decision(agent, retry=retry, team_id=team_id, _providers=providers, _health=health).allowed: result.append(agent)
        return sorted(result, key=lambda a: (self.policy.preference_rank(
            self.policy.effective_resource(a).model_id, role.value if role else a.role.value),
                                             a.created_at, a.id))

    def _ensure_architect(self, team):
        # Canonical instances only. Assign work to an existing member; never
        # clone a model into a fictional additional participant.
        return next((a for a in self.store.list_agents(team_id=team.id)
                     if not a.archived and a.role == RoleName.CEO
                     and self._decision(a, team_id=team.id).allowed), None)

    def _team(self, team_id=None):
        for team in self.store.list_teams():
            if team.archived or (team_id and team.id != team_id): continue
            architect = self._ensure_architect(team)
            agents = self.candidates(team.id)
            if not agents: continue
            planner = next((a for a in agents if architect and a.id == architect.id), None)
            planner = planner or next((a for a in agents if a.role in (RoleName.MEMBER, RoleName.CEO)), agents[0])
            builder = next((a for a in agents if a.role == RoleName.BUILDER), planner)
            return team, planner, builder
        raise ValueError('WAITING_RESOURCE: no authorized internal worker')

    def _yield_internal_work_to_owner(self):
        """Internal work may fail or wait, but may never block an owner mission."""
        with self.store._connect() as conn:
            rows = conn.execute('''SELECT c.session_id,c.document,c.lease_token,c.lease_until,a.document
                FROM mission_controls c JOIN mission_autonomy a ON a.session_id=c.session_id''').fetchall()
        for row in rows:
            mission, autonomy = json.loads(row[1]), json.loads(row[4])
            if (autonomy.get('mission_kind') not in ('DAILY_OPPORTUNITY_REVIEW', 'PRODUCT_CRITICISM_REVIEW')
                    or mission['state'] in ('COMPLETED', 'FAILED', 'CANCELLED')):
                continue
            if row[2] is not None and row[3] > self.controller.clock():
                continue
            self.controller.fail_idle(row[0], 'INTERNAL_REVIEW_YIELDED_TO_OWNER')
            self._metrics(row[0], content_review='FAILED', owner_priority_applied=True)

    def start(self, intent, session_id=None, *, mission_kind='OWNER_MISSION', evidence=None):
        if not isinstance(intent, str) or not 1 <= len(intent.strip()) <= 12000:
            raise ValueError('Intent must contain 1..12000 characters')
        if not self.policy.mission_entry_enabled: raise ValueError('WORKFORCE_POLICY_REQUIRED')
        with self.lock:
            if mission_kind == 'OWNER_MISSION':
                self._yield_internal_work_to_owner()
            with self.store._connect() as conn:
                for row in conn.execute('SELECT * FROM mission_controls').fetchall():
                    doc = json.loads(row['document'])
                    if self.controller.can_supersede_stale_provider_block(conn, doc, row):
                        continue
                    if doc['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
                        return {'success': False, 'code': 'MISSION_BUSY', 'state': doc['state'],
                                'session_id': doc['session_id'],
                                'error': 'Outra missão solicitada por você ainda está em andamento.'}
            sid = session_id or new_id('session')
            session = self.store.get_session(sid)
            team, planner, _ = self._team(session.team_id if session else None)
            if session is not None:
                if session.state.value != 'QUEUED' or session.team_id != team.id or self.store.list_runs(sid):
                    raise ValueError('Session is not an unstarted mission')
                session.objective = intent.strip()
            else: session = Session(sid, team.id, intent.strip())
            from core.lab_v1.source_mission import source_requested, prepare_source
            if source_requested(intent, mission_kind):
                workspace = self.policy.document.get('workspace')
                if workspace and resolve_lab_source_checkout(workspace) is None:
                    raise WorkspaceNotConfigured('WORKSPACE_NOT_CONFIGURED: persistent source checkout not found')
            sandbox = Path(canonical_resource(str(self.root / sid)))
            sandbox.mkdir(parents=True, exist_ok=False)
            source = prepare_source(self, sandbox, intent) if source_requested(intent, mission_kind) else None
            self.store.save_session(session)
            self.store.add_message(Message('owner:' + sid, sid, MessageKind.USER, 'Alex', intent.strip()))
            resources = tuple(_resource(a) for a in self.candidates(team.id))
            scope = ExecutionScope((str(sandbox), *resources), ('model.text', 'files.write', 'source.prepare', 'source.apply', 'source.tests', 'source.build'),
                authorization_state='POLICY_AUTHORIZED', authorization_ref='autopilot:internal-dynamic-v1')
            task = Task(sid + ':plan', sid, 'Planejar missão', 'Create a bounded, verifiable task plan for the objective.',
                        planner.id, assigned_agent_id=planner.id, acceptance='Valid DAG with supported deterministic acceptance methods')
            initial_steps = []
            if source:
                prepare_task = Task(sid + ':source_prepare', sid, 'Preparar candidata isolada',
                    'Create and verify the bounded source snapshot before model planning.', planner.id,
                    assigned_agent_id=planner.id, acceptance='Verified isolated source snapshot')
                self.store.save_task(prepare_task)
                initial_steps.append(MissionStep('source_prepare', prepare_task.id, 'ACTION',
                    capability='source.prepare', resources=(str(sandbox),)))
            self.store.save_task(task)
            initial_steps.append(MissionStep('plan', task.id, 'INVOKE',
                depends_on=('source_prepare',) if source else (), capability='model.text', resources=(_resource(planner),)))
            metrics = {'workflow': WORKFLOW, 'owner_touches': 1, 'sandbox': str(sandbox), 'planner_id': planner.id,
                'plan_version': 1, 'agent_selection_automatic': True, 'task_creation_automatic': False,
                'delegation_automatic': False, 'context_transfer_automatic': False,
                'verification_automatic': False, 'recovery_automatic': False, 'final_report_automatic': False,
                'content_review': 'NOT_VERIFIED', 'target': None, 'selected_roles': [planner.role.value],
                'mission_kind': mission_kind, 'evidence': evidence or {}, 'leader_id': planner.id,
                'planner_function': 'ARCHITECT', 'pause_requested': False,
                'pause_generation': 0, 'observation_count': 0,
                'learning_registered': False, 'next_work_proposed': False}
            if source:
                metrics['source_work'] = source
                metrics['mission_kind'] = 'SELF_IMPROVEMENT'
            with self.store._connect() as conn:
                conn.execute('INSERT INTO mission_autonomy VALUES(?,?)', (sid, json.dumps(metrics)))
            self.controller.plan(sid, initial_steps,
                MissionLimits(max_turns=24 if source else 16,
                              max_delegations=20 if source else 15,
                              max_retries=12 if source else 4,
                              max_actions=32 if source else 8, timeout_s=3600 if source else 1800),
                scope=scope, dynamic=True)
            return {'success': True, 'session_id': sid, 'state': 'QUEUED'}

    def metrics(self, sid):
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM mission_autonomy WHERE session_id=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def _event_once(self, event_id, event_type, sid, payload, *, entity_id=None):
        """Append one audit event without creating duplicates on replay.

        Events are the existing Lab audit stream, not a second autonomy store.
        The read-before-write is deliberately followed by a uniqueness-safe
        retry check so a restart can safely call the same checkpoint again.
        """
        if any(event.id == event_id for event in self.store.list_events(sid, limit=500)):
            return False
        try:
            self.store.append_event(LabEvent(
                event_id, 0, event_type, sid, entity_id, payload, now()))
        except Exception:
            if any(event.id == event_id for event in self.store.list_events(sid, limit=500)):
                return False
            raise
        return True

    @staticmethod
    def _continuous_digest(document):
        return hashlib.sha256(json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()

    def _paused(self, sid):
        metrics = self.metrics(sid) or {}
        return bool(metrics.get('pause_requested'))

    def pause(self, sid, reason='owner_requested'):
        """Request a safe pause at the next controller checkpoint.

        No lease is stolen and no in-flight operation is interrupted.  The
        current bounded operation may finish; the run loop then dispatches no
        further work until :meth:`resume` is called.
        """
        doc = self.controller.snapshot(sid)
        if doc['state'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
            return {'success': False, 'state': doc['state'], 'session_id': sid,
                    'code': 'MISSION_TERMINAL'}
        metrics = self.metrics(sid) or {}
        if metrics.get('pause_requested'):
            return {'success': True, 'state': 'PAUSED', 'session_id': sid,
                    'pause_generation': metrics.get('pause_generation', 1)}
        generation = int(metrics.get('pause_generation', 0)) + 1
        clean_reason = str(reason or 'owner_requested').strip()[:500] or 'owner_requested'
        self._metrics(sid, pause_requested=True, pause_generation=generation,
                      pause_reason=clean_reason, paused_at=now())
        self._event_once(
            f'autopilot-paused:{sid}:{generation}', 'mission.paused', sid,
            {'session_id': sid, 'generation': generation, 'reason': clean_reason},
        )
        return {'success': True, 'state': 'PAUSED', 'session_id': sid,
                'pause_generation': generation, 'reason': clean_reason}

    def resume(self, sid):
        """Resume a paused mission without resetting its controller history."""
        doc = self.controller.snapshot(sid)
        metrics = self.metrics(sid) or {}
        if not metrics.get('pause_requested'):
            state = doc['state'] if doc['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED') else doc['state']
            return {'success': True, 'state': state, 'session_id': sid,
                    'code': 'ALREADY_RUNNING' if state not in ('COMPLETED', 'FAILED', 'CANCELLED')
                    else 'MISSION_TERMINAL'}
        generation = int(metrics.get('pause_generation', 0))
        self._metrics(sid, pause_requested=False, resumed_at=now())
        self._event_once(
            f'autopilot-resumed:{sid}:{generation}', 'mission.resumed', sid,
            {'session_id': sid, 'generation': generation},
        )
        return {'success': True, 'state': doc['state'], 'session_id': sid,
                'pause_generation': generation}

    # Explicit aliases keep the public vocabulary readable to callers without
    # introducing another controller or another persistence path.
    pause_mission = pause
    resume_mission = resume

    def observe(self, sid):
        """Capture a deterministic, replay-safe observation of a mission."""
        doc = self.controller.snapshot(sid)
        metrics = self.metrics(sid) or {}
        steps = [{
            'id': step['id'], 'kind': step['kind'], 'status': step['status'],
            'attempt_id': step.get('attempt_id'),
            'verification': step.get('verification'),
        } for step in doc.get('steps', [])]
        observation = {
            'session_id': sid,
            'state': doc['state'],
            'blocker': doc.get('blocker'),
            'cancel_requested': bool(doc.get('cancel_requested')),
            'paused': bool(metrics.get('pause_requested')),
            'steps': steps,
            'used': dict(doc.get('used') or {}),
            'observations': len(self.controller.observations(sid)),
        }
        fingerprint = self._continuous_digest({key: value for key, value in observation.items()
                                               if key != 'observations'})
        event_id = f'autopilot-observed:{sid}:{fingerprint}'
        created = self._event_once(event_id, 'mission.observed', sid, {
            **observation, 'fingerprint': fingerprint,
        })
        self._metrics(sid, last_observation=observation, observation_fingerprint=fingerprint,
                      observation_event_id=event_id,
                      observation_count=int(metrics.get('observation_count', 0)) + int(created))
        return {'success': True, 'state': 'PAUSED' if observation['paused'] else observation['state'],
                'session_id': sid, 'observation': observation, 'event_id': event_id,
                'idempotent_replay': not created}

    observe_mission = observe

    def register_learning(self, sid, observation=None):
        """Persist bounded learning from the current evidence chain.

        Completion is eligible for the existing verified-memory promotion;
        blocked or paused work is still recorded as operational learning but is
        never presented as a successful outcome.
        """
        doc = self.controller.snapshot(sid)
        observation = observation or self.observe(sid)
        evidence = [step.get('verification', {}).get('evidence_ref')
                    for step in doc.get('steps', []) if step.get('verification')]
        evidence = [str(item) for item in evidence if item]
        paused = self._paused(sid) and doc['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED')
        outcome = 'PAUSED' if paused else doc['state']
        statement = ('Missão concluída e verificada; aceite determinístico foi preservado.'
                     if outcome == 'COMPLETED' else
                     f'Missão observada em {outcome}; nenhum próximo efeito foi presumido.'
                     )
        learning = {
            'session_id': sid, 'outcome': outcome, 'statement': statement,
            'evidence_refs': evidence[:32],
            'retry_count': int(doc.get('used', {}).get('retries', 0)),
            'observation_event_id': observation.get('event_id'),
        }
        fingerprint = self._continuous_digest(learning)
        event_id = f'autopilot-learning:{sid}:{fingerprint}'
        created = self._event_once(event_id, 'mission.learning_recorded', sid,
                                   {**learning, 'fingerprint': fingerprint})
        self._metrics(sid, learning_registered=True, learning_event_id=event_id,
                      learning_outcome=outcome, learning_fingerprint=fingerprint)
        return {'registered': True, 'event_id': event_id, 'learning': learning,
                'idempotent_replay': not created}

    record_learning = register_learning

    def propose_next_work(self, sid, observation=None):
        """Propose, but never silently start, the next bounded piece of work."""
        doc = self.controller.snapshot(sid)
        observation = observation or self.observe(sid)
        paused = self._paused(sid) and doc['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED')
        if paused:
            title, requires_owner = 'Retomar a missão após confirmação do owner', True
        elif doc['state'] == 'COMPLETED':
            title, requires_owner = 'Revisar o resultado verificado antes de novo trabalho', True
        elif doc['state'] in ('BLOCKED', 'BLOCKED_NEEDS_OWNER', 'FAILED'):
            title, requires_owner = 'Resolver o impedimento registrado com evidência', True
        elif doc['state'] in ('CANCELLED', 'CANCELLING'):
            title, requires_owner = 'Confirmar se uma nova missão deve ser criada', True
        else:
            title, requires_owner = 'Continuar a etapa pendente no mesmo sandbox', False
        proposal = {
            'session_id': sid, 'title': title, 'state': doc['state'],
            'requires_owner': requires_owner, 'paused': paused,
            'blocker': doc.get('blocker'), 'evidence_event_id': observation.get('event_id'),
        }
        fingerprint = self._continuous_digest(proposal)
        proposal['proposal_id'] = f'next-work:{sid}:{fingerprint}'
        created = self._event_once(
            'autopilot-' + proposal['proposal_id'], 'mission.next_work_proposed', sid,
            {**proposal, 'fingerprint': fingerprint},
        )
        self._metrics(sid, next_work=proposal, next_work_event_id='autopilot-' + proposal['proposal_id'],
                      next_work_proposed=True)
        return {**proposal, 'idempotent_replay': not created}

    next_work = propose_next_work

    def resume_failed_source(self, sid):
        """Resume from persisted receipts and budgets, without administrative rewrites."""
        metrics = self.metrics(sid)
        if not metrics or not metrics.get('source_work'):
            return {'success': False, 'code': 'SOURCE_MISSION_REQUIRED', 'session_id': sid}
        current = self.controller.snapshot(sid)
        if current['state'] in ('COMPLETED', 'CANCELLED', 'FAILED', 'BLOCKED_NEEDS_OWNER'):
            return {'success': current['state'] == 'COMPLETED', 'state': current['state'],
                    'code': 'SOURCE_TERMINAL_STATE', 'session_id': sid}
        return self.run(sid)

    def _metrics(self, sid, **updates):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            data = json.loads(conn.execute('SELECT document FROM mission_autonomy WHERE session_id=?', (sid,)).fetchone()[0])
            data.update(updates)
            conn.execute('UPDATE mission_autonomy SET document=? WHERE session_id=?', (json.dumps(data), sid))

    def validate_plan(self, sid, plan):
        from core.lab_v1.real_work_contract import validate_planner_task, reject_planner_solution_material
        reject_planner_solution_material(plan)
        from core.lab_v1.source_mission import SourceMission
        if self.metrics(sid).get('source_work'):
            return SourceMission(self, sid).validate_plan(plan)
        if not isinstance(plan, dict) or plan.get('plan_version') != 1 or not isinstance(plan.get('mission'), str):
            raise ValueError('PLAN_SCHEMA')
        items = plan.get('tasks')
        if not isinstance(items, list) or not 1 <= len(items) <= 8: raise ValueError('TASK_LIMIT')
        seen, paths = set(), set()
        sandbox = Path(self.metrics(sid)['sandbox'])
        for item in items:
            validate_planner_task(item)
            if not isinstance(item, dict): raise ValueError('TASK_SCHEMA')
            for field in ('id', 'title', 'instruction', 'role', 'capability', 'path'):
                if not isinstance(item.get(field), str) or not item[field].strip(): raise ValueError('TASK_' + field)
            if not re.fullmatch('[a-z][a-z0-9_-]{0,39}', item['id']) or item['id'] == 'plan' or item['id'] in seen:
                raise ValueError('TASK_ID')
            deps = item.get('depends_on')
            if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps) or not set(deps) <= seen:
                raise ValueError('DEPENDENCIES_MUST_PRECEDE')
            RoleName(item['role'])
            if item.get('risk') != 'LOW' or type(item.get('repair_budget')) is not int or not 0 <= item['repair_budget'] <= 2:
                raise ValueError('RISK_OR_REPAIR_BUDGET')
            relative = Path(item['path'])
            if relative.is_absolute() or len(relative.parts) != 1 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,60}\.(py|md|txt|json)', item['path']):
                raise ValueError('SANDBOX_PATH_REQUIRED')
            target = canonical_resource(str(sandbox / relative))
            if target in paths: raise ValueError('DUPLICATE_PATH')
            expected_suffix = {'artifact.python': {'.py'}, 'artifact.text': {'.md', '.txt'}, 'artifact.json': {'.json'}}
            if relative.suffix not in expected_suffix.get(item['capability'], set()): raise ValueError('UNSUPPORTED_CAPABILITY')
            validate_acceptance(item.get('acceptance'), item['capability'])
            seen.add(item['id']); paths.add(target)
        metrics = self.metrics(sid)
        if metrics.get('mission_kind') == 'DAILY_OPPORTUNITY_REVIEW':
            evidence = metrics.get('evidence') or {}
            if (len(items) != 1 or items[0]['role'] != 'REVIEWER'
                    or items[0]['capability'] != 'artifact.text' or items[0]['path'] != 'proposal.md'
                    or items[0]['acceptance'].get('method') != 'constraints'):
                raise ValueError('INDEPENDENT_REVIEW_PLAN_REQUIRED')
        if metrics.get('mission_kind') == 'PRODUCT_CRITICISM_REVIEW':
            reviewers = [item for item in items if item['role'] == 'REVIEWER']
            if not reviewers:
                raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
        return plan

    def _expand(self, sid):
        doc = self.controller.snapshot(sid)
        plan_step = next((step for step in doc['steps'] if step['id'] == 'plan'), None)
        if not doc.get('awaiting_expansion') or plan_step is None or plan_step['status'] != 'DONE': return
        if self.metrics(sid).get('source_work'):
            from core.lab_v1.source_mission import SourceMission
            return SourceMission(self, sid).expand()
        plan = self.validate_plan(sid, _extract_json(self.store.get_task(sid + ':plan').result))
        team = self.store.get_session(sid).team_id
        tasks, steps, selected = [], [], []
        planner_id = self.metrics(sid)['planner_id']
        for item in plan['tasks']:
            candidates = self.candidates(team, RoleName(item['role']))
            if not candidates:
                # Resource/role mismatch never grants another identity silently.
                self._block(sid, 'WORKFORCE_ROLE_UNAVAILABLE:' + item['role']); return
            worker = candidates[0]; selected.append(worker.role.value)
            spec = json.dumps(item, ensure_ascii=False)
            for phase, capability, kind in [('draft', 'model.text', 'DELEGATE'), ('write', 'files.write', 'ACTION')]:
                stepid = item['id'] + ':' + phase
                task = Task(sid + ':' + stepid, sid, item['title'] + (' · criar' if phase == 'draft' else ' · gravar'),
                    item['instruction'], planner_id, assigned_agent_id=worker.id, acceptance=spec, max_turns=1)
                tasks.append(task)
                dependencies = tuple(x + ':write' for x in item['depends_on']) or ('plan',)
                if phase == 'write': dependencies = (item['id'] + ':draft',)
                resource = _resource(worker) if phase == 'draft' else str(Path(self.metrics(sid)['sandbox']) / item['path'])
                steps.append(MissionStep(stepid, task.id, kind, dependencies, capability, (resource,)))
        if self.controller.expand_verified_plan(sid, tasks, steps, metadata=plan):
            with self.controller._transaction() as conn:
                doc, _ = self.controller._load(conn, sid)
                for step in doc['steps']:
                    if step['id'] != 'plan':
                        item = next(i for i in plan['tasks'] if step['id'].split(':')[0] == i['id'])
                        step['repair_budget'] = item['repair_budget']
                self.controller._save(conn, doc, 'mission.repair_budgets_bound')
            self._metrics(sid, task_creation_automatic=True, selected_roles=sorted(set(selected)),
                plan_version=doc['plan_version'], target=str(Path(self.metrics(sid)['sandbox']) / plan['tasks'][0]['path']))

    def _block(self, sid, reason):
        with self.controller._transaction() as conn:
            doc, row = self.controller._load(conn, sid)
            if row['lease_until'] > self.controller.clock(): return
            doc['state'], doc['blocker'] = 'BLOCKED_NEEDS_OWNER', reason
            self.controller._save(conn, doc, 'mission.owner_required')
        self._gap(sid, reason)

    def _gap(self, sid, reason):
        with self.store._connect() as conn:
            conn.execute('INSERT OR IGNORE INTO autonomy_gaps VALUES(?,?,?,?,?,?,?,?,?)', (
                'gap:' + sid + ':' + reason, sid, 'execution', reason,
                'Resolver impedimento quando a recuperação limitada não bastar',
                'Proposta: adicionar cobertura de regressão e capacidade verificável', 'LOW', 1, time.time()))
        key = 'cap-gap:' + sid + ':' + reason
        if not any(g.id == key for g in self.store.list_capability_gaps(sid)):
            self.store.save_capability_gap(CapabilityGap(key, sid, reason, detail='Falha observada na missão; evidência preservada.'))

    def _report(self, sid):
        doc = self.controller.snapshot(sid)
        if doc['state'] != 'COMPLETED' or doc.get('awaiting_expansion'): return
        if self.metrics(sid).get('source_work'):
            from core.lab_v1.source_mission import SourceMission
            return SourceMission(self, sid).report()
        mid = 'autopilot-report:' + sid
        if not any(m.id == mid for m in self.store.list_messages(sid)):
            files = [i['path'] for i in doc.get('planner_contract', {}).get('tasks', [])]
            self.store.add_message(Message(mid, sid, MessageKind.ZARA, 'ZARA',
                f"OBJETIVO: {self.store.get_session(sid).objective}\nRESULTADO: artefatos concluídos no sandbox.\n"
                f"ALTERAÇÕES: {', '.join(files)}\nVERIFICAÇÃO: casos de aceitação determinísticos e leitura dos bytes gravados.\n"
                "LIMITES: validação restrita aos casos e às capacidades declarados; nenhum acesso externo.\nAÇÃO DO OWNER: nenhuma."))
        self._metrics(sid, verification_automatic=True, final_report_automatic=True, content_review='ACCEPTANCE_CASES_VERIFIED')

    def _promote_verified_outcome(self, sid):
        """Promote a completed, verified mission into ZARA's central memory.

        This is the production caller for `memory_adapter.promote_verified_mission`
        and `store.promote_lesson`: a mission only reaches here with every step
        verification PASS and accepted artifacts, which is exactly the evidence
        chain both promotions require. Both paths are idempotent (the first is
        keyed by `verified-memory:<sid>`, the second by `lesson-verified:<sid>`),
        so crash/replay after completion never duplicates a fact or a lesson.
        """
        doc = self.controller.snapshot(sid)
        if doc['state'] != 'COMPLETED' or doc.get('awaiting_expansion'): return
        session = self.store.get_session(sid)
        adapter = self.runtime.memory_adapter
        files = [i['path'] for i in doc.get('planner_contract', {}).get('tasks', [])]
        artifact_list = ', '.join(files) or 'sandbox'
        if session is None or adapter is None or not hasattr(adapter, 'promote_verified_mission'):
            return
        statement = (f"Na missão '{session.objective}', os artefatos {artifact_list} foram "
                     "concluídos e verificados pelos casos de aceitação da missão.")
        try:
            adapter.promote_verified_mission(sid, statement)
        except (ValueError, OSError):
            return
        # Central marked-verified lesson: same evidence chain, global audience.
        events = self.store.list_events(sid, limit=500)
        marker_id = 'lesson-verified:' + sid
        if any(e.id == marker_id for e in events): return
        evidence = next((e for e in events if e.type == 'mission.verified'), None)
        if evidence is None:
            evidence = next((e for e in events if e.type in ('artifact.created', 'task.completed')), None)
        if evidence is None: return
        try:
            marker = self.store.append_event(LabEvent(
                marker_id, 0, EventType.LESSON_MARKED_VERIFIED, sid, None,
                {'lesson': statement, 'evidence_event_id': evidence.id}, now()))
            self.store.promote_lesson(marker.id)
            self._metrics(sid, central_memory_promoted=True)
        except (ValueError, OSError):
            # A promotion failure must never fail an already completed mission.
            return

    def _recover_interrupted(self, sid):
        doc = self.controller.snapshot(sid)
        if doc['state'] in ('CANCELLED', 'COMPLETED', 'FAILED'): return
        # A lease still held by a process that died with the previous Lab would
        # otherwise freeze this mission until it expired on its own.
        self.controller.release_dead_leases()
        with self.store._connect() as conn:
            row = conn.execute('SELECT lease_until FROM mission_controls WHERE session_id=?', (sid,)).fetchone()
        if row[0] > self.controller.clock(): return
        step = next((s for s in doc['steps'] if s['status'] in ('DISPATCHED', 'RECONCILE')), None)
        if not step: return
        if step['capability'] == 'model.text':
            artifacts = self.store.list_artifacts(sid)
            artifact = next((a for a in artifacts if a.id == 'response:' + str(step['attempt_id'])
                             and a.task_id == step['task_id']), None)
            if artifact:
                from core.lab_v1.review_evidence_packet import _bound_response_run
                try:
                    indexed = {item.id: item for item in artifacts}
                    if len(indexed) != len(artifacts):
                        raise ValueError('MODEL_RESPONSE_BINDING_DUPLICATE_ARTIFACT')
                    _bound_response_run(
                        self.store, indexed, session_id=sid, task_id=step['task_id'],
                        attempt_id=step['attempt_id'], response=artifact)
                except ValueError as exc:
                    self.controller.reconcile(
                        sid, step['id'], verdict='UNKNOWN', evidence_ref=str(exc))
                    return
                self.controller.reconcile(sid, step['id'], verdict='APPLIED', evidence_ref=artifact.id,
                    receipt=Receipt(artifact.id, artifact.body))
                return
            # A text-only attempt cannot have a filesystem/tool effect. Retain
            # its consumed turn/cost uncertainty and authorize only a budgeted retry.
            with self.store._connect() as conn:
                conn.execute("UPDATE runs SET state='FAILED',error='INTERRUPTED_OUTPUT_UNKNOWN',ended_at=? "
                    "WHERE session_id=? AND task_id=? AND state='STARTED'", (time.time(), sid, step['task_id']))
            self.controller.reconcile(sid, step['id'], verdict='NOT_APPLIED',
                evidence_ref='text-only:no-tool-effect:attempt:' + str(step['attempt_id']))
            self._metrics(sid, recovery_automatic=True)
        # File writes with incomplete receipts are never replayed. Read-only
        # reconciliation can recover only a durable RECEIVED receipt + exact bytes.
        elif step['capability'] == 'files.write':
            with self.store._connect() as conn:
                record = conn.execute('SELECT document FROM mission_action_results WHERE attempt_id=?',
                                      (step['attempt_id'],)).fetchone()
            if record:
                data = json.loads(record[0]); path = Path(canonical_resource(data['path']))
                if (data.get('status') == 'RECEIVED' and path.is_file()
                        and hashlib.sha256(path.read_bytes()).hexdigest() == data.get('sha256')):
                    self.controller.reconcile(sid, step['id'], verdict='APPLIED', evidence_ref='sandbox-recovery:' + step['attempt_id'],
                        receipt=Receipt('sandbox-action:' + step['attempt_id'], f'{path.name} gravado; sha256={data["sha256"]}'))
        elif step['capability'] in ('source.prepare', 'source.apply', 'source.tests', 'source.build'):
            from core.lab_v1.source_mission import SourceMission
            receipt = SourceMission(self, sid).recover_receipt(step)
            if receipt:
                self.controller.reconcile(sid, step['id'], verdict='APPLIED',
                    evidence_ref='source-recovery:' + receipt.artifact_ref, receipt=receipt)
                self._metrics(sid, recovery_automatic=True)
            else:
                self.controller.reconcile(sid, step['id'], verdict='UNKNOWN',
                    evidence_ref='source-action:no-durable-bound-receipt:' + str(step['attempt_id']))

    def run(self, sid):
        metrics = self.metrics(sid)
        if not metrics or metrics.get('workflow') != WORKFLOW: raise ValueError('UNSUPPORTED_LEGACY_WORKFLOW')
        if not self.lock.acquire(blocking=False):
            return {'success': False, 'state': self.controller.snapshot(sid)['state'], 'session_id': sid}
        try:
            ports = _AutopilotPorts(self, sid, metrics)
            self._recover_interrupted(sid)
            self._sync_agent_continuity(sid)
            self.controller.resume_due_resource(sid)
            self.observe(sid)
            for _ in range(48):
                if self._paused(sid):
                    break
                self._expand(sid)
                if self._paused(sid):
                    break
                before = self.controller.snapshot(sid)
                doc = self.controller.tick(sid, ports)
                self._sync_agent_continuity(sid)
                self.observe(sid)
                if doc['state'] == 'BLOCKED' and doc['blocker'] in ('VERIFICATION_FAIL', 'VERIFICATION_INCONCLUSIVE'):
                    step = next(s for s in doc['steps'] if s['status'] == 'VERIFYING')
                    evidence = next((a.body for a in self.store.list_artifacts(sid)
                                     if a.id == step['verification']['evidence_ref']), '{}')
                    self._gap(sid, doc['blocker'])
                    if self.metrics(sid).get('source_work'):
                        from core.lab_v1.source_mission import SourceMission
                        mission = SourceMission(self, sid)
                        # A refused plan is a refused model artifact, recoverable
                        # by the architect inside the same bounded budget. Before
                        # this, only a refused review had a way back.
                        if (mission.repair_rejected_plan(evidence) if step['id'] == 'plan'
                                else mission.repair(evidence)):
                            continue
                        # Source missions own their bounded repair/replan budget;
                        # never fall through to the generic retry path, which
                        # could bypass the persisted limits.
                        doc = self.controller.snapshot(sid)
                    elif self.controller.repair_step(sid, reason=evidence):
                        self._metrics(sid, recovery_automatic=True); continue
                    doc = self.controller.snapshot(sid)
                if (doc['state'] == 'BLOCKED' and doc['blocker'] == 'PATCH_DRAFT_REJECTED'
                        and self.metrics(sid).get('source_work')):
                    # The local executor refused the draft before writing anything.
                    # That is feedback, not an unknown effect: give it back to the
                    # worker once, inside the same repair budget.
                    from core.lab_v1.source_mission import SourceMission
                    self._gap(sid, doc['blocker'])
                    refusal = (doc.get('last_failure') or {}).get('message') or doc['blocker']
                    if SourceMission(self, sid).repair_rejected_draft(refusal):
                        continue
                    doc = self.controller.snapshot(sid)
                if doc['state'] == 'COMPLETED':
                    self._report(sid)
                    self._promote_verified_outcome(sid)
                    break
                if doc['state'] in ('BLOCKED', 'WAITING_RESOURCE', 'BLOCKED_NEEDS_OWNER', 'FAILED', 'CANCELLED'):
                    if doc['state'] == 'WAITING_RESOURCE':
                        failed = next((s for s in doc['steps'] if s['status'] == 'PROVIDER_FAILED'), None)
                        if failed:
                            agent = self.store.get_agent(self.store.get_task(failed['task_id']).assigned_agent_id)
                            replacements = self.candidates(self.store.get_session(sid).team_id, agent.role, exclude=(agent.id,))
                            if replacements and self.controller.retry_text_with(sid, replacements[0].id):
                                self._metrics(sid, recovery_automatic=True); continue
                    if doc.get('blocker'): self._gap(sid, doc['blocker'])
                    break
                if doc == before: break
            doc = self.controller.snapshot(sid)
            if (metrics.get('mission_kind') in ('DAILY_OPPORTUNITY_REVIEW', 'PRODUCT_CRITICISM_REVIEW', 'SELF_IMPROVEMENT')
                    and not metrics.get('source_work')
                    and doc['state'] == 'BLOCKED_NEEDS_OWNER'):
                doc = self.controller.fail_idle(sid, 'INTERNAL_REVIEW_FAILED:' + str(doc.get('blocker') or 'UNKNOWN'))
                self._metrics(sid, content_review='FAILED')
            observation = self.observe(sid)
            learning = self.register_learning(sid, observation)
            proposal = self.propose_next_work(sid, observation)
            paused = self._paused(sid) and doc['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED')
            return {'success': doc['state'] == 'COMPLETED',
                    'state': 'PAUSED' if paused else doc['state'], 'session_id': sid,
                    'mission': doc, 'autonomy': self.metrics(sid),
                    'cycle': {'observation': observation, 'learning': learning,
                              'next_work': proposal}}
        finally: self.lock.release()

    def run_continuous(self, sid):
        """Run one bounded observe→plan→execute→verify cycle.

        Continuity means the persisted mission can be resumed repeatedly; it
        does not mean an unbounded background loop or a second task database.
        """
        return self.run(sid)

    continuous_cycle = run_continuous
    cycle = run_continuous


class _AutopilotPorts:
    def __init__(self, engine, sid, metrics):
        self.engine, self.store, self.sid, self.metrics = engine, engine.store, sid, metrics
        self.actions = SandboxActionPorts(self.store, engine.executor_factory(Path(metrics['sandbox'])))

    def execute(self, dispatch):
        task = self.store.get_task(dispatch.task_id)
        source = None
        if self.metrics.get('source_work'):
            from core.lab_v1.source_mission import SourceMission
            source = SourceMission(self.engine, self.sid)
            if dispatch.capability.startswith('source.'):
                return source.execute(dispatch)
        if dispatch.capability == 'files.write':
            spec = json.loads(task.acceptance)
            draft = self.store.get_task(self.sid + ':' + spec['id'] + ':draft')
            if draft.state.value != 'COMPLETED': raise ScopeViolation('UNVERIFIED_DRAFT')
            request = SandboxActionRequest('action:' + task.id, self.sid, task.id, dispatch.agent_id,
                'files.write', str(Path(self.metrics['sandbox']) / spec['path']), draft.result, dispatch.execution_scope)
            self.actions.prepare(request)
            return self.actions.execute(dispatch)
        agent = self.store.get_agent(dispatch.agent_id)
        choice = self.engine.policy.effective_resource(agent)
        from dataclasses import replace as _replace2
        effective_agent = _replace2(agent, provider_id=choice.provider_id, model=choice.model_id)
        doc = self.engine.controller.snapshot(self.sid)
        step = next(s for s in doc['steps'] if s['id'] == dispatch.step_id)
        decision = self.engine._decision(agent, retry=bool(step.get('resource_failures') or step.get('quota_waits')),
                                         team_id=self.store.get_session(self.sid).team_id)
        if not decision.allowed:
            raise TextProviderFailure('OFFLINE' if decision.code == 'RESOURCE_UNAVAILABLE' else decision.code)
        adapter = self.engine.runtime.registry.get(choice.provider_id)
        if not getattr(adapter, 'controlled_text_only', False): raise ScopeViolation('TEXT_ONLY_REQUIRED')
        dispatch.execution_scope.require('model.text', (_resource(effective_agent),), 'LOW')
        session = self.store.get_session(self.sid)
        memory_adapter = self.engine.runtime.memory_adapter
        shared_memory = None
        if memory_adapter is not None and hasattr(memory_adapter, 'recover_agent_context'):
            try:
                shared_memory = list(memory_adapter.recover_agent_context(session, agent.id))
            except Exception:
                shared_memory = None
        if shared_memory is not None:
            dispatch.context.relevant_memory.extend(shared_memory)
        else:
            continuity = self.engine._get_continuity()
            resume_context = continuity.resume(self.sid, agent.id)
            if resume_context.checkpoint:
                checkpoint = resume_context.checkpoint
                dispatch.context.relevant_memory.append(
                    f'Checkpoint anterior [cursor={checkpoint.cursor}]: {checkpoint.summary}')
            handoff = resume_context.handoff
            if handoff is not None:
                dispatch.context.relevant_memory.append(
                    f'Handoff [{handoff.stage}] artefato {handoff.artifact_ref} '
                    f'evidencia: {", ".join(handoff.evidence_refs)}')
            for open_task in resume_context.open_tasks:
                if open_task.id != dispatch.task_id:
                    dispatch.context.relevant_memory.append(
                        f'Tarefa ainda aberta [{open_task.id}]: {open_task.title}')
            for lesson in resume_context.relevant_experiences:
                source_session = self.store.get_session(lesson.source_session_id)
                if (source_session is not None
                        and source_session.team_id == resume_context.session.team_id):
                    dispatch.context.relevant_memory.append(
                        f'{lesson.statement} [evidencia: {lesson.evidence_ref}]')
        prompt = dispatch.context.render()
        if dispatch.step_id == 'plan':
            roles = sorted({a.role.value for a in self.engine.candidates(self.store.get_session(self.sid).team_id)})
            mission_kind = self.engine.metrics(self.sid).get('mission_kind')
            daily = mission_kind == 'DAILY_OPPORTUNITY_REVIEW'
            criticism = mission_kind == 'PRODUCT_CRITICISM_REVIEW'
            daily_rule = (('Review observed source evidence independently. Produce an artifact.text task for REVIEWER, '
                'path proposal.md. Acceptance uses constraints, never the final content. Cite the source URL and observed '
                'hash in the worker output; separate observations from recommendations. ') if daily else '')
            criticism_rule = (('You are the ZARA architect. Turn the recorded product criticism into the smallest safe '
                'improvement plan. Plan only sandbox artifacts. Include at least one independent REVIEWER task. '
                'Do not claim the criticism is proven beyond its verbatim evidence and do not modify or promote production. ')
                if criticism else '')
            system = (daily_rule + criticism_rule + 'Return JSON only: {"mission":"objective", "plan_version":1, "tasks":[...]} with 1..8 tasks. '
                'Each task: id (lowercase unique), title, instruction, role, capability, path (one new filename), '
                'depends_on (earlier task ids), risk="LOW", repair_budget=1, acceptance. '
                'Available roles: ' + ', '.join(roles) + '. Select only necessary roles; no fanout. '
                'Capabilities: artifact.python = pure Python functions, verified by acceptance '
                '{"method":"python_cases","cases":[{"function":"name","args":[input],"expected":expected}, ...]} '
                'with at least two distinct cases based on the owner objective. The interpreter supports simple assignments, '
                'if/return, arithmetic, comparisons, string methods, literal lists/dicts, len/str/int/round/sorted. '
                'NO imports, loops, classes, recursion, decorators, files, network or shell. '
                'artifact.text requires acceptance {"method":"constraints","min_chars":20,"max_chars":6000,"required_sections":[]}. '
                'Planner plans tasks only: NEVER embed solutions, finished artifact text or code in instructions, metadata or acceptance. artifact.json uses json_schema without const/default/examples. Do not change implementation into documentation. Unsupported mission: return '
                '{"unsupported":"concise missing capability"}. Never assert work already happened. Each file is self-contained.')
        else:
            spec = json.loads(task.acceptance)
            system = ('Implement only the requested artifact. Return raw file content, no markdown fences, no claims. '
                'For Python use only pure public functions: assignments, if/return, arithmetic, comparisons, literals, '
                'string strip/lower/upper/casefold/split/join/replace and len/str/int/float/round/sorted. '
                'No imports, loops, classes, recursion, decorators, file access or shell. '
                'Follow the acceptance cases. Repair any failure evidence supplied.')
            prompt += '\nARTIFACT: ' + json.dumps(spec, ensure_ascii=False)
            self.engine._metrics(self.sid, delegation_automatic=True, context_transfer_automatic=True)
        if source:
            system, prompt = source.model_input(dispatch)
        run, result = self.engine.runtime._run_agent(self.store.get_session(self.sid), effective_agent, prompt, system,
            task=task, timeout_s=max(1, int(dispatch.deadline - time.time()) - 2))
        if not result.ok: raise TextProviderFailure(result.availability.value)
        if not adapter.identifies_model(effective_agent.model, result.model_reported):
            run.state = RunState.FAILED; run.error = 'MODEL_MISMATCH: ' + result.model_reported; self.store.save_run(run)
            raise TextProviderFailure('MODEL_MISMATCH')
        body = result.text or ''
        if re.search(r'(?i)\b(?:nvapi-|sk-(?:proj-|ant-)?)[A-Za-z0-9_-]{12,}', body):
            raise ScopeViolation('CREDENTIAL_OUTPUT_REJECTED')
        artifact = Artifact('response:' + dispatch.attempt_id, self.sid, task.id, 'MODEL_TEXT', task.title, body=body)
        response_binding = {
            'version': 1,
            'session_id': self.sid,
            'task_id': task.id,
            'attempt_id': dispatch.attempt_id,
            'run_id': run.id,
            'artifact_id': artifact.id,
            'artifact_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
        }
        binding_artifact = Artifact(
            'MODEL_RESPONSE_BINDING:' + dispatch.attempt_id,
            self.sid,
            task.id,
            'MODEL_RESPONSE_BINDING',
            'Exact attempt, Run and response binding',
            body=json.dumps(response_binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        )
        self.store.save_bound_model_response(artifact, binding_artifact)
        current = self.engine.controller.snapshot(self.sid)
        active = next(s for s in current['steps'] if s['id'] == dispatch.step_id)
        if (active['attempt_id'] != dispatch.attempt_id or current['cancel_requested']
                or self.engine.controller.clock() >= dispatch.deadline):
            raise LeaseLost('Stale model response retained as evidence, not delivered as a new turn')
        # Model responses are internal protocol payloads (the planner and
        # reviewer deliberately speak JSON). Never leak that wire format into
        # the owner's conversation. Publish only a short human-facing status;
        # the complete payload remains auditable in the artifact/run record.
        chat_body = None
        if dispatch.step_id == 'plan':
            try:
                planned = json.loads(body)
                titles = [str(item.get('title', '')).strip() for item in planned.get('tasks', [])
                          if isinstance(item, dict) and item.get('title')]
                chat_body = ('Entendi. Vou cuidar disso com a equipe.' +
                             (f" Plano criado com {len(titles)} etapa(s): " + ', '.join(titles[:4]) + '.'
                              if titles else ''))
            except (TypeError, ValueError):
                chat_body = 'Entendi. Estou organizando a missão com a equipe.'
        elif dispatch.step_id.endswith(':draft'):
            chat_body = f'{agent.name} está trabalhando na solução.'
        elif dispatch.step_id == 'review':
            chat_body = 'A revisão independente da equipe foi concluída.'
        if chat_body:
            self.store.add_message(Message('message:' + run.id, self.sid, MessageKind.AGENT, 'ZARA',
                chat_body, author_agent_id=agent.id, run_id=run.id))
        return Receipt(artifact.id, body)

    def verify(self, dispatch, receipt):
        task = self.store.get_task(dispatch.task_id)
        if self.metrics.get('source_work'):
            from core.lab_v1.source_mission import SourceMission
            return SourceMission(self.engine, self.sid).verify(dispatch, receipt)
        evidence = {'passed': False, 'source': receipt.artifact_ref}
        if dispatch.capability == 'files.write':
            bytes_result = self.actions.verify(dispatch, receipt)
            spec = json.loads(task.acceptance)
            path = Path(self.metrics['sandbox']) / spec['path']
            verified = ArtifactVerifier().verify(spec, path.read_text(encoding='utf-8') if path.is_file() else '')
            passed = bytes_result.verdict == 'PASS' and verified.state == VerificationState.VERIFIED
            evidence.update(passed=passed, bytes_evidence=bytes_result.evidence_ref, proof=verified.proof, error=verified.error)
        else:
            artifact = next((a for a in self.store.list_artifacts(self.sid) if a.id == receipt.artifact_ref
                             and a.task_id == task.id and a.body == receipt.summary), None)
            if artifact and 0 < len(artifact.body.encode()) <= 32768:
                try:
                    if dispatch.step_id == 'plan':
                        self.engine.validate_plan(self.sid, _extract_json(artifact.body))
                        evidence.update(passed=True, method='bounded_plan_schema_and_acceptance')
                    else:
                        result = ArtifactVerifier().verify(json.loads(task.acceptance), artifact.body)
                        evidence.update(passed=result.state == VerificationState.VERIFIED, proof=result.proof, error=result.error)
                except (ValueError, TypeError, KeyError) as exc: evidence['error'] = str(exc)[:300]
        evidence['verdict'] = 'PASS' if evidence['passed'] else 'FAIL'
        eid = new_id('verification')
        self.store.save_artifact(Artifact(eid, self.sid, task.id, 'VERIFICATION', 'Independent postconditions', body=json.dumps(evidence)))
        return Verification(evidence['verdict'], eid)
