import { useEffect, useRef, useState } from 'react';
import type { CoreState } from './types';

/** "Deu certo" e "falhou" são confirmações momentâneas, não estados de
 *  repouso. Se o STANDBY seguinte não chegar (backend ocupado, evento
 *  perdido), o Core ficaria verde ou vermelho para sempre — dizendo algo
 *  sobre o presente que só valia para o passado. */
const TRANSIENT_MS = 2600;

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

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const subscribe = window.zaraIPC?.on?.stateChange;
    if (!subscribe) return;

    const unsubscribe = subscribe((raw: string) => {
      const normalized = String(raw || '').toLowerCase();
      const next: CoreState = KNOWN_STATES.has(normalized) ? (normalized as CoreState) : 'idle';
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      setState(next);
      if (next === 'success' || next === 'error') {
        timer.current = setTimeout(() => {
          timer.current = null;
          setState('idle');
        }, TRANSIENT_MS);
      }
    });

    return () => {
      unsubscribe?.();
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return state;
}
