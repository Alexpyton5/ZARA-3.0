import { useEffect, useRef, useState } from 'react';
import { X, RefreshCw } from 'lucide-react';
import "../../styles/zh-drawer-motion.css";
import { ToolsCard } from './ToolsCard';
import { TextCommandInput } from './TextCommandInput';
import { normalizeHistoryResponse, type ChatMessage } from '../../lib/chatHistory';
import { errorMessage, formatDate } from './homeActions';
import { recoverDurableLabMutations, runDurableLabMutation } from '../../lib/labDurableOperation';

type Item = { id?: string; title?: string; content?: string; fact?: string; message?: string; state?: string; due_at_utc?: number; updated_at?: number };
type LabMessage = { id: string; author: string; target: string; content: string; created_at: number };
type LabActivity = { id: number; actor: string; event: string; detail: string; created_at: number };
// ZARA-LAB-V1-001: shapes match core/lab_v1/runtime.py LabRuntime.snapshot()
// (verified by reading it directly, not guessed): top-level agents/
// role_bindings/providers/participation/sessions always come back; the rich
// per-session data (messages/tasks/handoffs/total_cost_usd) is nested under
// `session`, and that key is only present when a session_id was passed in
// and found. The renderer still checks Array.isArray/typeof everywhere
// because service.py's error path returns a plain {success:false,error}
// dict with none of these keys.
type LabV1RawAgent = { id: string; name?: string; provider_id?: string; model?: string; role?: string; archived?: boolean };
type LabV1RawBinding = { agent_id?: string; role?: string; designation?: string; active?: boolean; unbound_at?: number | null };
type LabV1RawProvider = { id: string; label?: string; availability?: string; detail?: string };
type LabV1RawMessage = { id?: string; author?: string; content?: string; kind?: string; created_at?: number };
type LabV1RawTask = { id?: string; title?: string; assigned_agent_id?: string | null; state?: string; result?: string | null };
type LabV1RawHandoff = { id?: string; role?: string; from_agent_id?: string | null; to_agent_id?: string; reason?: string; created_at?: number };
type LabV1RawSession = {
  id?: string; objective?: string; state?: string; updated_at?: number;
  messages?: LabV1RawMessage[]; tasks?: LabV1RawTask[]; handoffs?: LabV1RawHandoff[];
  total_cost_usd?: number | null;
};
type LabV1Snapshot = {
  success?: boolean; error?: string;
  session?: LabV1RawSession | null;
  sessions?: LabV1RawSession[];
  agents?: LabV1RawAgent[];
  role_bindings?: LabV1RawBinding[];
  providers?: LabV1RawProvider[];
  participation?: Record<string, string>;
};
type LabV1RosterEntry = { id: string; name: string; role: string; model: string; providerId: string; designation: string; participation: string };
type LabV1View = {
  sessionId: string; objective: string; sessionState: string;
  roster: LabV1RosterEntry[];
  providers: LabV1RawProvider[];
  messages: LabV1RawMessage[];
  tasks: Array<{ id: string; title: string; assignee: string; state: string; result: string | null }>;
  handoffs: Array<{ id: string; role: string; from: string; to: string; reason: string }>;
  costLabel: string;
};
type ViewData = { items?: Item[]; messages?: ChatMessage[]; engines?: Array<{ id: string; name?: string; available?: boolean }>; summary?: string; projects?: Array<{ id: string; keys: string[] }>; keys?: string[]; labMessages?: LabMessage[]; labActivity?: LabActivity[]; workers?: Array<{ id: string; name: string; can_chat: boolean }>; labV1?: LabV1View };

// Never invents WORKING: participation is only ever what the backend reported
// for that agent id. Missing means unknown, not idle.
function normalizeLabV1(raw: LabV1Snapshot | null | undefined): LabV1View | null {
  if (!raw || typeof raw !== 'object') return null;
  // Opening the Lab with no session chosen would otherwise show an empty room
  // even when real missions exist, because the backend only expands one session
  // when asked for it by id. Adopt the most recent one so the panel opens on
  // real work; the effect below then re-fetches it with its messages and tasks.
  const sessionList = Array.isArray(raw.sessions) ? raw.sessions : [];
  const mostRecent = sessionList.length
    ? sessionList.reduce((a, b) => ((b?.updated_at ?? 0) > (a?.updated_at ?? 0) ? b : a))
    : null;
  const session = raw.session ?? mostRecent ?? null;
  const agents = Array.isArray(raw.agents) ? raw.agents : [];
  const bindings = Array.isArray(raw.role_bindings) ? raw.role_bindings : [];
  const participation = raw.participation && typeof raw.participation === 'object' ? raw.participation : {};
  const providers = Array.isArray(raw.providers) ? raw.providers : [];
  const messages = Array.isArray(session?.messages) ? (session!.messages as LabV1RawMessage[]) : [];
  const tasks = Array.isArray(session?.tasks) ? (session!.tasks as LabV1RawTask[]) : [];
  const handoffs = Array.isArray(session?.handoffs) ? (session!.handoffs as LabV1RawHandoff[]) : [];
  const nameOf = (id?: string | null) => (id ? agents.find(agent => agent.id === id)?.name || id : '—');
  const roster: LabV1RosterEntry[] = agents.filter(agent => !agent.archived).map(agent => {
    const binding = bindings.find(entry => entry.agent_id === agent.id && entry.active !== false && !entry.unbound_at);
    return {
      id: agent.id,
      name: agent.name || agent.id,
      role: binding?.role || agent.role || '—',
      model: agent.model || '—',
      providerId: agent.provider_id || '—',
      designation: binding?.designation || 'PERMANENT',
      participation: participation[agent.id] || '',
    };
  });
  const cost = typeof session?.total_cost_usd === 'number' ? session.total_cost_usd : null;
  return {
    sessionId: session?.id || '',
    objective: session?.objective || '',
    sessionState: session?.state || '',
    roster,
    providers,
    messages,
    tasks: tasks.map(task => ({ id: task.id || '', title: task.title || 'Tarefa', assignee: nameOf(task.assigned_agent_id), state: task.state || '—', result: task.result ?? null })),
    handoffs: handoffs.map(handoff => ({ id: handoff.id || '', role: handoff.role || '—', from: nameOf(handoff.from_agent_id), to: nameOf(handoff.to_agent_id), reason: handoff.reason || '' })),
    // A missing or zero cost is unproven spend, not a free mission -- never "grátis".
    costLabel: cost && cost > 0 ? `US$ ${cost.toFixed(2)}` : '—',
  };
}
const CHANNELS = ['whatsapp', 'telegram', 'instagram', 'gmail'] as const;
const SECTIONS = ['Conversas', 'Projetos', 'Arquivos', 'Aplicativos', 'Automações', 'Memórias', 'ZARA Lab', 'Dispositivos', 'Sistema', 'Configurações'];

export function HomeDrawer({ section, onClose, onNavigate }: { section: string; onClose: () => void; onNavigate: (section: string) => void }) {
  const [data, setData] = useState<ViewData>({});
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [revision, setRevision] = useState(0);
  const [text, setText] = useState('');
  const [date, setDate] = useState('');
  const [query, setQuery] = useState('');
  const [target, setTarget] = useState('');
  const [labV1SessionId, setLabV1SessionId] = useState<string | undefined>(undefined);
  useEffect(() => { void recoverDurableLabMutations(window.zaraIPC?.labV1 || {}); }, []);
  const dialog = useRef<HTMLElement>(null);
  const op = useRef(false);
  const refresh = () => setRevision(value => value + 1);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select, textarea, [tabindex="0"]') ?? []);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setError(''); setLoading(true);
    const api = window.zaraIPC;
    async function load(): Promise<ViewData> {
      let result;
      if (section === 'Conversas' || section === 'Histórico') {
        result = await api?.conversationHistory?.list?.(200);
        if (!result || result.error) throw new Error(result?.error || 'Histórico não conectado.');
        return { messages: normalizeHistoryResponse(result) };
      }
      if (section === 'Memórias' || section === 'Arquivos') {
        result = await api?.memoryGalaxy?.list?.();
        if (!result?.success) throw new Error(result?.error || 'Memórias não conectadas.');
        return { items: result.nodes ?? [] };
      }
      if (section === 'Automações') {
        result = await api?.reminders?.list?.() as { success?: boolean; reminders?: Item[]; error?: string };
        if (!result?.success) throw new Error(result?.error || 'Agenda não conectada.');
        return { items: result.reminders ?? [] };
      }
      if (section === 'Projetos') {
        result = await api?.projectMemory?.context?.();
        if (!result?.success) throw new Error('Projetos não conectados.');
        return {
          projects: Array.isArray(result.projects) ? result.projects : [],
          keys: Array.isArray(result.legacy_document_keys) ? result.legacy_document_keys : Array.isArray(result.keys) ? result.keys : [],
          summary: result.active_project_id ? `Projeto selecionado: ${result.active_project_id}` : 'Selecione um documento para recuperar o contexto.',
        };
      }
      if (section === 'Configurações') {
        result = await api?.engine?.list?.();
        if (!result) throw new Error('Modelos não conectados.');
        const engines = result.engines ?? result.models ?? [];
        return { engines: Array.isArray(engines) ? engines.map((engine: string | { id: string; name?: string; available?: boolean }) => typeof engine === 'string' ? { id: engine } : engine) : [], summary: 'Selecione o modelo ou gerencie o áudio da ZARA.' };
      }
      if (section === 'ZARA Lab') {
        // ZARA-LAB-V1-001: try the new multi-agent runtime first. Any
        // failure -- unavailable channel, success:false, thrown error --
        // falls back to the old council-room panel so Alex is never left
        // with a dead Lab. Reads only; this never submits anything.
        try {
          const v1 = await api?.labV1?.snapshot?.(labV1SessionId);
          if (v1 && v1.success !== false) {
            const normalized = normalizeLabV1(v1);
            if (normalized) {
              return { labV1: normalized, summary: 'Sala de trabalho com agentes reais. Objetivo, equipe e resultados vêm direto da sessão.' };
            }
          }
        } catch { /* falls through to the old Lab below */ }
        result = await api?.lab?.state?.();
        if (!result || result.success === false) throw new Error(result?.error || 'ZARA Lab não conectado.');
        const state = result.state ?? result;
        return {
          items: [...(state.tasks ?? []), ...(state.proposals ?? [])].map(item => ({ id: item.id, title: item.title || item.goal || 'Tarefa', content: item.summary || item.description || item.current_step || '', state: item.status })),
          labMessages: Array.isArray(state.messages) ? state.messages.slice(-60) : [],
          labActivity: Array.isArray(state.activity) ? state.activity.slice().sort((a: LabActivity, b: LabActivity) => b.created_at - a.created_at).slice(0, 12) : [],
          workers: Array.isArray(state.workers) ? state.workers : [],
          summary: 'Uma sala para trabalhar com a ZARA. Acompanhe conversas, tarefas e decisões registradas.',
        };
      }
      if (section === 'Sistema' || section === 'Dispositivos') {
        result = await api?.system?.info?.();
        if (!result || result.success === false) throw new Error(result?.error || 'Informações do sistema não conectadas.');
        const info = result.info ?? result;
        return { items: Object.entries(info).filter(([key]) => !['success', 'error'].includes(key)).map(([title, value]) => ({ title, content: typeof value === 'object' ? Object.entries(value ?? {}).map(([key, entry]) => `${key}: ${typeof entry === 'object' ? JSON.stringify(entry) : entry}`).join('\n') : String(value) })) };
      }
      return {};
    }
    load().then(result => {
      if (cancelled) return;
      setData(result);
      // Keep polling scoped to the session the backend actually reported,
      // so "no session yet" -> create -> poll keeps hitting the right one.
      if (result.labV1?.sessionId && result.labV1.sessionId !== labV1SessionId) setLabV1SessionId(result.labV1.sessionId);
    }).catch(cause => { if (!cancelled) setError(errorMessage(cause)); }).finally(() => { if (!cancelled) setLoading(false); });
    const off = ['Conversas', 'Histórico'].includes(section) ? api?.on?.message?.(() => { if (!cancelled) refresh(); }) : undefined;
    return () => { cancelled = true; off?.(); };
  }, [section, revision, labV1SessionId]);

  useEffect(() => {
    if (section !== 'ZARA Lab' || loading) return;
    const timer = setTimeout(refresh, 15000);
    return () => clearTimeout(timer);
  }, [section, loading, revision]);

  async function run(task: () => Promise<unknown> | undefined, message: string, reload = false) {
    if (op.current) return;
    op.current = true; setPending(true); setFeedback('');
    try {
      const result = await task() as { success?: boolean; error?: string; output?: string; doc?: { content?: string } } | undefined;
      if (!result || result.success === false || result.error) throw new Error(result?.error || 'Serviço indisponível.');
      setFeedback(result.doc?.content || result.output || message);
      if (reload) { setText(''); refresh(); }
    } catch (cause) { setFeedback(errorMessage(cause)); }
    finally { op.current = false; setPending(false); }
  }
  const matching = data.items?.filter(item => `${item.title ?? ''} ${item.content ?? item.fact ?? item.message ?? ''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const labV1 = data.labV1;

  return <div className="zh-drawer-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="zh-drawer" ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label={section}>
      <header className="zh-drawer-header"><h2>{section}</h2><button onClick={onClose} aria-label="Fechar painel"><X size={22} /></button></header>
      <div className="zh-drawer-body">
        <div className="zh-drawer-toolbar"><button onClick={refresh} disabled={loading}><RefreshCw size={14} /> Atualizar</button>{data.items && <input aria-label="Buscar neste painel" placeholder="Buscar…" value={query} onChange={event => setQuery(event.target.value)} />}</div>
        {loading && <p role="status">Consultando…</p>}{error && <p role="alert" className="zh-feedback">{error}</p>}
        {data.summary && <p>{data.summary}</p>}
        {section === 'Aplicativos' && <ToolsCard />}
        {section === 'ZARA Lab' && labV1 && <>
          <h3>Equipe</h3>
          <div className="zh-drawer-toolbar">{labV1.roster.map(member => <article className="zh-detail-card" key={member.id}><h3>{member.name}{member.designation === 'ACTING' && member.role === 'CEO' ? ' — Acting CEO' : ''}</h3><p>{member.role} · {member.model}</p><small>{member.designation === 'ACTING' && member.role !== 'CEO' ? `Designação: ACTING · ` : ''}{member.participation ? `Estado: ${member.participation}` : 'Estado desconhecido'}</small></article>)}{labV1.roster.length === 0 && <p className="zh-empty-state">Nenhum agente registrado nesta equipe.</p>}</div>

          <h3>Provedores</h3>
          <div className="zh-drawer-toolbar">{labV1.providers.map(provider => <article className="zh-detail-card" key={provider.id}><h3>{provider.label || provider.id}</h3><small>{provider.availability || 'DESCONHECIDO'}</small>{provider.detail && <p>{provider.detail}</p>}</article>)}{labV1.providers.length === 0 && <p className="zh-empty-state">Nenhum provedor reportado.</p>}</div>

          <h3>Objetivo</h3>
          {labV1.sessionId ? <p>{labV1.objective || 'Sem objetivo registrado.'} <small>({labV1.sessionState || 'estado desconhecido'})</small></p> : <p className="zh-empty-state">Nenhuma missão iniciada nesta sala ainda.</p>}

          <h3>Conversa</h3>
          <div className="zh-lab-log">{labV1.messages.map((message, index) => <article key={message.id || index} className="zh-conversation-message"><strong>{message.author || 'ZARA'}</strong><p>{message.content}</p>{typeof message.created_at === 'number' && <small>{formatDate(message.created_at)}</small>}</article>)}{labV1.messages.length === 0 && <p className="zh-empty-state">Nenhuma mensagem registrada nesta sessão.</p>}</div>

          <h3>Tarefas</h3>
          <div className="zh-lab-log">{labV1.tasks.map((taskItem, index) => <article key={taskItem.id || index} className="zh-detail-card"><h3>{taskItem.title}</h3><p>Responsável: {taskItem.assignee} · Estado: {taskItem.state}</p>{taskItem.result && <p>{taskItem.result}</p>}</article>)}{labV1.tasks.length === 0 && <p className="zh-empty-state">Nenhuma tarefa registrada.</p>}</div>

          {!!labV1.handoffs.length && <details><summary>Handoffs</summary><div className="zh-lab-log">{labV1.handoffs.map((handoff, index) => <article key={handoff.id || index} className="zh-detail-card"><strong>{handoff.role}</strong><p>{handoff.from} → {handoff.to}</p>{handoff.reason && <small>{handoff.reason}</small>}</article>)}</div></details>}

          <h3>Custo</h3>
          <p>{labV1.costLabel}</p>

          <form className="zh-drawer-form" onSubmit={event => {
            event.preventDefault();
            if (!text.trim()) return;
            void run(async () => {
              const result = await runDurableLabMutation(window.zaraIPC?.labV1 || {}, 'autopilot', { intent: text.trim() });
              if (!result?.success || !result.session_id) throw new Error(result?.error || 'Já existe uma missão ativa ou não há equipe disponível.');
              setLabV1SessionId(result.session_id);
              return result;
            }, 'Missão registrada. A equipe produzirá um documento verificado no sandbox.', true);
          }}>
            <label htmlFor="zh-autopilot-intent">Autopilot · documento em sandbox</label>
            <textarea id="zh-autopilot-intent" value={text} onChange={event => setText(event.target.value)}
              maxLength={12000} rows={3} placeholder="Descreva o documento que a equipe deve produzir…" required />
            <small>Seleciona a equipe, delega, grava e verifica o arquivo. Revisão do conteúdo e autoatualização ainda não certificadas.</small>
            <button disabled={pending || !text.trim()}>Iniciar Autopilot</button>
            {labV1.sessionId && ['QUEUED', 'RUNNING', 'VERIFYING', 'BLOCKED', 'CANCELLING'].includes(labV1.sessionState) &&
              <button type="button" disabled={pending} onClick={() => void run(() => runDurableLabMutation(window.zaraIPC?.labV1 || {}, 'cancel', { sessionId: labV1.sessionId! }), 'Cancelamento solicitado.')}>Cancelar missão Autopilot</button>}
          </form>

          {labV1.sessionId
            ? <form className="zh-drawer-form" onSubmit={event => { event.preventDefault(); const content = text.trim(); if (!content) return; void run(() => runDurableLabMutation(window.zaraIPC?.labV1 || {}, 'submit', { sessionId: labV1.sessionId!, text: content }), 'Mensagem na fila.', true); }}>
                <label htmlFor="zh-lab-v1-message">Enviar para a equipe</label>
                <textarea id="zh-lab-v1-message" value={text} onChange={event => setText(event.target.value)} required maxLength={12000} rows={3} placeholder="Descreva o próximo passo…" />
                <button disabled={pending || !text.trim()}>Enviar</button>
              </form>
            : <form className="zh-drawer-form" onSubmit={event => {
                event.preventDefault();
                const objective = text.trim();
                if (!objective) return;
                void run(async () => {
                  // LabV1Service.create_session returns {success, session: Session.to_dict()},
                  // never a bare session_id (core/lab_v1/service.py:72-97).
                  const created = await window.zaraIPC?.labV1?.createSession?.(objective) as { success?: boolean; session?: { id?: string }; error?: string } | undefined;
                  const sessionId = created?.session?.id;
                  if (!created?.success || !sessionId) throw new Error(created?.error || 'Não foi possível iniciar a sessão.');
                  setLabV1SessionId(sessionId);
                  return runDurableLabMutation(window.zaraIPC?.labV1 || {}, 'submit', { sessionId, text: objective });
                }, 'Mensagem na fila.', true);
              }}>
                <label htmlFor="zh-lab-v1-objective">Qual é o objetivo desta missão?</label>
                <textarea id="zh-lab-v1-objective" value={text} onChange={event => setText(event.target.value)} required maxLength={12000} rows={3} placeholder="Descreva o que a equipe deve fazer…" />
                <button disabled={pending || !text.trim()}>Começar missão</button>
              </form>}
        </>}
        {section === 'ZARA Lab' && !labV1 && <>
          <form className="zh-drawer-form" onSubmit={event => { event.preventDefault(); if (text.trim() && data.workers?.some(worker => worker.id === target && worker.can_chat)) void run(() => window.zaraIPC?.lab?.send?.({ author:'alex', target, content:text.trim() }), 'Mensagem recebida pelo Lab. A resposta aparecerá na conversa.', true); }}>
            <label htmlFor="zh-lab-target">Conversar com</label><select id="zh-lab-target" value={target} onChange={event => setTarget(event.target.value)} required disabled={Boolean(error) || pending}><option value="">Escolha um participante</option>{data.workers?.filter(worker => worker.can_chat).map(worker => <option key={worker.id} value={worker.id}>{worker.name || worker.id}</option>)}</select>
            <label htmlFor="zh-lab-message">O que vamos fazer?</label><textarea id="zh-lab-message" value={text} onChange={event => setText(event.target.value)} required maxLength={12000} rows={3} placeholder="Descreva seu objetivo ou continue uma conversa…" />
            <button disabled={pending || Boolean(error) || !text.trim() || !data.workers?.some(worker => worker.id === target && worker.can_chat)}>Enviar ao participante</button>
          </form>
          <h3>Conversa</h3><div className="zh-lab-log">{data.labMessages?.map(message => <article key={message.id} className="zh-conversation-message"><strong>{message.author} → {message.target}</strong><p>{message.content}</p><small>{formatDate(message.created_at)}</small></article>)}{data.labMessages?.length === 0 && <p className="zh-empty-state">Nenhuma mensagem registrada nesta sala.</p>}</div>
          {!!data.labActivity?.length && <details><summary>Atividade registrada</summary><div className="zh-lab-log">{data.labActivity.map(entry => <article key={entry.id} className="zh-detail-card"><strong>{entry.actor} · {entry.event}</strong><p>{entry.detail}</p><small>{formatDate(entry.created_at)}</small></article>)}</div></details>}
          <h3>Tarefas e propostas</h3>
        </>}
        {section === 'Comunicações' && <><p>Abra seus serviços. As contagens aparecerão quando houver uma integração conectada.</p><div className="zh-drawer-toolbar">{CHANNELS.map(id => <button key={id} disabled={pending} onClick={() => void run(() => window.zaraIPC?.desktop?.openExternal?.(id), 'Abertura solicitada.')}>{id === 'gmail' ? 'Gmail' : id[0].toUpperCase() + id.slice(1)}</button>)}</div></>}
        {section === 'Arquivos' && <div className="zh-drawer-toolbar">{(['home','documents','downloads','desktop'] as const).map((id, index) => <button key={id} disabled={pending} onClick={() => void run(() => window.zaraIPC?.desktop?.openFolder?.(id), 'Pasta aberta.')}>{['Pasta pessoal','Documentos','Downloads','Área de trabalho'][index]}</button>)}<button onClick={() => onNavigate('Memórias')}>Memórias</button></div>}
        {data.projects?.map(project => <article className="zh-detail-card" key={project.id}><h3>{project.id}</h3><p>{project.keys.length} documentos de contexto</p><button onClick={() => onNavigate('Memórias')}>Consultar memórias</button></article>)}
        {data.keys?.map(key => <article className="zh-detail-card" key={key}><h3>{key}</h3><button disabled={pending} onClick={() => void run(() => window.zaraIPC?.projectMemory?.get?.(key), 'Documento vazio.')}>Ler documento</button></article>)}
        {matching?.map((item, index) => <article className="zh-detail-card" key={item.id || index}><h3>{item.title || (section === 'Automações' ? item.message : 'Memória')}</h3><p>{item.content || item.fact}</p>{item.state && <small>{item.state}</small>}{item.due_at_utc && <p>{formatDate(item.due_at_utc)}</p>}</article>)}
        {matching?.length === 0 && !loading && <div className="zh-empty-state">Nenhum registro encontrado.</div>}
        {data.messages?.map((message, index) => <article className="zh-conversation-message" data-role={message.role} key={message.id || index}><strong>{message.role === 'user' ? 'Você' : 'ZARA'}</strong><p>{message.content}</p></article>)}
        {data.messages?.length === 0 && <div className="zh-empty-state">Sua conversa começa aqui.</div>}
        {['Conversas','Histórico'].includes(section) && <TextCommandInput onSent={refresh} />}
        {section === 'Memórias' && <form className="zh-drawer-form" onSubmit={event => { event.preventDefault(); if (text.trim()) void run(() => window.zaraIPC?.userMemory?.add?.({ fact: text.trim(), source:'user' }), 'Memória guardada.', true); }}><label htmlFor="zh-memory">O que você quer que a ZARA lembre?</label><textarea id="zh-memory" value={text} onChange={event => setText(event.target.value)} required maxLength={4000} /><button disabled={pending || !text.trim()}>Guardar memória</button></form>}
        {section === 'Automações' && <form className="zh-drawer-form" onSubmit={event => { event.preventDefault(); const due = new Date(date).getTime() / 1000; if (due <= Date.now()/1000) { setFeedback('Escolha um horário futuro.'); return; } void run(() => window.zaraIPC?.reminders?.create?.({ text: text.trim(), due_at: due, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }), 'Lembrete criado.', true); }}><label htmlFor="zh-reminder">Novo lembrete</label><input id="zh-reminder" value={text} onChange={event => setText(event.target.value)} required /><input aria-label="Quando lembrar" type="datetime-local" required value={date} onChange={event => setDate(event.target.value)} /><button disabled={pending || !text.trim() || !date}>Criar lembrete</button></form>}
        {section === 'Configurações' && <><div className="zh-drawer-toolbar">{data.engines?.map(engine => <button key={engine.id} disabled={pending || engine.available === false} onClick={() => void run(() => window.zaraIPC?.engine?.change?.(engine.id), `Modelo selecionado: ${engine.name || engine.id}`)}>{engine.name || engine.id}</button>)}</div><div className="zh-drawer-toolbar"><button disabled={pending} onClick={() => void run(() => window.zaraIPC?.voice?.mute?.(true), 'Saída de voz silenciada.')}>Silenciar voz</button><button disabled={pending} onClick={() => void run(() => window.zaraIPC?.voice?.mute?.(false), 'Saída de voz ativada.')}>Ativar fala</button><button disabled={pending} onClick={() => void run(() => window.zaraIPC?.voice?.status?.().then(status => ({ success:true, output: status.mode ? `Modo de voz: ${status.mode}` : status.error || 'Use o modo voz para iniciar a conversa.' })), '')}>Estado da voz</button></div></>}
        {section === 'Ajuda' && <><h3>Fale, digite ou escolha uma ação.</h3><p>Use o modo voz no centro do Dock para iniciar ou parar a conversa. Durante a fala da ZARA, o mesmo botão interrompe a resposta.</p><p>Experimente “qual o uso de memória?”, “abrir Chrome” ou “listar meus lembretes”. A Zoe pode usar o computador sem a antiga chave; o app mostra o resultado observado de cada ação.</p><p>Em Arquivos você abre suas pastas; em Memórias consulta o contexto salvo; em Histórico encontra as conversas locais.</p><button onClick={() => onNavigate('Conversas')}>Conversar com a ZARA</button></>}
        {section === 'Mais opções' && <div className="zh-drawer-toolbar">{SECTIONS.map(name => <button key={name} onClick={() => onNavigate(name)}>{name}</button>)}</div>}
        {feedback && <div className="zh-detail-card zh-feedback" role="status">{feedback}</div>}
      </div>
    </section>
  </div>;
}
