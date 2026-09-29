/**
 * Ponte tipada para o canal do computer-agent no preload (Frente B).
 *
 * O preload pode chegar por dois caminhos (a Frente C escolhe um na
 * integração — ver CONTRATO-FRENTE-C.md):
 *  1. `window.zaraComputerAgent` — preload separado (`src/preload-computer-agent.ts`);
 *  2. `window.zaraIPC.computerAgent` — seção mesclada dentro do `preload.ts`.
 *
 * Esta função resolve qualquer um dos dois, então o renderer não quebra
 * independente da escolha da Frente C.
 */

/**
 * Ponte utilizável: os 4 membros essenciais existem de verdade
 * (o `isUsableBridge` abaixo garante — o chamador não precisa de `?.`).
 */
export interface UsableComputerAgentBridge {
  run: (goal: string) => Promise<unknown>;
  showOverlay?: () => Promise<unknown>;
  hideOverlay?: () => Promise<unknown>;
  onStarted: (callback: (data: ComputerAgentStartedPayload) => void) => () => void;
  onStep: (callback: (data: ComputerAgentStepPayload) => void) => () => void;
  onStopped: (callback: (data: ComputerAgentStoppedPayload) => void) => () => void;
}

/** A ponte só vale se tiver o essencial: run + as 3 inscrições de evento. */
function isUsableBridge(candidate: ComputerAgentPreloadAPI | undefined): candidate is UsableComputerAgentBridge {
  return (
    !!candidate &&
    typeof candidate.run === 'function' &&
    typeof candidate.onStarted === 'function' &&
    typeof candidate.onStep === 'function' &&
    typeof candidate.onStopped === 'function'
  );
}

/**
 * Devolve a ponte do computer-agent, ou `null` quando o preload ainda não
 * foi ligado (nesse caso o chamador mostra erro honesto em vez de fingir
 * que o comando foi enviado).
 */
export function getComputerAgentBridge(): UsableComputerAgentBridge | null {
  if (typeof window === 'undefined') return null;
  if (isUsableBridge(window.zaraComputerAgent)) return window.zaraComputerAgent;
  const merged = window.zaraIPC?.computerAgent;
  if (isUsableBridge(merged)) return merged;
  return null;
}
