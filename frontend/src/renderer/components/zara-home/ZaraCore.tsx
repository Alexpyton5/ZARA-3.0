import type { CoreState } from './types';
import zaraLogo from '../../../assets/zara-home/zara-logo.png';

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

/** Core central — camadas CSS (gradiente + box-shadow + animação) mais o
 * logo "ZA" real por cima, não um PNG único do dashboard inteiro. Reage a
 * `state` de verdade; não é puramente decorativo quando há estado real
 * disponível (ver useZaraCoreState). */
export function ZaraCore({ state }: ZaraCoreProps) {
  return (
    <div className="zh-core-wrap" role="region" aria-label={`ZARA Core: ${state}`}>
      <div className="zh-core-platform" aria-hidden="true" />
      <div className="zh-core" data-state={state}>
        <img className="zh-core-mark" src={zaraLogo} alt="" aria-hidden="true" />
      </div>
      <div className="zh-core-label">{LABELS[state]}</div>
    </div>
  );
}
