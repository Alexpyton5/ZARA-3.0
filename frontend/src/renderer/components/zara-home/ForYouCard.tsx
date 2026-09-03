import { Calendar, CheckSquare, Settings } from 'lucide-react';
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';

const ITEMS = [
  { img: whatsapp, Icon: null, label: 'João espera sua resposta', sub: 'WhatsApp • 10 min', color: '#25d366' },
  { img: null, Icon: Calendar, label: 'Reunião às 14:00', sub: 'Projeto ZARA', color: '#b7c4bf' },
  { img: null, Icon: CheckSquare, label: '3 tarefas pendentes', sub: 'Ver todas', color: '#b7c4bf' },
  { img: null, Icon: Settings, label: 'Atualização disponível', sub: '1 biblioteca', color: '#c7a868' },
];

/**
 * "Para você" — conteúdo 1:1 com o MASTER (valores de demonstração estáticos
 * até que uma fonte real de sugestões seja exposta ao renderer).
 * Chips: círculos escuros com glifo outline colorido, como no MASTER.
 */
export function ForYouCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Para você">
      <h2>Para você</h2>
      <div className="zh-foryou-list">
        {ITEMS.map(({ img, Icon, label, sub, color }) => (
          <div className="zh-foryou-item" key={label}>
            <span className="zh-foryou-icon" style={{ color }}>
              {img ? (
                <img src={img} alt="" />
              ) : (
                Icon && <Icon size={15} strokeWidth={2} />
              )}
            </span>
            <span className="zh-foryou-text">
              <strong>{label}</strong>
              <span>{sub}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
