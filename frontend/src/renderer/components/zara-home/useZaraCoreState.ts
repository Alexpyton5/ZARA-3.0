import { useEffect, useState } from 'react';
import type { CoreState } from './types';

const KNOWN_STATES: ReadonlySet<string> = new Set<CoreState>([
  'idle', 'listening', 'understanding', 'thinking', 'planning', 'executing',
  'awaiting_authorization', 'speaking', 'success', 'error', 'offline',
]);

/**
 * Mapeia `window.zaraIPC.on.stateChange` (canal já existente, usado por
 * outras telas como HUD/Orb) para o vocabulário de CoreState desta Home.
 *
 * Não inventa estado novo: se o backend mandar uma string que não bate com
 * nenhum estado conhecido, cai em 'idle' em vez de quebrar a UI. Se o canal
 * IPC nem existir neste build (renderer isolado/preview), fica em 'offline'.
 */
export function useZaraCoreState(): CoreState {
  const [state, setState] = useState<CoreState>(() =>
    window.zaraIPC?.on?.stateChange ? 'idle' : 'offline',
  );

  useEffect(() => {
    const subscribe = window.zaraIPC?.on?.stateChange;
    if (!subscribe) return;

    const unsubscribe = subscribe((raw: string) => {
      const normalized = String(raw || '').toLowerCase();
      setState(KNOWN_STATES.has(normalized) ? (normalized as CoreState) : 'idle');
    });

    return () => unsubscribe?.();
  }, []);

  return state;
}
