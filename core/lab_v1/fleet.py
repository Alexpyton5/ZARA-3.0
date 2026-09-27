"""Explicit bounded model certification; catalog discovery never activates an agent."""
from dataclasses import asdict, replace
import json
import time

from core.lab_v1.domain import AgentProfile, Availability, ProviderResult, RoleName, TeamMembership, new_id
from core.lab_v1.providers.base import InvocationOptions


class FleetCertification:
    def __init__(self, runtime):
        self.runtime, self.store = runtime, runtime.store
        with self.store._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS model_certification_runs ('
                'id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, model TEXT NOT NULL, document TEXT NOT NULL)')

    def certify(self, *, key, provider_id, model, effort=None, timeout_s=90):
        """An idempotency key authorizes at most one call, including across restart.

        Certification Runs deliberately have no AgentInstance: profiles can only
        be registered after inference proof. They are not Mission execution Runs.
        """
        adapter = self.runtime.registry.get(provider_id)
        descriptor = next((m for m in getattr(adapter, 'declared_models', ()) if m.model_id == model), None)
        if not adapter or not getattr(adapter, 'controlled_text_only', False) or descriptor is None:
            raise ValueError('MODEL_NOT_DISCOVERED_TEXT_ONLY')
        if effort is not None and effort not in descriptor.effort_levels:
            raise ValueError('UNSUPPORTED_EFFORT')
        if not key or not 1 <= timeout_s <= 120:
            raise ValueError('INVALID_CERTIFICATION_BUDGET')
        doc = {'id': key, 'kind': 'MODEL_CERTIFICATION_NOT_MISSION', 'provider_id': provider_id,
            'model': model, 'effort': effort, 'supported_efforts': list(descriptor.effort_levels),
            'state': 'STARTED', 'started_at': time.time(), 'agent_id': None, 'cost_status': 'UNKNOWN'}
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT document FROM model_certification_runs WHERE id=?', (key,)).fetchone()
            if old:
                prior = json.loads(old[0])
                if any(prior[k] != doc[k] for k in ('provider_id', 'model', 'effort')):
                    raise ValueError('IDEMPOTENCY_KEY_MISMATCH')
                return prior
            if conn.execute("SELECT 1 FROM model_certification_runs WHERE json_extract(document,'$.state')='STARTED'").fetchone():
                raise ValueError('CERTIFICATION_ALREADY_RUNNING_OR_UNCERTAIN')
            conn.execute('INSERT INTO model_certification_runs VALUES(?,?,?,?)', (key, provider_id, model, json.dumps(doc)))
        try:
            info = adapter.probe()
            if info.availability in (Availability.DISABLED_BY_OWNER_POLICY, Availability.AUTH_REQUIRED, Availability.OFFLINE):
                result = ProviderResult(False, availability=info.availability, error=info.availability.value)
            else:
                result = adapter.invoke(model=model, options=InvocationOptions(effort=effort), timeout_s=timeout_s,
                    max_turns=1, system='ZARA runtime model certification. No tools, actions or hidden reasoning.',
                    prompt='In one short sentence explain why a proposed code change is not proof that a test passed.')
                if result.ok and not result.text.strip():
                    result = ProviderResult(False, availability=Availability.ERROR, error='EMPTY_RESPONSE')
                if result.ok and provider_id == 'nvidia':
                    if not result.model_reported:
                        result = replace(result, ok=False,
                            availability=Availability.MODEL_UNAVAILABLE,
                            error='MODEL_IDENTITY_MISSING')
                    elif not adapter.identifies_model(model, result.model_reported):
                        result = replace(result, ok=False,
                            availability=Availability.MODEL_UNAVAILABLE,
                            error='MODEL_IDENTITY_MISMATCH')
        except Exception as exc:
            # Do not persist unsanitized exception text or retry an uncertain call.
            result = ProviderResult(False, availability=Availability.ERROR, error=type(exc).__name__)
        self.runtime.registry.record_result(provider_id, model, result)
        doc.update(state='COMPLETED' if result.ok else 'FAILED', ended_at=time.time(), result=asdict(result))
        with self.store._connect() as conn:
            conn.execute('UPDATE model_certification_runs SET document=? WHERE id=?', (json.dumps(doc), key))
        return doc

    def register_proven_agent(self, certification_id, *, team_id, name, role: RoleName):
        if self.store.get_team(team_id) is None:
            raise ValueError('UNKNOWN_TEAM')
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM model_certification_runs WHERE id=?', (certification_id,)).fetchone()
        doc = json.loads(row[0]) if row else {}
        if doc.get('state') != 'COMPLETED' or not doc.get('result', {}).get('ok'):
            raise ValueError('NO_CALLABLE_PROOF')
        if doc.get('agent_id'):
            agent = self.store.get_agent(doc['agent_id'])
            if agent is not None and 'model.text' not in agent.capabilities:
                agent.capabilities.append('model.text')
                self.store.save_agent(agent)
            return agent
        agent = AgentProfile(new_id('agent'), name, doc['provider_id'], doc['model'], role=role, effort=doc['effort'], capabilities=['model.text'])
        self.store.save_agent(agent)
        self.store.save_membership(TeamMembership(new_id('member'), team_id, agent.id))
        doc['agent_id'] = agent.id
        with self.store._connect() as conn:
            conn.execute('UPDATE model_certification_runs SET document=? WHERE id=?', (json.dumps(doc), certification_id))
        return agent
