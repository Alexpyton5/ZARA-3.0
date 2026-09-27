"""Bounded technology observations from official release feeds; never installs code."""
import hashlib
import json
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

SOURCES = (
    ('OpenAI Codex', 'https://github.com/openai/codex/releases.atom'),
    ('DeepSeek Harness', 'https://github.com/deepseek-ai/deepseek-harness/releases.atom'),
    ('Hermes', 'https://github.com/NousResearch/hermes-agent/releases.atom'),
)
_FICTITIOUS_HOSTS = frozenset({'example.com', 'example.org', 'example.net', 'invalid', 'test'})


def _source_url(url):
    """Return a canonical public URL or reject a fabricated/local source."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError('SOURCE_URL_REQUIRED')
    raw = url.strip()
    parts = urllib.parse.urlsplit(raw)
    host = (parts.hostname or '').casefold().rstrip('.')
    if parts.scheme.lower() not in {'http', 'https'} or not host or parts.username or parts.password:
        raise ValueError('SOURCE_URL_INVALID')
    if (host in _FICTITIOUS_HOSTS or host.endswith(('.example', '.invalid', '.test', '.local', '.internal', '.lan'))):
        raise ValueError('SOURCE_URL_FICTITIOUS')
    try:
        address = __import__('ipaddress').ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local
                                or address.is_multicast or address.is_reserved or address.is_unspecified):
        raise ValueError('SOURCE_URL_NON_PUBLIC')
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc, parts.path or '/', parts.query, ''))


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def review_evidence_bound(content, evidence):
    """Facts section is byte-for-byte the observation plus its source identity."""
    facts_marker = 'FATOS OBSERVADOS:\n'
    evaluation_marker = '\nAVALIAÇÃO (PROPOSTA, NÃO FATO):\n'
    status = 'STATUS: PROPOSTA NÃO APLICADA — AGUARDA OWNER'
    if (not content.startswith(facts_marker) or content.count(facts_marker) != 1
            or content.count(evaluation_marker) != 1):
        return False
    facts, remainder = content.split(facts_marker, 1)[1].split(evaluation_marker, 1)
    expected = (str(evidence.get('evidence_excerpt') or '').strip() + '\nFONTE: ' +
                str(evidence.get('source') or '') + '\nEVIDENCE_SHA256: ' +
                str(evidence.get('evidence_sha256') or ''))
    return facts == expected and remainder.rstrip().endswith(status)


class TechnologyScout:
    def __init__(self, store, *, fetch=None, clock=time.time):
        self.store, self.fetch, self.clock = store, fetch or self._fetch, clock
        with store._connect() as conn:
            conn.executescript('''CREATE TABLE IF NOT EXISTS lab_scout_clock(id INTEGER PRIMARY KEY, next_run REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS lab_opportunities(id TEXT PRIMARY KEY, document TEXT NOT NULL, created_at REAL NOT NULL);''')

    @staticmethod
    def _fetch(url):
        request = urllib.request.Request(url, headers={'User-Agent': 'ZARA-TechnologyScout/0.1', 'Accept': 'application/atom+xml'})
        with urllib.request.urlopen(request, timeout=12) as response:
            if urllib.parse.urlparse(response.url).hostname != 'github.com': raise ValueError('Untrusted feed redirect')
            data = response.read(262145)
            if len(data) > 262144: raise ValueError('Feed budget exceeded')
            return data

    def run_due(self):
        now = self.clock()
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT next_run FROM lab_scout_clock WHERE id=1').fetchone()
            if row and row[0] > now: return {'state': 'NOT_DUE', 'new': 0}
            conn.execute('INSERT INTO lab_scout_clock VALUES(1,?) ON CONFLICT(id) DO UPDATE SET next_run=excluded.next_run', (now + 21600,))
        added, failures = 0, []
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        for source_name, source_url in SOURCES:
            try:
                root = ET.fromstring(self.fetch(source_url))
                for entry in root.findall('a:entry', ns)[:3]:
                    title = (entry.findtext('a:title', '', ns) or '').strip()[:180]
                    link = entry.find('a:link', ns)
                    url = link.get('href', '') if link is not None else ''
                    allowed = source_url.removesuffix('releases.atom') + 'releases/tag/'
                    if not title or not url.startswith(allowed): continue
                    try:
                        url = _source_url(url)
                    except ValueError:
                        continue
                    key = hashlib.sha256(url.encode()).hexdigest()[:24]
                    summary = re.sub('<[^>]*>', ' ', entry.findtext('a:content', '', ns))[:2500]
                    observed_excerpt = ' '.join(summary.split())[:1200]
                    feed_digest = hashlib.sha256(
                        (source_url + '\n' + url + '\n' + summary).encode('utf-8')
                    ).hexdigest()
                    score = min(100, 60 + 8 * len(set(re.findall(r'\b(?:fix|security|agent|memory|tool|windows|sdk|api)\b', summary.lower()))))
                    doc = {'id': key, 'opportunity': source_name + ': ' + title, 'source': url,
                        'published_at': entry.findtext('a:updated', '', ns), 'observed_at': now,
                        'evidence_excerpt': observed_excerpt,
                        'evidence_sha256': hashlib.sha256(summary.encode('utf-8')).hexdigest(),
                        'source_access': {'status': 'READ', 'accessed_url': source_url,
                                          'retrieved_at': _utc_now(), 'content_sha256': feed_digest},
                        'read_evidence': {'status': 'READ', 'excerpt': observed_excerpt,
                                          'evidence_sha256': hashlib.sha256(summary.encode('utf-8')).hexdigest()},
                        'provenance': {'source_url': url, 'feed_url': source_url,
                                       'retrieved_at': _utc_now(), 'content_sha256': feed_digest},
                        'finding_validation': {'status': 'UNVERIFIED', 'reason': 'OWNER_REVIEW_REQUIRED'},
                        'memory': {'reusable': True, 'status': 'PERSISTED', 'lesson':
                                   'Revisar notas oficiais e testar versao fixada em sandbox.'},
                        'why_it_matters': 'Atualizacao de uma dependencia ou ferramenta utilizada pelo Lab.',
                        'expected_benefit': 'Avaliar compatibilidade, correcoes e capacidades novas.',
                        'cost': 'UNKNOWN', 'risk': 'REQUIRES_REVIEW', 'relevance_score': score,
                        'proposed_experiment': 'Revisar notas oficiais e testar versao fixada em sandbox.',
                        'state': 'PROPOSED', 'source_is_instruction': False}
                    if score < 68: continue
                    with self.store._connect() as conn:
                        added += conn.execute('INSERT OR IGNORE INTO lab_opportunities VALUES(?,?,?)', (key, json.dumps(doc), now)).rowcount
            except Exception:
                failures.append(source_name)
        return {'state': 'OBSERVED' if not failures else 'PARTIAL', 'new': added, 'failed_sources': failures}

    def next_unreviewed(self):
        with self.store._connect() as conn:
            for row in conn.execute('SELECT document FROM lab_opportunities ORDER BY created_at,id'):
                document = json.loads(row[0])
                if document.get('state') == 'PROPOSED':
                    return document
        return None

    def link_review(self, opportunity_id, session_id):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT document FROM lab_opportunities WHERE id=?', (opportunity_id,)).fetchone()
            if row is None: raise ValueError('Unknown opportunity')
            document = json.loads(row[0])
            if document.get('state') != 'PROPOSED': return document
            document.update(state='REVIEWING', review_session_id=session_id, review_started_at=self.clock())
            conn.execute('UPDATE lab_opportunities SET document=? WHERE id=?', (json.dumps(document), opportunity_id))
            return document

    def finish_review(self, opportunity_id, *, accepted):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT document FROM lab_opportunities WHERE id=?', (opportunity_id,)).fetchone()
            if row is None: raise ValueError('Unknown opportunity')
            document = json.loads(row[0])
            document.update(state='READY_FOR_OWNER' if accepted else 'REJECTED_BY_TEAM',
                            review_finished_at=self.clock())
            conn.execute('UPDATE lab_opportunities SET document=? WHERE id=?', (json.dumps(document), opportunity_id))
            return document

    def verify_review(self, opportunity_id):
        """Independent minimum proof: two workers plus exact observed-source binding.

        This verifies traceability, not whether adopting the release is wise. The
        result remains an owner proposal and cannot enter ReleaseQueue directly.
        """
        with self.store._connect() as conn:
            row = conn.execute('SELECT document FROM lab_opportunities WHERE id=?', (opportunity_id,)).fetchone()
        if row is None: return {'passed': False, 'reason': 'OPPORTUNITY_MISSING'}
        opportunity = json.loads(row[0]); sid = opportunity.get('review_session_id')
        if not sid: return {'passed': False, 'reason': 'REVIEW_SESSION_MISSING'}
        mission = self.store.mission_snapshot(sid)
        runs = self.store.list_runs(sid)
        agents = {agent.id: agent for agent in self.store.list_agents()}
        completed = [run for run in runs if run.state.value == 'COMPLETED']
        leader_ids = {run.agent_id for run in completed if agents.get(run.agent_id) and agents[run.agent_id].role.value in ('CEO', 'MEMBER')}
        reviewer_ids = {run.agent_id for run in completed if agents.get(run.agent_id) and agents[run.agent_id].role.value == 'REVIEWER'}
        with self.store._connect() as conn:
            autonomy_row = conn.execute(
                'SELECT document FROM mission_autonomy WHERE session_id=?', (sid,)).fetchone()
        autonomy = json.loads(autonomy_row[0]) if autonomy_row else {}
        target = Path(autonomy['target']) if autonomy.get('target') else None
        if target is not None and target.name != 'proposal.md': target = None
        content = target.read_text(encoding='utf-8') if target and target.is_file() else ''
        passed = bool(mission and mission.get('state') == 'COMPLETED' and leader_ids and reviewer_ids
                      and leader_ids.isdisjoint(reviewer_ids)
                      and review_evidence_bound(content, opportunity))
        return {'passed': passed, 'reason': None if passed else 'INDEPENDENT_SOURCE_REVIEW_REQUIRED',
                'semantic_claims': 'OWNER_REVIEW_REQUIRED'}

    def snapshot(self):
        with self.store._connect() as conn:
            rows = conn.execute('SELECT document FROM lab_opportunities ORDER BY created_at DESC LIMIT 20').fetchall()
            clock = conn.execute('SELECT next_run FROM lab_scout_clock WHERE id=1').fetchone()
        return {'next_run': clock[0] if clock else None, 'opportunities': [json.loads(r[0]) for r in rows]}
