import type { AtividadeItem, DecisaoItem, ProjetoUsuario, TrabalhoItem } from '../components/zara-nova/types';

export interface NovaUiState {
  warning?: string;
  paused: boolean | null;
  projects: ProjetoUsuario[];
  work: TrabalhoItem[];
  activity: AtividadeItem[];
  decisions: DecisaoItem[];
}

export function parseNovaUiState(raw: any): NovaUiState {
  if (raw?.success !== true) throw new Error(raw?.error || 'O motor não confirmou os dados da equipe.');
  for (const key of ['projects', 'work', 'activity', 'decisions']) {
    if (!Array.isArray(raw[key])) throw new Error('Os dados da equipe chegaram incompletos.');
  }
  return { warning: typeof raw.warning === 'string' ? raw.warning : undefined,
    paused: typeof raw.paused === 'boolean' ? raw.paused : null,
    projects: raw.projects, work: raw.work, activity: raw.activity, decisions: raw.decisions };
}

export function requireActionResult(raw: any, fallback: string): void {
  if (raw?.success !== true) throw new Error(raw?.error || fallback);
}
