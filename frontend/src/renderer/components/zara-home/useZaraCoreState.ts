import { useEffect, useRef, useState } from 'react';
import type { CoreState } from './types';

/** "Deu certo" e "falhou" são confirmações momentâneas, não estados de
 *  repouso. Se o STANDBY seguinte não chegar (backend ocupado, evento
 *  perdido), o Core ficaria verde ou vermelho para sempre — dizendo algo
 *  sobre o presente que só valia para o passado. */
const TRANSIENT_MS = 2600;

/**
 * Tempo MÍNIMO de exibição por estado.
 *
 * "Entendi", "executando" e "conferindo" acontecem de verdade no backend
 * (ver `_executar_intent_de_pc`), mas em sequência, em poucos milissegundos.
 * Sem um piso de exibição o olho não vê nenhum deles e a tela pula direto de
 * repouso para verde — o Alex não fica sabendo que houve verificação.
 *
 * Isto NÃO inventa fase: cada estado da fila foi realmente emitido, na ordem
 * em que aconteceu. O preço é que a tela pode ficar até ~0,8s atrás da
 * realidade num comando muito rápido. É um atraso conhecido e limitado, não
 * uma animação decorativa.
 */
const DWELL_MS: Partial<Record<CoreState, number>> = {
  understanding: 260,
  executing: 220,
  verifying: 300,
};

const KNOWN_STATES: ReadonlySet<string> = new Set<CoreState>([
  'idle', 'listening', 'understanding', 'thinking', 'planning', 'executing',
  'verifying', 'awaiting_authorization', 'speaking', 'success', 'error', 'offline',
]);

/** Fila curta: um comando encadeia no máximo 4 fases. O teto existe para a
 *  tela nunca acumular um atraso grande se o backend ficar falante. */
const MAX_FILA = 6;

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
  const fila = useRef<CoreState[]>([]);
  const ocupadoAte = useRef(0);

  useEffect(() => {
    const subscribe = window.zaraIPC?.on?.stateChange;
    if (!subscribe) return;

    function limparTimer() {
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    }

    function aplicar(next: CoreState) {
      limparTimer();
      setState(next);
      const dwell = DWELL_MS[next] ?? 0;
      ocupadoAte.current = Date.now() + dwell;

      if (dwell > 0) {
        // Sempre agenda o dreno: os estados seguintes chegam DEPOIS deste
        // instante (é o caso normal — o backend emite as fases em sequência),
        // então esperar a fila encher antes de agendar deixaria tudo parado.
        timer.current = setTimeout(() => {
          timer.current = null;
          ocupadoAte.current = 0;
          const proximo = fila.current.shift();
          if (proximo) aplicar(proximo);
        }, dwell);
        return;
      }

      // SUCCESS e ERROR voltam sozinhos ao repouso.
      if (next === 'success' || next === 'error') {
        timer.current = setTimeout(() => {
          timer.current = null;
          ocupadoAte.current = 0;
          setState('idle');
        }, TRANSIENT_MS);
      }
    }

    const unsubscribe = subscribe((raw: string) => {
      const normalized = String(raw || '').toLowerCase();
      const next: CoreState = KNOWN_STATES.has(normalized) ? (normalized as CoreState) : 'idle';

      if (Date.now() < ocupadoAte.current) {
        // O estado atual ainda não completou o tempo mínimo: entra na fila em
        // vez de ser engolido.
        if (fila.current.length < MAX_FILA) fila.current.push(next);
        return;
      }
      fila.current.length = 0;
      aplicar(next);
    });

    return () => {
      unsubscribe?.();
      limparTimer();
      fila.current.length = 0;
    };
  }, []);

  return state;
}
