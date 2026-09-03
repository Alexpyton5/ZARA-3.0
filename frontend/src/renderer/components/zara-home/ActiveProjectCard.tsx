import { ChevronRight } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.svg';

/**
 * "Projeto ativo" — estrutura 1:1 com o MASTER: título, mini core à esquerda,
 * "ZARA App" / "Desenvolvimento" / "61%" emerald, linha de progresso fina,
 * linha "Última sessão" + Continuar, dots abaixo.
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
          <span className="zh-project-percent">61%</span>
        </div>
      </div>

      <div className="zh-progress-track">
        <div className="zh-progress-fill" style={{ width: '61%' }} />
      </div>

      <div className="zh-project-row">
        <p className="zh-project-last-session">Última sessão: hoje, 14:12</p>
        <button className="zh-project-continue" type="button">
          Continuar
          <ChevronRight size={15} strokeWidth={2} />
        </button>
      </div>

      <div className="zh-project-dots" aria-hidden="true">
        {Array.from({ length: 7 }).map((_, i) => (
          <span key={i} data-active={i === 3} />
        ))}
      </div>
    </section>
  );
}
