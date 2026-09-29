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
 * + o selo "ZARA usando o PC…" com o passo atual. Some quando o backend
 * emite `computer_agent_stopped` (o main destrói a janela).
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
    </div>
  );
}
