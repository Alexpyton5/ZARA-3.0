
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';
import telegram from '../../../assets/zara-home/brands/telegram.svg';

/**
 * O site de referência mostra WhatsApp/Telegram/Instagram/Gmail com contagens
 * fake. A ZARA hoje só tem ponte real com Telegram
 * (core/telegram_ponte.py) — sem canal IPC exposto ao renderer ainda.
 * Mostramos só o que tem asset real baixado (whatsapp/telegram) e marcamos
 * contagem como NOT_CONNECTED_YET em vez de inventar número.
 */
export function CommunicationsCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Comunicações">
      <h2>Comunicações</h2>
      <div className="zh-comm-row">
        <span className="zh-comm-pill">
          <img src={whatsapp} alt="" /> WhatsApp <span className="zh-not-connected">—</span>
        </span>
        <span className="zh-comm-pill">
          <img src={telegram} alt="" /> Telegram <span className="zh-not-connected">—</span>
        </span>
      </div>
      <p className="zh-not-connected" style={{ marginTop: 8 }}>
        NOT_CONNECTED_YET — contagem de mensagens não exposta ao renderer ainda.
      </p>
    </section>
  );
}
