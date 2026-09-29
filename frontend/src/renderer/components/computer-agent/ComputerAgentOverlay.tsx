import { useEffect } from 'react';
import { useComputerAgent } from './useComputerAgent';
import './computer-agent-overlay.css';

/**
 * Janela de overlay do use-computer (Frente B).
 *
 * NÃO é uma tela do app: o main process (Frente C) abre esta mesma página
 * do renderer numa BrowserWindow separada — fullscreen, transparente,
 * always-on-top e click-through — passando `?overlay=computer-agent` na URL
 * (ver `main.tsx` e CONTRATO-FRENTE-C.md).
 *
 * O que ela mostra: só a borda neon (verde/roxo, ~6px) nas bordas da tela
 * + o selo "ZARA usando o PC…" com o passo atual e a barra de progresso.
 * Some quando o backend emite `computer_agent_stopped` (o main destrói a janela).
 */
export function ComputerAgentOverlay() {
  const { active, goal, step, stepIndex, stepTotal } = useComputerAgent();

  useEffect(() => {
    document.documentElement.classList.add('ca-overlay-mode');
    document.title = 'ZARA — usando o computador';
    return () => {
      document.documentElement.classList.remove('ca-overlay-mode');
    };
  }, []);

  const progress =
    stepIndex !== null && stepTotal !== null && stepTotal > 0 ? ` · passo ${stepIndex + 1} de ${stepTotal}` : '';
  const detail = step || goal;
  const detailText = detail ? `${detail}${progress}` : '';

  // Fração de progresso 0–100 quando o backend informa passo/total; `null` =
  // modo indeterminado (brilho deslizando) quando o total ainda é desconhecido.
  const progressPct =
    stepIndex !== null && stepTotal !== null && stepTotal > 0
      ? Math.min(100, Math.max(0, ((stepIndex + 1) / stepTotal) * 100))
      : null;

  return (
    <div className="ca-overlay" aria-hidden={!active}>
      <div className={`ca-edges${active ? ' ca-edges--active' : ''}`} aria-hidden="true">
        <div className="ca-edge ca-edge--top" />
        <div className="ca-edge ca-edge--right" />
        <div className="ca-edge ca-edge--bottom" />
        <div className="ca-edge ca-edge--left" />
      </div>
      <div className={`ca-selo${active ? ' ca-selo--active' : ''}`} role="status" aria-live="polite">
        <span className="ca-selo__dot" aria-hidden="true" />
        <span className="ca-selo__title">ZARA usando o PC…</span>
        {detailText && (
          <span className="ca-selo__step" title={detailText}>
            {detailText}
          </span>
        )}
      </div>
      {active && (
        <div
          className="ca-progress ca-progress--active"
          role="progressbar"
          aria-label="Progresso do uso do computador"
          aria-valuemin={0}
          aria-valuemax={stepTotal ?? undefined}
          aria-valuenow={stepIndex !== null ? stepIndex + 1 : undefined}
          aria-hidden="true"
        >
          <div
            className={`ca-progress__fill${progressPct === null ? ' ca-progress__fill--indeterminate' : ''}`}
            style={progressPct !== null ? { width: `${progressPct}%` } : undefined}
          />
        </div>
      )}
    </div>
  );
}
