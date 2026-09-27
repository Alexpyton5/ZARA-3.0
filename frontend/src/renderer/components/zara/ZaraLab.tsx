import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, BadgeCheck, BrainCircuit, Check, ChevronRight, CircleDot,
  Clock3, Code2, FlaskConical, GitBranch, LoaderCircle, MessageSquareText,
  RefreshCw, Send, ShieldCheck, Sparkles, UserRound, Wrench, X
} from 'lucide-react';

type Worker = {
  id: string;
  name: string;
  role: string;
  state: string;
  detail: string;
  executable?: string | null;
  can_chat: boolean;
  can_execute: boolean;
};

type LabMessage = {
  id: string;
  author: string;
  target: string;
  content: string;
  kind: string;
  created_at: number;
};

type Proposal = {
  id: string;
  title: string;
  summary: string;
  status: string;
  risk: string;
  owner: string;
  cost: string;
  approved_by?: string | null;
  updated_at: number;
};

type LabTask = {
  id: string;
  proposal_id?: string | null;
  title: string;
  owner: string;
  status: string;
  progress?: number | null;
  current_step: string;
  assigned_worker?: string | null;
  attempts?: number;
  max_attempts?: number;
  checkpoint_saved?: boolean;
  checkpoint_at?: number | null;
  last_error?: string | null;
  needs_alex?: boolean;
  updated_at: number;
};

type AutonomyState = {
  status: string;
  persistent: boolean;
  execution_enabled: boolean;
  total_tasks: number;
  counts: Record<string, number>;
  online_workers: number;
};

type ActivityEntry = {
  id: number;
  actor: string;
  event: string;
  detail: string;
  created_at: number;
};

type MentorRelayState = {
  state: string;
  detail: string;
  online: boolean;
  updated_at?: number | null;
  age_seconds?: number | null;
  pending: number;
};

type MissionMilestone = {
  code: string;
  title: string;
  description: string;
  state: 'done' | 'partial' | 'pending';
  evidence: string[];
  updated_at: number;
};

type MissionFeedEntry = {
  id: number;
  actor: string;
  event: string;
  detail: string;
  created_at: number;
};

type MissionSnapshot = {
  mission_id: string;
  room?: { name: string } | null;
  milestones: MissionMilestone[];
  feed: MissionFeedEntry[];
  active_cycle?: { id: string; objective: string; status: string } | null;
  autonomy?: {
    enabled: boolean;
    running: boolean;
    phase: string;
    cycle_id?: string | null;
    last_summary?: string;
  };
  status?: string;
};

type LabState = {
  version: string;
  execution_runtime: string;
  approval_gate: boolean;
  workers: Worker[];
  messages: LabMessage[];
  proposals: Proposal[];
  tasks: LabTask[];
  activity: ActivityEntry[];
  autonomy?: AutonomyState;
  mentor_relay?: MentorRelayState;
  mission?: MissionSnapshot;
};

const emptyState: LabState = {
  version: 'LAB-AUTONOMY-001', execution_runtime: 'AUTONOMY ONLINE • WORKER EXECUTION LOCKED', approval_gate: true,
  workers: [], messages: [], proposals: [], tasks: [], activity: [],
  autonomy: { status: 'STARTING', persistent: true, execution_enabled: false, total_tasks: 0, counts: {}, online_workers: 0 },
  mentor_relay: { state: 'EXTERNAL', detail: 'Relay ainda não conectado.', online: false, pending: 0 },
};

const participantIcon = (id: string) => {
  if (id === 'alex') return UserRound;
  if (id === 'zara') return Sparkles;
  if (id === 'mentor') return BrainCircuit;
  if (id === 'hermes') return Wrench;
  if (id === 'opencode') return Code2;
  if (id === 'openclaw') return BrainCircuit;
  if (id === 'cline') return ShieldCheck;
  return GitBranch;
};

const readableTime = (epoch: number) => new Date(epoch * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const stateClass = (state: string) => state.toLowerCase().replace(/[^a-z]+/g, '-');

const milestoneIcon = (state: string) => {
  if (state === 'done') return Check;
  if (state === 'partial') return Clock3;
  return CircleDot;
};

const MissionBoard: React.FC<{ mission?: MissionSnapshot; onRefresh: () => void }> = ({ mission, onRefresh }) => {
  const [verifying, setVerifying] = useState<string | null>(null);
  const [evidence, setEvidence] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!mission || mission.status === 'ERROR') {
    return (
      <section className="lab-panel lab-mission">
        <header className="lab-panel-header"><div><FlaskConical size={15}/><span>LIVING TEAM MISSION</span></div><em>OFFLINE</em></header>
        <div className="lab-empty small">Missão indisponível no backend.</div>
      </section>
    );
  }

  const confirmVerify = async (code: string) => {    const ref = evidence.trim();
    if (!ref || busy) return;
    setBusy(true);
    setError('');
    try {
      await window.zaraIPC?.lab?.missionVerify?.({ code, state: 'done', evidence: [ref] });
      setVerifying(null);
      setEvidence('');
      onRefresh();
    } catch {
      setError('Falha ao verificar o marco. Evidência é obrigatória.');
    } finally {
      setBusy(false);
    }
  };

  const feed = (mission.feed || []).slice(-12);

  const autonomy = mission.autonomy;
  const autoOn = !!autonomy?.enabled;
  const autoRunning = !!autonomy?.running;

  const toggleAutonomy = async () => {
    try {
      if (autoOn) {
        await window.zaraIPC?.lab?.autonomyStop?.();
      } else {
        await window.zaraIPC?.lab?.autonomyStart?.();
      }
      onRefresh();
    } catch {
      /* painel segue mostrando o último estado conhecido */
    }
  };

  return (
    <section className="lab-panel lab-mission">
      <header className="lab-panel-header">
        <div><FlaskConical size={15}/><span>LIVING TEAM MISSION</span></div>
        <button
          className={autoOn ? 'approve' : 'reject'}
          onClick={() => void toggleAutonomy()}
          title="O conselho trabalha sozinho: lê o código, debate e propõe"
        >
          {autoRunning ? <LoaderCircle className="spin" size={13}/> : <Sparkles size={13}/>}
          {autoOn ? 'AUTÔNOMO ON' : 'AUTÔNOMO OFF'}
        </button>
        <em>{mission.mission_id}</em>
      </header>
      {autoRunning && autonomy?.phase && autonomy.phase !== 'idle' && (
        <div className="lab-lock-note"><RefreshCw size={13}/> CONSELHO AUTÔNOMO — FASE {autonomy.phase.toUpperCase()}{autonomy.cycle_id ? ` · ${autonomy.cycle_id}` : ''}</div>
      )}
      {autonomy?.last_summary && !autoRunning && (
        <div className="lab-lock-note"><Check size={13}/> ÚLTIMO CICLO AUTÔNOMO: {autonomy.last_summary}</div>
      )}
      <div className="lab-card-scroll">
        {mission.active_cycle && (
          <div className="lab-lock-note"><RefreshCw size={13}/> CICLO ATIVO {mission.active_cycle.id} — {mission.active_cycle.objective}</div>
        )}
        {(mission.milestones || []).map((m) => {
          const Icon = milestoneIcon(m.state);
          const isOpen = verifying === m.code;
          return (
            <article className="lab-task" key={m.code}>
              <div>
                <strong>{m.code}</strong>
                <span>{m.title.toUpperCase()}</span>
              </div>
              <p>{m.description}</p>
              <footer>
                <em className={`worker-state state-${stateClass(m.state)}`}><i/>{m.state.toUpperCase()}</em>
                <span><Icon size={12}/> {m.evidence.length} EVIDÊNCIA(S)</span>
                {m.state !== 'done' && !isOpen && (
                  <button className="approve" onClick={() => { setVerifying(m.code); setEvidence(''); setError(''); }}>
                    <BadgeCheck size={13}/> VERIFICAR
                  </button>
                )}
              </footer>
              {m.evidence.length > 0 && (
                <div className="lab-lock-note"><ShieldCheck size={13}/> {m.evidence.join(' • ')}</div>
              )}
              {isOpen && (
                <div className="lab-verify-row">
                  <input
                    value={evidence}
                    onChange={(e) => setEvidence(e.target.value)}
                    placeholder="Referência da evidência (ex.: .unlazy/.../GATES.md)"
                  />
                  <button className="approve" disabled={!evidence.trim() || busy} onClick={() => void confirmVerify(m.code)}>
                    {busy ? <LoaderCircle className="spin" size={13}/> : <Check size={13}/>} CONFIRMAR
                  </button>
                  <button className="reject" onClick={() => setVerifying(null)}><X size={13}/></button>
                </div>
              )}
            </article>
          );
        })}
        {error && <div className="lab-error"><Activity size={13}/>{error}<button onClick={() => setError('')}><X size={12}/></button></div>}
      </div>
      <div className="lab-activity-feed">
        <h3><Activity size={13}/> MISSION FEED — {mission.room?.name || 'ZARA Core'}</h3>
        {feed.length === 0 && <div className="lab-empty small">Nenhum evento da missão ainda.</div>}
        {feed.map((f) => (
          <div key={f.id}><time>{readableTime(f.created_at)}</time><strong>{f.actor.toUpperCase()}</strong><span>{f.event}</span><em>{f.detail}</em></div>
        ))}
      </div>
    </section>
  );
};

export const ZaraLab: React.FC = () => {
  const [lab, setLab] = useState<LabState>(emptyState);
  const [target, setTarget] = useState('zara');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [proposalTitle, setProposalTitle] = useState('');
  const [proposalSummary, setProposalSummary] = useState('');
  const [proposalRisk, setProposalRisk] = useState('MEDIUM');
  const [proposalOwner, setProposalOwner] = useState('opencode');
  const [proposalBusy, setProposalBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (quiet = false) => {
    try {
      const state = await window.zaraIPC?.lab?.state?.();
      if (state) {
        setLab(state as LabState);
        setError('');
      }
    } catch {
      if (!quiet) setError('ZARA Lab backend indisponível.');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(true), 2200);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [refresh]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [lab.messages]);

  const chatWorkers = useMemo(() => lab.workers.filter((w) => w.id !== 'alex'), [lab.workers]);
  const selectedWorker = lab.workers.find((w) => w.id === target);

  const sendMessage = async (e?: FormEvent) => {
    e?.preventDefault();
    const content = message.trim();
    if (!content || sending) return;
    setSending(true);
    setMessage('');
    try {
      const result = await window.zaraIPC?.lab?.send?.({ author: 'alex', target, content });
      if (target === 'mentor' && result?.state === 'QUEUED') {
        setError(result?.relay_online ? '' : 'Mentor Relay offline: mensagem preservada na fila e será enviada quando a ponte voltar.');
      }
      await refresh(true);
    } catch {
      setError(`Falha ao enviar para ${target.toUpperCase()}.`);
    } finally {
      setSending(false);
    }
  };

  const createProposal = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!proposalTitle.trim() || !proposalSummary.trim() || proposalBusy) return;
    setProposalBusy(true);
    try {
      await window.zaraIPC?.lab?.createProposal?.({
        title: proposalTitle.trim(), summary: proposalSummary.trim(), risk: proposalRisk, owner: proposalOwner,
      });
      setProposalTitle(''); setProposalSummary(''); setProposalRisk('MEDIUM');
      await refresh(true);
    } catch {
      setError('Não foi possível criar a proposta.');
    } finally {
      setProposalBusy(false);
    }
  };

  const decide = async (id: string, decision: 'APPROVE' | 'REJECT') => {
    try {
      await window.zaraIPC?.lab?.decideProposal?.({ id, decision });
      await refresh(true);
    } catch {
      setError('Falha no Approval Gate.');
    }
  };

  return (
    <main className="lab-stage">
      <section className="lab-topline">
        <div>
          <span className="lab-kicker"><FlaskConical size={14}/> ZARA LAB</span>
          <h1>COUNCIL & DEVELOPMENT CENTER</h1>
          <p>Discussão, propostas, aprovação e fluxo de trabalho — sem alterar a ZARA oficial durante a conversa.</p>
        </div>
        <div className="lab-runtime-status">
          <span><ShieldCheck size={14}/> APPROVAL GATE <strong>{lab.approval_gate ? 'ON' : 'OFF'}</strong></span>
          <span><Code2 size={14}/> EXECUTION <strong>{lab.execution_runtime}</strong></span>
          <button onClick={() => void refresh()} title="Atualizar estado real"><RefreshCw size={14}/></button>
        </div>
      </section>

      <section className="lab-roster" aria-label="Equipe do laboratório">
        {lab.workers.map((worker) => {
          const Icon = participantIcon(worker.id);
          return (
            <button key={worker.id} className={`lab-person ${target === worker.id ? 'selected' : ''}`} disabled={worker.id === 'alex'} onClick={() => worker.id !== 'alex' && setTarget(worker.id)} title={worker.detail}>
              <div className="lab-person-icon"><Icon size={16}/></div>
              <div><strong>{worker.name}</strong><span>{worker.role}</span></div>
              <em className={`worker-state state-${stateClass(worker.state)}`}><i/>{worker.state}</em>
            </button>
          );
        })}
      </section>

      <div className="lab-grid">
        <section className="lab-panel lab-council">
          <header className="lab-panel-header">
            <div><MessageSquareText size={15}/><span>COUNCIL ROOM</span></div>
            <em>
              {selectedWorker ? `@${selectedWorker.name} • ${selectedWorker.state}` : 'SELECIONE UM MEMBRO'}
              {selectedWorker?.id === 'mentor' && lab.mentor_relay?.pending ? ` • ${lab.mentor_relay.pending} PENDING` : ''}
            </em>
          </header>
          <div className="lab-chat-scroll">
            {loading && <div className="lab-empty"><LoaderCircle className="spin" size={18}/> CARREGANDO LABORATÓRIO...</div>}
            {!loading && lab.messages.length === 0 && <div className="lab-empty">O Conselho está pronto. Converse com ZARA, Mentor ou OpenClaw.</div>}
            {lab.messages.map((m) => {
              const Icon = participantIcon(m.author);
              const isAlex = m.author === 'alex';
              return (
                <article className={`lab-message ${isAlex ? 'alex' : ''} ${m.kind === 'status' ? 'status' : ''}`} key={m.id}>
                  <div className="lab-message-avatar"><Icon size={15}/></div>
                  <div className="lab-message-content">
                    <div><strong>{m.author.toUpperCase()}</strong><span>→ @{m.target.toUpperCase()}</span><time>{readableTime(m.created_at)}</time></div>
                    <p>{m.content}</p>
                  </div>
                </article>
              );
            })}
            <div ref={chatEndRef}/>
          </div>
          <form className="lab-composer" onSubmit={sendMessage}>
            <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Destinatário">
              {chatWorkers.map((w) => <option key={w.id} value={w.id}>@{w.name} • {w.state}</option>)}
            </select>
            <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Discuta uma ideia com o Conselho..."/>
            <button type="submit" disabled={!message.trim() || sending}>{sending ? <LoaderCircle className="spin" size={17}/> : <Send size={17}/>}</button>
          </form>
          {error && <div className="lab-error"><Activity size={13}/>{error}<button onClick={() => setError('')}><X size={12}/></button></div>}
        </section>

        <section className="lab-panel lab-proposal-builder">
          <header className="lab-panel-header"><div><Sparkles size={15}/><span>NOVA PROPOSTA</span></div><em>ALEX GATE</em></header>
          <form onSubmit={createProposal}>
            <label>TÍTULO<input value={proposalTitle} onChange={(e) => setProposalTitle(e.target.value)} placeholder="Ex.: Personality Engine 2.0"/></label>
            <label>RESUMO<textarea value={proposalSummary} onChange={(e) => setProposalSummary(e.target.value)} placeholder="O que queremos melhorar e por quê?"/></label>
            <div className="lab-form-row">
              <label>RISCO<select value={proposalRisk} onChange={(e) => setProposalRisk(e.target.value)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select></label>
              <label>LEAD<select value={proposalOwner} onChange={(e) => setProposalOwner(e.target.value)}><option value="opencode">OpenCode</option><option value="openclaw">OpenClaw</option><option value="cline">Cline</option><option value="aider">Aider</option><option value="hermes">Hermes</option></select></label>
            </div>
            <button className="lab-primary" type="submit" disabled={proposalBusy || !proposalTitle.trim() || !proposalSummary.trim()}>{proposalBusy ? <LoaderCircle className="spin" size={15}/> : <BadgeCheck size={15}/>} REGISTRAR PARA DISCUSSÃO</button>
          </form>
        </section>

        <section className="lab-panel lab-proposals">
          <header className="lab-panel-header"><div><BadgeCheck size={15}/><span>PROPOSALS</span></div><em>{lab.proposals.length}</em></header>
          <div className="lab-card-scroll">
            {lab.proposals.length === 0 && <div className="lab-empty small">Nenhuma proposta criada.</div>}
            {lab.proposals.map((p) => (
              <article className="lab-proposal" key={p.id}>
                <div className="lab-proposal-title"><span>{p.id}</span><em className={`proposal-status status-${p.status.toLowerCase()}`}>{p.status}</em></div>
                <strong>{p.title}</strong>
                <p>{p.summary}</p>
                <footer><span>RISK {p.risk}</span><span>LEAD {p.owner.toUpperCase()}</span><span>{p.cost}</span></footer>
                {p.status === 'DISCUSSION' && <div className="lab-decision-row"><button className="reject" onClick={() => void decide(p.id, 'REJECT')}><X size={13}/> REJEITAR</button><button className="approve" onClick={() => void decide(p.id, 'APPROVE')}><Check size={13}/> APROVAR PLANO</button></div>}
                {p.status === 'APPROVED' && <div className="lab-lock-note"><ShieldCheck size={13}/> APROVADA • EXECUÇÃO DE CÓDIGO CONTINUA BLOQUEADA</div>}
              </article>
            ))}
          </div>
        </section>

        <section className="lab-panel lab-workflow">
          <header className="lab-panel-header">
            <div><GitBranch size={15}/><span>AUTONOMY WORKFLOW</span></div>
            <em>{lab.autonomy?.status || 'UNKNOWN'} • {lab.autonomy?.total_tasks ?? lab.tasks.length} TASK(S)</em>
          </header>
          <div className="lab-workflow-list">
            {lab.tasks.length === 0 && <div className="lab-empty small">Aprovar uma proposta cria uma tarefa na fila.</div>}
            {lab.tasks.map((t) => (
              <article key={t.id} className="lab-task">
                <div>
                  <strong>{t.id}</strong>
                  <span>{t.assigned_worker ? `WORKER ${t.assigned_worker.toUpperCase()}` : `PREFERRED ${t.owner.toUpperCase()}`}</span>
                </div>
                <p>{t.title}</p>
                {typeof t.progress === 'number' && <div className="lab-progress"><i style={{ width: `${Math.max(0, Math.min(100, t.progress))}%` }}/></div>}
                <footer>
                  <em>{t.status}</em>
                  <span>{t.current_step}</span>
                  {typeof t.attempts === 'number' && <span>TRY {t.attempts}/{t.max_attempts ?? 3}</span>}
                  {t.checkpoint_saved && <span>CHECKPOINT SAVED</span>}
                  {t.needs_alex && <span>NEEDS ALEX</span>}
                </footer>
                {t.last_error && <div className="lab-lock-note"><ShieldCheck size={13}/> {t.last_error}</div>}
              </article>
            ))}
          </div>
          <div className="lab-activity-feed">
            <h3><Activity size={13}/> LIVE ACTIVITY</h3>
            {lab.activity.slice(0, 8).map((a) => <div key={a.id}><time>{readableTime(a.created_at)}</time><strong>{a.actor.toUpperCase()}</strong><span>{a.event}</span><em>{a.detail}</em></div>)}
          </div>
        </section>

        <MissionBoard mission={lab.mission} onRefresh={() => void refresh(true)} />
      </div>

      <footer className="lab-footer">
        <span><CircleDot size={10}/> LAB MENTOR RELAY 001</span>
        <span><ShieldCheck size={11}/> Production writes: BLOCKED</span>
        <span><Clock3 size={11}/> State persisted in LOCALAPPDATA</span>
        <span className="lab-next">NEXT: PROJECT MEMORY → SAFE WORKER CLAIM → RECOVERY <ChevronRight size={12}/></span>
      </footer>
    </main>
  );
};
