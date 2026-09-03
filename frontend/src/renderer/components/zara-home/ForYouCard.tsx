import { MessageCircle, Calendar, CheckSquare, RefreshCw } from 'lucide-react';

const ITEMS = [
  { icon: MessageCircle, label: 'Mensagens', sub: 'Aguardando conexão', color: '#25d366' },
  { icon: Calendar, label: 'Agenda', sub: 'Aguardando conexão', color: '#7c9cff' },
  { icon: CheckSquare, label: 'Tarefas', sub: 'Aguardando conexão', color: '#00d699' },
  { icon: RefreshCw, label: 'Atualizações', sub: 'Aguardando conexão', color: '#c7a868' },
];

/**
 * "Para você" — estrutura visual copiada do MASTER (4 itens com ícone
 * colorido, título e subtítulo). Como não existe fonte real de sugestões,
 * mantemos o subtítulo honesto "Aguardando conexão" em vez de inventar dados.
 */
export function ForYouCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Para você">
      <h2>Para você</h2>
      <div className="zh-foryou-list">
        {ITEMS.map(({ icon: Icon, label, sub, color }) => (
          <div className="zh-foryou-item" key={label}>
            <span className="zh-foryou-icon" style={{ color, background: `${color}1c` }}>
              <Icon size={16} strokeWidth={1.8} />
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
