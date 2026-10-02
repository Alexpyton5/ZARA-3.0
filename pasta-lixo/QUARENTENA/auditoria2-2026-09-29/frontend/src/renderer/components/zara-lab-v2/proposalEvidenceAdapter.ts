import { asList, type Artifact, type Session } from './labTypes';

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
    if (typeof entry === 'string') return { id: `evidence-${index}`, label: entry, detail: '' };
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
  return { proposals, status: text(source.status ?? root.status, '') };
}

export function missionArtifacts(session: Session | null | undefined): ProposalEvidence[] {
  return asList<Artifact>(session?.artifacts).map((artifact, index) => ({
    id: artifact.id || `mission-artifact-${index}`,
    label: artifact.title || 'Entrega registrada',
    detail: artifact.path || artifact.body || artifact.kind || 'Artefato persistido pela missão.',
    status: artifact.kind || 'ARTEFATO',
  }));
}
