export type Agent = { id: string; name: string; provider_id: string; model: string; role?: string; lifecycle?: string; archived?: boolean; fallback_agent_id?: string | null; reports_to?: string | null; effort?: string | null };
export type Provider = { id: string; label?: string; availability?: string; detail?: string; observed_at?: number; supports_effort?: boolean; installed?: boolean | null; authenticated?: boolean | null; quota_available?: boolean | null };
export type Model = { provider_id?: string; provider?: string; model_id?: string; id?: string; display_name?: string; availability?: string; supports_effort?: boolean; effort_levels?: string[]; capabilities?: string[] };
export type Team = { id: string; name: string; objective?: string };
export type Binding = { agent_id: string; team_id?: string; role: string; designation?: string; active?: boolean; unbound_at?: number | null };
export type Message = { id: string; author: string; author_agent_id?: string | null; kind: string; content: string; created_at: number; run_id?: string | null };
export type Task = { id: string; title: string; state: string; assigned_agent_id?: string | null; result?: string | null; instruction?: string; acceptance?: string };
export type Run = { id: string; agent_id: string; provider_id: string; model: string; model_reported?: string | null; state: string; cost_usd?: number | null; cost_basis?: string; input_tokens?: number | null; output_tokens?: number | null; duration_ms?: number | null; error?: string | null };
export type Handoff = { id: string; role: string; from_agent_id?: string | null; to_agent_id: string; reason?: string; context_summary?: string; outcome?: string; created_at: number };
export type LabEvent = { id: string; type: string; entity_id?: string | null; payload?: Record<string, unknown>; occurred_at: number };
export type Artifact = { id: string; title: string; kind?: string; body?: string; path?: string; created_at?: number };
export type Decision = { id: string; statement: string; rationale?: string; created_at?: number };
export type Session = { id: string; team_id: string; objective: string; state: string; updated_at: number; messages?: Message[]; tasks?: Task[]; runs?: Run[]; handoffs?: Handoff[]; events?: LabEvent[]; artifacts?: Artifact[]; decisions?: Decision[]; capability_gaps?: Array<{ id: string; required: string; detail?: string; available?: boolean }>; mission?: { state: string; blocker?: string | null }; autonomy?: { owner_touches: number; content_review: string; gaps?: Array<{ reason: string }> }; acceptance_criteria?: string[]; max_delegations?: number; max_cost_usd?: number | null; total_cost_usd?: number | null };
export type ProviderHealth = { availability: string; scope: 'provider' | 'model'; source: string; timestamp: number; detail: string; retry_after?: number | null };
export type Snapshot = { autonomy_policy?: { enabled: boolean; background_enabled?: boolean; background_task_state?: 'RUNNING' | 'STOPPED' | 'FAILED'; background_error?: string | null; last_state: string; last_tick?: number; last_heartbeat?: number }; workcells?: Array<{ id: string; name: string; kind: string; availability: string; detail: string }>; success?: boolean; error?: string; team?: Team | null; teams?: Team[]; session?: Session | null; sessions?: Session[]; agents?: Agent[]; providers?: Provider[]; models?: Model[]; health?: Record<string, ProviderHealth>; role_bindings?: Binding[]; memberships?: Array<{ team_id: string; agent_id: string; left_at?: number | null }>; participation?: Record<string, string>; regent?: { name?: string; state?: string; detail?: string } };
export type RoomSnapshotSuccess = Omit<Snapshot, 'success' | 'error'> & { success: true; error?: never };
export type RoomSnapshotFailure = { success: false; error: string; code?: string };
export type RoomSnapshotResult = RoomSnapshotSuccess | RoomSnapshotFailure;

export const asList = <T,>(value?: T[] | null): T[] => Array.isArray(value) ? value : [];
export const modelId = (model: Model) => model.model_id || model.id || '';
export const modelProvider = (model: Model) => model.provider_id || model.provider || '';
export const activeBinding = (binding: Binding) => binding.active !== false && !binding.unbound_at;
export const ROLES = ['CEO', 'BUILDER', 'REVIEWER', 'RESEARCHER', 'MEMBER'];
const LABELS: Record<string, string> = {
  AVAILABLE: 'Disponível', UNKNOWN: 'Não verificado', OFFLINE: 'Offline', AUTH_REQUIRED: 'Autenticação necessária',
  PLANNING: 'Planejando', WORKING: 'Trabalhando', REPAIRING: 'Corrigindo', WAITING_RESOURCE: 'Aguardando recurso', BLOCKED_NEEDS_OWNER: 'Aguardando o owner',
  QUOTA_EXHAUSTED: 'Cota esgotada', RATE_LIMITED: 'Limite temporário', MODEL_UNAVAILABLE: 'Modelo indisponível',
  PROVIDER_ERROR: 'Erro do provedor', ERROR: 'Erro', BUSY: 'Ocupado', STOPPED: 'Parado',
  IDLE: 'Em espera', THINKING: 'Pensando', WAITING: 'Aguardando', REVIEWING: 'Revisando', DONE: 'Concluído',
  QUEUED: 'Na fila', RUNNING: 'Em andamento', WAITING_USER: 'Precisa de você', VERIFYING: 'Verificando',
  COMPLETED: 'Concluído', BLOCKED: 'Bloqueado', FAILED: 'Falhou', CANCELLING: 'Cancelando', CANCELLED: 'Cancelado',
  CREATED: 'Criada', ASSIGNED: 'Atribuída', STARTED: 'Em execução', CEO: 'Líder', BUILDER: 'Execução',
  REVIEWER: 'Revisão', RESEARCHER: 'Pesquisa', MEMBER: 'Participante', PERMANENT: 'Permanente', TEMPORARY: 'Temporário',
};
export const label = (value?: string | null) => value ? LABELS[value] || value : 'Não informado';
export function timestamp(value?: number, date = false) {
  if (!value || !Number.isFinite(value)) return '—';
  return new Date(value < 1e12 ? value * 1000 : value).toLocaleString('pt-BR', date
    ? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }
    : { hour: '2-digit', minute: '2-digit' });
}
export function initials(name: string) { return name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase() || '·'; }
export function avatarHue(id: string) { return [...id].reduce((total, char) => total + char.charCodeAt(0) * 17, 0) % 360; }
export function requireResult<T extends { success?: boolean; error?: string }>(result: T | null | undefined): T {
  if (!result || result.success === false || result.error) throw new Error(result?.error || 'O Lab não respondeu. Tente novamente.');
  return result;
}
export const failureText = (cause: unknown) => cause instanceof Error ? cause.message : 'Não foi possível concluir esta ação.';
