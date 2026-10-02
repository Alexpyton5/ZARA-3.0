import { useEffect, useState } from 'react';
import { ArrowUpRight, FlaskConical, CheckCheck, ListTodo } from 'lucide-react';

type LabTask = { title?: string; status?: string; updated_at?: number };
type LabSnapshot = { tasks: LabTask[]; proposals: Array<{ status?: string }> };
const COMPLETE = new Set(['DONE', 'COMPLETED', 'CANCELLED', 'REJECTED', 'FAILED']);

/** A read-only view of persisted Lab work. Opening Home never dispatches agents. */
export function LabHomeCard({ onNavigate }: { onNavigate: (section: string) => void }) {
  const [snapshot, setSnapshot] = useState<LabSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    let pending = false;
    async function refresh() {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const response = await window.zaraIPC?.lab?.state?.();
        const state = response?.state ?? response;
        if (!response || response.success === false || !Array.isArray(state?.tasks) || !Array.isArray(state?.proposals)) throw new Error('Unavailable');
        if (!cancelled) setSnapshot({ tasks: state.tasks, proposals: state.proposals });
      } catch {
        if (!cancelled) setSnapshot(null);
      } finally {
        pending = false;
        if (!cancelled) setLoading(false);
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { cancelled = true; clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, []);
  const tasks = snapshot?.tasks.filter(task => !COMPLETE.has((task.status ?? '').toUpperCase()));
  const reviews = snapshot?.proposals.filter(proposal => ['DISCUSSION', 'PENDING', 'PROPOSED', 'AWAITING_APPROVAL', 'PENDING_APPROVAL'].includes((proposal.status ?? '').toUpperCase())).length;
  const latest = tasks?.slice().sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0))[0];
  return <section className="zh-section zh-glass-panel zh-lab-card" aria-label="ZARA Lab — visão geral">
    <header className="zh-lab-heading"><h2>ZARA Lab</h2><span data-connected={Boolean(snapshot)}>{loading ? 'Consultando' : snapshot ? 'Memória local' : 'Sem conexão'}</span></header>
    <button type="button" className="zh-lab-entry" onClick={() => onNavigate('ZARA Lab')} aria-label="Abrir ZARA Lab">
      <span className="zh-lab-symbol"><FlaskConical size={31} strokeWidth={1.4} /></span>
      <span className="zh-lab-copy"><strong>{latest?.title || 'Ideias em movimento'}</strong><span>{latest ? 'Retomar o trabalho no Lab' : 'Tarefas, decisões e contexto'}</span></span>
      <ArrowUpRight size={22} strokeWidth={1.4} />
    </button>
    <div className="zh-lab-summary"><span><ListTodo size={16} />{tasks ? `${tasks.length} pendentes` : 'Tarefas —'}</span><span><CheckCheck size={16} />{reviews !== undefined ? `${reviews} para revisar` : 'Revisões —'}</span><button type="button" onClick={() => onNavigate('Aplicativos')}>Aplicativos</button></div>
  </section>;
}
