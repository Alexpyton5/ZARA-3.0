import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowUpRight, Check, ChevronRight, Circle, FileText, Plus, Search, Send, ShieldCheck, Square, Users, X, Zap } from 'lucide-react';
import { useLabRoom } from './useLabRoom';
import { useMemo } from 'react';
import { asList, avatarHue, failureText, HANDOFF_STAGES, handoffStageLabel, initials, label, requireResult, reviewVerdictLabel, timestamp, type Agent } from './labTypes';
import './lab-room.css';
import './improvement-opportunities.css';
import zaraMark from '../../../assets/zara-home/zara-mark.svg';
import { cortarKore, observarKore } from '../../lib/aecAudio';
import { runDurableLabMutation } from '../../lib/labDurableOperation';
import { ProposalEvidencePanel } from './ProposalEvidencePanel';

/** M040 — painel de propostas do Scout (leitura proativa). */
function ImprovementOpportunities({ opportunities, busy, onApprove, onReject }: {
  opportunities: Array<Record<string, unknown>> | undefined;
  busy: boolean;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const items = useMemo(() => asList(opportunities), [opportunities]);
  if (!items.length) return null;
  return (
    <section className="zl-panel zl-opportunities">
      <h3>Pesquisa proativa — melhorias encontradas</h3>
      <p className="zl-muted">O leitor trouxe estas novidades com fonte e data. Você decide se aplica.</p>
      <ul>
        {items.map((item) => {
          const id = String(item['id'] || '');
          const opportunity = String(item['opportunity'] || 'Sem título');
          const source = String(item['source'] || '');
          const published = String(item['published_at'] || item['observed_at'] || '');
          return (
            <li key={id} className="zl-opportunity">
              <strong>{opportunity}</strong>
              <a href={source} target="_blank" rel="noopener noreferrer">{source}</a>
              <small>{published}</small>
              <div className="zl-actions">
                <button type="button" disabled={busy} onClick={() => onApprove(id)}>Aprovar</button>
                <button type="button" disabled={busy} onClick={() => onReject(id)}>Rejeitar</button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

type AgentProfileVersion = { version: number; updated_at?: string; soul?: string; provider_id?: string; model?: string; permissions?: string[] };
type AgentProfile = AgentProfileVersion & { agent_id: string; history?: AgentProfileVersion[] };

/** Review messages carry JSON {verdict, notes}; plain prose still counts as the note. */
export function parseReview(content: string): { verdict: string; notes: string } {
  try {
    const value = JSON.parse(content);
    if (value && typeof value.verdict === 'string') return { verdict: value.verdict, notes: typeof value.notes === 'string' ? value.notes : '' };
  } catch { /* reviewer answered in prose */ }
  return { verdict: '', notes: normalizeConversationContent(content) };
}

/** Baton notes name their stage in JSON {stage} or plainly in the text. */
export function handoffStage(content: string): string {
  try {
    const value = JSON.parse(content);
    if (value && typeof value.stage === 'string') return value.stage.toUpperCase();
  } catch { /* plain-text baton note */ }
  const upper = content.toUpperCase();
  return HANDOFF_STAGES.find(stage => upper.includes(stage)) || '';
}

const CONVERSATION_FIELDS = ['reply_to_alex', 'answer', 'response', 'message', 'summary'] as const;

/** Convert provider envelopes into the sentence the owner should read.
 *
 * The structured envelope remains persisted for the Lab, but it must never be
 * the renderer's fallback text. Unknown objects are reduced to safe human
 * fields instead of leaking JSON or an internal protocol to the conversation.
 */
export function normalizeConversationContent(content: unknown): string {
  if (typeof content !== 'string') return humanizeConversationValue(content);
  const trimmed = content.trim();
  if (!trimmed) return '';
  try {
    return humanizeConversationValue(JSON.parse(trimmed));
  } catch {
    return content;
  }
}

function humanize_conversation_label(key: string): string {
  return {
    state: 'Estado da missão',
    error: 'Problema',
    detail: 'Detalhe',
    notes: 'Observação',
    verdict: 'Veredito',
  }[key] || key.replace(/_/g, ' ');
}

function humanizeConversationValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(humanizeConversationValue).filter(Boolean).join('\n');
  if (!value || typeof value !== 'object') return '';
  const record = value as Record<string, unknown>;
  for (const field of CONVERSATION_FIELDS) {
    if (record[field] !== undefined && record[field] !== null) {
      const text = humanizeConversationValue(record[field]);
      if (text) return text;
    }
  }
  if (record.title || record.instruction) {
    return [record.title, record.instruction].map(humanizeConversationValue).filter(Boolean).join('\n\n');
  }
  const visible = ['verdict', 'state', 'error', 'detail', 'notes']
    .filter(key => record[key] !== undefined && record[key] !== null)
    .map(key => `${humanize_conversation_label(key)}: ${humanizeConversationValue(record[key])}`)
    .filter(Boolean);
  return visible.join('\n') || 'Atualização registrada pela equipe.';
}

function Avatar({ name, id = name, small = false }: { name: string; id?: string; small?: boolean }) {
  if (name.toUpperCase() === 'ZARA') return <span className={`zl-avatar zl-zara-avatar ${small ? 'small' : ''}`}><img src={zaraMark} alt="ZARA" /></span>;
  return <span className={`zl-avatar ${small ? 'small' : ''}`} style={{ background: `hsl(${avatarHue(id)} 38% 20%)`, color: `hsl(${avatarHue(id)} 75% 78%)` }}>{initials(name)}</span>;
}

/** Every activity, message and result is a persisted backend record. */
export function LabRoom({ onClose }: { onClose: () => void }) {
  const room = useLabRoom();
  const { snapshot: data, sessionId, teamId, select, refresh } = room;
  const session = data?.session;
  const [text, setText] = useState('');
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [playing, setPlaying] = useState(false);
  useEffect(() => observarKore(setPlaying), []);
  const [tab, setTab] = useState<'operations' | 'people'>('people');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showAgent, setShowAgent] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [openPersonMenu, setOpenPersonMenu] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [agentProvider, setAgentProvider] = useState('');
  const [agentModel, setAgentModel] = useState('');
  const [agentSoul, setAgentSoul] = useState('');
  const [agentPermissions, setAgentPermissions] = useState('read_workspace, write_sandbox, run_tests');
  const [agentProfileVersion, setAgentProfileVersion] = useState(0);
  const [agentHistory, setAgentHistory] = useState<AgentProfileVersion[]>([]);
  const [rollbackVersion, setRollbackVersion] = useState('');
  const [researchTopic, setResearchTopic] = useState('Melhorias seguras para a ZARA');
  const [researchSource, setResearchSource] = useState('https://github.com/openai/codex/releases.atom');
  const [researchNotice, setResearchNotice] = useState('');
  const [ownerFeedbackAccepted, setOwnerFeedbackAccepted] = useState(false);
  const root = useRef<HTMLElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const operation = useRef(false);
  const agents = asList(data?.agents).filter(a => !a.archived);
  const members = agents.filter(a => asList(data?.memberships).some(m => m.agent_id === a.id && !m.left_at));
  const sessions = asList(data?.sessions).filter(s => s.objective.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const messages = creating ? [] : asList(session?.messages);
  const tasks = creating ? [] : asList(session?.tasks);
  const runs = creating ? [] : asList(session?.runs);
  const missionState = session?.mission?.state || session?.state;
  const rollbackProfile = agentHistory.find(item => String(item.version) === rollbackVersion);
  const missionOpen = !creating && !!session?.mission && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(missionState || '');
  const supervisorLive = data?.autonomy_policy?.background_task_state === 'RUNNING' && data?.autonomy_policy?.last_state !== 'FAILED';
  const running = missionOpen && ['QUEUED', 'PLANNING', 'RUNNING', 'WORKING', 'VERIFYING', 'REPAIRING', 'CANCELLING'].includes(missionState || '');
  const missionLabel = !data ? (room.error ? 'Conexão indisponível' : 'Conectando à equipe…') : creating ? 'Nova missão' : room.error ? 'Conexão indisponível' : missionState === 'WAITING_RESOURCE' ? 'Aguardando recurso' : missionState === 'BLOCKED_NEEDS_OWNER' ? 'Aguardando o owner' : running && supervisorLive ? `Missão ${label(missionState).toLowerCase()}` : running ? 'Continuidade parada' : 'Pronta para novo objetivo';
  const nameOf = (id?: string | null) => agents.find(a => a.id === id)?.name || 'ZARA';
  const pipeline = data?.research_scheduler?.pipeline;
  const residentHealth = data?.resident_health;
  const factualCapabilities = [
    { label: 'Supervisor', ready: residentHealth?.resident === true, detail: !data ? 'conectando' : residentHealth?.resident ? 'ativo' : 'parado' },
    { label: 'Memória', ready: data?.central_memory?.available === true && !data?.central_memory?.degraded, detail: data?.central_memory?.degraded ? 'degradada' : data?.central_memory?.available ? 'conectada' : 'não verificada' },
    { label: 'Pesquisa', ready: residentHealth?.research_scheduler === 'READY', detail: !data ? 'consultando' : residentHealth?.research_scheduler === 'READY' ? 'pronta' : 'bloqueada' },
  ];

  function pipelineAction(payload: Record<string, unknown>, message: string) {
    void perform(async () => {
      requireResult(await window.zaraIPC?.labV1?.researchSkill?.(payload as any));
      setResearchNotice(message);
    });
  }

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    root.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { if (showAgent) setShowAgent(false); else onClose(); }
      if (event.key !== 'Tab') return;
      const nodes = Array.from(root.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary,[tabindex="0"]') || []);
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === root.current)) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, [onClose, showAgent]);
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' }); }, [messages.length, sessionId]);
  useEffect(() => {
    if (running && supervisorLive) setOwnerFeedbackAccepted(false);
  }, [running, supervisorLive]);

  async function perform(action: () => Promise<void>) {
    if (operation.current) return;
    operation.current = true; setBusy(true); setError('');
    try { await action(); await refresh(); } catch (cause) { setError(failureText(cause)); }
    finally { operation.current = false; setBusy(false); }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const intent = text.trim();
    if (!intent) return;
    void perform(async () => {
      const api = window.zaraIPC?.labV1;
      const targetSessionId = creating ? '' : sessionId;
      const result = requireResult(await runDurableLabMutation(api || {}, 'roomMessage', {
        sessionId: targetSessionId, text: intent,
      }));
      if (result.code === 'OWNER_INPUT_ACCEPTED') setOwnerFeedbackAccepted(true);
      if (!result.session_id) throw new Error('O backend não registrou a conversa.');
      if (result.session_id !== sessionId || creating) select(result.session_id);
      setCreating(false);
      setText('');
    });
  }
  function researchNow() {
    void perform(async () => {
      setResearchNotice('Pesquisando fontes oficiais…');
      const result = requireResult(await window.zaraIPC?.labV1?.researchSkill?.({
        operation: 'research', topic: researchTopic,
        sources: researchSource.split(/\s*,\s*|\n/).filter(Boolean).slice(0, 8),
      }));
      const found = (result as { result?: { findings?: unknown[]; failures?: unknown[] } }).result;
      setResearchNotice(`Pesquisa registrada: ${found?.findings?.length || 0} evidência(s), ${found?.failures?.length || 0} falha(s).`);
    });
  }
  function person(agent: Agent) {
    const health = data?.health?.[`model:${agent.provider_id}:${agent.model}`];
    const provider = asList(data?.providers).find(p => p.id === agent.provider_id);
    const state = provider?.availability !== 'AVAILABLE' ? provider?.availability : health?.availability || 'UNKNOWN';
    const working = data?.participation?.[agent.id] === 'WORKING';
    const role = asList(data?.role_bindings).find(b => b.agent_id === agent.id && b.active !== false && !b.unbound_at)?.role || agent.role;
    const openConfiguration = () => {
      setEditingAgent(agent); setAgentProvider(agent.provider_id); setAgentModel(agent.model);
      setAgentSoul(''); setAgentPermissions('read_workspace, write_sandbox, run_tests');
      setAgentProfileVersion(0); setAgentHistory([]); setRollbackVersion('');
      void perform(async () => {
        const result = requireResult(await window.zaraIPC?.labV1?.agentProfile?.(agent.id)) as { profile?: AgentProfile };
        const profile = result.profile;
        if (!profile) return;
        setAgentSoul(profile.soul || '');
        setAgentProvider(profile.provider_id || agent.provider_id);
        setAgentModel(profile.model || agent.model);
        setAgentPermissions((profile.permissions || []).join(', '));
        setAgentProfileVersion(profile.version || 0);
        setAgentHistory(profile.history || []);
      });
    };
    const closeMenu = () => setOpenPersonMenu(current => current === agent.id ? null : current);
    return <article className="zl-person zl-person--interactive" key={agent.id} onClick={openConfiguration} onKeyDown={event => { if (event.target !== event.currentTarget) return; if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openConfiguration(); } }} role="button" tabIndex={0} aria-label={'Configurar participante ' + agent.name}>
      <Avatar name={agent.name} id={agent.id} small /><div><strong>{agent.name} <em>{label(role)}</em></strong><small>{agent.model}</small><span className={state === 'AVAILABLE' ? 'zl-good' : 'zl-muted'}>{working ? 'Trabalhando nesta sala' : label(state)}</span></div>
      <details className="zl-person-menu" open={openPersonMenu === agent.id} onClick={event => event.stopPropagation()} onToggle={event => setOpenPersonMenu(event.currentTarget.open ? agent.id : current => current === agent.id ? null : current)}><summary aria-label={`Gerenciar ${agent.name}`}>···</summary><div>
        <button disabled={busy || !teamId} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.rebindRole?.({ team_id: teamId, role: 'CEO', agent_id: agent.id, reason: 'Alex alterou a liderança na sala' })); closeMenu(); })}>Definir como líder</button>
        <button disabled={busy} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.archiveAgent?.(agent.id)); closeMenu(); })}>Arquivar participante</button>
      </div></details>
    </article>;
  }

  return <section className={`zl-room ${inspectorOpen ? 'inspector-open' : ''}`} role="dialog" aria-modal="true" aria-label="ZARA Lab" tabIndex={-1} ref={root}>
    <aside className="zl-sidebar">
      <header className="zl-brand"><button aria-label="Voltar para início" onClick={onClose}><ArrowLeft size={19} /></button><img className="zl-mark" src={zaraMark} alt="ZARA" /><div><strong>ZARA <b>LAB</b></strong><small>Sua equipe de inteligência</small></div></header>
      <div className="zl-sidebar-title"><h2>Conversas</h2><button aria-label="Nova missão" onClick={() => { setCreating(true); setText(''); }}><Plus size={20} /></button></div>
      <label className="zl-search"><Search size={16} /><input placeholder="Buscar uma missão" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label className="zl-team-select"><Users size={15} /><select aria-label="Selecionar equipe" value={teamId || data?.team?.id || ''} onChange={e => { select('', e.target.value); setCreating(false); }}><option value="">Todas as equipes disponíveis</option>{asList(data?.teams).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
      <nav className="zl-conversations" aria-label="Missões">
        {sessions.map(s => <div className={`zl-conversation-row ${!creating && s.id === sessionId ? 'selected' : ''}`} key={s.id}><button className="zl-conversation" onClick={() => { select(s.id, s.team_id); setCreating(false); setText(''); }}><Avatar name={s.objective} id={s.id} /><span><strong>{s.objective}</strong><small><Circle size={7} fill="currentColor" /> {label(s.state)}</small></span><time>{timestamp(s.updated_at)}</time></button><button className="zl-delete-conversation" aria-label={`Excluir ${s.objective}`} title="Excluir conversa" onClick={() => void perform(async () => { if (!window.confirm('Excluir esta conversa?')) return; requireResult(await window.zaraIPC?.labV1?.deleteSession?.(s.id)); if (s.id === sessionId) select('', s.team_id); })}>×</button></div>)}
        {!sessions.length && <div className="zl-empty-small">As missões da equipe aparecerão aqui.</div>}
      </nav>
      <footer className="zl-owner"><Avatar name="Alex" small /><div><strong>Alex</strong><small>Você define o objetivo</small></div><ShieldCheck size={18} /></footer>
    </aside>

    <main className="zl-conversation-main">
      <header className="zl-chat-header"><Avatar name="ZARA" id="zara" /><div><h1>{creating ? 'Nova missão' : data?.team?.name || 'ZARA Lab'}</h1><p>{members.length ? `${members.length} agentes · ZARA regente` : 'Aguardando equipe comprovada'} <span>·</span> <span className="zl-good">{missionLabel}</span> <span>·</span> <span className={data?.central_memory?.degraded ? 'zl-muted' : 'zl-good'} title="Status da memória central">Memória {data?.central_memory?.degraded ? 'degradada' : data?.central_memory?.available ? 'conectada' : 'não verificada'}</span></p><div className="zl-capability-row" aria-label="Estado factual do ZARA Lab">{factualCapabilities.map(capability => <span key={capability.label} className={capability.ready ? 'zl-capability is-on' : 'zl-capability'}>● {capability.label} {capability.detail}</span>)}</div></div><button onClick={() => { setTab('people'); setInspectorOpen(v => !v); }} aria-label="Ver participantes"><Users size={20} /></button><button onClick={onClose} aria-label="Fechar ZARA Lab"><X size={20} /></button></header>
      {!creating && session && <div className="zl-mission-strip"><Zap size={15} /><span>{session.objective}</span>
        {(session.state === 'VERIFYING' || session.state === 'REPAIRING' || missionState === 'VERIFYING' || missionState === 'REPAIRING') && <i className="zl-chip zl-chip--success">{missionState === 'REPAIRING' || session.state === 'REPAIRING' ? 'Corrigindo com o executor' : 'Verificando o resultado'}</i>}
        <b>{label(missionState)}</b></div>}
      <section className="zl-research-panel" aria-label="Pesquisa autônoma e chat estruturado">
        <div><strong>Lab Autopilot · Pesquisa</strong><small>Pesquisadores registram evidências; CEO aprova a ativação.</small></div>
        <input value={researchTopic} onChange={e => setResearchTopic(e.target.value)} placeholder="Tema da pesquisa" aria-label="Tema da pesquisa" />
        <input value={researchSource} onChange={e => setResearchSource(e.target.value)} placeholder="URL oficial" aria-label="Fontes oficiais" />
        <button disabled={busy || !researchTopic.trim() || !researchSource.trim()} onClick={researchNow}>Pesquisar agora</button>
        {researchNotice && <span className="zl-muted">{researchNotice}</span>}
      </section>
      <div className="zl-messages" ref={log} role="log" aria-label="Conversa da equipe" aria-live="polite">
        {!data && <p className="zl-status-note" role="status">{room.error ? 'A conexão com a equipe falhou. Seu texto foi preservado.' : 'Carregando a equipe e as conversas…'}</p>}
        {data && !messages.length && <div className="zl-welcome"><span className="zl-welcome-orb"><img src={zaraMark} alt="ZARA" /></span><span className="zl-eyebrow">ZARA + SUA EQUIPE</span><h2>Uma ideia sua.<br />Um objetivo para todos.</h2><p>Uma intenção. Sua equipe cuida do contexto, divide o trabalho e devolve um resultado com evidências.</p><button onClick={() => { setCreating(true); setText('Crie um briefing curto para melhorar a experiência do ZARA Lab.'); }}>Começar com um briefing <ArrowUpRight size={16} /></button></div>}
        {messages.map(message => {
          const mine = message.kind === 'USER';
          const system = message.kind === 'ZARA';
          const author = agents.find(a => a.id === message.author_agent_id);
          const factualRun = runs.find(run => run.id === message.run_id);
          const content = normalizeConversationContent(message.content);
          if (message.kind === 'DELEGATE') {
            const target = message.to_agent_id ? nameOf(message.to_agent_id) : label(message.to_role);
            return <article className="zl-message delegation" key={message.id}>
              {!mine && <Avatar name={message.author} id={message.author_agent_id || message.author} small />}
              <div className="zl-bubble">
                <strong>Delegação · {message.author} → {target}</strong>
                {author && <span className="zl-author-role">{label(author.role)}{factualRun && <> · {factualRun.provider_id === 'codex_cli' ? 'OpenAI / Codex' : factualRun.provider_id} · {factualRun.model_reported || factualRun.model}{factualRun.model_reported && factualRun.model_reported !== factualRun.model && ` (solicitado: ${factualRun.model})`}</>}</span>}
                <p>{content}</p>
                <footer><span>Maestro → {label(message.to_role) || 'Executor'}</span><time>{timestamp(message.created_at)}</time></footer>
              </div>
            </article>;
          }
          if (message.kind === 'REVIEW') {
            const review = parseReview(message.content);
            const escalated = message.to_role === 'OWNER';
            const exhausted = escalated || review.verdict === 'REVIEW_LOOP_EXHAUSTED';
            const approved = review.verdict === 'APPROVED' && !exhausted;
            return <article className="zl-message review" key={message.id}>
              <Avatar name={message.author} id={message.author_agent_id || message.author} small />
              <div className="zl-bubble">
                <strong>Revisão · {message.author}
                  <span className={`zl-chip ${approved ? 'zl-chip--success' : 'zl-chip--warning'}`}>
                    {exhausted ? reviewVerdictLabel('REVIEW_LOOP_EXHAUSTED') : reviewVerdictLabel(review.verdict) || 'Veredito'}
                  </span></strong>
                {review.notes && <p>{review.notes}</p>}
                {exhausted && <p className="zl-review-alert">Rodadas de revisão esgotadas; a decisão final fica com o CEO.</p>}
                <footer><time>{timestamp(message.created_at)}</time></footer>
              </div>
            </article>;
          }
          if (message.kind === 'HANDOFF') {
            const stage = handoffStage(message.content);
            return <article className="zl-message handoff" key={message.id}>
              <div className="zl-bubble" role="note" aria-label="Bastão da equipe">
                <strong>Bastão · {handoffStageLabel(stage) || 'Transição de estágio'}</strong>
                <p className="zl-handoff-track">
                  {HANDOFF_STAGES.map((step, index) => <span className="zl-handoff-step" key={step}>
                    {index > 0 && <span className="zl-handoff-arrow">→</span>}
                    <span className={`zl-chip zl-chip--neutral zl-handoff-stage ${step === stage ? 'is-active' : ''}`}>{handoffStageLabel(step)}</span>
                  </span>)}
                </p>
                <footer><time>{timestamp(message.created_at)}</time></footer>
              </div>
            </article>;
          }
          return <article className={`zl-message ${mine ? 'mine' : ''} ${system ? 'system' : ''}`} key={message.id}>
          {!mine && <Avatar name={message.author} id={message.author_agent_id || message.author} small />}
          <div className="zl-bubble"><strong>{mine ? 'Você' : message.author}{system && <ShieldCheck size={12} />}</strong>{author && <span className="zl-author-role">{label(author.role)}{factualRun && <> · {factualRun.provider_id === 'codex_cli' ? 'OpenAI / Codex' : factualRun.provider_id} · {factualRun.model_reported || factualRun.model}{factualRun.model_reported && factualRun.model_reported !== factualRun.model && ` (solicitado: ${factualRun.model})`}</>}</span>}<p>{content}</p><footer>{message.run_id && <span>Resposta registrada</span>}<time>{timestamp(message.created_at)}</time>{mine && <Check size={13} />}</footer></div>
        </article>; })}
        {running && supervisorLive && <div className="zl-working"><span /><span /><span /><small>{runs.find(r => r.state === 'STARTED') ? `${nameOf(runs.find(r => r.state === 'STARTED')?.agent_id)} está trabalhando` : `Supervisor ativo · ${label(data?.autonomy_policy?.last_state)}`}</small></div>}
      </div>
      {ownerFeedbackAccepted && !running && !supervisorLive && <div className="zl-status-note" role="status">Orientação registrada. O executor não está ativo agora; a missão aguarda retomada.</div>}
      {busy && <div className="zl-status-note" role="status">Enviando ao Lab… aguardando confirmação.</div>}
      {(error || room.error) && <div className="zl-error" role="alert">{error || room.error}</div>}
      <form className="zl-composer" onSubmit={submit}>
        <div className="zl-composer-mode"><span className="zl-composer-regent"><ShieldCheck size={13} /> ZARA coordena · você define o objetivo</span>{playing && <button className="zl-interrupt-speech" type="button" onClick={() => { cortarKore(); void window.zaraIPC?.message?.interrupt?.(); }}>Interromper fala</button>}</div>
        <div className="zl-input-row"><textarea aria-label="Mensagem para a equipe" value={text} onChange={e => setText(e.target.value)} maxLength={12000} rows={2} placeholder={missionOpen ? 'Envie uma atualização ou fale com @participante…' : 'Converse com a equipe, use @nome ou peça uma melhoria…'} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy && text.trim()) e.currentTarget.form?.requestSubmit(); } }} /><button type="submit" className="zl-send" disabled={busy || !text.trim()} aria-label="Enviar mensagem"><Send size={19} /></button></div>
        <small className="zl-composer-note">{missionOpen ? 'Sua mensagem atualiza esta missão no próximo ponto seguro.' : 'Enter para enviar · Shift + Enter para nova linha'}</small>
      </form>
    </main>

    <aside className="zl-inspector"><header><button className="zl-inspector-close" aria-label="Fechar painel" onClick={() => setInspectorOpen(false)}><X size={17} /></button><div className="zl-inspector-tabs" role="tablist" aria-label="Painel da sala"><button role="tab" aria-selected={tab === 'operations'} className={tab === 'operations' ? 'active' : ''} onClick={() => setTab('operations')}>Operações</button><button role="tab" aria-selected={tab === 'people'} className={tab === 'people' ? 'active' : ''} onClick={() => setTab('people')}>Participantes</button></div></header>
      <div className="zl-inspector-body">{tab === 'operations' ? <>
        <div className="zl-regent"><ShieldCheck size={22} /><div><strong>{running ? 'ZARA está coordenando' : 'Estado factual da missão'}</strong><p>Coordenação, continuidade e evidências persistidas.</p></div></div>
        <div className="zl-autonomy"><h3>Continuidade</h3><p>{!data ? 'Conectando ao supervisor…' : supervisorLive ? `Supervisor ativo · ${label(data?.autonomy_policy?.last_state)}` : `Supervisor ${label(data?.autonomy_policy?.background_task_state || 'STOPPED').toLowerCase()}`}</p>{data?.autonomy_policy?.background_error && <p className="zl-error">{data.autonomy_policy.background_error}</p>}<h3>Melhoria contínua</h3><p>{data?.autonomy_policy?.enabled && supervisorLive ? 'Ciclos seguros ativos' : data?.autonomy_policy?.enabled ? 'Ciclos configurados; supervisor parado' : 'Novos ciclos pausados'}</p><button disabled={busy || !data?.autonomy_policy} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.configureAutonomy?.(!data?.autonomy_policy?.enabled)); })}>{data?.autonomy_policy?.enabled ? 'Pausar novos ciclos' : 'Ativar ciclos automáticos'}</button></div>
        <div className="zl-section-heading"><h3>Plano de trabalho</h3><span>{tasks.filter(t => t.state === 'COMPLETED').length}/{tasks.length}</span></div>
        {tasks.map((task, index) => <details className="zl-task" key={task.id}><summary><span className={task.state === 'COMPLETED' ? 'done' : ''}>{task.state === 'COMPLETED' ? <Check size={13} /> : index + 1}</span><div><strong>{task.title}</strong><small>{nameOf(task.assigned_agent_id)} · {label(task.state)}</small></div><ChevronRight size={14} /></summary><p>{normalizeConversationContent(task.instruction)}</p>{task.result && <pre>{normalizeConversationContent(task.result)}</pre>}</details>)}
        {!tasks.length && <p className="zl-empty-small">O plano aparece quando a equipe inicia uma missão.</p>}
        <h3>Entregas</h3>{(!creating ? asList(session?.artifacts) : []).map(artifact => <details className="zl-artifact" key={artifact.id}><summary><FileText size={17} /><div><strong>{artifact.title}</strong><small>{artifact.kind || 'Artefato'} · {timestamp(artifact.created_at)}</small></div></summary>{artifact.path && <p>{artifact.path}</p>}<pre>{normalizeConversationContent(artifact.body)}</pre></details>)}
        <ProposalEvidencePanel session={session} onRefresh={refresh} />
        <h3>Governança de Skills</h3>
        <div className="zl-skill-governance"><p>{pipeline?.candidates?.length || 0} candidato(s) · {pipeline?.active?.length || 0} ativo(s)</p>
          {(pipeline?.candidates || []).map(candidate => { const tested = (candidate.tests || []).some(test => test.passed === true); return <article key={`${candidate.skill_id}:${candidate.version}`} className="zl-skill-card"><strong>{candidate.skill_id} <span className="zl-chip zl-chip--neutral">v{candidate.version}</span></strong><small>{candidate.description || 'Candidato gerado pelo Lab'} · {tested ? 'teste aprovado' : 'aguarda teste aprovado'}</small><div><button disabled={busy || !tested} onClick={() => pipelineAction({ operation: 'activate', skill_id: candidate.skill_id, version: candidate.version, owner_approved: true }, 'Skill aprovada pelo CEO e ativada.')}>Aprovar e ativar</button><button disabled={busy || !tested} onClick={() => pipelineAction({ operation: 'rollback', skill_id: candidate.skill_id }, 'Rollback solicitado.')}>Rollback</button></div></article>; })}
          {!pipeline?.candidates?.length && <p className="zl-empty-small">Pesquisas ainda não geraram candidatos.</p>}
        </div>
        <h3>Execuções reais</h3>{runs.map(run => <details className="zl-run" key={run.id}><summary><strong>{nameOf(run.agent_id)}</strong><span>{label(run.state)}</span></summary><dl><dt>Provedor</dt><dd>{run.provider_id}</dd><dt>Solicitado</dt><dd>{run.model}</dd><dt>Reportado</dt><dd>{run.model_reported || 'Não informado pelo provedor'}</dd><dt>Tokens</dt><dd>{run.input_tokens ?? '—'} entrada · {run.output_tokens ?? '—'} saída</dd><dt>Tempo</dt><dd>{run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'}</dd><dt>Custo</dt><dd>{run.cost_usd != null ? `US$ ${run.cost_usd.toFixed(4)}` : 'Não informado'}</dd></dl>{run.error && <p className="zl-error">{run.error}</p>}</details>)}
        {session?.autonomy && !creating && <div className="zl-autonomy"><h3>Autonomia desta missão</h3><p>{session.autonomy.owner_touches} comando inicial</p><p>Resultado: {session.autonomy.content_review === 'NOT_CERTIFIED' ? 'Arquivo verificado; conteúdo sem revisão independente' : session.autonomy.content_review}</p>{session.autonomy.gaps?.map((gap, i) => <p key={i}>{gap.reason}</p>)}</div>}
        {missionOpen && <button className="zl-cancel" disabled={busy} onClick={() => void perform(async () => { requireResult(await runDurableLabMutation(window.zaraIPC?.labV1 || {}, 'cancel', { sessionId })); })}><Square size={13} /> Cancelar missão</button>}
      </> : <>
        <div className="zl-section-heading"><h3>Equipe desta sala</h3><button aria-label="Adicionar participante" onClick={() => setShowAgent(true)}><Plus size={17} /></button></div>
        <article className="zl-person"><Avatar name="ZARA" small /><div><strong>ZARA <em>Regente</em></strong><small>Coordenação do sistema</small><span className="zl-good">{data?.regent?.state || 'Conectando'}</span></div></article>
        {members.map(person)}
        {agents.some(a => !members.includes(a)) && <><h3>Outros participantes</h3>{agents.filter(a => !members.includes(a)).map(person)}</>}
        <h3>Células de trabalho</h3>{asList(data?.workcells).map(cell => <article className="zl-person" key={cell.id}><Avatar name={cell.name} small /><div><strong>{cell.name}</strong><small>{cell.detail}</small><span className="zl-muted">{label(cell.availability)}</span></div></article>)}
        <h3>Conexões</h3>{asList(data?.providers).map(provider => <details className="zl-provider" key={provider.id}><summary><strong>{provider.label || provider.id}</strong><span className={provider.availability === 'AVAILABLE' ? 'zl-good' : 'zl-muted'}>{label(provider.availability)}</span></summary><p>{provider.detail}</p></details>)}
      </>}</div>
      <footer className="zl-sync"><span className={room.error ? 'warn' : ''} />{room.loading ? 'Conectando ao Lab…' : `Sincronizado ${room.lastSynced ? new Date(room.lastSynced).toLocaleTimeString('pt-BR') : '—'}`}</footer>
      <ImprovementOpportunities
        opportunities={data?.improvement_opportunities}
        busy={busy}
        onApprove={(id) => void perform(async () => {
          requireResult(await window.zaraIPC?.labV1?.proposalFeedUpdate?.(id, 'ACCEPTED' as any));
        })}
        onReject={(id) => void perform(async () => {
          requireResult(await window.zaraIPC?.labV1?.proposalFeedUpdate?.(id, 'REJECTED_BY_TEAM' as any));
        })}
      />
    </aside>
    {showAgent && <div className="zl-modal"><form onSubmit={event => { event.preventDefault(); void perform(async () => { requireResult(await window.zaraIPC?.labV1?.createAgent?.({ name: agentName.trim(), provider_id: agentProvider, model: agentModel, team_id: teamId || undefined })); setShowAgent(false); setAgentName(''); }); }}><header><h2>Adicionar participante</h2><button type="button" aria-label="Fechar cadastro" onClick={() => setShowAgent(false)}><X size={19} /></button></header><label>Nome<input required maxLength={80} value={agentName} onChange={e => setAgentName(e.target.value)} /></label><label>Provedor<select required value={agentProvider} onChange={e => { setAgentProvider(e.target.value); setAgentModel(''); }}><option value="">Selecione</option>{asList(data?.providers).map(p => <option value={p.id} key={p.id}>{p.label}</option>)}</select></label><label>Modelo<select required value={agentModel} onChange={e => setAgentModel(e.target.value)}><option value="">Selecione um modelo do catálogo</option>{asList(data?.models).filter(m => m.provider_id === agentProvider).map(m => <option value={m.model_id} key={m.model_id}>{m.display_name || m.model_id}</option>)}</select></label><p>A disponibilidade depende da autenticação e das respostas reais do provedor.</p><button className="zl-primary" disabled={busy || !agentName.trim() || !agentModel}>Adicionar à equipe</button></form></div>}
    {editingAgent && <div className="zl-modal"><form onSubmit={event => { event.preventDefault(); void perform(async () => {
      const permissions = agentPermissions.split(/[,\n]/).map(value => value.trim()).filter(Boolean);
      requireResult(await window.zaraIPC?.labV1?.updateAgentProfile?.({ agent_id: editingAgent.id, soul: agentSoul, provider_id: agentProvider, model: agentModel, permissions }));
      setEditingAgent(null);
    }); }}><header><h2>Configurar {editingAgent.name}</h2><button type="button" aria-label="Fechar configuração" onClick={() => setEditingAgent(null)}><X size={19} /></button></header>
      <label>Provedor<select required value={agentProvider} onChange={e => { setAgentProvider(e.target.value); setAgentModel(''); }}><option value="">Selecione</option>{asList(data?.providers).map(p => <option value={p.id} key={p.id}>{p.label}</option>)}</select></label>
      <label>Modelo<select required value={agentModel} onChange={e => setAgentModel(e.target.value)}><option value="">Selecione um modelo do catálogo</option>{asList(data?.models).filter(m => m.provider_id === agentProvider).map(m => <option value={m.model_id} key={m.model_id}>{m.display_name || m.model_id}</option>)}</select></label>
      <label>Soul.md<textarea rows={9} maxLength={24000} value={agentSoul} onChange={e => setAgentSoul(e.target.value)} placeholder="Missão, prioridades e forma de trabalhar deste agente" /></label>
      <label>Permissões<textarea rows={3} value={agentPermissions} onChange={e => setAgentPermissions(e.target.value)} placeholder="read_workspace, write_sandbox, run_tests" /></label>
      <p>Versão atual: {agentProfileVersion || 'perfil inicial'}. A mudança vale no próximo turno real do agente.</p>
      {!!agentHistory.length && <div><label>Restaurar versão<select value={rollbackVersion} onChange={e => setRollbackVersion(e.target.value)}><option value="">Escolha uma versão</option>{agentHistory.map(item => <option key={item.version} value={item.version}>v{item.version} · {item.model || 'modelo padrão'} · {item.updated_at || 'sem data'}</option>)}</select></label>{rollbackProfile && <details><summary>Ver diferenças</summary><pre>{`MODELO\nversão escolhida: ${rollbackProfile.provider_id || 'padrão'} / ${rollbackProfile.model || 'padrão'}\natual: ${agentProvider || 'padrão'} / ${agentModel || 'padrão'}\n\nPERMISSÕES\nversão escolhida: ${(rollbackProfile.permissions || []).join(', ') || 'nenhuma'}\natual: ${agentPermissions || 'nenhuma'}\n\nSOUL.MD DA VERSÃO ESCOLHIDA\n${rollbackProfile.soul || '(vazio)'}\n\nSOUL.MD ATUAL\n${agentSoul || '(vazio)'}`}</pre></details>}<button type="button" disabled={busy || !rollbackVersion} onClick={() => void perform(async () => { const result = requireResult(await window.zaraIPC?.labV1?.rollbackAgentProfile?.(editingAgent.id, Number(rollbackVersion))) as { profile?: AgentProfile }; const profile = result.profile; if (profile) { setAgentSoul(profile.soul || ''); setAgentProvider(profile.provider_id || agentProvider); setAgentModel(profile.model || agentModel); setAgentPermissions((profile.permissions || []).join(', ')); setAgentProfileVersion(profile.version || 0); setAgentHistory(profile.history || []); setRollbackVersion(''); } })}>Restaurar</button></div>}
      <button className="zl-primary" disabled={busy || !agentModel}>Salvar configuração</button>
    </form></div>}
  </section>;
}
