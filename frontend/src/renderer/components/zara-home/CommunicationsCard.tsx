import { ChevronRight } from 'lucide-react';
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';
import telegram from '../../../assets/zara-home/brands/telegram.svg';
import { useHomeFeedback } from './useHomeFeedback';

function InstagramGlyph() {
  // Glifo oficial do Instagram: câmera arredondada sobre o gradiente oficial
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <defs>
        <radialGradient id="zh-ig-bg" cx="30%" cy="107%" r="150%">
          <stop offset="0%" stopColor="#fdf497" />
          <stop offset="5%" stopColor="#fdf497" />
          <stop offset="45%" stopColor="#fd5949" />
          <stop offset="60%" stopColor="#d6249f" />
          <stop offset="90%" stopColor="#285AEB" />
        </radialGradient>
      </defs>
      <rect width="24" height="24" rx="7" fill="url(#zh-ig-bg)" />
      <rect x="4.2" y="4.2" width="15.6" height="15.6" rx="4.6" fill="none" stroke="#fff" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="3.6" fill="none" stroke="#fff" strokeWidth="1.7" />
      <circle cx="16.9" cy="7.1" r="1.15" fill="#fff" />
    </svg>
  );
}

function GmailGlyph() {
  // Glifo oficial do Gmail: envelope com "M" nas cores da marca
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22 6.5v11a1.5 1.5 0 0 1-1.5 1.5H19V9.7l-7 5.05-7-5.05V19H3.5A1.5 1.5 0 0 1 2 17.5v-11c0-1.2 1.37-1.88 2.33-1.16L12 10.7l7.67-5.36C20.63 4.62 22 5.3 22 6.5z" />
      <path fill="#EA4335" d="M2 6.5c0-1.2 1.37-1.88 2.33-1.16L5 5.83V19H3.5A1.5 1.5 0 0 1 2 17.5v-11z" />
      <path fill="#34A853" d="M22 6.5v11a1.5 1.5 0 0 1-1.5 1.5H19V5.83l.67-.49C20.63 4.62 22 5.3 22 6.5z" />
      <path fill="#FBBC04" d="M5 5.83 12 10.7l7-4.87V9.7l-7 5.05-7-5.05V5.83z" />
    </svg>
  );
}

const CHANNELS = [
  { name: 'WhatsApp', id: 'whatsapp' as const, icon: whatsapp, badgeClass: 'zh-comm-badge--wa' },
  { name: 'Telegram', id: 'telegram' as const, icon: telegram, badgeClass: 'zh-comm-badge--tg' },
  { name: 'Instagram', id: 'instagram' as const, Glyph: InstagramGlyph, badgeClass: 'zh-comm-badge--ig' },
  { name: 'Gmail', id: 'gmail' as const, Glyph: GmailGlyph, badgeClass: 'zh-comm-badge--gmail' },
];

/**
 * Comunicações — ícones 1:1 com o MASTER (glifos oficiais das marcas).
 * Contagens são valores de demonstração estáticos do MASTER até que o
 * backend exponha contagens reais por canal.
 */
export function CommunicationsCard({ onNavigate }: { onNavigate: (section: string) => void }) {
  const { feedback, pending, run } = useHomeFeedback();
  return (
    <section className="zh-section zh-glass-panel" aria-label="Comunicações">
      <h2>Comunicações</h2>
      <div className="zh-comm-row">
        {CHANNELS.map(({ name, id, icon, Glyph, badgeClass }) => (
          <button className="zh-comm-item" key={name} type="button" disabled={pending} onClick={() => void run(() => window.zaraIPC?.desktop?.openExternal?.(id), `${name} aberto no navegador.`)} aria-label={`Abrir ${name}`} title={`${name} • contagem de mensagens não conectada`}>
            <div
              className={`zh-comm-badge${badgeClass ? ` ${badgeClass}` : ''}`}
              aria-label={name}
            >
              {icon ? (
                <img src={icon} alt="" />
              ) : (
                Glyph && <Glyph />
              )}
            </div>
            <span className="zh-comm-value" aria-label="Contagem não conectada">—</span>
          </button>
        ))}
        <button className="zh-comm-more" type="button" aria-label="Mais comunicações" onClick={() => onNavigate('Comunicações')}>
          <ChevronRight size={16} strokeWidth={2} />
        </button>
      </div>
      {feedback && <p className="zh-card-feedback" role="status">{feedback}</p>}
    </section>
  );
}
