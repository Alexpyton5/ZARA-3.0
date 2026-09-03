
import zaraLogo from '../../../assets/zara-home/zara-mark.png';

/**
 * "Projeto ativo" — sem noção de "projeto" persistente exposta ao renderer
 * hoje (core/*.py não tem esse conceito de produto ainda). Mantido como
 * card estrutural com fallback NOT_CONNECTED_YET em vez de inventar estado
 * de projeto/progresso falso.
 */
export function ActiveProjectCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Projeto ativo">
      <h2>Projeto ativo</h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <img src={zaraLogo} alt="" style={{ width: 28, height: 28 }} />
        <div>
          <strong style={{ display: 'block', fontSize: 13 }}>ZARA 3.0</strong>
          <span className="zh-not-connected">Rastreamento de progresso ainda não conectado</span>
        </div>
      </div>
      <div className="zh-progress-track">
        <div className="zh-progress-fill" style={{ width: '0%' }} />
      </div>
      <p className="zh-not-connected" style={{ marginTop: 8 }}>NOT_CONNECTED_YET</p>
    </section>
  );
}
