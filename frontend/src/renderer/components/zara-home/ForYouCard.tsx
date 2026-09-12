import { useEffect, useState } from 'react';
import { Calendar, CheckSquare, Settings } from 'lucide-react';
import whatsapp from '../../../assets/zara-home/brands/whatsapp.svg';
import { formatDate } from './homeActions';

type Reminder = { id: string; message: string; due_at_utc: number; state: string };

/** Keeps all four MASTER rows while displaying only connected data. */
export function ForYouCard({ onNavigate }: { onNavigate: (section: string) => void }) {
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [remindersConnected, setRemindersConnected] = useState(false);
  const [taskCount, setTaskCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    let pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      const responses = await Promise.allSettled([
        window.zaraIPC?.reminders?.list?.('SCHEDULED'),
        window.zaraIPC?.lab?.state?.(),
      ]);
      pending = false;
      if (cancelled) return;
      const reminders = responses[0].status === 'fulfilled' ? responses[0].value as { success?: boolean; reminders?: Reminder[] } | undefined : undefined;
      setRemindersConnected(Boolean(reminders?.success));
      setReminder(reminders?.success && Array.isArray(reminders.reminders) ? reminders.reminders.sort((a, b) => a.due_at_utc - b.due_at_utc)[0] ?? null : null);
      const lab = responses[1].status === 'fulfilled' ? responses[1].value : undefined;
      const state = lab?.state ?? lab;
      setTaskCount(Array.isArray(state?.tasks) ? state.tasks.filter((task: { status?: string }) => !['DONE', 'COMPLETED', 'CANCELLED', 'REJECTED', 'FAILED'].includes((task.status || '').toUpperCase())).length : null);
    }
    void load();
    const timer = setInterval(() => void load(), 60000);
    const offCreated = window.zaraIPC?.on?.reminderCreated?.(() => void load());
    const offFired = window.zaraIPC?.on?.reminderFired?.(() => void load());
    return () => { cancelled = true; clearInterval(timer); offCreated?.(); offFired?.(); };
  }, []);

  const items = [
    { img: whatsapp, Icon: null, label: 'Suas comunicações', sub: 'Abra seus aplicativos', section: 'Comunicações', color: '#00df9f' },
    { img: null, Icon: Calendar, label: reminder?.message || (remindersConnected ? 'Nenhum lembrete agendado' : 'Seus lembretes'), sub: reminder ? formatDate(reminder.due_at_utc) : remindersConnected ? 'Criar um lembrete' : 'Consultar agenda local', section: 'Automações', color: '#00df9f' },
    { img: null, Icon: CheckSquare, label: taskCount === null ? 'Tarefas do ZARA Lab' : `${taskCount} ${taskCount === 1 ? 'tarefa pendente' : 'tarefas pendentes'}`, sub: 'Ver todas', section: 'ZARA Lab', color: '#00df9f' },
    { img: null, Icon: Settings, label: 'Modelos e voz', sub: 'Ver configurações', section: 'Configurações', color: '#fa594f' },
  ];
  return (
    <section className="zh-section zh-glass-panel zh-foryou-card" aria-label="Para você">
      <h2>Para você</h2>
      <div className="zh-foryou-list">
        {items.map(({ img, Icon, label, sub, section, color }) => (
          <button type="button" className="zh-foryou-item" key={section} onClick={() => onNavigate(section)}>
            <span className="zh-foryou-icon" style={{ color }}>{img ? <img src={img} alt="" /> : Icon && <Icon size={27} strokeWidth={1.8} />}</span>
            <span className="zh-foryou-text"><strong>{label}</strong><span>{sub}</span></span>
          </button>
        ))}
      </div>
    </section>
  );
}
