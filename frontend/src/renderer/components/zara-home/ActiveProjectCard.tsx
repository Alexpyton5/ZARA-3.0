import { ChevronRight } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.png';

/**
 * "Projeto ativo" — conteúdo 1:1 com o MASTER (valores de demonstração
 * estáticos até que exista rastreamento real de projeto no backend).
 */
export function ActiveProjectCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Projeto ativo">
      <h2>Projeto ativo</h2>
      <div className="zh-project-header">
        <span className="zh-project-badge">
          <img src={zaraLogo} alt="" />
        </span>
        <div className="zh-project-meta">
          <strong>ZARA App</strong>
          <span>Desenvolvimento</span>
        </div>
      </div>

      <div className="zh-progress-row">
        <span className="zh-progress-label">61%</span>
        <div className="zh-progress-track">
          <div className="zh-progress-fill" style={{ width: '61%' }} />
        </div>
      </div>

      <p className="zh-project-last-session">Última sessão: hoje, 14:12</p>

      <div className="zh-project-footer">
        <div className="zh-project-dots" aria-hidden="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <span key={i} data-active={i === 2} />
          ))}
        </div>
        <button className="zh-project-continue" type="button">
          Continuar
          <ChevronRight size={14} strokeWidth={2} />
        </button>
      </div>
    </section>
  );
}
