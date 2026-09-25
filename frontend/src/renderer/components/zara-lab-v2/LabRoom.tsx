import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowUpRight, Check, ChevronRight, Circle, FileText, Plus, Search, Send, ShieldCheck, Square, Users, X, Zap } from 'lucide-react';
import { useLabRoom } from './useLabRoom';
import { asList, avatarHue, failureText, initials, label, requireResult, timestamp, type Agent } from './labTypes';
import './lab-room.css';
import zaraMark from '../../../assets/zara-home/zara-mark.svg';
import { cortarKore, observarKore } from '../../lib/aecAudio';

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
  const [templateSearch, setTemplateSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [playing, setPlaying] = useState(false);
  useEffect(() => observarKore(setPlaying), []);
  const [tab, setTab] = useState<'operations' | 'people'>('operations');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showAgent, setShowAgent] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [agentProvider, setAgentProvider] = useState('');
  const [agentModel, setAgentModel] = useState('');
  const root = useRef<HTMLElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const operation = useRef(false);
  const agents = asList(data?.agents).filter(a => !a.archived);
  const members = agents.filter(a => asList(data?.memberships).some(m => m.agent_id === a.id && !m.left_at));
  const templates = asList(data?.agent_templates);
  const templateQuery = templateSearch.trim().toLocaleLowerCase('pt-BR');
  const matchingTemplates = templateQuery
    ? templates.filter(template => `${template.name} ${template.description} ${template.division}`.toLocaleLowerCase('pt-BR').includes(templateQuery))
    : templates;
  const activeTeamId = teamId || data?.team?.id || '';
  const teamSessions = asList(data?.sessions)
    .filter(s => !activeTeamId || s.team_id === activeTeamId)
    .sort((a, b) => b.updated_at - a.updated_at);
  const allMessages = asList(data?.team_messages);
  const query = search.trim().toLocaleLowerCase('pt-BR');
  const messages = query
    ? allMessages.filter(message => `${message.mission_objective || ''}\n${message.content}`.toLocaleLowerCase('pt-BR').includes(query))
    : allMessages;
  const firstMessageByMission = new Map<string, string>();
  for (const message of messages) {
    if (!firstMessageByMission.has(message.session_id)) firstMessageByMission.set(message.session_id, message.id);
  }
  const tasks = creating ? [] : asList(session?.tasks);
  const runs = creating ? [] : asList(session?.runs);
  const linkedMemorySources = asList(session?.events)
    .filter(event => event.type === 'memory.linked')
    .flatMap(event => {
      const payload = event.payload || {};
      const agentName = typeof payload.agent_name === 'string' ? payload.agent_name : 'Agente';
      const sources = Array.isArray(payload.sources) ? payload.sources : [];
      return sources.flatMap(source => {
        if (!source || typeof source !== 'object') return [];
        const row = source as Record<string, unknown>;
        const path = typeof row.path === 'string' ? row.path.replace(/\\/g, '/') : '';
        if (!path || path.startsWith('/') || /^[a-z]:/i.test(path) || /(^|\/)\.\.(\/|$)/.test(path)) return [];
        return [{ key: `${event.id}:${path}`, path, title: typeof row.title === 'string' ? row.title : path, agentName, occurredAt: event.occurred_at, updatedAt: typeof row.updated_at === 'number' ? row.updated_at : undefined }];
      });
    })
    .slice(-8)
    .reverse();
  const missionState = session?.mission?.state || session?.state;
  const missionOpen = !creating && !!session?.mission && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(missionState || '');
  const backgroundRunning = data?.autonomy_policy?.background_task_state === 'RUNNING';
  const supervisorLive = backgroundRunning && data?.autonomy_policy?.last_state !== 'FAILED';
  const cycleState = data?.autonomy_policy?.last_state;
  const cycleStatus = !data?.autonomy_policy?.enabled ? 'Novos ciclos pausados'
    : !backgroundRunning ? 'Ciclos configurados; supervisor parado'
    : cycleState === 'BUDGET_EXHAUSTED' ? 'Limite diário atingido; retoma amanhã'
    : cycleState === 'WAITING_RETRY' || cycleState === 'FAILED' ? 'Falha no ciclo; nova tentativa agendada'
    : 'Ciclos em andamento';
  const running = missionOpen && ['QUEUED', 'PLANNING', 'RUNNING', 'WORKING', 'VERIFYING', 'REPAIRING', 'CANCELLING'].includes(missionState || '');
  const missionLabel = creating ? 'Nova missão' : room.error ? 'Conexão indisponível' : missionState === 'WAITING_RESOURCE' ? 'Aguardando recurso' : missionState === 'BLOCKED_NEEDS_OWNER' ? 'Aguardando o owner' : running && supervisorLive ? `Missão ${label(missionState).toLowerCase()}` : running ? 'Continuidade parada' : cycleState === 'BUDGET_EXHAUSTED' ? 'Limite diário atingido' : 'Pronta para novo objetivo';
  const nameOf = (id?: string | null) => agents.find(a => a.id === id)?.name || 'ZARA';

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
      const result = requireResult(await api?.autopilot(intent));
      if (!result.session_id) throw new Error('O backend não registrou uma missão.');
      select(result.session_id, activeTeamId); setCreating(false);
      setText('');
    });
  }
  function person(agent: Agent) {
    const health = data?.health?.[`model:${agent.provider_id}:${agent.model}`];
    const provider = asList(data?.providers).find(p => p.id === agent.provider_id);
    const state = provider?.availability !== 'AVAILABLE' ? provider?.availability : health?.availability || 'UNKNOWN';
    const working = data?.participation?.[agent.id] === 'WORKING';
    const role = asList(data?.role_bindings).find(b => b.agent_id === agent.id && b.active !== false && !b.unbound_at)?.role || agent.role;
    return <article className="zl-person" key={agent.id}>
      <Avatar name={agent.name} id={agent.id} small /><div><strong>{agent.name} <em>{label(role)}</em></strong><small>{agent.model}</small><span className={state === 'AVAILABLE' ? 'zl-good' : 'zl-muted'}>{working ? 'Trabalhando nesta sala' : label(state)}</span></div>
      <details className="zl-person-menu"><summary aria-label={`Gerenciar ${agent.name}`}>···</summary><div>
        <button disabled={busy || !teamId} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.rebindRole?.({ team_id: teamId, role: 'CEO', agent_id: agent.id, reason: 'Alex alterou a liderança na sala' })); })}>Definir como líder</button>
        <button disabled={busy} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.archiveAgent?.(agent.id)); })}>Arquivar participante</button>
      </div></details>
    </article>;
  }

  return <section className={`zl-room ${inspectorOpen ? 'inspector-open' : ''}`} role="dialog" aria-modal="true" aria-label="ZARA Lab" tabIndex={-1} ref={root}>
    <aside className="zl-sidebar">
      <header className="zl-brand"><button aria-label="Voltar para início" onClick={onClose}><ArrowLeft size={19} /></button><img className="zl-mark" src={zaraMark} alt="ZARA" /><div><strong>ZARA <b>LAB</b></strong><small>Sua equipe de inteligência</small></div></header>
      <div className="zl-sidebar-title"><h2>Equipe</h2><button aria-label="Novo objetivo para a equipe" onClick={() => { setCreating(true); setText(''); }}><Plus size={20} /></button></div>
      <label className="zl-search"><Search size={16} /><input placeholder="Buscar no grupo" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <nav className="zl-conversations" aria-label="Sala da equipe">
        <button className="zl-conversation selected" aria-current="page" onClick={() => { select('', activeTeamId); setCreating(false); setText(''); }}>
          <Avatar name={data?.team?.name || 'ZARA Core'} id={activeTeamId || 'zara-core'} />
          <span><strong>{data?.team?.name || 'ZARA Core'}</strong><small><Circle size={7} fill="currentColor" /> {session ? label(missionState) : 'Sala contínua'}</small></span>
          <time>{timestamp(teamSessions[0]?.updated_at)}</time>
        </button>
        <div className="zl-empty-small">{teamSessions.length} {teamSessions.length === 1 ? 'missão no histórico' : 'missões no histórico'}</div>
      </nav>
      <footer className="zl-owner"><Avatar name="Alex" small /><div><strong>Alex</strong><small>Você define o objetivo</small></div><ShieldCheck size={18} /></footer>
    </aside>

    <main className="zl-conversation-main">
      <header className="zl-chat-header"><Avatar name="ZARA" id="zara" /><div><h1>{data?.team?.name || 'ZARA Core'}</h1><p>{members.length ? `${members.length} agentes · ZARA regente` : templates.length ? `${templates.length} perfis sob demanda · ZARA regente` : 'Aguardando equipe comprovada'} <span>·</span> <span className="zl-good">{missionLabel}</span></p></div><button onClick={() => { setTab('people'); setInspectorOpen(v => !v); }} aria-label="Ver participantes"><Users size={20} /></button><button onClick={onClose} aria-label="Fechar ZARA Lab"><X size={20} /></button></header>
      {!creating && session && <div className="zl-mission-strip"><Zap size={15} /><span>{session.objective}</span><b>{label(missionState)}</b></div>}
      <div className="zl-messages" ref={log} role="log" aria-label="Conversa da equipe" aria-live="polite">
        {!allMessages.length && <div className="zl-welcome"><span className="zl-welcome-orb"><img src={zaraMark} alt="ZARA" /></span><span className="zl-eyebrow">ZARA + SUA EQUIPE</span><h2>Uma ideia sua.<br />Um objetivo para todos.</h2><p>Uma intenção. Sua equipe cuida do contexto, divide o trabalho e devolve um resultado com evidências.</p><button onClick={() => { setCreating(true); setText('Crie um briefing curto para melhorar a experiência do ZARA Lab.'); }}>Começar com um briefing <ArrowUpRight size={16} /></button></div>}
        {allMessages.length > 0 && !messages.length && <p className="zl-empty-small zl-no-search-results">Nenhuma mensagem corresponde à busca.</p>}
        {messages.map(message => { const mine = message.kind === 'USER'; const system = message.kind === 'ZARA'; const author = agents.find(a => a.id === message.author_agent_id); const firstInMission = firstMessageByMission.get(message.session_id) === message.id; const mission = teamSessions.find(item => item.id === message.session_id); let content = message.content; try { const value = JSON.parse(content); content = value.summary || (value.title && value.instruction ? value.title + '\n\n' + value.instruction : content); } catch { /* delivered plain text */ } return <Fragment key={message.id}>
          {firstInMission && <section className="zl-mission-card" aria-label={`Objetivo: ${message.mission_objective || mission?.objective || 'sem descrição'}`}>
            <div className="zl-mission-card-heading"><span><Zap size={14} /> Novo objetivo</span><time>{timestamp(message.created_at, true)}</time></div>
            <p>{message.mission_objective || mission?.objective || 'Objetivo não registrado'}</p>
            <div className="zl-mission-card-footer"><span>{label(message.mission_state || mission?.state)}</span><button type="button" onClick={() => select(message.session_id, activeTeamId)} aria-label="Ver progresso deste objetivo">Ver progresso <ArrowUpRight size={13} /></button></div>
          </section>}
          <article className={`zl-message ${mine ? 'mine' : ''} ${system ? 'system' : ''}`}>
            {!mine && <Avatar name={message.author} id={message.author_agent_id || message.author} small />}
            <div className="zl-bubble"><strong>{mine ? 'Você' : message.author}{system && <ShieldCheck size={12} />}</strong>{author && <span className="zl-author-role">{label(author.role)} · {author.provider_id === 'codex_cli' ? 'OpenAI / Codex' : author.provider_id}</span>}<p>{content}</p><footer>{message.run_id && <span>Resposta registrada</span>}<time>{timestamp(message.created_at)}</time>{mine && <Check size={13} />}</footer></div>
          </article>
        </Fragment>; })}
        {running && supervisorLive && <div className="zl-working"><span /><span /><span /><small>{runs.find(r => r.state === 'STARTED') ? `${nameOf(runs.find(r => r.state === 'STARTED')?.agent_id)} está trabalhando` : `Supervisor ativo · ${label(data?.autonomy_policy?.last_state)}`}</small></div>}
      </div>
      {(error || room.error) && <div className="zl-error" role="alert">{error || room.error}</div>}
      <form className="zl-composer" onSubmit={submit}>
        <div className="zl-composer-mode"><span className="zl-composer-regent"><ShieldCheck size={13} /> ZARA coordena · você define o objetivo</span>{playing && <button type="button" onClick={() => { cortarKore(); void window.zaraIPC?.message?.interrupt?.(); }}>Interromper fala</button>}</div>
        <div className="zl-input-row"><textarea aria-label="Mensagem para a equipe" value={text} onChange={e => setText(e.target.value)} maxLength={12000} rows={2} placeholder="Conte para a ZARA o que você quer realizar…" onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy && text.trim() && !missionOpen) e.currentTarget.form?.requestSubmit(); } }} /><button type="submit" className="zl-send" disabled={busy || !text.trim() || missionOpen} aria-label="Enviar mensagem"><Send size={19} /></button></div>
        <small className="zl-composer-note">{missionOpen ? 'A missão pertence ao Mission Controller. Você pode acompanhar ou cancelar nas operações.' : 'Enter para enviar · Shift + Enter para nova linha'}</small>
      </form>
    </main>

    <aside className="zl-inspector"><header><button className="zl-inspector-close" aria-label="Fechar painel" onClick={() => setInspectorOpen(false)}><X size={17} /></button><button className={tab === 'operations' ? 'active' : ''} onClick={() => setTab('operations')}>Operações</button><button className={tab === 'people' ? 'active' : ''} onClick={() => setTab('people')}>Participantes</button></header>
      <div className="zl-inspector-body">{tab === 'operations' ? <>
        <div className="zl-regent"><ShieldCheck size={22} /><div><strong>{running ? 'ZARA está coordenando' : 'Estado factual da missão'}</strong><p>Coordenação, continuidade e evidências persistidas.</p></div></div>
        <div className="zl-autonomy"><h3>Continuidade</h3><p>{backgroundRunning ? `Supervisor ativo · ${label(cycleState)}` : `Supervisor ${label(data?.autonomy_policy?.background_task_state || 'STOPPED').toLowerCase()}`}</p>{data?.autonomy_policy?.background_error && <p className="zl-error">{data.autonomy_policy.background_error}</p>}<h3>Melhoria contínua</h3><p>{cycleStatus}</p><button disabled={busy || !data?.autonomy_policy} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.configureAutonomy(!data?.autonomy_policy?.enabled)); })}>{data?.autonomy_policy?.enabled ? 'Pausar novos ciclos' : 'Ativar ciclos automáticos'}</button></div>
        <div className="zl-autonomy"><h3>Memória compartilhada</h3><p>{data?.shared_memory?.state === 'CONNECTED' ? 'Obsidian conectado' : data?.shared_memory?.state === 'CONNECTED_EMPTY' ? 'Cofre conectado; pasta de memória vazia' : data?.shared_memory?.state === 'UNAVAILABLE' ? 'Obsidian indisponível' : 'Verificando Obsidian'}</p><p>{data?.shared_memory?.source || 'Obsidian · Zara-Memoria'} · {data?.shared_memory?.notes_count ?? 0} notas encontradas (limite 128)</p><p>Leitura direta, sem índice salvo · verificado {timestamp(data?.shared_memory?.checked_at)}</p><p>Nota mais recente: {timestamp(data?.shared_memory?.latest_updated_at ?? undefined, true)}</p><h3>Fontes consultadas nesta missão</h3>{linkedMemorySources.length ? <ul className="zl-memory-sources">{linkedMemorySources.map(source => <li key={source.key}><strong>{source.title}</strong><small>{source.path} · {source.agentName} · consultada {timestamp(source.occurredAt, true)} · nota atualizada {timestamp(source.updatedAt, true)}</small></li>)}</ul> : <p className="zl-empty-small">Nenhuma fonte foi registrada nesta missão ainda.</p>}</div>
        <div className="zl-section-heading"><h3>Plano de trabalho</h3><span>{tasks.filter(t => t.state === 'COMPLETED').length}/{tasks.length}</span></div>
        {tasks.map((task, index) => <details className="zl-task" key={task.id}><summary><span className={task.state === 'COMPLETED' ? 'done' : ''}>{task.state === 'COMPLETED' ? <Check size={13} /> : index + 1}</span><div><strong>{task.title}</strong><small>{nameOf(task.assigned_agent_id)} · {label(task.state)}</small></div><ChevronRight size={14} /></summary><p>{task.instruction}</p>{task.result && <pre>{task.result}</pre>}</details>)}
        {!tasks.length && <p className="zl-empty-small">O plano aparece quando a equipe inicia uma missão.</p>}
        <h3>Entregas</h3>{(!creating ? asList(session?.artifacts) : []).map(artifact => <details className="zl-artifact" key={artifact.id}><summary><FileText size={17} /><div><strong>{artifact.title}</strong><small>{artifact.kind || 'Artefato'} · {timestamp(artifact.created_at)}</small></div></summary>{artifact.path && <p>{artifact.path}</p>}<pre>{artifact.body}</pre></details>)}
        <h3>Execuções reais</h3>{runs.map(run => <details className="zl-run" key={run.id}><summary><strong>{nameOf(run.agent_id)}</strong><span>{label(run.state)}</span></summary><dl><dt>Provedor</dt><dd>{run.provider_id}</dd><dt>Solicitado</dt><dd>{run.model}</dd><dt>Reportado</dt><dd>{run.model_reported || 'Não informado pelo provedor'}</dd><dt>Tokens</dt><dd>{run.input_tokens ?? '—'} entrada · {run.output_tokens ?? '—'} saída</dd><dt>Tempo</dt><dd>{run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'}</dd><dt>Custo</dt><dd>{run.cost_usd != null ? `US$ ${run.cost_usd.toFixed(4)}` : 'Não informado'}</dd></dl>{run.error && <p className="zl-error">{run.error}</p>}</details>)}
        {session?.autonomy && !creating && <div className="zl-autonomy"><h3>Autonomia desta missão</h3><p>{session.autonomy.owner_touches ? `${session.autonomy.owner_touches} comando inicial` : 'Iniciada pela ZARA, sem comando do Alex'}</p><p>Resultado: {session.autonomy.content_review === 'NOT_CERTIFIED' ? 'Arquivo verificado; conteúdo sem revisão independente' : session.autonomy.content_review}</p>{session.autonomy.gaps?.map((gap, i) => <p key={i}>{gap.reason}</p>)}</div>}
        {missionOpen && <button className="zl-cancel" disabled={busy} onClick={() => void perform(async () => { requireResult(await window.zaraIPC?.labV1?.cancelMission(sessionId)); })}><Square size={13} /> Cancelar missão</button>}
      </> : <>
        <div className="zl-section-heading"><h3>Equipe desta sala ({members.length})</h3><button aria-label="Adicionar participante" onClick={() => setShowAgent(true)}><Plus size={17} /></button></div>
        <article className="zl-person"><Avatar name="ZARA" small /><div><strong>ZARA <em>Regente</em></strong><small>Coordenação do sistema</small><span className="zl-good">{data?.regent?.state || 'Conectando'}</span></div></article>
        {members.map(person)}
        {!members.length && <p className="zl-empty-small">{templates.length ? 'Nenhum agente entrou nesta equipe ainda. Os perfis abaixo podem ser chamados conforme a missão.' : 'Nenhum agente entrou nesta equipe ainda.'}</p>}
        {agents.some(a => !members.includes(a)) && <><h3>Outros participantes</h3>{agents.filter(a => !members.includes(a)).map(person)}</>}
        <section className="zl-template-catalog" aria-label="Catálogo Agent Agency">
          <div className="zl-section-heading"><h3>Agent Agency</h3><span>{templates.length} perfis</span></div>
          <p className="zl-template-help">Especialistas disponíveis sob demanda. O trabalho real aparece na equipe e nas execuções.</p>
          <label className="zl-template-search"><Search size={15} /><input type="search" aria-label="Buscar perfil do Agent Agency" placeholder="Buscar nome, área ou especialidade" value={templateSearch} onChange={event => setTemplateSearch(event.target.value)} /></label>
          {templates.length ? <>
            <small className="zl-template-count">{matchingTemplates.length} {matchingTemplates.length === 1 ? 'perfil encontrado' : 'perfis encontrados'}</small>
            <div className="zl-template-list" role="list" aria-label="Perfis do Agent Agency">
              {matchingTemplates.map(template => <article className="zl-template" role="listitem" key={template.id}><Avatar name={template.name} id={template.id} small /><div><strong>{template.name}</strong><small>{template.division}</small><p title={template.description}>{template.description}</p></div></article>)}
            </div>
            {!matchingTemplates.length && <p className="zl-empty-small">Nenhum perfil corresponde à busca.</p>}
          </> : <p className="zl-empty-small">{data?.agent_templates ? 'Nenhum perfil disponível neste catálogo.' : 'Catálogo ainda não disponível nesta versão do Lab.'}</p>}
        </section>
        <h3>Células de trabalho</h3>{asList(data?.workcells).map(cell => <article className="zl-person" key={cell.id}><Avatar name={cell.name} small /><div><strong>{cell.name}</strong><small>{cell.detail}</small><span className="zl-muted">{label(cell.availability)}</span></div></article>)}
        <h3>Conexões</h3>{asList(data?.providers).map(provider => <details className="zl-provider" key={provider.id}><summary><strong>{provider.label || provider.id}</strong><span className={provider.availability === 'AVAILABLE' ? 'zl-good' : 'zl-muted'}>{label(provider.availability)}</span></summary><p>{provider.detail}</p></details>)}
      </>}</div>
      <footer className="zl-sync"><span className={room.error ? 'warn' : ''} />{room.loading ? 'Conectando ao Lab…' : `Sincronizado ${room.lastSynced ? new Date(room.lastSynced).toLocaleTimeString('pt-BR') : '—'}`}</footer>
    </aside>
    {showAgent && <div className="zl-modal"><form onSubmit={event => { event.preventDefault(); void perform(async () => { requireResult(await window.zaraIPC?.labV1?.createAgent?.({ name: agentName.trim(), provider_id: agentProvider, model: agentModel, team_id: teamId || undefined })); setShowAgent(false); setAgentName(''); }); }}><header><h2>Adicionar participante</h2><button type="button" aria-label="Fechar cadastro" onClick={() => setShowAgent(false)}><X size={19} /></button></header><label>Nome<input required maxLength={80} value={agentName} onChange={e => setAgentName(e.target.value)} /></label><label>Provedor<select required value={agentProvider} onChange={e => { setAgentProvider(e.target.value); setAgentModel(''); }}><option value="">Selecione</option>{asList(data?.providers).map(p => <option value={p.id} key={p.id}>{p.label}</option>)}</select></label><label>Modelo<select required value={agentModel} onChange={e => setAgentModel(e.target.value)}><option value="">Selecione um modelo do catálogo</option>{asList(data?.models).filter(m => m.provider_id === agentProvider).map(m => <option value={m.model_id} key={m.model_id}>{m.display_name || m.model_id}</option>)}</select></label><p>A disponibilidade depende da autenticação e das respostas reais do provedor.</p><button className="zl-primary" disabled={busy || !agentName.trim() || !agentModel}>Adicionar à equipe</button></form></div>}
  </section>;
}
