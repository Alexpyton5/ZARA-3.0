import { ChevronRight } from 'lucide-react';
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';
import telegram from '../../../assets/zara-home/brands/telegram.svg';

/**
 * O site de referência mostra WhatsApp/Telegram/Instagram/Gmail como
 * círculos coloridos com contagem de mensagens embaixo. A ZARA hoje só tem
 * ponte real com Telegram (core/telegram_ponte.py) — sem canal IPC exposto
 * ao renderer ainda, e sem asset baixado para Instagram/Gmail. Reproduzimos
 * a estrutura visual real (círculo colorido + rótulo abaixo) só para os
 * dois canais que existem de verdade no projeto, com "—" honesto em vez da
 * contagem fake (12, 3, 5, 7) do site de referência.
 */
export function CommunicationsCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Comunicações">
      <h2>Comunicações</h2>
      <div className="zh-comm-row">
        <div className="zh-comm-badge" style={{ background: '#25d366' }}>
          <img src={whatsapp} alt="WhatsApp" />
        </div>
        <div className="zh-comm-badge" style={{ background: '#26a5e4' }}>
          <img src={telegram} alt="Telegram" />
        </div>
        <button className="zh-comm-more" type="button" aria-label="Mais comunicações">
          <ChevronRight size={16} strokeWidth={2} />
        </button>
      </div>
      <p className="zh-not-connected" style={{ marginTop: 10 }}>
        NOT_CONNECTED_YET — contagem de mensagens não exposta ao renderer ainda.
      </p>
    </section>
  );
}
