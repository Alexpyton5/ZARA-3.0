import type { CoreState } from './types';
import zaraLogo from '../../../assets/zara-home/zara-logo.png';
import coreGlass from '../../../assets/zara-home/core-glass.png';

const LABELS: Record<CoreState, string> = {
  idle: 'Em espera',
  listening: 'Ouvindo',
  understanding: 'Entendendo',
  thinking: 'Pensando',
  planning: 'Planejando',
  executing: 'Executando',
  awaiting_authorization: 'Aguardando autorização',
  speaking: 'Falando',
  success: 'Concluído',
  error: 'Erro',
  offline: 'Offline',
};

interface ZaraCoreProps {
  state: CoreState;
}

/** Core central — usa o asset real de vidro (`core-glass.png`, o mesmo PNG
 * de esfera do site de referência, renderizado lá como `<img class=
 * "te-sphere-art">`) com o glow de cor por baixo e o glyph "ZA" por cima,
 * mais um feixe de luz vertical ligando o Core à "plataforma" abaixo —
 * mesma composição do site (`.te-platform-shaft`). Reage a `state` de
 * verdade (ver useZaraCoreState); não é puramente decorativo. */
export function ZaraCore({ state }: ZaraCoreProps) {
  return (
    <div className="zh-core-wrap" role="region" aria-label={`ZARA Core: ${state}`}>
      <div className="zh-core" data-state={state}>
        <img className="zh-core-glass" src={coreGlass} alt="" aria-hidden="true" />
        <img className="zh-core-mark" src={zaraLogo} alt="" aria-hidden="true" />
      </div>
      <div className="zh-core-shaft" aria-hidden="true" />
      <div className="zh-core-label">{LABELS[state]}</div>
    </div>
  );
}
