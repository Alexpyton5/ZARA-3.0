import { ChevronRight, Camera, Mail } from 'lucide-react';
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';
import telegram from '../../../assets/zara-home/brands/telegram.svg';

const CHANNELS = [
  { name: 'WhatsApp', icon: whatsapp, color: '#25d366', value: '—' },
  { name: 'Telegram', icon: telegram, color: '#26a5e4', value: '—' },
  { name: 'Instagram', Icon: Camera, color: '#e4405f', value: '—' },
  { name: 'Gmail', Icon: Mail, color: '#ea4335', value: '—' },
];

/**
 * Comunicações — estrutura visual do MASTER (4 ícones coloridos em círculos
 * com contagem abaixo). Não temos contagem real, então usamos "—" honesto
 * em vez de números fake.
 */
export function CommunicationsCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Comunicações">
      <h2>Comunicações</h2>
      <div className="zh-comm-row">
        {CHANNELS.map(({ name, icon, Icon, color, value }) => (
          <div className="zh-comm-item" key={name}>
            <div className="zh-comm-badge" style={{ background: color }} aria-label={name}>
              {icon ? (
                <img src={icon} alt="" />
              ) : (
                Icon && <Icon size={18} strokeWidth={1.8} />
              )}
            </div>
            <span className="zh-comm-value">{value}</span>
          </div>
        ))}
        <button className="zh-comm-more" type="button" aria-label="Mais comunicações">
          <ChevronRight size={16} strokeWidth={2} />
        </button>
      </div>
    </section>
  );
}
