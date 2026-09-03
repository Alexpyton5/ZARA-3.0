import { ChevronRight } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.png';

/**
 * "Projeto ativo" — estrutura visual do MASTER (ícone, título, subtítulo,
 * barra de progresso, última sessão, botão Continuar, dots). Não temos
 * rastreamento real de projeto, então mantemos textos honestos e progresso
 * em 0% em vez de inventar 61%.
 */
export function ActiveProjectCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Projeto ativo">
      <h2>Projeto ativo</h2>
      <div className="zh-project-header">
        <img src={zaraLogo} alt="" />
        <div className="zh-project-meta">
          <strong>ZARA App</strong>
          <span>Desenvolvimento</span>
        </div>
      </div>

      <div className="zh-progress-track">
        <div className="zh-progress-fill" style={{ width: '0%' }} />
      </div>

      <p className="zh-project-last-session">Nenhuma sessão recente</p>

      <div className="zh-project-footer">
        <div className="zh-project-dots" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} data-active={i === 0} />
          ))}
        </div>
        <button className="zh-project-continue" type="button" disabled>
          Continuar
          <ChevronRight size={14} strokeWidth={2} />
        </button>
      </div>
    </section>
  );
}
