import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { LoaderCircle, Send } from 'lucide-react';
import { MemoryGalaxyModal } from './MemoryGalaxyModal';
import { ZaraLab } from './ZaraLab';
import { normalizeReminderEvent } from '../../../reminderEvents';
import { ChatMessage, normalizeHistoryResponse } from '../../lib/chatHistory';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore } from '../../lib/aecAudio';

type VoiceState = 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'PROCESSING' | 'SLEEPING' | 'MUTED';
type Theme = 'light' | 'dark';

interface Toast { id: number; text: string; kind?: 'ok' | 'warn' | 'error'; }
interface EngineOption { id: string; name: string; provider: string; status?: string; }
interface MiniLabMessage { id: string; author: string; content: string; createdAt: number; }

const initialMessages: ChatMessage[] = [];

// Os ícones são os mesmos traços do desenho do Alex, redesenhados como componentes
// para não depender de uma biblioteca que muda de forma entre versões.
const IconeHoje = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M5 17.5 3.8 21l3.8-1.5a8.4 8.4 0 1 0-2.6-2Z"/></svg>;
const IconeMemorias = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M20.8 5.9c-2.1-2.1-5.4-2.1-7.5 0L12 7.2l-1.3-1.3a5.3 5.3 0 0 0-7.5 7.5L12 22l8.8-8.6a5.3 5.3 0 0 0 0-7.5Z"/></svg>;
const IconeRotinas = () => <svg viewBox="0 0 24 24" aria-hidden="true"><rect fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" x="3.5" y="5.2" width="17" height="15" rx="2"/><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M8 3v4M16 3v4M3.5 9.2h17"/></svg>;
const IconeLab = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M9 3h6M10 3v6l-5.5 9.4A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.6L14 9V3M7.3 16h9.4"/></svg>;
const IconeSino = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M18 8.5a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7M13.7 20a2 2 0 0 1-3.4 0"/></svg>;
const IconeEscrever = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>;
const IconeMic = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3ZM5 11a7 7 0 0 0 14 0M12 18v3"/></svg>;
const IconeMicMudo = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18M9 9v3a3 3 0 0 0 4.6 2.5M15 11.5V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 10.5 6M12 18v3"/></svg>;
const IconeSol = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.6"/><path fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
const IconeTema = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M4 7h4M12 7h8M4 17h8M16 17h4M10 4v6M14 14v6"/></svg>;

const navegacao = [
  { key: 'HOME', label: 'Hoje', Icone: IconeHoje },
  { key: 'MEMORY CORE', label: 'Memórias', Icone: IconeMemorias },
  { key: 'AUTOMATIONS', label: 'Rotinas', Icone: IconeRotinas },
  { key: 'CONVERSATIONS', label: 'ZARA LAB', Icone: IconeLab },
] as const;

// A classe de estado do anel é a mesma que o CSS do Alex já espera.
function classeDoAnel(state: VoiceState): string {
  if (state === 'LISTENING') return 'orb-listening';
  if (state === 'SPEAKING') return 'orb-speaking';
  return 'orb-idle';
}

function horaCurta(timestamp: number) {
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

// As cores dos balões do Lab são as do desenho: vinho, dourado e cinza.
function tomDoAutor(author: string): string {
  const a = author.toLowerCase();
  if (a.includes('claude')) return 'wine';
  if (a.includes('openai') || a.includes('codex') || a.includes('gpt')) return 'gold';
  if (a.includes('alex')) return 'wine';
  return 'gray';
}

export const ZaraControlCenter: React.FC = () => {
  const [activeNav, setActiveNav] = useState('HOME');
  // O tema de entrada é o escuro (Sage) — é assim na interface que Alex aprovou.
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('zara-tema') === 'light' ? 'light' : 'dark');
  const [state, setState] = useState<VoiceState>('STANDBY');
  const [voiceLevel, setVoiceLevel] = useState(0.02);
  const [tomDaVoz, setTomDaVoz] = useState(0.45);
  const [mudo, setMudo] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [supercerebro, setSupercerebro] = useState(false);
  const [galaxyOpen, setGalaxyOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [historyReady, setHistoryReady] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [input, setInput] = useState('');
  const [metrics, setMetrics] = useState({ cpu: 0, memory: 0, network: 0, storage: 0 });
  const [backendOnline, setBackendOnline] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const [engines, setEngines] = useState<EngineOption[]>([]);
  const [selectedEngine, setSelectedEngine] = useState('auto_smart');
  const [voiceLabel, setVoiceLabel] = useState('GEMINI LIVE • KORE');
  const [miniLabMessages, setMiniLabMessages] = useState<MiniLabMessage[]>([]);
  const [miniLabInput, setMiniLabInput] = useState('');
  const [miniLabBusy, setMiniLabBusy] = useState(false);
  const [miniLabOnline, setMiniLabOnline] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const labFimRef = useRef<HTMLDivElement>(null);
  const toastIdRef = useRef(0);
  const historyReadyRef = useRef(false);
  const pendingHistoryMessagesRef = useRef<ChatMessage[]>([]);
  const autoVoiceStartedRef = useRef(false);

  const notify = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((current) => [...current.slice(-2), { id, text, kind }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 3200);
  }, []);

  useEffect(() => { localStorage.setItem('zara-tema', theme); }, [theme]);

  // ZARA-AEC-RENDERER-001. Só abre o microfone aqui quando o backend disser que
  // ele é o dono do áudio; no modo local o PortAudio já capturou, e duas capturas
  // concorrentes brigariam pelo dispositivo.
  const ligarAecSePreciso = useCallback(async (resultado: { audio_transport?: string } | null) => {
    if (resultado?.audio_transport !== 'renderer') return;
    const r = await iniciarAudioAec((pcm) => window.zaraIPC?.voice?.sendMicChunk?.(pcm));
    if (!r.ok) { notify('Não consegui abrir o microfone; a voz não vai ouvir você.', 'error'); return; }
    if (!r.aecAtivo) notify('Microfone aberto sem cancelamento de eco — ela pode se ouvir falar.', 'warn');
  }, [notify]);

  // ZARA-BOTAO-MUDO-005 — o backend guarda a escolha; o botão abre na cor certa.
  useEffect(() => {
    let vivo = true;
    window.zaraIPC?.voice?.mute?.()
      .then((r) => { if (vivo && r && typeof r.mudo === 'boolean') setMudo(r.mudo); })
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    const api = window.zaraIPC;
    if (!api) return;
    const offs: Array<() => void> = [];

    if (api.on?.stateChange) offs.push(api.on.stateChange((nextState: string) => setState(nextState as VoiceState)));
    // ZARA-AEC-RENDERER-001: a voz da Kore toca AQUI, no mesmo processo que captura
    // o microfone. É isso que dá ao AEC do Chromium o sinal de referência.
    if (api.on?.voiceOutputAudio) offs.push(api.on.voiceOutputAudio((data) => {
      if (data?.stop) { cortarKore(); return; }
      if (data?.pcm) tocarKore(data.pcm, data.sampleRate || 24000);
    }));
    if (api.on?.voiceLevel) offs.push(api.on.voiceLevel((level: number, tone: number, speaking: boolean) => {
      setVoiceLevel(Math.max(0, Math.min(1, level || 0)));
      if (typeof tone === 'number' && Number.isFinite(tone)) setTomDaVoz(Math.max(0, Math.min(1, tone)));
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
    if (api.on?.supercerebroChange) offs.push(api.on.supercerebroChange((active: boolean) => setSupercerebro(Boolean(active))));
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
        setEngines(list);
        const ids = new Set(list.map((engine) => engine.id));
        const preferred = String(result?.current || localStorage.getItem('zara-ai-engine') || 'auto_smart');
        const next = ids.has(preferred) ? preferred : ids.has('auto_smart') ? 'auto_smart' : (list[0]?.id || 'auto_smart');
        setSelectedEngine(next);
        localStorage.setItem('zara-ai-engine', next);
        const changePromise = api.engine?.change?.(next);
        if (changePromise) void changePromise.catch(() => undefined);
        if (result?.voice?.voice) setVoiceLabel(`${result.voice.name || 'GEMINI LIVE'} • ${result.voice.voice}`.toUpperCase());
      }).catch(() => {
        setEngines([
          { id: 'auto_smart', name: 'AUTO • INTELIGENTE', provider: 'zara' },
          { id: 'auto_economy', name: 'AUTO • ECONÔMICO', provider: 'zara' },
        ]);
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
      api.supercerebro?.status?.().then((result: any) => setSupercerebro(Boolean(result?.active && result?.connected))).catch(() => setSupercerebro(false));
    };

    refreshBackend();
    // A ZARA é voice-first: ela sobe ouvindo, sem Alex ter que clicar em nada.
    if (!autoVoiceStartedRef.current) {
      autoVoiceStartedRef.current = true;
      setState('PROCESSING');
      api.voice?.start?.().then(async (result: any) => {
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        else if (result?.mode) setVoiceLabel(String(result.mode).toUpperCase());
        setVoiceOn(true);
        setState(result?.wake_mode ? 'IDLE' : 'LISTENING');
      }).catch(() => {
        setVoiceOn(false);
        setState('STANDBY');
        notify('Voz automática indisponível; o chat de texto continua ativo.', 'warn');
      });
    }
    const refreshTimer = window.setInterval(refreshBackend, 5000);
    return () => {
      window.clearInterval(refreshTimer);
      offs.forEach((off) => off());
    };
  }, [notify, ligarAecSePreciso]);

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
    // A primeira busca sai da pilha do efeito de propósito: chamada direto ali,
    // ela dispara setState durante a montagem e cascateia render.
    const primeira = window.setTimeout(() => void refreshMiniLab(), 0);
    const timer = window.setInterval(() => void refreshMiniLab(), 3000);
    return () => { window.clearTimeout(primeira); window.clearInterval(timer); };
  }, [refreshMiniLab]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    labFimRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [miniLabMessages]);

  // Este botão controla se ela OUVE. O da onda controla se ela FALA.
  const toggleVoice = async () => {
    try {
      if (voiceOn) {
        await window.zaraIPC?.voice?.stop?.();
        pararAudioAec();
        setVoiceOn(false); setState('MUTED'); setVoiceLevel(0.02);
      } else {
        setState('PROCESSING');
        const result: any = await window.zaraIPC?.voice?.start?.();
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        else if (result?.mode) setVoiceLabel(String(result.mode).toUpperCase());
        setVoiceOn(true); setState('LISTENING');
      }
    } catch {
      setVoiceOn(false); setState('STANDBY');
      notify('O módulo de voz ainda não está disponível.', 'error');
    }
  };

  // ZARA-BOTAO-MUDO-001 / 003 — calar a voz sem desligar a ZARA. Ela continua
  // ouvindo, entendendo e executando; só para de falar.
  const alternarMudo = async () => {
    const desejado = !mudo;
    setMudo(desejado);
    try {
      const r = await window.zaraIPC?.voice?.mute?.(desejado);
      if (r && typeof r.mudo === 'boolean' && r.mudo !== desejado) setMudo(r.mudo);
      notify(desejado ? 'Ela parou de falar. Continua ouvindo e executando.' : 'Ela voltou a falar.');
    } catch {
      setMudo(!desejado);
      notify('Não consegui mudar isso agora.', 'error');
    }
  };

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (!historyReady) { notify('A conversa ainda está sendo carregada.', 'warn'); return; }
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

  const clearConversationHistory = async () => {
    if (clearingHistory || busy || voiceOn || !historyReady) return;
    if (!window.confirm('Apagar definitivamente o histórico de conversas desta ZARA?')) return;
    setClearingHistory(true);
    try {
      const clear = window.zaraIPC?.conversationHistory?.clear;
      if (!clear) throw new Error('IPC de histórico indisponível');
      const result: any = await clear();
      if (!result?.success) throw new Error('Limpeza não confirmada');
      setMessages([]);
      notify('Histórico de conversas apagado.');
    } catch {
      notify('Não foi possível apagar o histórico.', 'error');
    } finally {
      setClearingHistory(false);
    }
  };

  const changeEngine = async (engine: string) => {
    const previous = selectedEngine;
    setSelectedEngine(engine);
    try {
      const result: any = await window.zaraIPC?.engine?.change?.(engine);
      if (!result?.success) throw new Error('Engine não confirmado pelo backend');
      localStorage.setItem('zara-ai-engine', engine);
    } catch {
      setSelectedEngine(previous);
      notify('Este motor não está disponível com as chaves atuais.', 'error');
    }
  };

  const toggleSuper = async () => {
    const next = !supercerebro;
    try {
      const toggle = window.zaraIPC?.supercerebro?.toggle;
      if (!toggle) throw new Error('IPC do Supercérebro indisponível');
      const result: any = await toggle(next);
      if (!result || typeof result.active !== 'boolean') throw new Error('Resposta inválida do backend');
      const actual = Boolean(result.active && (next ? result.connected : true));
      setSupercerebro(actual);
      notify(`Supercérebro ${actual ? 'ativado' : 'desativado'}.`);
    } catch {
      setSupercerebro(false);
      notify('O gateway Hermes não confirmou a ativação.', 'error');
    }
  };

  const runDiagnostics = async () => {
    try {
      const nextMetrics: any = await window.zaraIPC?.system?.metrics?.();
      if (nextMetrics) {
        setBackendOnline(true);
        setMetrics((current) => ({
          cpu: Number(nextMetrics.cpu ?? current.cpu), memory: Number(nextMetrics.ram ?? current.memory),
          network: Number(nextMetrics.network ?? current.network), storage: Number(nextMetrics.storage ?? nextMetrics.disk ?? current.storage),
        }));
      }
      notify('Métricas atualizadas.');
    } catch {
      setBackendOnline(false);
      notify('Diagnóstico indisponível no backend atual.', 'error');
    }
  };

  const handleNavigation = (key: string) => {
    if (key === 'MEMORY CORE') { setGalaxyOpen(true); return; }
    if (key === 'AUTOMATIONS') { notify('Rotinas aparecerão aqui quando o módulo estiver disponível.', 'warn'); return; }
    setActiveNav(key);
  };

  // A deformação da corda vem do nível de voz real, não de um timer. É o mesmo
  // mecanismo do desenho do Alex: um filtro de turbulência cuja escala cresce
  // quando ela ouve ou fala.
  const nivel = Math.max(0, Math.min(1, voiceLevel));
  const escalaDaCorda = state === 'LISTENING' || state === 'SPEAKING' ? (1.2 + nivel * 9.5) : nivel * 1.6;

  return (
    <main className={`zara-preview theme-${theme} ${classeDoAnel(state)}`}>
      <section className="desktop-frame" aria-label="Interface da ZARA">
        <section className="main-window">
          <aside className="sidebar">
            <button type="button" className="brand" aria-label="ZARA" onClick={() => setActiveNav('HOME')}>
              <img className="brand-light" src="./zara-brand-light.png" alt="ZARA"/>
              <img className="brand-dark" src="./zara-brand-dark.png" alt="ZARA"/>
            </button>

            <nav aria-label="Navegação principal">
              {navegacao.map(({ key, label, Icone }) => (
                <button type="button" key={key} className={activeNav === key ? 'active' : ''} onClick={() => handleNavigation(key)}>
                  <Icone/><span>{label}</span>
                </button>
              ))}
            </nav>

            <footer>
              <div className="online-row">
                <i className={backendOnline ? 'online' : ''}/>
                <span>{backendOnline ? 'ONLINE' : 'OFFLINE'}</span>
                <button type="button" aria-label="Alternar tema" onClick={() => setTheme((c) => c === 'light' ? 'dark' : 'light')}><IconeTema/></button>
              </div>
              <div className="user-row">
                <img src="./avatar-alex.png" alt=""/>
                <span>⌄</span>
              </div>
            </footer>
          </aside>

          <div className="main-actions">
            <button type="button" aria-label="Diagnóstico" onClick={() => void runDiagnostics()} title={`CPU ${metrics.cpu.toFixed(0)}% • Memória ${metrics.memory.toFixed(0)}%`}><IconeSino/></button>
            <button type="button" aria-label="Limpar conversa" disabled={clearingHistory || busy || voiceOn || !historyReady} onClick={() => void clearConversationHistory()}><IconeEscrever/></button>
          </div>

          {activeNav === 'CONVERSATIONS' ? (
            <section className="home-stage"><div className="lab-cheio"><ZaraLab /></div></section>
          ) : (
            <section className="home-stage">
              <div className="presence-stage">
                <div
                  className="orb"
                  aria-label={`Estado do anel: ${state.toLowerCase()}`}
                  style={{
                    ['--audio-level' as any]: nivel.toFixed(3),
                    ['--audio-tone' as any]: tomDaVoz.toFixed(3),
                  }}
                >
                  <svg className="orb-filter-defs" width="0" height="0" aria-hidden="true">
                    <defs>
                      <filter id="zara-cord-vibration" x="-24%" y="-24%" width="148%" height="148%" colorInterpolationFilters="sRGB">
                        <feTurbulence type="fractalNoise" baseFrequency="0.0132 0.0871" numOctaves={1} seed={7} result="cordNoise"/>
                        <feDisplacementMap in="SourceGraphic" in2="cordNoise" scale={escalaDaCorda} xChannelSelector="R" yChannelSelector="G"/>
                      </filter>
                    </defs>
                  </svg>
                  <canvas className="spectrum-canvas" aria-hidden="true" width={194} height={194}/>
                  <img className="ring-light ring-base" src="./zara-ring-light.png" alt="Presença luminosa da ZARA"/>
                  <img className="ring-dark ring-base" src="./zara-ring-dark.png" alt=""/>
                </div>

                <form className="command-bar" onSubmit={send}>
                  <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Como posso pensar com você hoje?" aria-label="Mensagem para ZARA"/>
                  {/* microfone = ela OUVE; onda = ela FALA. Duas coisas diferentes. */}
                  <button
                    type="button"
                    className={`mic-button ${voiceOn ? 'ligado' : 'desligado'}`}
                    onClick={() => void toggleVoice()}
                    aria-pressed={voiceOn}
                    aria-label={voiceOn ? 'Microfone ligado — clique para travar' : 'Microfone travado — clique para ela ouvir'}
                    title={voiceOn ? `Ela está te ouvindo (${voiceLabel}). Clique para travar o microfone.` : 'Microfone travado. Ela não ouve nada.'}
                  >
                    {voiceOn ? <IconeMic/> : <IconeMicMudo/>}
                  </button>
                  <button
                    type="button"
                    className={`voice-button ${mudo ? 'desligado' : 'ligado'}`}
                    onClick={() => void alternarMudo()}
                    aria-pressed={!mudo}
                    aria-label={mudo ? 'Voz silenciada — clique para ela voltar a falar' : 'Silenciar a voz dela'}
                    title={mudo ? 'Calada. Clique para ela voltar a falar.' : 'Ela fala. Clique para calar (continua ouvindo e executando).'}
                  >
                    <span className="voice-bars"><i/><i/><i/><i/><i/></span>
                  </button>
                </form>
                {messages.length > 0 && (
                  <section className="conversa-recente" ref={logRef} aria-label="Conversa recente">
                    {messages.slice(-4).map((message, index) => (
                      <article key={message.id || `${message.timestamp}-${index}`} className={message.role}>
                        <strong>{message.role === 'assistant' ? 'ZARA' : message.role === 'system' ? 'Sistema' : 'Você'}</strong>
                        <p>{message.content}</p>
                        <time>{horaCurta(message.timestamp)}</time>
                      </article>
                    ))}
                  </section>
                )}

              </div>

              <aside className="today-card">
                <header><div><IconeSol/><strong>Hoje</strong></div><span>•••</span></header>
                <article><span className="agenda-symbol">▣</span><div><strong>Reunião de projeto</strong><small>10:00</small></div></article>
                <article><span className="agenda-symbol plane">⌁</span><div><strong>Viagem</strong><small>15:30&nbsp; · &nbsp;Guarulhos</small></div></article>
                <article className="priority"><span className="agenda-symbol">☆</span><div><strong>Prioridade do dia</strong><small>Preparar relatório<br/>estratégico</small></div></article>
                <label className="motor-de-ia">
                  Motor de IA
                  <select value={selectedEngine} disabled={supercerebro || engines.length === 0} onChange={(e) => void changeEngine(e.target.value)}>
                    {engines.map((engine) => <option key={engine.id} value={engine.id}>{engine.name}</option>)}
                  </select>
                </label>
              </aside>
            </section>
          )}
        </section>

        <aside className="lab-window">
          <div className="window-controls">
            <button type="button" aria-label="Minimizar" onClick={() => window.zaraIPC?.window?.minimize?.()}>—</button>
            <button type="button" aria-label="Maximizar" onClick={() => window.zaraIPC?.window?.maximize?.()}><i/></button>
            <button type="button" aria-label="Fechar" onClick={() => window.zaraIPC?.window?.close?.()}>×</button>
          </div>
          <img className="lab-watermark" src="./zara-lab-watermark.png" alt=""/>
          <div className="participants">
            <div><img src="./avatar-claude.png" alt="Claude"/><small>Claude</small></div>
            <div><img src="./avatar-openai.png" alt="OpenAI"/><small>OpenAI</small></div>
            <div><img src="./avatar-zara.png" alt="ZARA"/><small>ZARA</small></div>
          </div>
          <div className="lab-messages">
            {miniLabMessages.length === 0 ? (
              <article className="gray"><p>{miniLabOnline ? 'O laboratório aguarda mensagens reais.' : 'ZARA Lab indisponível.'}</p></article>
            ) : miniLabMessages.map((message) => (
              <article key={message.id} className={tomDoAutor(message.author)}>
                <strong>{message.author === 'alex' ? 'Alex' : message.author.toUpperCase()}</strong>
                <p>{message.content}</p>
              </article>
            ))}
            <div ref={labFimRef}/>
          </div>
          <form className="lab-composer" onSubmit={sendMiniLab}>
            <input value={miniLabInput} onChange={(e) => setMiniLabInput(e.target.value)} placeholder="Participar da conversa..." aria-label="Mensagem para o ZARA Lab"/>
            <button type="submit" disabled={miniLabBusy || !miniLabInput.trim()} aria-label="Enviar">
              {miniLabBusy ? <LoaderCircle className="spin" size={15}/> : <Send size={16}/>}
            </button>
          </form>
          <button type="button" className={`hermes ${supercerebro ? 'ativo' : ''}`} onClick={() => void toggleSuper()}>
            {supercerebro ? 'Hermes conectado' : 'Conectar Hermes'}
          </button>
        </aside>
      </section>

      <div className="zara-toasts">{toasts.map((t) => <div key={t.id} className={`zara-toast ${t.kind || 'ok'}`}>{t.text}</div>)}</div>
      {galaxyOpen && <MemoryGalaxyModal onClose={() => setGalaxyOpen(false)}/>}
    </main>
  );
};
