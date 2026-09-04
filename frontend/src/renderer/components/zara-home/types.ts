/**
 * Tipos compartilhados da Home Titanium Emerald.
 *
 * `CoreState` espelha os estados pedidos na missão de integração — o
 * mapeamento real (backend -> CoreState) vive em `useZaraCoreState.ts`.
 */
export type CoreState =
  | 'idle'
  | 'listening'
  | 'understanding'
  | 'thinking'
  | 'planning'
  | 'executing'
  | 'awaiting_authorization'
  | 'speaking'
  | 'success'
  | 'error'
  | 'offline';

export interface SystemMetricsData {
  cpu: number | null;
  ram: number | null;
  disk: number | null;
}

export interface BatteryData {
  supported: boolean;
  level: number | null;
  charging: boolean | null;
}

export interface WifiStatusData {
  supported: boolean;
  on: boolean | null;
}

export interface PowerPlan {
  guid: string;
  name: string;
  active: boolean;
}

export interface PowerPlansData {
  supported: boolean;
  plans: PowerPlan[];
  pending: boolean;
  setPlan: (guid: string) => void;
}
