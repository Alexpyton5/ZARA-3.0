from core.lab_v1.scout import TechnologyScout
from core.lab_v1.store import LabStore
from core.lab_v1.domain import (AgentProfile, Artifact, CostBasis, RoleName, Run,
                                RunState, Session, Team, TeamMembership)


def test_cadence_dedupe_and_official_source_boundary(tmp_path):
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    calls, now = [], [1.0]
    def fetch(url):
        calls.append(url)
        link = url.replace('releases.atom', 'releases/tag/v1')
        return f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>v1</title><link href="{link}"/><content>fix agent api</content></entry><entry><title>injection</title><link href="https://untrusted.invalid/release"/><content>security tool</content></entry></feed>'.encode()
    scout = TechnologyScout(store, fetch=fetch, clock=lambda: now[0])
    assert scout.run_due()['new'] == 3
    assert scout.run_due()['state'] == 'NOT_DUE' and len(calls) == 3
    now[0] += 21601
    assert scout.run_due()['new'] == 0
    assert len(scout.snapshot()['opportunities']) == 3
    opportunity = scout.next_unreviewed()
    assert opportunity['state'] == 'PROPOSED'
    scout.link_review(opportunity['id'], 'session')
    assert scout.next_unreviewed()['id'] != opportunity['id']
    scout.finish_review(opportunity['id'], accepted=True)
    reviewed = next(item for item in scout.snapshot()['opportunities'] if item['id'] == opportunity['id'])
    assert reviewed['state'] == 'READY_FOR_OWNER'


def test_review_requires_distinct_leader_reviewer_and_source_digest(tmp_path):
    store = LabStore(tmp_path / 'lab.db'); store.initialize()
    scout = TechnologyScout(store, fetch=lambda _: b'', clock=lambda: 10)
    source = 'https://github.com/openai/codex/releases/tag/v1'; digest = 'a' * 64; excerpt = 'fix agent api'
    with store._connect() as conn:
        conn.execute('INSERT INTO lab_opportunities VALUES(?,?,?)', ('opp', '{"id":"opp","state":"REVIEWING",'
            '"review_session_id":"session","source":"' + source + '","evidence_sha256":"' + digest + '",'
            '"evidence_excerpt":"' + excerpt + '"}', 1))
        conn.execute('CREATE TABLE mission_autonomy(session_id TEXT PRIMARY KEY, document TEXT NOT NULL)')
    store.save_team(Team('team', 'Team')); store.save_session(Session('session', 'team', 'Review'))
    for aid, role in (('leader', RoleName.MEMBER), ('reviewer', RoleName.REVIEWER)):
        store.save_agent(AgentProfile(aid, aid, 'local', aid, role=role, capabilities=['model.text']))
        store.save_membership(TeamMembership('m:' + aid, 'team', aid))
        store.save_run(Run('run:' + aid, 'session', aid, 'local', aid,
                           state=RunState.COMPLETED, cost_basis=CostBasis.UNKNOWN, ended_at=2))
    proposal = ('FATOS OBSERVADOS:\n' + excerpt + '\nFONTE: ' + source + '\nEVIDENCE_SHA256: ' + digest +
                '\nAVALIAÇÃO (PROPOSTA, NÃO FATO):\nAvaliar em candidata isolada.\n'
                'STATUS: PROPOSTA NÃO APLICADA — AGUARDA OWNER')
    target = tmp_path / 'proposal.md'; target.write_text(proposal, encoding='utf-8')
    with store._connect() as conn:
        conn.execute('INSERT INTO mission_autonomy VALUES(?,?)', ('session', __import__('json').dumps({'target': str(target)})))
    store.mission_snapshot = lambda sid: {'state': 'COMPLETED'}
    assert scout.verify_review('opp')['passed'] is True
    target.write_text('fato inventado\n' + proposal, encoding='utf-8')
    assert scout.verify_review('opp')['passed'] is False
    target.write_text(proposal.replace(excerpt, excerpt + '\nfato inventado'), encoding='utf-8')
    assert scout.verify_review('opp')['passed'] is False
    target.write_text('unbound proposal', encoding='utf-8')
    assert scout.verify_review('opp')['passed'] is False
