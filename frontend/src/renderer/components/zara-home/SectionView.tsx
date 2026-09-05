import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  MessageCircle, Folder, File, LayoutGrid, Workflow, BrainCircuit,
  FlaskConical, Monitor, Settings, RefreshCw, Trash2,
} from 'lucide-react';

/**
 * Seções da Sidebar que NÃO são a Home.
 *
 * Até aqui os 11 itens da Sidebar só trocavam o destaque: o conteúdo da tela
 * continuava sendo o "Hoje" em todos eles. Ou seja, 10 dos 11 botões eram
 * decoração — exatamente o que a regra de honestidade da Home proíbe.
 *
 * Cada seção aqui é ligada a um canal IPC que JÁ existe e JÁ tem handler no
 * backend (ver `handler_map` em core/ipc_handlers.py). Nada de dado
 * inventado: quando o canal não existe no runtime, ou responde erro, a seção
 * diz isso em vez de mostrar uma lista vazia bonitinha. As duas seções sem
 * backend nenhum (Arquivos por navegação, Dispositivos) aparecem
 * explicitamente como ainda não construídas.
 */

type Loader<T> = () => Promise<T>;

interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Carrega um canal IPC e distingue os três desfechos: dados, erro, e canal
 *  inexistente no runtime (o que não é a mesma coisa que "vazio"). */
function useChannel<T>(loader: Loader<T> | null, deps: unknown[] = []): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: Boolean(loader) });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!loader) return;
    let alive = true;
    loader()
      .then((data) => { if (alive) setState({ data, error: null, loading: false }); })
      .catch((err: unknown) => {
        if (alive) setState({ data: null, error: err instanceof Error ? err.message : String(err), loading: false });
      });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  // Canal ausente é conclusão de render, não efeito: não há nada para
  // sincronizar com o mundo externo quando o preload não expõe o método.
  if (!loader) {
    return { data: null, error: 'Canal não disponível neste runtime.', loading: false, reload: () => {} };
  }

  return { ...state, reload: () => { setState((s) => ({ ...s, loading: true })); setTick((t) => t + 1); } };
}

function SectionShell({
  icon, title, subtitle, onReload, children,
}: { icon: ReactNode; title: string; subtitle: string; onReload?: () => void; children: ReactNode }) {
  return (
    <section className="zh-section-view zh-glass-panel" aria-label={title}>
      <header className="zh-section-view-head">
        <span className="zh-section-view-icon">{icon}</span>
        <span className="zh-section-view-titles">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </span>
        {onReload ? (
          <button className="zh-section-reload" type="button" onClick={onReload} aria-label="Recarregar">
            <RefreshCw size={15} strokeWidth={1.8} />
          </button>
        ) : null}
      </header>
      <div className="zh-section-view-body">{children}</div>
    </section>
  );
}

function StateLine({ loading, error, empty, emptyText }: { loading: boolean; error: string | null; empty: boolean; emptyText: string }) {
  if (loading) return <p className="zh-section-state">Carregando…</p>;
  if (error) return <p className="zh-section-state zh-section-state--error">Não foi possível ler: {error}</p>;
  if (empty) return <p className="zh-section-state">{emptyText}</p>;
  return null;
}

function fmtTime(ms: number | null | undefined): string {
  if (!ms) return '';
  const d = new Date(ms < 1e12 ? ms * 1000 : ms);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/* ------------------------------------------------------------------ */

function Conversas() {
  const list = window.zaraIPC?.conversationHistory?.list;
  const clear = window.zaraIPC?.conversationHistory?.clear;
  const { data, error, loading, reload } = useChannel(list ? () => list(200) : null);
  const messages: Array<{ id: string; role: string; content: string; engine: string; timestamp: number }> =
    Array.isArray(data?.messages) ? data.messages : [];

  return (
    <SectionShell
      icon={<MessageCircle size={18} strokeWidth={1.7} />}
      title="Conversas"
      subtitle="Transcrição local, só neste computador."
      onReload={list ? reload : undefined}
    >
      <StateLine loading={loading} error={error} empty={messages.length === 0} emptyText="Nenhuma conversa guardada ainda." />
      {messages.length > 0 && (
        <>
          <div className="zh-section-toolbar">
            <span className="zh-section-count">{messages.length} mensagens</span>
            {clear ? (
              <button
                className="zh-section-danger"
                type="button"
                onClick={() => { clear().then(reload).catch(() => reload()); }}
              >
                <Trash2 size={13} strokeWidth={1.8} /> Apagar tudo
              </button>
            ) : null}
          </div>
          <ul className="zh-msg-list">
            {messages.slice().reverse().map((m) => (
              <li key={m.id} className="zh-msg" data-role={m.role}>
                <span className="zh-msg-meta">
                  <strong>{m.role === 'user' ? 'Alex' : 'ZARA'}</strong>
                  <span>{fmtTime(m.timestamp)}{m.engine ? ` · ${m.engine}` : ''}</span>
                </span>
                <p>{m.content}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </SectionShell>
  );
}

function Memorias() {
  const list = window.zaraIPC?.userMemory?.list;
  const forget = window.zaraIPC?.userMemory?.forget;
  const { data, error, loading, reload } = useChannel(list ? () => list() : null);
  const facts: Array<{ id: string; fact: string; category: string; confidence: number; status: string; source: string; updated_at: number }> =
    Array.isArray(data?.facts) ? data.facts : [];

  return (
    <SectionShell
      icon={<BrainCircuit size={18} strokeWidth={1.7} />}
      title="Memórias"
      subtitle="O que a ZARA guardou sobre você. Você pode apagar qualquer item."
      onReload={list ? reload : undefined}
    >
      <StateLine loading={loading} error={error} empty={facts.length === 0} emptyText="Nenhum fato guardado ainda." />
      {facts.length > 0 && (
        <ul className="zh-fact-list">
          {facts.map((f) => (
            <li key={f.id} className="zh-fact">
              <span className="zh-fact-body">
                <strong>{f.fact}</strong>
                <span>
                  {f.category} · confiança {Math.round((f.confidence ?? 0) * 100)}% · {f.source}
                  {f.updated_at ? ` · ${fmtTime(f.updated_at)}` : ''}
                </span>
              </span>
              {forget ? (
                <button
                  className="zh-section-danger"
                  type="button"
                  aria-label={`Esquecer: ${f.fact}`}
                  onClick={() => { forget(f.id).then(reload).catch(() => reload()); }}
                >
                  <Trash2 size={13} strokeWidth={1.8} /> Esquecer
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

function Projetos() {
  const list = window.zaraIPC?.projectMemory?.list;
  const get = window.zaraIPC?.projectMemory?.get;
  const { data, error, loading, reload } = useChannel(list ? () => list() : null);
  const keys: string[] = Array.isArray(data?.keys) ? data.keys : [];
  const [open, setOpen] = useState<string | null>(null);
  const [doc, setDoc] = useState<{ title?: string; content?: string } | null>(null);

  const openDoc = useCallback((key: string) => {
    setOpen(key);
    setDoc(null);
    get?.(key).then((r: { doc?: { title?: string; content?: string } }) => setDoc(r?.doc ?? null)).catch(() => setDoc(null));
  }, [get]);

  return (
    <SectionShell
      icon={<Folder size={18} strokeWidth={1.7} />}
      title="Projetos"
      subtitle="Documentos da Project Memory local."
      onReload={list ? reload : undefined}
    >
      <StateLine loading={loading} error={error} empty={keys.length === 0} emptyText="Nenhum documento de projeto." />
      {keys.length > 0 && (
        <div className="zh-doc-split">
          <ul className="zh-doc-keys">
            {keys.map((k) => (
              <li key={k}>
                <button type="button" data-active={k === open} onClick={() => openDoc(k)}>{k}</button>
              </li>
            ))}
          </ul>
          <div className="zh-doc-body">
            {open === null ? <p className="zh-section-state">Escolha um documento.</p>
              : doc === null ? <p className="zh-section-state">Carregando…</p>
              : (
                <>
                  <h2>{doc.title || open}</h2>
                  <pre>{doc.content || '(vazio)'}</pre>
                </>
              )}
          </div>
        </div>
      )}
    </SectionShell>
  );
}

function Automacoes() {
  const list = window.zaraIPC?.reminders?.list;
  const cancel = window.zaraIPC?.reminders?.cancel;
  const { data, error, loading, reload } = useChannel(list ? () => list() : null);
  const reminders: Array<{ id: string; message: string; due_at_utc: number; state: string; source: string }> =
    Array.isArray((data as { reminders?: unknown })?.reminders) ? (data as { reminders: never[] }).reminders : [];

  return (
    <SectionShell
      icon={<Workflow size={18} strokeWidth={1.7} />}
      title="Automações"
      subtitle="Lembretes reais persistidos pelo Reminder Core."
      onReload={list ? reload : undefined}
    >
      <StateLine loading={loading} error={error} empty={reminders.length === 0} emptyText="Nenhum lembrete agendado." />
      {reminders.length > 0 && (
        <ul className="zh-fact-list">
          {reminders.map((r) => (
            <li key={r.id} className="zh-fact">
              <span className="zh-fact-body">
                <strong>{r.message}</strong>
                <span>{fmtTime(r.due_at_utc)} · {r.state}{r.source ? ` · ${r.source}` : ''}</span>
              </span>
              {cancel && r.state === 'PENDING' ? (
                <button
                  className="zh-section-danger"
                  type="button"
                  onClick={() => { cancel(r.id).then(reload).catch(() => reload()); }}
                >
                  Cancelar
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

function Aplicativos() {
  const execute = window.zaraIPC?.action?.execute;
  const { data, error, loading, reload } = useChannel(
    execute ? () => execute('os_app_list', {}) : null,
  );
  const result = (data as { result?: { success?: boolean; data?: { apps?: unknown[]; platform_supported?: boolean } } })?.result;
  const apps: Array<{ id: string; display_name: string; aliases: string[]; installed: boolean | null; running: boolean | null }> =
    Array.isArray(result?.data?.apps) ? (result!.data!.apps as never[]) : [];
  const supported = result?.data?.platform_supported !== false;
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Record<string, string>>({});

  function open(app: { id: string; display_name: string }) {
    if (!execute || busy) return;
    setBusy(app.id);
    execute('os_app', { app: app.id })
      .then((res: { result?: { success?: boolean; output?: string; error?: string } }) => {
        const r = res?.result;
        // O texto vem do executor, nunca de uma string fixa de sucesso.
        setOutcome((o) => ({ ...o, [app.id]: r?.success ? (r.output || 'Aberto.') : (r?.error || 'Não foi possível abrir.') }));
      })
      .catch((e: unknown) => setOutcome((o) => ({ ...o, [app.id]: e instanceof Error ? e.message : String(e) })))
      .finally(() => setBusy(null));
  }

  return (
    <SectionShell
      icon={<LayoutGrid size={18} strokeWidth={1.7} />}
      title="Aplicativos"
      subtitle="A mesma lista segura que a ZARA usa por voz — não uma lista paralela."
      onReload={execute ? reload : undefined}
    >
      <StateLine loading={loading} error={error} empty={apps.length === 0} emptyText="Nenhum aplicativo na lista segura." />
      {!supported && apps.length > 0 && (
        <p className="zh-section-state">Abertura de aplicativos só funciona no Windows. Aqui a lista é só leitura.</p>
      )}
      {apps.length > 0 && (
        <div className="zh-app-grid">
          {apps.map((a) => (
            <button
              key={a.id}
              className="zh-app-card"
              type="button"
              disabled={!supported || busy === a.id || a.installed === false}
              title={a.installed === false ? 'Não encontrado neste computador' : a.aliases.join(', ')}
              onClick={() => open(a)}
            >
              <strong>{a.display_name}</strong>
              <span>
                {busy === a.id ? 'Abrindo…'
                  : outcome[a.id] ? outcome[a.id]
                  : a.running ? 'Aberto agora'
                  : a.installed === false ? 'Não encontrado'
                  : a.installed === true ? 'Instalado'
                  : 'Estado desconhecido'}
              </span>
            </button>
          ))}
        </div>
      )}
    </SectionShell>
  );
}

function Lab() {
  const state = window.zaraIPC?.lab?.state;
  const { data, error, loading, reload } = useChannel(state ? () => state() : null);
  const proposals: Array<{ id: string; title: string; summary: string; risk: string; status?: string }> =
    Array.isArray((data as { proposals?: unknown })?.proposals) ? (data as { proposals: never[] }).proposals : [];
  const messages: Array<{ author: string; content: string }> =
    Array.isArray((data as { messages?: unknown })?.messages) ? (data as { messages: never[] }).messages : [];

  return (
    <SectionShell
      icon={<FlaskConical size={18} strokeWidth={1.7} />}
      title="ZARA Lab"
      subtitle="Estado real do conselho interno."
      onReload={state ? reload : undefined}
    >
      <StateLine
        loading={loading}
        error={error}
        empty={proposals.length === 0 && messages.length === 0}
        emptyText="O Lab está inicializado, mas sem propostas nem mensagens."
      />
      {proposals.length > 0 && (
        <>
          <h2 className="zh-section-subhead">Propostas</h2>
          <ul className="zh-fact-list">
            {proposals.map((p) => (
              <li key={p.id} className="zh-fact">
                <span className="zh-fact-body">
                  <strong>{p.title}</strong>
                  <span>risco {p.risk}{p.status ? ` · ${p.status}` : ''} — {p.summary}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {messages.length > 0 && (
        <>
          <h2 className="zh-section-subhead">Últimas mensagens</h2>
          <ul className="zh-msg-list">
            {messages.slice(-30).reverse().map((m, i) => (
              <li key={i} className="zh-msg">
                <span className="zh-msg-meta"><strong>{m.author}</strong></span>
                <p>{m.content}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </SectionShell>
  );
}

function Capacidades({ title, subtitle, icon }: { title: string; subtitle: string; icon: ReactNode }) {
  const selfStatus = window.zaraIPC?.system?.selfStatus;
  const { data, error, loading, reload } = useChannel(selfStatus ? () => selfStatus() : null);
  const capabilities: Array<{ label: string; status: string; detail: string }> =
    Array.isArray((data as { capabilities?: unknown })?.capabilities) ? (data as { capabilities: never[] }).capabilities : [];

  return (
    <SectionShell icon={icon} title={title} subtitle={subtitle} onReload={selfStatus ? reload : undefined}>
      <StateLine loading={loading} error={error} empty={capabilities.length === 0} emptyText="Sem leitura de capacidades." />
      {capabilities.length > 0 && (
        <ul className="zh-cap-list">
          {capabilities.map((c) => (
            <li key={c.label} className="zh-cap" data-status={c.status}>
              <span className="zh-cap-dot" />
              <span className="zh-cap-body">
                <strong>{c.label}</strong>
                <span>{c.detail}</span>
              </span>
              <span className="zh-cap-status">{c.status}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

function NaoConstruido({ icon, title, motivo }: { icon: ReactNode; title: string; motivo: string }) {
  return (
    <SectionShell icon={icon} title={title} subtitle="Ainda não construído.">
      <p className="zh-section-state">{motivo}</p>
    </SectionShell>
  );
}

/* ------------------------------------------------------------------ */

export function SectionView({ section }: { section: string }) {
  switch (section) {
    case 'Conversas': return <Conversas />;
    case 'Memórias': return <Memorias />;
    case 'Projetos': return <Projetos />;
    case 'Automações': return <Automacoes />;
    case 'Aplicativos': return <Aplicativos />;
    case 'ZARA Lab': return <Lab />;
    case 'Configurações':
      return (
        <Capacidades
          icon={<Settings size={18} strokeWidth={1.7} />}
          title="Configurações"
          subtitle="O que está realmente ligado neste runtime, lido do backend."
        />
      );
    case 'Dispositivos':
      return (
        <Capacidades
          icon={<Monitor size={18} strokeWidth={1.7} />}
          title="Dispositivos"
          subtitle="Hardware e periféricos que a ZARA consegue alcançar agora."
        />
      );
    case 'Arquivos':
      return (
        <NaoConstruido
          icon={<File size={18} strokeWidth={1.7} />}
          title="Arquivos"
          motivo={'A ZARA já mexe em arquivos por comando ("procure", "abra o último"), mas um navegador de arquivos dentro do app ainda não existe. Preferimos dizer isso a mostrar uma lista falsa.'}
        />
      );
    default:
      return null;
  }
}
