import { useEffect, useState } from 'react';
import { getComputerAgentBridge } from './computerAgentBridge';

export interface ComputerAgentStatus {
  /** `true` enquanto o agente está ativo (a borda fica visível). */
  active: boolean;
  /** Objetivo que disparou a execução (vem do evento `computer_agent_started`). */
  goal: string;
  /** Passo atual (reservado: o backend ainda não emite `computer_agent_step`). */
  step: string;
  /** Índice do passo, quando o backend informar. */
  stepIndex: number | null;
  /** Total de passos, quando o backend informar. */
  stepTotal: number | null;
  /** `true` quando a ponte do preload ainda não foi ligada (Frente C). */
  bridgeMissing: boolean;
}

const IDLE: ComputerAgentStatus = {
  active: false,
  goal: '',
  step: '',
  stepIndex: null,
  stepTotal: null,
  bridgeMissing: false,
};

/**
 * Assina os eventos do computer-agent vindos do backend
 * (`computer-agent-started` / `computer-agent-step` / `computer-agent-stopped`,
 * repassados pelo main process — ver CONTRATO-FRENTE-C.md).
 */
export function useComputerAgent(): ComputerAgentStatus {
  const [status, setStatus] = useState<ComputerAgentStatus>(IDLE);

  useEffect(() => {
    const bridge = getComputerAgentBridge();
    if (!bridge) {
      setStatus((current) => ({ ...current, bridgeMissing: true }));
      return;
    }
    const offStarted = bridge.onStarted((data) => {
      setStatus({
        active: true,
        goal: typeof data?.goal === 'string' ? data.goal : '',
        step: '',
        stepIndex: null,
        stepTotal: null,
        bridgeMissing: false,
      });
    });
    const offStep = bridge.onStep((data) => {
      setStatus((current) => ({
        ...current,
        active: true,
        step: typeof data?.step === 'string' ? data.step : '',
        stepIndex: typeof data?.index === 'number' ? data.index : null,
        stepTotal: typeof data?.total === 'number' ? data.total : null,
      }));
    });
    const offStopped = bridge.onStopped(() => {
      setStatus((current) => ({ ...current, active: false, step: '', stepIndex: null, stepTotal: null }));
    });
    return () => {
      offStarted();
      offStep();
      offStopped();
    };
  }, []);

  return status;
}
