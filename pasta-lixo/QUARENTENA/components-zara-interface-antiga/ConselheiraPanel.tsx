// Painel "Conselheira" — conversa contínua com a zoe (Muse) via ponte Gmail.
// É a visão "Jarvis" do Alex: a zoe como conselheira/CEO dentro da ZARA.
// As mensagens viajam por e-mail (zoeeproject@gmail.com); a ponte é
// sincronizada a cada 5 minutos enquanto o painel está aberto.
import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity, Bot, Clock3, LoaderCircle, Mail, MessageSquareText,
  RefreshCw, Send, Sparkles, UserRound, X
} from 'lucide-react';

type ConselheiraMessage = {
  chat_id: string;
  role: string;
  text: string;
  created_at: number;
};

type ConselheiraStatus = {
  pending: number;
  awaiting_reply: number;
  mailbox: string;
  transport: string;
  tag: string;
  check_interval_seconds: number;
  last_sync_at: number | null;
};

const FALLBACK_INTERVAL_MS = 5 * 60 * 1000; // 5 minutos (padrão da ponte)

function readableTime(ts: number) {
  return new Date(ts * 1000).toLocaleString([], {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function lastSyncLabel(ts: number | null) {
  if (!ts) return 'NUNCA';
  const mins = Math.floor((Date.now() / 1000 - ts) / 60);
  if (mins < 1) return 'AGORA';
  if (mins < 60) return `HÁ ${mins} MIN`;
  return readableTime(ts).toUpperCase();
}

export const ConselheiraPanel: React.FC = () => {
  const [messages, setMessages] = useState<ConselheiraMessage[]>([]);
  const [status, setStatus] = useState<ConselheiraStatus | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const api = window.zaraIPC?.conselheira;
    if (!api) {
      setError('Ponte Conselheira indisponível no backend.');
      setLoading(false);
      return;
    }
    try {
      const [msgs, st] = await Promise.all([
        api.getMessages?.({ limit: 200 }),
        api.getStatus?.(),
      ]);
      setMessages(Array.isArray(msgs) ? (msgs as ConselheiraMessage[]) : []);
      setStatus((st as ConselheiraStatus) ?? null);
    } catch (e) {
      setError(`Falha ao carregar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const doSync = useCallback(async () => {
    const api = window.zaraIPC?.conselheira;
    if (!api || syncing) return;
    setSyncing(true);
    try {
      const result = (await api.sync?.()) as { replies?: unknown[] } | undefined;
      await refresh();
      if (result?.replies && result.replies.length > 0) {
        setError('');
      }
    } catch (e) {
      setError(`Falha na sincronização: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSyncing(false);
    }
  }, [refresh, syncing]);

  useEffect(() => {
    // Carga inicial do painel (o intervalo de auto-sync é configurado abaixo).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  // Sincronização automática a cada 5 minutos (padrão da ponte).
  useEffect(() => {
    const intervalMs = (status?.check_interval_seconds || 300) * 1000 || FALLBACK_INTERVAL_MS;
    const timer = window.setInterval(() => { void doSync(); }, intervalMs);
    return () => window.clearInterval(timer);
  }, [doSync, status?.check_interval_seconds]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const sendMessage = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    const api = window.zaraIPC?.conselheira;
    if (!text || sending || !api) return;
    setSending(true);
    setError('');
    try {
      await api.sendMessage?.({ text });
      setInput('');
      await refresh();
    } catch (err) {
      setError(`Falha ao enviar: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="lab-stage">
      <section className="lab-topline">
        <div>
          <span className="lab-kicker"><Sparkles size={14}/> CONSELHEIRA</span>
          <h1>ZOE — SUA CONSELHEIRA</h1>
          <p>Conversa contínua com a zoe (Muse) dentro da ZARA. Cada mensagem viaja pela ponte Gmail com um snapshot da ZARA anexado; a resposta chega em alguns minutos.</p>
        </div>
        <div className="lab-runtime-status">
          <span><Mail size={14}/> PONTE <strong>{status?.mailbox || '…'}</strong></span>
          <span><Clock3 size={14}/> SYNC <strong>{lastSyncLabel(status?.last_sync_at ?? null)}</strong></span>
          <button onClick={() => void doSync()} title="Sincronizar agora" disabled={syncing}>
            {syncing ? <LoaderCircle className="spin" size={14}/> : <RefreshCw size={14}/>}
          </button>
        </div>
      </section>

      <div className="lab-grid">
        <section className="lab-panel lab-council">
          <header className="lab-panel-header">
            <div><MessageSquareText size={15}/><span>CONVERSA</span></div>
            <em>
              {status ? `${status.pending} PENDENTE(S) • ${status.awaiting_reply} AGUARDANDO ZOE` : 'CARREGANDO…'}
            </em>
          </header>
          <div className="lab-chat-scroll">
            {loading && <div className="lab-empty"><LoaderCircle className="spin" size={18}/> CARREGANDO CONVERSA...</div>}
            {!loading && messages.length === 0 && (
              <div className="lab-empty">Nenhuma conversa ainda. Pergunte algo à zoe — ela responde como sua conselheira.</div>
            )}
            {messages.map((m) => {
              const isAlex = m.role === 'alex';
              const Icon = isAlex ? UserRound : Bot;
              return (
                <article className={`lab-message ${isAlex ? 'alex' : ''}`} key={`${m.chat_id}-${m.created_at}-${m.role}`}>
                  <div className="lab-message-avatar"><Icon size={15}/></div>
                  <div className="lab-message-content">
                    <div><strong>{isAlex ? 'ALEX' : 'ZOE'}</strong><time>{readableTime(m.created_at)}</time></div>
                    <p>{m.text}</p>
                  </div>
                </article>
              );
            })}
            <div ref={chatEndRef}/>
          </div>
          <form className="lab-composer" onSubmit={sendMessage}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Fale com a zoe..."
              aria-label="Mensagem para a zoe"
            />
            <button type="submit" disabled={!input.trim() || sending}>
              {sending ? <LoaderCircle className="spin" size={17}/> : <Send size={17}/>}
            </button>
          </form>
          {error && <div className="lab-error"><Activity size={13}/>{error}<button onClick={() => setError('')}><X size={12}/></button></div>}
          <p className="panel-caption" style={{ padding: '8px 16px' }}>
            A ponte sincroniza sozinha a cada 5 minutos. A zoe tem autonomia total: decide tudo, e cada decisão fica registrada na fila local (auditável).
          </p>
        </section>
      </div>
    </main>
  );
};
