import { Bell, CalendarClock, MessageCircle, BrainCircuit } from 'lucide-react';
import { useHomeSignals, type HomeSignal } from './useHomeSignals';

const ICONS: Record<HomeSignal['kind'], typeof Bell> = {
  reminder: CalendarClock,
  reminders: Bell,
  history: MessageCircle,
  memory: BrainCircuit,
};

const DESTINOS: Record<HomeSignal['kind'], string> = {
  reminder: 'Automações',
  reminders: 'Automações',
  history: 'Conversas',
  memory: 'Memórias',
};

interface ForYouCardProps {
  onNavigate?: (section: string) => void;
}

/**
 * "Para você".
 *
 * Até aqui este card era conteúdo de maquete: "João espera sua resposta •
 * WhatsApp • 10 min", "Reunião às 14:00", "3 tarefas pendentes". Nada disso
 * vinha de lugar nenhum — era ficção acionável na tela principal, do tipo que
 * faz o Alex ir procurar uma mensagem do João que não existe.
 *
 * Agora só entra o que o backend realmente tem: lembretes persistidos pelo
 * Reminder Core, histórico local e memória do usuário. Sem sinal, o card diz
 * que não há nada — nunca preenche com exemplo.
 */
export function ForYouCard({ onNavigate }: ForYouCardProps) {
  const { signals, loading, connected } = useHomeSignals();

  return (
    <section className="zh-section zh-glass-panel" aria-label="Para você">
      <h2>Para você</h2>
      <div className="zh-foryou-list">
        {!connected ? (
          <p className="zh-not-connected">Sem conexão com o backend agora.</p>
        ) : loading ? (
          <p className="zh-not-connected">Lendo…</p>
        ) : signals.length === 0 ? (
          <p className="zh-not-connected">Nada pendente agora.</p>
        ) : (
          signals.map((s) => {
            const Icon = ICONS[s.kind];
            return (
              <button
                className="zh-foryou-item"
                type="button"
                key={s.key}
                onClick={() => onNavigate?.(DESTINOS[s.kind])}
              >
                <span className="zh-foryou-icon">
                  <Icon size={15} strokeWidth={2} />
                </span>
                <span className="zh-foryou-text">
                  <strong>{s.label}</strong>
                  <span>{s.sub}</span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
