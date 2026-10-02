import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, FileCheck2, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { asList, failureText, label, requireResult, type Artifact, type Session } from './labTypes';

type JsonRecord = Record<string, unknown>;

export type ProposalEvidence = {
  id: string;
  label: string;
  detail: string;
  status?: string;
};

export type LabProposal = {
  id: string;
  title: string;
  summary: string;
  risk: string;
  owner: string;
  state: string;
  evidence: ProposalEvidence[];
  updatedAt?: string | number;
};

export type ProposalPanelState = {
  proposals: LabProposal[];
  status?: string;
};

type TransparencyFact = { label: string; values: string[] };

function record(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function values(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function normalizeEvidence(value: unknown): ProposalEvidence[] {
  return values(value).map((entry, index) => {
    if (typeof entry === 'string') {
      return { id: `evidence-${index}`, label: entry, detail: '' };
    }
    const item = record(entry);
    return {
      id: text(item.id ?? item.ref ?? item.path, `evidence-${index}`),
      label: text(item.title ?? item.name ?? item.label ?? item.path ?? item.ref, 'Evidência registrada'),
      detail: text(item.detail ?? item.description ?? item.summary ?? item.path, ''),
      status: text(item.status ?? item.state, ''),
    };
  });
}

/**
 * Adapter boundary for the existing `lab.state` IPC response. Backend versions
 * have returned either the feed directly or wrapped under `data`; the panel
 * keeps that tolerance local instead of spreading transport assumptions through
 * the Lab UI.
 */
export function normalizeProposalState(raw: unknown): ProposalPanelState {
  const root = record(raw);
  const payload = record(root.data ?? root.result ?? raw);
  const source = Object.keys(payload).length ? payload : root;
  const proposalValues = source.proposals ?? source.proposal_feed ?? source.items;
  const proposals = values(Array.isArray(raw) ? raw : proposalValues).map((entry, index) => {
    const item = record(entry);
    const state = text(item.state ?? item.status, 'PROPOSED').toUpperCase();
    return {
      id: text(item.proposal_id ?? item.id, `proposal-${index}`),
      title: text(item.title ?? item.name, 'Proposta sem título'),
      summary: text(item.summary ?? item.description, 'Sem resumo disponível.'),
      risk: text(item.risk, 'Não informado'),
      owner: text(item.owner ?? item.author, 'Não informado'),
      state,
      evidence: normalizeEvidence(item.evidence_refs ?? item.evidence ?? item.evidences),
      updatedAt: typeof item.updated_at === 'string' || typeof item.updated_at === 'number' ? item.updated_at : undefined,
    } satisfies LabProposal;
  });
  return {
    proposals,
    status: text(source.status ?? root.status, ''),
  };
}

function formatDate(value?: string | number): string {
  if (value == null || value === '') return 'Atualização não informada';
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? 'Atualização não informada' : date.toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function proposalStateClass(state: string): string {
  if (['APPROVED', 'ACTIVATED', 'TESTED'].includes(state)) return 'is-positive';
  if (['REJECTED'].includes(state)) return 'is-negative';
  if (['APPROVAL_REQUIRED', 'CANDIDATE'].includes(state)) return 'is-attention';
  return 'is-neutral';
}

function missionArtifacts(session: Session | null | undefined): ProposalEvidence[] {
  return asList<Artifact>(session?.artifacts).map((artifact, index) => ({
    id: artifact.id || `mission-artifact-${index}`,
    label: artifact.title || 'Entrega registrada',
    detail: artifact.path || artifact.body || artifact.kind || 'Artefato persistido pela missão.',
    status: artifact.kind || 'ARTEFATO',
  }));
}

/** Builds the inspector strictly from persisted Lab V1 snapshot fields. */
export function transparencyFacts(session: Session | null | undefined): TransparencyFact[] {
  const blocker = text(session?.mission?.blocker);
  const gaps = asList(session?.capability_gaps).flatMap(gap =>
    [text(gap.required), text(gap.detail)].filter(Boolean));
  const decisions = asList(session?.decisions).flatMap(decision =>
    [text(decision.statement), text(decision.rationale)].filter(Boolean));
  const criteria = asList(session?.acceptance_criteria).filter((criterion): criterion is string =>
    typeof criterion === 'string' && !!criterion.trim()).map(criterion => criterion.trim());
  return [
    ...(blocker ? [{ label: 'Bloqueio', values: [blocker] }] : []),
    ...(gaps.length ? [{ label: 'Lacunas', values: gaps }] : []),
    ...(decisions.length ? [{ label: 'Decisões registradas', values: decisions }] : []),
    ...(criteria.length ? [{ label: 'Critérios de aceite', values: criteria }] : []),
  ];
}

export function ProposalEvidencePanel({ session, onRefresh }: { session?: Session | null; onRefresh?: () => Promise<void> }) {
  const [state, setState] = useState<ProposalPanelState>({ proposals: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    const readState = window.zaraIPC?.labV1?.proposalList;
    if (!readState) {
      setError('O canal de propostas não está disponível nesta versão.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      setState(normalizeProposalState(requireResult(await readState())));
    } catch (cause) {
      setError(failureText(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function decide(proposal: LabProposal, decision: 'APPROVE' | 'REJECT') {
    const decideProposal = window.zaraIPC?.labV1?.proposalUpdate;
    if (!decideProposal) {
      setError('O canal de decisão de propostas não está disponível nesta versão.');
      return;
    }
    setBusyId(proposal.id);
    setError('');
    try {
      requireResult(await decideProposal({ proposalId: proposal.id, state: decision === 'APPROVE' ? 'APPROVED' : 'REJECTED' }));
      await load();
      await onRefresh?.();
    } catch (cause) {
      setError(failureText(cause));
    } finally {
      setBusyId('');
    }
  }

  const artifacts = useMemo(() => missionArtifacts(session), [session]);
  const inspectorFacts = useMemo(() => transparencyFacts(session), [session]);
  const missionState = session?.mission?.state || session?.state;
  const pending = state.proposals.filter(proposal => proposal.state === 'APPROVAL_REQUIRED');

  return <section className="zl-proposal-panel" aria-labelledby="zl-proposal-title">
    <header className="zl-proposal-header">
      <div>
        <span className="zl-proposal-eyebrow">COUNCIL / EVIDÊNCIAS</span>
        <h2 id="zl-proposal-title">Propostas e evidências</h2>
        <p>O feed persistido, separado da conversa, para decisões que precisam de contexto.</p>
      </div>
      <button className="zl-proposal-refresh" onClick={() => void load()} disabled={loading || !!busyId} aria-label="Atualizar propostas" title="Atualizar propostas">
        <RefreshCw size={15} className={loading ? 'is-spinning' : ''} />
      </button>
    </header>

    <div className="zl-proposal-context">
      <span><ShieldCheck size={13} /> Missão selecionada</span>
      <strong>{session?.objective || 'Nenhuma missão selecionada'}</strong>
      <b className={missionState ? proposalStateClass(missionState) : 'is-neutral'}>{missionState ? label(missionState) : 'Sem estado'}</b>
    </div>

    {inspectorFacts.length > 0 && <section className="zl-mission-evidence" aria-labelledby="zl-mission-inspector-title">
      <h3 id="zl-mission-inspector-title">Situação da missão</h3>
      {inspectorFacts.map(fact => <div className="zl-evidence-row" key={fact.label}><strong>{fact.label}</strong>{fact.values.map((value, index) => <p key={`${fact.label}-${index}`}>{value}</p>)}</div>)}
    </section>}

    <div className="zl-proposal-meta" role="status" aria-live="polite">
      <span className={error ? 'zl-proposal-dot is-error' : 'zl-proposal-dot'} />
      {loading ? 'Consultando o feed…' : `${state.proposals.length} proposta${state.proposals.length === 1 ? '' : 's'} registrada${state.proposals.length === 1 ? '' : 's'}`}
      {pending.length > 0 && <em>{pending.length} aguardando decisão</em>}
      {state.status && <small>{state.status}</small>}
    </div>

    {error && <div className="zl-proposal-error" role="alert"><AlertCircle size={14} />{error}</div>}
    {!loading && !state.proposals.length && <div className="zl-proposal-empty"><FileCheck2 size={20} /><strong>Nenhuma proposta persistida</strong><p>Quando o conselho registrar uma proposta, seu estado e suas evidências aparecerão aqui.</p></div>}

    <div className="zl-proposal-list">
      {state.proposals.map(proposal => {
        const canDecide = proposal.state === 'APPROVAL_REQUIRED';
        const busy = busyId === proposal.id;
        return <article className="zl-proposal-card" key={proposal.id}>
          <div className="zl-proposal-card-head">
            <div><span className="zl-proposal-id">{proposal.id}</span><h3>{proposal.title}</h3></div>
            <span className={`zl-proposal-state ${proposalStateClass(proposal.state)}`}>{label(proposal.state)}</span>
          </div>
          <p className="zl-proposal-summary">{proposal.summary}</p>
          <dl className="zl-proposal-facts"><div><dt>Responsável</dt><dd>{proposal.owner}</dd></div><div><dt>Risco</dt><dd>{proposal.risk}</dd></div><div><dt>Atualizado</dt><dd>{formatDate(proposal.updatedAt)}</dd></div></dl>
          <div className="zl-proposal-evidence"><strong><FileCheck2 size={13} /> Evidências ({proposal.evidence.length})</strong>{proposal.evidence.length ? proposal.evidence.map(evidence => <div className="zl-evidence-row" key={evidence.id}><span>{evidence.label}</span>{evidence.status && <small>{label(evidence.status)}</small>}{evidence.detail && <p>{evidence.detail}</p>}</div>) : <p className="zl-proposal-muted">Nenhuma referência anexada.</p>}</div>
          {canDecide && <div className="zl-proposal-actions"><button disabled={!!busyId} onClick={() => void decide(proposal, 'REJECT')}><X size={13} /> Rejeitar</button><button className="is-approve" disabled={!!busyId} onClick={() => void decide(proposal, 'APPROVE')}><Check size={13} /> {busy ? 'Registrando…' : 'Aprovar'}</button></div>}
        </article>;
      })}
    </div>

    {!!artifacts.length && <div className="zl-mission-evidence"><h3>Evidências da missão</h3><p>Entregas registradas no snapshot atual do Lab.</p>{artifacts.map(artifact => <div className="zl-evidence-row" key={artifact.id}><span>{artifact.label}</span><small>{artifact.status}</small><p>{artifact.detail}</p></div>)}</div>}
  </section>;
}
