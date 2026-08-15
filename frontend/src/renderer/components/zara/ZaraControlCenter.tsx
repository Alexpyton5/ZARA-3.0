import React, { CSSProperties, FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  AudioLines, Bell, CalendarDays, ChevronDown, CircleDot, FlaskConical,
  Heart, LoaderCircle, MessageCircle, Mic, MicOff, Send,
  SlidersHorizontal, SquarePen, SunMedium
} from 'lucide-react';
import { MemoryGalaxyModal } from './MemoryGalaxyModal';
import { ZaraLab } from './ZaraLab';
import { normalizeReminderEvent } from '../../../reminderEvents';
import { ChatMessage, normalizeHistoryResponse } from '../../lib/chatHistory';
import '../../styles/pearl.css';

type VoiceState = 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'PROCESSING' | 'SLEEPING' | 'MUTED';
type Theme = 'light' | 'dark';

interface Toast { id: number; text: string; kind?: 'ok' | 'warn' | 'error'; }
interface EngineOption { id: string; name: string; provider: string; status?: string; }
interface MiniLabMessage { id: string; author: string; content: string; createdAt: number; }

const ZaraMark: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg className={`zara-mark ${className}`} viewBox="0 0 124 96" role="img" aria-label="Símbolo ZA">
    <path className="zara-mark-z" d="M13 17.5H74.5L28 77.5H91" />
    <path className="zara-mark-a" d="M59 77.5 87 24l27 53.5H59Zm16-19h29" />
  </svg>
);

const initialMessages: ChatMessage[] = [];

const navigation = [
  { key: 'HOME', label: 'Hoje', icon: MessageCircle },
  { key: 'MEMORY CORE', label: 'Memórias', icon: Heart },
  { key: 'AUTOMATIONS', label: 'Rotinas', icon: CalendarDays },
  { key: 'CONVERSATIONS', label: 'ZARA LAB', icon: FlaskConical },
] as const;

const orbStateLabel: Record<VoiceState, string> = {
  STANDBY: 'Em espera', IDLE: 'Em espera', LISTENING: 'Ouvindo', THINKING: 'Pensando',
  SPEAKING: 'Falando', PROCESSING: 'Processando', SLEEPING: 'Em repouso', MUTED: 'Microfone mutado',
};

function timeLabel(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function normalizeLabMessages(raw: unknown): MiniLabMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw.slice(-8).flatMap((entry: any, index: number) => {
    const content = typeof entry?.content === 'string' ? entry.content.trim() : '';
    if (!content) return [];
    const epoch = Number(entry?.created_at ?? 0);
    return [{
      id: String(entry?.id ?? `${epoch}-${index}`),
      author: String(entry?.author ?? 'zara'),
      content,
      createdAt: epoch > 0 && epoch < 10_000_000_000 ? epoch * 1000 : (epoch || Date.now()),
    }];
  });
}

export const ZaraControlCenter: React.FC = () => {
  const [activeNav, setActiveNav] = useState('HOME');
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('zara-theme') === 'dark' ? 'dark' : 'light');
  const [state, setState] = useState<VoiceState>('STANDBY');
  const [voiceLevel, setVoiceLevel] = useState(0.02);
  const [voiceOn, setVoiceOn] = useState(false);
  const [galaxyOpen, setGalaxyOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [historyReady, setHistoryReady] = useState(false);
  const [input, setInput] = useState('');
  const [metrics, setMetrics] = useState({ cpu: 0, memory: 0, network: 0, storage: 0 });
  const [backendOnline, setBackendOnline] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const [selectedEngine, setSelectedEngine] = useState('auto_smart');
  const [voiceLabel, setVoiceLabel] = useState('GEMINI LIVE • KORE');
  const [miniLabMessages, setMiniLabMessages] = useState<MiniLabMessage[]>([]);
  const [miniLabInput, setMiniLabInput] = useState('');
  const [miniLabBusy, setMiniLabBusy] = useState(false);
  const [miniLabOnline, setMiniLabOnline] = useState(false);
  const commandInputRef = useRef<HTMLInputElement>(null);
  const miniLabEndRef = useRef<HTMLDivElement>(null);
  const toastIdRef = useRef(0);
  const historyReadyRef = useRef(false);
  const pendingHistoryMessagesRef = useRef<ChatMessage[]>([]);

  const notify = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((current) => [...current.slice(-2), { id, text, kind }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 3200);
  }, []);

  useEffect(() => {
    localStorage.setItem('zara-theme', theme);
  }, [theme]);

  useEffect(() => {
    const api = window.zaraIPC;
    if (!api) return;
    const offs: Array<() => void> = [];

    if (api.on?.stateChange) offs.push(api.on.stateChange((nextState: string) => setState(nextState as VoiceState)));
    if (api.on?.voiceLevel) offs.push(api.on.voiceLevel((level: number, _tone: number, speaking: boolean) => {
      setVoiceLevel(Math.max(0, Math.min(1, level || 0)));
      if (speaking) setState('SPEAKING');
    }));
    if (api.on?.message) offs.push(api.on.message((message: { role: string; content: string }) => {
      if (!message?.content) return;
      const incoming: ChatMessage = {
        role: message.role === 'user' ? 'user' : message.role === 'system' ? 'system' : 'assistant',
        content: message.content,
        timestamp: Date.now(),
      };
      if (!historyReadyRef.current) pendingHistoryMessagesRef.current.push(incoming);
      else setMessages((current) => [...current, incoming]);
    }));
    if (api.on?.metrics) offs.push(api.on.metrics((nextMetrics: any) => {
      setMetrics((current) => ({
        cpu: Number(nextMetrics?.cpu ?? current.cpu),
        memory: Number(nextMetrics?.ram ?? nextMetrics?.memory ?? current.memory),
        network: Number(nextMetrics?.network ?? current.network),
        storage: Number(nextMetrics?.storage ?? nextMetrics?.disk ?? current.storage),
      }));
    }));
    if (api.on?.reminderFired) offs.push(api.on.reminderFired((rawReminder: unknown) => {
      const reminder = normalizeReminderEvent(rawReminder);
      if (!reminder) return;
      const incoming: ChatMessage = { role: 'assistant', content: `🔔 Lembrete: ${reminder.text}`, timestamp: Date.now() };
      if (!historyReadyRef.current) pendingHistoryMessagesRef.current.push(incoming);
      else setMessages((current) => [...current, incoming]);
      notify(`🔔 ${reminder.text}`);
    }));

    const completeHistoryLoad = (persisted: ChatMessage[]) => {
      const pending = pendingHistoryMessagesRef.current;
      pendingHistoryMessagesRef.current = [];
      historyReadyRef.current = true;
      setMessages([...persisted, ...pending]);
      setHistoryReady(true);
    };

    const historyPromise = api.conversationHistory?.list?.(500);
    if (historyPromise) historyPromise.then((result: unknown) => completeHistoryLoad(normalizeHistoryResponse(result))).catch(() => completeHistoryLoad([]));
    else void Promise.resolve().then(() => completeHistoryLoad([]));

    const engineListPromise = api.engine?.list?.();
    if (engineListPromise) {
      engineListPromise.then((result: any) => {
        const list: EngineOption[] = Array.isArray(result?.engines) ? result.engines : [];
        const ids = new Set(list.map((engine) => engine.id));
        const preferred = String(result?.current || localStorage.getItem('zara-ai-engine') || 'auto_smart');
        const next = ids.has(preferred) ? preferred : ids.has('auto_smart') ? 'auto_smart' : (list[0]?.id || 'auto_smart');
        setSelectedEngine(next);
        localStorage.setItem('zara-ai-engine', next);
        const changePromise = api.engine?.change?.(next);
        if (changePromise) void changePromise.catch(() => undefined);
        if (result?.voice?.voice) setVoiceLabel(`${result.voice.name || 'GEMINI LIVE'} • ${result.voice.voice}`.toUpperCase());
      }).catch(() => {
        setSelectedEngine('auto_smart');
      });
    }

    const refreshBackend = () => {
      api.system?.metrics?.().then((nextMetrics: any) => {
        setBackendOnline(true);
        setMetrics((current) => ({
          cpu: Number(nextMetrics?.cpu ?? current.cpu), memory: Number(nextMetrics?.ram ?? current.memory),
          network: Number(nextMetrics?.network ?? current.network), storage: Number(nextMetrics?.storage ?? nextMetrics?.disk ?? current.storage),
        }));
      }).catch(() => setBackendOnline(false));
    };

    refreshBackend();
    const refreshTimer = window.setInterval(refreshBackend, 5000);
    return () => {
      window.clearInterval(refreshTimer);
      offs.forEach((off) => off());
    };
  }, [notify]);

  const refreshMiniLab = useCallback(async () => {
    try {
      const snapshot: any = await window.zaraIPC?.lab?.state?.();
      if (!snapshot || !Array.isArray(snapshot.messages)) throw new Error('Estado do Lab indisponível');
      setMiniLabMessages(normalizeLabMessages(snapshot.messages));
      setMiniLabOnline(true);
    } catch {
      setMiniLabOnline(false);
    }
  }, []);

  useEffect(() => {
    void refreshMiniLab();
    const timer = window.setInterval(() => void refreshMiniLab(), 3000);
    return () => window.clearInterval(timer);
  }, [refreshMiniLab]);

  useEffect(() => {
    miniLabEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [miniLabMessages]);

  const toggleVoice = async () => {
    try {
      if (voiceOn) {
        await window.zaraIPC?.voice?.stop?.();
        setVoiceOn(false);
        setState('MUTED');
        setVoiceLevel(0.02);
      } else {
        const result: any = await window.zaraIPC?.voice?.start?.();
        if (result?.mode === 'gemini_live') setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        else if (result?.mode) setVoiceLabel(String(result.mode).toUpperCase());
        setVoiceOn(true);
        setState('LISTENING');
      }
    } catch {
      notify('O módulo de voz ainda não está disponível.', 'error');
    }
  };

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (!historyReady) {
      notify('A conversa ainda está sendo carregada.', 'warn');
      return;
    }
    const userMessage: ChatMessage = { role: 'user', content: text, timestamp: Date.now() };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setBusy(true);
    setState('THINKING');
    try {
      const history = [...messages, userMessage]
        .filter((message) => message.role !== 'system')
        .slice(-16)
        .map((message) => ({ role: message.role === 'assistant' ? 'assistant' : 'user', content: message.content }));
      const response: any = await window.zaraIPC?.message?.send?.({ message: text, engine: selectedEngine, history });
      const content = String(response?.content ?? response?.response ?? response?.message ?? response ?? '').trim();
      if (content) setMessages((current) => [...current, { role: 'assistant', content, timestamp: Date.now() }]);
    } catch {
      setMessages((current) => [...current, { role: 'system', content: 'Backend indisponível para esta solicitação.', timestamp: Date.now() }]);
    } finally {
      setBusy(false);
      setState(voiceOn ? 'LISTENING' : 'STANDBY');
    }
  };

  const sendMiniLab = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = miniLabInput.trim();
    if (!content || miniLabBusy) return;
    setMiniLabBusy(true);
    setMiniLabInput('');
    try {
      const sender = window.zaraIPC?.lab?.send;
      if (!sender) throw new Error('IPC do Lab indisponível');
      await sender({ author: 'alex', target: 'zara', content });
      await refreshMiniLab();
    } catch {
      setMiniLabInput(content);
      notify('Não foi possível participar do ZARA Lab agora.', 'error');
    } finally {
      setMiniLabBusy(false);
    }
  };

  const handleNavigation = (key: string) => {
    if (key === 'MEMORY CORE') {
      setGalaxyOpen(true);
      return;
    }
    if (key === 'AUTOMATIONS') {
      notify('Rotinas aparecerão aqui quando o módulo estiver disponível.', 'warn');
      return;
    }
    setActiveNav(key);
  };

  const orbStyle = {
    '--voice-level': voiceLevel,
    '--voice-glow': `${13 + voiceLevel * 25}px`,
    '--voice-scale': 1.015 + voiceLevel * 0.055,
    '--voice-halo': 1.1 + voiceLevel * 0.15,
  } as CSSProperties;

  return (
    <div className={`pearl-desktop theme-${theme}`}>
      <section className="pearl-window" aria-label="Interface principal da ZARA">
        <header className="pearl-titlebar">
          <div className="pearl-titlebar-drag" />
          <div className="pearl-title-actions" aria-label="Ações rápidas">
            <button type="button" onClick={() => notify('Sem novas notificações.')} aria-label="Notificações"><Bell size={20}/></button>
            <button type="button" onClick={() => commandInputRef.current?.focus()} aria-label="Nova conversa"><SquarePen size={20}/></button>
          </div>
        </header>

        <aside className="pearl-sidebar">
          <button type="button" className="pearl-brand" onClick={() => setActiveNav('HOME')} aria-label="Voltar para Hoje">
            <ZaraMark />
            <span>ZARA</span>
          </button>

          <nav className="pearl-navigation" aria-label="Navegação principal">
            {navigation.map(({ key, label, icon: Icon }) => (
              <button type="button" key={key} className={activeNav === key ? 'active' : ''} onClick={() => handleNavigation(key)}>
                <Icon size={20}/><span>{label}</span>
              </button>
            ))}
          </nav>

          <div className="pearl-sidebar-footer">
            <div className={`pearl-online ${backendOnline ? 'online' : ''}`}><i/><span>{backendOnline ? 'ONLINE' : 'OFFLINE'}</span></div>
            <button type="button" className="pearl-diagnostics" onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')} title={`Alternar tema • CPU ${metrics.cpu.toFixed(0)}% • Memória ${metrics.memory.toFixed(0)}%`} aria-label={theme === 'light' ? 'Ativar tema escuro' : 'Ativar tema claro'}><SlidersHorizontal size={18}/></button>
            <div className="pearl-user"><span>A</span><div><strong>Alex</strong><small>{backendOnline ? 'ZARA conectada' : 'Modo local'}</small></div><ChevronDown size={16}/></div>
          </div>
        </aside>

        <div className={`pearl-window-content ${activeNav === 'CONVERSATIONS' ? 'lab-open' : ''}`}>
          {activeNav === 'CONVERSATIONS' ? (
            <div className="pearl-lab-full"><ZaraLab /></div>
          ) : (
            <div className="pearl-home">
              <main className="pearl-center-stage">
                <section className={`pearl-orb state-${state.toLowerCase()}`} style={orbStyle} aria-label={`Estado da ZARA: ${orbStateLabel[state]}`}>
                  <div className="pearl-orb-halo" />
                  <img className="pearl-orb-image" src="./zara-orb-pearl.png" alt=""/>
                </section>

                <form className="pearl-command" onSubmit={send}>
                  <input ref={commandInputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder="Como posso pensar com você hoje?" aria-label="Mensagem para ZARA"/>
                  <button type="button" className={`pearl-mute ${voiceOn ? 'active' : ''}`} onClick={() => void toggleVoice()} aria-label={voiceOn ? 'Mutar microfone' : 'Ativar microfone'} title={voiceLabel}>
                    {voiceOn ? <Mic size={20}/> : <MicOff size={20}/>} 
                  </button>
                  <button type="button" className={`pearl-voice ${voiceOn ? 'active' : ''}`} onClick={() => void toggleVoice()} aria-label="Modo voz"><AudioLines size={22}/></button>
                  <button type="submit" className="pearl-send" disabled={busy || !historyReady || !input.trim()} aria-label="Enviar mensagem">
                    {busy ? <LoaderCircle className="spin" size={20}/> : <Send size={20}/>} 
                  </button>
                </form>
              </main>

              <aside className="pearl-today-card">
                <header><div><SunMedium size={22}/><strong>Hoje</strong></div><button type="button" aria-label="Mais opções">•••</button></header>
                <div className="pearl-agenda-item"><span className="agenda-icon">▣</span><div><strong>Reunião de projeto</strong><small>10:00</small></div></div>
                <div className="pearl-agenda-item"><span className="agenda-icon">⌁</span><div><strong>Viagem</strong><small>15:30&nbsp; · &nbsp;Guarulhos</small></div></div>
                <div className="pearl-agenda-item priority"><span className="agenda-icon">☆</span><div><strong>Prioridade do dia</strong><small>Preparar relatório estratégico</small></div></div>
              </aside>
            </div>
          )}
        </div>
      </section>

      <aside className={`pearl-mini-lab ${miniLabOnline ? 'online' : ''}`} aria-label="Mini ZARA Lab">
        <div className="pearl-lab-mini-controls" aria-label="Controles da janela">
          <button type="button" onClick={() => window.zaraIPC?.window?.minimize?.()} aria-label="Minimizar"><span aria-hidden="true">—</span></button>
          <button type="button" onClick={() => window.zaraIPC?.window?.maximize?.()} aria-label="Maximizar ou restaurar"><span className="maximize-glyph" aria-hidden="true"/></button>
          <button type="button" className="close" onClick={() => window.zaraIPC?.window?.close?.()} aria-label="Fechar"><span aria-hidden="true">×</span></button>
        </div>
        <div className="pearl-lab-watermark"><ZaraMark/><span>ZARA</span></div>
        <div className="pearl-lab-participants" aria-label="Perfis de IA do laboratório">
          <div><span className="claude">C</span><small>Claude</small></div>
          <div><span className="openai">O</span><small>OpenAI</small></div>
          <div><span className="zara"><ZaraMark/></span><small>ZARA</small></div>
        </div>

        <div className="pearl-lab-messages">
          {miniLabMessages.length === 0 ? (
            <div className="pearl-lab-empty"><CircleDot size={15}/><span>{miniLabOnline ? 'O laboratório aguarda mensagens reais.' : 'ZARA Lab indisponível.'}</span></div>
          ) : miniLabMessages.slice(-4).map((message) => (
            <article key={message.id} className={`from-${message.author.toLowerCase()}`}>
              <strong>{message.author === 'alex' ? 'Alex' : message.author.toUpperCase()}</strong>
              <p>{message.content}</p>
              <time>{timeLabel(message.createdAt)}</time>
            </article>
          ))}
          <div ref={miniLabEndRef}/>
        </div>

        <form className="pearl-lab-composer" onSubmit={sendMiniLab}>
          <input value={miniLabInput} onChange={(event) => setMiniLabInput(event.target.value)} placeholder="Participar da conversa..." aria-label="Mensagem para o ZARA Lab"/>
          <button type="submit" disabled={miniLabBusy || !miniLabInput.trim()} aria-label="Enviar para o ZARA Lab">{miniLabBusy ? <LoaderCircle className="spin" size={16}/> : <Send size={17}/>}</button>
        </form>
      </aside>

      <div className="pearl-toast-stack">{toasts.map((toast) => <div key={toast.id} className={`pearl-toast ${toast.kind || 'ok'}`}>{toast.text}</div>)}</div>
      {galaxyOpen && <MemoryGalaxyModal onClose={() => setGalaxyOpen(false)}/>} 
    </div>
  );
};
