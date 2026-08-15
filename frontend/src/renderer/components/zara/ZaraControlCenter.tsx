import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Home, MessageCircle, Brain, Zap, Database, Box, SlidersHorizontal, Mic, MicOff, Send,
  Minimize, Square, X, Bell, Activity, Grid3X3, ShieldCheck, Cpu, Network,
  Search, RefreshCw, ChevronRight, Bot,
  Palette, Wrench, BrainCircuit, CircleDot, LoaderCircle, Trash2,
  Volume2, VolumeX
} from 'lucide-react';
import { VoiceParticleSphere, VoiceState } from './VoiceParticleSphere';
import { MemoryGalaxyModal } from './MemoryGalaxyModal';
import { PainelAparencia } from './PainelAparencia';
import { ConversaInstrumento } from './ConversaInstrumento';
import { ZaraLab } from './ZaraLab';
import { normalizeReminderEvent } from '../../../reminderEvents';
import { ChatMessage, normalizeHistoryResponse } from '../../lib/chatHistory';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore } from '../../lib/aecAudio';
import { APARENCIA_INICIAL } from '../../lib/aparencia';

interface Toast { id: number; text: string; kind?: 'ok' | 'warn' | 'error'; }
interface EngineOption { id: string; name: string; provider: string; free_tier?: string; status?: string; }

type HermesAgent = 'appearance' | 'intelligence' | 'functionality';

const nav = [
  ['HOME', Home], ['CONVERSATIONS', MessageCircle], ['INTELLIGENCE', Brain],
  ['AUTOMATIONS', Zap], ['DATA HUB', Database], ['MEMORY CORE', Box],
  ['SYSTEMS', SlidersHorizontal], ['SETTINGS', SlidersHorizontal],
] as const;

const initialMessages: ChatMessage[] = [];

function timeLabel(ts: number) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export const ZaraControlCenter: React.FC = () => {
  const [activeNav, setActiveNav] = useState('HOME');
  const [state, setState] = useState<VoiceState>('STANDBY');
  const [voiceLevel, setVoiceLevel] = useState(0.02);
  const [mudo, setMudo] = useState(false);   // ZARA-BOTAO-MUDO-001
  const [voiceOn, setVoiceOn] = useState(false);
  const [supercerebro, setSupercerebro] = useState(false);
  const [galaxyOpen, setGalaxyOpen] = useState(false);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [interfaceNova, setInterfaceNova] = useState(() => APARENCIA_INICIAL?.interfaceNova ?? false);
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
  const logRef = useRef<HTMLDivElement>(null);
  const toastIdRef = useRef(0);
  const historyReadyRef = useRef(false);
  const pendingHistoryMessagesRef = useRef<ChatMessage[]>([]);
  const autoVoiceStartedRef = useRef(false);

  const notify = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((t) => [...t.slice(-2), { id, text, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);

  // ZARA-AEC-RENDERER-001. Só abre o microfone aqui quando o backend disser que
  // ele é o dono do áudio; no modo local o PortAudio já capturou, e duas
  // capturas concorrentes brigariam pelo dispositivo.
  const ligarAecSePreciso = useCallback(async (resultado: { audio_transport?: string } | null) => {
    if (resultado?.audio_transport !== 'renderer') return;
    const r = await iniciarAudioAec((pcm) => window.zaraIPC?.voice?.sendMicChunk?.(pcm));
    if (!r.ok) {
      notify('Não consegui abrir o microfone; a voz não vai ouvir você.', 'error');
      return;
    }
    if (!r.aecAtivo) {
      notify('Microfone aberto sem cancelamento de eco — ela pode se ouvir falar.', 'warn');
    }
  }, [notify]);

  useEffect(() => {
    const api = window.zaraIPC;
    if (!api) return;
    const offs: Array<() => void> = [];
    if (api.on?.stateChange) offs.push(api.on.stateChange((s) => setState(s as VoiceState)));
    // ZARA-AEC-RENDERER-001: a voz da Kore toca AQUI, no mesmo processo que
    // captura o microfone. É isso que dá ao AEC do Chromium o sinal de
    // referência e impede a ZARA de responder ao próprio alto-falante.
    if (api.on?.voiceOutputAudio) offs.push(api.on.voiceOutputAudio((data) => {
      if (data?.stop) { cortarKore(); return; }
      if (data?.pcm) tocarKore(data.pcm, data.sampleRate || 24000);
    }));
    if (api.on?.voiceLevel) offs.push(api.on.voiceLevel((level, _tone, speaking) => {
      setVoiceLevel(Math.max(0, Math.min(1, level || 0)));
      if (speaking) setState('SPEAKING');
    }));
    if (api.on?.message) offs.push(api.on.message((m) => {
      if (!m?.content) return;
      const incoming: ChatMessage = { role: (m.role === 'user' ? 'user' : m.role === 'system' ? 'system' : 'assistant'), content: m.content, timestamp: Date.now() };
      if (!historyReadyRef.current) {
        pendingHistoryMessagesRef.current.push(incoming);
      } else {
        setMessages((old) => [...old, incoming]);
      }
    }));
    if (api.on?.metrics) offs.push(api.on.metrics((m) => {
      setMetrics((old) => ({
        cpu: Number(m?.cpu ?? old.cpu), memory: Number(m?.ram ?? m?.memory ?? old.memory),
        network: Number(m?.network ?? old.network), storage: Number(m?.storage ?? m?.disk ?? old.storage),
      }));
    }));
    if (api.on?.supercerebroChange) offs.push(api.on.supercerebroChange((active) => setSupercerebro(Boolean(active))));
    if (api.on?.reminderFired) offs.push(api.on.reminderFired((rawReminder) => {
      const reminder = normalizeReminderEvent(rawReminder);
      if (!reminder) return;
      const incoming: ChatMessage = {
        role: 'assistant',
        content: `🔔 Lembrete: ${reminder.text}`,
        timestamp: Date.now(),
      };
      if (!historyReadyRef.current) {
        pendingHistoryMessagesRef.current.push(incoming);
      } else {
        setMessages((old) => [...old, incoming]);
      }
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
    if (historyPromise) {
      historyPromise
        .then((result: unknown) => completeHistoryLoad(normalizeHistoryResponse(result)))
        .catch(() => completeHistoryLoad([]));
    } else {
      void Promise.resolve().then(() => completeHistoryLoad([]));
    }

    const engineListPromise = api.engine?.list?.();
    if (engineListPromise) {
      engineListPromise.then((result: any) => {
        const list: EngineOption[] = Array.isArray(result?.engines) ? result.engines : [];
        setEngines(list);
        const availableIds = new Set(list.map((item) => item.id));
        const preferred = String(result?.current || localStorage.getItem('zara-ai-engine') || 'auto_smart');
        const next = availableIds.has(preferred) ? preferred : (availableIds.has('auto_smart') ? 'auto_smart' : (list[0]?.id || 'auto_smart'));
        setSelectedEngine(next);
        localStorage.setItem('zara-ai-engine', next);
        const changePromise = api.engine?.change?.(next);
        if (changePromise) void changePromise.catch(() => undefined);
        const voice = result?.voice;
        if (voice?.voice) setVoiceLabel(`${voice?.name || 'GEMINI LIVE'} • ${voice.voice}`.toUpperCase());
      }).catch(() => {
        setEngines([{ id: 'auto_smart', name: 'AUTO • INTELIGENTE', provider: 'zara' }, { id: 'auto_economy', name: 'AUTO • ECONÔMICO', provider: 'zara' }]);
        setSelectedEngine('auto_smart');
      });
    }

    const refreshBackend = () => {
      api.system?.metrics?.().then((m: any) => {
        setBackendOnline(true);
        setMetrics((old) => ({ cpu: Number(m?.cpu ?? old.cpu), memory: Number(m?.ram ?? old.memory), network: Number(m?.network ?? old.network), storage: Number(m?.storage ?? m?.disk ?? old.storage) }));
      }).catch(() => setBackendOnline(false));
      api.supercerebro?.status?.().then((r: any) => {
        setSupercerebro(Boolean(r?.active && r?.connected));
      }).catch(() => setSupercerebro(false));
    };
    refreshBackend();
    if (!autoVoiceStartedRef.current) {
      autoVoiceStartedRef.current = true;
      setState('PROCESSING');
      api.voice?.start?.().then(async (result: any) => {
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') {
          setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        } else if (result?.mode) {
          setVoiceLabel(String(result.mode).toUpperCase());
        }
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
  }, [notify]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const agentStatus = useMemo(() => supercerebro ? 'GATEWAY CONECTADO • AGENTE PENDENTE' : 'AGENTE PENDENTE', [supercerebro]);

  const toggleSuper = async () => {
    const next = !supercerebro;
    try {
      const toggle = window.zaraIPC?.supercerebro?.toggle;
      if (!toggle) throw new Error('IPC do Supercérebro indisponível');
      const result: any = await toggle(next);
      if (!result || typeof result !== 'object' || typeof result.active !== 'boolean') {
        throw new Error('Resposta inválida do backend');
      }
      const actual = Boolean(result.active && (next ? result.connected : true));
      setSupercerebro(actual);
      notify(`Supercérebro ${actual ? 'ativado' : 'desativado'}.`);
    } catch {
      setSupercerebro(false);
      notify('O gateway Hermes não confirmou a ativação.', 'error');
    }
  };

  // ZARA-BOTAO-MUDO-001
  // ZARA-BOTAO-MUDO-003
  // Alex: "o botao deve ser clicavel e permancer do jeito que eu clicar".
  // A versão anterior só mudava depois que o backend respondesse — se a
  // resposta demorasse ou falhasse, o botão parecia morto. Agora ele vira na
  // hora, manda o estado EXATO que ele escolheu (não "alterna", que
  // dessincroniza), e volta atrás só se o backend recusar.
  const alternarMudo = async () => {
    const desejado = !mudo;
    setMudo(desejado);
    try {
      const r = await window.zaraIPC?.voice?.mute?.(desejado);
      if (r && typeof r.mudo === 'boolean' && r.mudo !== desejado) setMudo(r.mudo);
      notify(desejado ? 'Ela parou de falar. Continua ouvindo e executando.'
                      : 'Ela voltou a falar.');
    } catch {
      setMudo(!desejado);   // não pegou: o botão volta a dizer a verdade
      notify('Não consegui mudar isso agora.', 'error');
    }
  };

  // ZARA-BOTAO-MUDO-005
  // Alex: "eu tenho que ficar toda hora clicando em deixar vermelho é?".
  // Não. O backend guarda a escolha; aqui o botão pergunta como ficou da última
  // vez, para abrir já na cor certa em vez de voltar sempre para verde.
  useEffect(() => {
    let vivo = true;
    window.zaraIPC?.voice?.mute?.()
      .then((r) => { if (vivo && r && typeof r.mudo === 'boolean') setMudo(r.mudo); })
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  const toggleVoice = async () => {
    try {
      if (voiceOn) {
        await window.zaraIPC?.voice?.stop?.();
        pararAudioAec();
        setVoiceOn(false); setState('STANDBY'); setVoiceLevel(0.02);
      } else {
        setState('PROCESSING');
        const result: any = await window.zaraIPC?.voice?.start?.();
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') {
          setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        } else if (result?.mode) {
          setVoiceLabel(String(result.mode).toUpperCase());
        }
        setVoiceOn(true); setState('LISTENING');
      }
    } catch {
      setVoiceOn(false); setState('STANDBY');
      notify('O módulo de voz ainda não está disponível.', 'error');
    }
  };

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (!historyReady) {
      notify('A conversa ainda está sendo carregada.', 'warn');
      return;
    }
    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: Date.now() };
    setMessages((old) => [...old, userMsg]);
    setInput(''); setBusy(true); setState('THINKING');
    try {
      const history = [...messages, userMsg]
        .filter((m) => m.role !== 'system')
        .slice(-16)
        .map((m) => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.content }));
      const res: any = await window.zaraIPC?.message?.send?.({ message: text, engine: selectedEngine, history });
      const content = String(res?.content ?? res?.response ?? res?.message ?? res ?? '').trim();
      if (content) setMessages((old) => [...old, { role: 'assistant', content, timestamp: Date.now() }]);
    } catch {
      setMessages((old) => [...old, { role: 'system', content: 'Backend indisponível para esta solicitação.', timestamp: Date.now() }]);
    } finally {
      setBusy(false); setState(voiceOn ? 'LISTENING' : 'STANDBY');
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
      const chosen = engines.find((item) => item.id === engine);
      notify(`Motor de IA: ${chosen?.name || engine}`);
    } catch {
      setSelectedEngine(previous);
      notify('Este motor não está disponível com as chaves atuais.', 'error');
    }
  };

  const runDiagnostics = async () => {
    try {
      const m: any = await window.zaraIPC?.system?.metrics?.();
      if (m) {
        setBackendOnline(true);
        setMetrics((old) => ({ cpu: Number(m.cpu ?? old.cpu), memory: Number(m.ram ?? old.memory), network: Number(m.network ?? old.network), storage: Number(m.storage ?? m.disk ?? old.storage) }));
      }
      notify('Diagnóstico básico e métricas atualizados.');
    } catch { setBackendOnline(false); notify('Diagnóstico indisponível no backend atual.', 'error'); }
  };

  const systemScan = async () => {
    try { await window.zaraIPC?.system?.info?.(); notify('Informações do sistema consultadas.'); }
    catch { notify('System Scan indisponível no backend atual.', 'error'); }
  };

  const implementedNav = new Set(['HOME', 'CONVERSATIONS', 'MEMORY CORE', 'SYSTEMS', 'SETTINGS']);

  const handleNav = (label: string) => {
    if (!implementedNav.has(label)) return;
    if (label === 'MEMORY CORE') { setGalaxyOpen(true); return; }
    if (label === 'SETTINGS') { setAppearanceOpen(true); return; }
    setActiveNav(label);
    if (label === 'SYSTEMS') void runDiagnostics();
  };

  const hermesAgents: Array<[HermesAgent, string, string, React.ComponentType<any>]> = [
    ['appearance', 'APPEARANCE AGENT', 'Interface • design • experiência', Palette],
    ['intelligence', 'INTELLIGENCE AGENT', 'Skills • pesquisa • raciocínio', BrainCircuit],
    ['functionality', 'FUNCTIONALITY AGENT', 'Integrações • automações • recursos', Wrench],
  ];

  return (
    <div className="zara-shell">
      <header className="topbar">
        <div className="top-brand"><strong>ZARA</strong><span>AI CONTROL CENTER</span></div>
        <div className={`engine-picker ${supercerebro ? 'hermes-priority' : ''}`} title={supercerebro ? 'Supercérebro ativo: Hermes Gateway tem prioridade sobre o motor selecionado' : 'Escolha o motor de IA para o chat de texto'}>
          <span>AI ENGINE</span>
          <select value={selectedEngine} disabled={supercerebro || engines.length === 0} onChange={(e) => void changeEngine(e.target.value)}>
            {engines.map((engine) => <option key={engine.id} value={engine.id}>{engine.name}{engine.status && !engine.id.startsWith('auto_') ? ` • ${engine.status}` : ''}</option>)}
          </select>
          <em>{supercerebro ? 'HERMES PRIORITY' : (engines.find((item) => item.id === selectedEngine)?.provider || 'ZARA').toUpperCase()}</em>
        </div>
        <div className="window-controls">
          <button onClick={() => window.zaraIPC?.window?.minimize?.()} aria-label="Minimizar"><Minimize size={17}/></button>
          <button onClick={() => window.zaraIPC?.window?.maximize?.()} aria-label="Maximizar"><Square size={14}/></button>
          <button className="close" onClick={() => window.zaraIPC?.window?.close?.()} aria-label="Fechar"><X size={17}/></button>
        </div>
      </header>

      <aside className="side-rail">
        <nav className="side-nav">
          {nav.map(([label, Icon]) => (
            <button key={label} disabled={!implementedNav.has(label)} title={!implementedNav.has(label) ? 'Módulo ainda não implementado no backend' : undefined} className={activeNav === label ? 'active' : ''} onClick={() => handleNav(label)}>
              <Icon size={21}/><span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="side-bottom">
          <button className={`super-switch ${supercerebro ? 'on' : ''}`} onClick={toggleSuper} aria-pressed={supercerebro}>
            <BrainCircuit size={20}/><span>SUPERCÉREBRO</span><i><b/></i><small>{supercerebro ? 'ON' : 'OFF'}</small>
          </button>
          <div className="core-card">
            <img src="./zara-symbol.png" alt="Logo ZARA"/>
            <div><strong>ZARA CORE</strong><span>v3.0</span><em><CircleDot size={9}/> {backendOnline ? 'ONLINE' : 'OFFLINE'}</em></div>
          </div>
          <div className="admin-card"><div className="admin-avatar">A</div><div><strong>Admin</strong><span>Superuser</span></div><ChevronRight size={15}/></div>
        </div>
      </aside>

      {activeNav === 'CONVERSATIONS' ? (
        <ZaraLab />
      ) : (
        <>
      <main className={`center-stage ${activeNav === 'HOME' && interfaceNova ? 'instrumento-ativo' : ''}`}>
        {activeNav === 'HOME' && interfaceNova ? (
          <ConversaInstrumento
            mensagens={messages}
            estado={state}
            nivelVoz={voiceLevel}
            historicoPronto={historyReady}
          />
        ) : (
        <section className="orb-zone">
          <VoiceParticleSphere level={voiceLevel} state={state}/>
          <div className={`voice-state state-${state.toLowerCase()}`}>{state === 'LISTENING' ? 'OUVINDO' : state === 'IDLE' ? 'EM ESPERA — diga ZARA' : state === 'SPEAKING' ? 'FALANDO' : state === 'THINKING' ? 'PROCESSANDO' : state === 'PROCESSING' ? 'RECONECTANDO' : ''}</div>
          <div className={`voice-engine-label ${voiceOn ? 'active' : ''}`}>{voiceLabel}</div>
        </section>
        )}
        <form className="command-bar" onSubmit={send}>
          {/* ZARA-BOTAO-MIC-001
              Alex: "eu faria o mesmo botao vermelho para travar o mic dela...
              para ela nao responder coisa que nao pedi mas ela ouviu e levou
              pra la consumindo tokens atoa".

              O botão já existia e já ligava/desligava o microfone — o que não
              existia era a COR. Sem ela, ele não tinha como saber se estava
              sendo ouvido, e "não sei se está ligado" é o mesmo que desligado.

              São dois botões e duas coisas diferentes, de propósito:
                este  = ela OUVE ou não
                o outro = ela FALA ou não */}
          <button
            type="button"
            className={`mic ${voiceOn ? 'active' : ''}`}
            onClick={toggleVoice}
            aria-pressed={voiceOn}
            aria-label={voiceOn ? 'Microfone ligado — clique para travar' : 'Microfone travado — clique para ela ouvir'}
            title={voiceOn ? 'VERDE = ela está te ouvindo. Clique para travar o microfone.' : 'VERMELHO = microfone travado. Ela não ouve nada.'}
            style={{
              background: voiceOn ? '#12b866' : '#e0243a',
              borderColor: voiceOn ? '#25e88a' : '#ff4d63',
              color: '#ffffff',
              boxShadow: voiceOn ? '0 0 14px rgba(18,184,102,.65)' : '0 0 14px rgba(224,36,58,.65)',
              transition: 'background .15s ease, box-shadow .15s ease',
            }}
          >
            {voiceOn ? <Mic size={20}/> : <MicOff size={20}/>}
          </button>
          {/* ZARA-BOTAO-MUDO-001 — calar a voz sem desligar a ZARA.
              Ela continua ouvindo, entendendo e executando; só para de falar.
              Alex pediu porque ela anunciava "o Claude respondeu" enquanto ele
              estava lendo a resposta na tela. */}
          <button
            type="button"
            className={`mic ${mudo ? 'muted' : 'active'}`}
            onClick={alternarMudo}
            aria-pressed={mudo}
            aria-label={mudo ? 'Voz silenciada — clique para ela voltar a falar' : 'Silenciar a voz dela'}
            title={mudo ? 'VERMELHO = calada. Clique para ela voltar a falar.' : 'VERDE = ela fala. Clique para calar (continua ouvindo e executando).'}
            // ZARA-BOTAO-MUDO-004
            // Alex: "o botao da zara nao fica verde ou vermelho".
            // As classes `.mic.active`/`.mic.muted` não pintavam nada na folha de
            // estilo, então o botão ficava igual nos dois estados. A cor vai aqui,
            // no elemento, onde nenhum CSS de fora apaga.
            style={{
              background: mudo ? '#e0243a' : '#12b866',
              borderColor: mudo ? '#ff4d63' : '#25e88a',
              color: '#ffffff',
              boxShadow: mudo ? '0 0 14px rgba(224,36,58,.65)' : '0 0 14px rgba(18,184,102,.65)',
              transition: 'background .15s ease, box-shadow .15s ease',
            }}
          >
            {mudo ? <VolumeX size={20}/> : <Volume2 size={20}/>}
          </button>
          <input className="zara-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Message ZARA..."/>
          <button type="submit" className="send" disabled={busy || !historyReady || !input.trim()} aria-label="Enviar">{busy ? <LoaderCircle className="spin" size={19}/> : <Send size={21}/>}</button>
        </form>

        {!(activeNav === 'HOME' && interfaceNova) && (
        <section className="conversation-card">
          <header><span>CONVERSATION LOG</span><button type="button" disabled={clearingHistory || busy || voiceOn || !historyReady} onClick={clearConversationHistory}><Trash2 size={13}/> {clearingHistory ? 'CLEARING...' : 'CLEAR'}</button></header>
          <div className="conversation-scroll" ref={logRef}>
            {messages.length === 0 && <div className="empty-log">{historyReady ? 'Nenhuma conversa salva.' : 'Carregando conversas...'}</div>}
            {messages.map((m, i) => (
              <article className={`message-row ${m.role}`} key={m.id || `${m.timestamp}-${i}`}>
                <div className="message-icon">{m.role === 'assistant' ? <img src="./zara-symbol.png"/> : m.role === 'system' ? <Activity size={16}/> : <span>A</span>}</div>
                <div className="message-body"><div><strong>{m.role === 'assistant' ? 'ZARA' : m.role === 'system' ? 'SYSTEM' : 'You'}</strong><time>{timeLabel(m.timestamp)}</time></div><p>{m.content}</p></div>
              </article>
            ))}
          </div>
        </section>
        )}
      </main>

      <aside className="right-rail">
        <section className="panel hermes-lab">
          <header><span><Bot size={16}/> HERMES LAB</span><em className={supercerebro ? 'online' : ''}><i/> {supercerebro ? 'GATEWAY ONLINE' : 'STANDBY'}</em></header>
          <p className="panel-caption">Agentes planejados • nenhuma atualização é aplicada sem aprovação do Alex.</p>
          <div className="agent-list">
            {hermesAgents.map(([key, title, desc, Icon]) => (
              <div className="agent-row" key={key}><div className="agent-icon"><Icon size={16}/></div><div><strong>{title}</strong><span>{desc}</span></div><small><i/>{agentStatus}</small></div>
            ))}
          </div>
        </section>

        <section className="status-strip panel"><div><Activity size={16}/><span>BACKEND STATUS<strong>{backendOnline ? 'ONLINE' : 'OFFLINE'}</strong></span></div><Bell size={16}/></section>

        <section className="panel system-overview">
          <header><span><Grid3X3 size={15}/> SYSTEM OVERVIEW</span></header>
          {[
            ['CPU', `${metrics.cpu.toFixed(0)}%`, Cpu],
            ['MEMORY', `${metrics.memory.toFixed(0)}%`, Brain],
            ['BACKEND', backendOnline ? 'ONLINE' : 'OFFLINE', Network],
            ['MEMORY CORE', backendOnline ? 'READY' : 'OFFLINE', Database],
          ].map(([name, status, Icon]: any) => (
            <div className="overview-row" key={name}><Icon size={15}/><span>{name}</span><em>{status}</em><i className={!backendOnline && (name === 'BACKEND' || name === 'MEMORY CORE') ? 'offline-dot' : ''}/></div>
          ))}
        </section>

        <section className="panel active-modules">
          <header><span><Box size={15}/> ACTIVE MODULES</span></header>
          {[['Natural Language', backendOnline ? 'READY' : 'OFFLINE'],['Reasoning Engine', backendOnline ? 'READY' : 'OFFLINE'],['Memory Galaxy','PENDING'],['Voice Interface','ON DEMAND']].map(([n,v]) => <div className="module-row" key={n}><span>{n}</span><em>{v}</em><i/></div>)}
        </section>

        <section className="panel quick-actions">
          <header><span><Zap size={16}/> QUICK ACTIONS</span></header>
          <button onClick={runDiagnostics}>Run Diagnostics<ChevronRight size={15}/></button>
          <button onClick={systemScan}>System Scan<ChevronRight size={15}/></button>
          <button disabled title="Será habilitado quando o fluxo de propostas/aprovação estiver implementado">Update Core<ChevronRight size={15}/></button>
          <button disabled title="Relatórios ainda não possuem backend">View Reports<ChevronRight size={15}/></button>
          <button className="galaxy-button" onClick={() => setGalaxyOpen(true)}><Search size={14}/> Memory Galaxy<ChevronRight size={15}/></button>
        </section>

        <section className="security-footer panel"><div><ShieldCheck size={16}/><span>IPC<strong>LOCAL</strong></span></div><div><RefreshCw size={16}/><span>BACKEND<strong>{backendOnline ? 'READY' : 'OFFLINE'}</strong></span></div></section>
      </aside>
        </>
      )}

      <div className="toast-stack">{toasts.map((t) => <div key={t.id} className={`toast ${t.kind || 'ok'}`}>{t.text}</div>)}</div>
      <PainelAparencia
        aberto={appearanceOpen}
        onClose={() => setAppearanceOpen(false)}
        onInterfaceNovaChange={setInterfaceNova}
      />
      {galaxyOpen && <MemoryGalaxyModal onClose={() => setGalaxyOpen(false)}/>} 
    </div>
  );
};
