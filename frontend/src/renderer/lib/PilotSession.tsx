import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { PILOTS, cancelPilotReply, checkPilotCancellation, isPilotProvider, preparePilotTurn, probePilot, sendPilotMessage, type PilotProvider } from './pilotConversation';
import type { MuseWebview } from './museConversation';
import { useZoeVoice } from './useZoeVoice';
import { createPilotTurnRecorder } from './pilotLearning';
import { extractZoeComputerGoal } from './computerAgentTrigger';
import { getComputerAgentBridge } from '../components/computer-agent/computerAgentBridge';

interface Webview extends MuseWebview {
  reload(): void;
  addEventListener(name: string, listener: (event: any) => void): void;
  removeEventListener(name: string, listener: (event: any) => void): void;
}

type Session = {
  provider: PilotProvider;
  connected: boolean;
  loading: boolean;
  error: string;
  accountOpen: boolean;
  connect: (provider?: PilotProvider) => void;
  closeAccount: () => void;
  send: (text: string) => Promise<string>;
  voice: ReturnType<typeof useZoeVoice>;
};
const Context = createContext<Session | null>(null);

function savedProvider(): PilotProvider {
  try { const value = localStorage.getItem('zara-pilot-provider'); return isPilotProvider(value) ? value : 'muse'; }
  catch { return 'muse'; }
}

export function PilotSessionProvider({ children }: { children: ReactNode }) {
  const [provider, setProvider] = useState<PilotProvider>(savedProvider);
  const [panel, setPanel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [mountedWebview, setMountedWebview] = useState<Webview | null>(null);
  const webviewRef = useRef<Webview | null>(null);
  const sending = useRef(false);
  const version = useRef(0);
  const voice = useZoeVoice(webviewRef, connected, provider);
  const config = PILOTS[provider];

  const stopSession = useCallback(async () => {
    version.current += 1;
    const webview = webviewRef.current;
    await Promise.allSettled([
      voice.stop(),
      ...(sending.current && webview ? [cancelPilotReply(webview, provider)] : []),
    ]);
  }, [provider, voice.stop]);

  useEffect(() => () => { version.current += 1; }, []);

  const ref = useCallback((node: HTMLElement | null) => {
    const element = node as unknown as Webview | null;
    webviewRef.current = element;
    setMountedWebview(element);
  }, []);

  useEffect(() => {
    if (!mountedWebview) return;
    let alive = true;
    let checking = false;
    const check = async () => {
      if (checking) return;
      checking = true;
      try {
        const signedIn = await probePilot(mountedWebview, provider);
        if (alive) { setConnected(signedIn); setLoading(false); setError(''); }
      } catch { if (alive) { setConnected(false); setLoading(false); setError('A conversa está indisponível. Abra sua conta ou tente recarregar.'); } }
      finally { checking = false; }
    };
    const start = (event: any) => { if (event.isMainFrame === false) return; version.current += 1; setLoading(true); setConnected(false); };
    const fail = (event: any) => {
      if (event.isMainFrame === false || event.errorCode === -3) return;
      setConnected(false); setLoading(false);
      setError('Não foi possível abrir sua conta. Confira a conexão e tente novamente.');
    };
    const ready = () => { void check(); };
    mountedWebview.addEventListener('did-start-navigation', start);
    mountedWebview.addEventListener('dom-ready', ready);
    mountedWebview.addEventListener('did-stop-loading', ready);
    mountedWebview.addEventListener('did-fail-load', fail);
    const timer = window.setInterval(ready, 2500);
    return () => {
      alive = false; window.clearInterval(timer);
      mountedWebview.removeEventListener('did-start-navigation', start);
      mountedWebview.removeEventListener('dom-ready', ready);
      mountedWebview.removeEventListener('did-stop-loading', ready);
      mountedWebview.removeEventListener('did-fail-load', fail);
    };
  }, [mountedWebview, provider]);

  const connect = useCallback((next: PilotProvider = provider) => {
    if (next !== provider) {
      void stopSession();
      setConnected(false); setLoading(true); setError(''); setProvider(next);
      try { localStorage.setItem('zara-pilot-provider', next); } catch { /* session still works */ }
    }
    setPanel(true);
  }, [provider, stopSession]);

  const closeAccount = useCallback(() => setPanel(false), []);

  const send = useCallback(async (text: string): Promise<string> => {
    if (sending.current || !['off', 'error'].includes(voice.voiceState)) throw new Error('Espere a resposta ou desligue o microfone antes de enviar por texto.');
    sending.current = true;
    const currentVersion = version.current;
    const cancelled = () => version.current !== currentVersion;
    try {
      const goal = extractZoeComputerGoal(text);
      const manualFallback = goal === null ? undefined : async () => {
        if (!goal) throw new Error('Diga o que você quer fazer no computador.');
        const bridge = getComputerAgentBridge();
        if (!bridge) throw new Error('O controle do computador está indisponível.');
        const result = await bridge.run(goal) as { success?: boolean; verified?: boolean; error?: string; steps?: Array<{ outcome?: string }> };
        checkPilotCancellation(cancelled);
        if (!result?.success) throw new Error(result?.error || 'O trabalho no computador não foi concluído.');
        const outcomes = (result.steps || []).map(step => step.outcome).filter(Boolean).join('\n');
        return { success: true, response: `${result.verified ? 'Resultado confirmado.' : 'O executor terminou; a confirmação visual ainda não foi obtida.'}${outcomes ? `\n${outcomes}` : ''}` };
      };
      const turn = await preparePilotTurn(text, window.zaraIPC?.pilot, cancelled, manualFallback);
      if (turn.handled) return turn.response;
      if (!connected || !webviewRef.current) { connect(); throw new Error('Entre na sua conta para conversar com o piloto.'); }
      const record = createPilotTurnRecorder(provider, text, 'text', window.zaraIPC?.pilot);
      return await sendPilotMessage(webviewRef.current, provider, turn.text, cancelled, turn.context,
        (submission, reply) => { void record(submission, reply); });
    } finally { sending.current = false; }
  }, [provider, connected, connect, voice.voiceState]);

  const reload = () => { void stopSession(); setError(''); setLoading(true); mountedWebview?.reload(); };
  const context = { provider, connected, loading, error, accountOpen: panel, connect, closeAccount, send, voice: { ...voice, stop: stopSession } };

  return <Context.Provider value={context}>
    {children}
    <section aria-label={`Conta ${config.nome}`} aria-hidden={!panel} style={panel
      ? { position: 'fixed', inset: 24, zIndex: 10000, background: 'var(--panel, #fff)', borderRadius: 18, boxShadow: '0 12px 80px #0005', display: 'flex', flexDirection: 'column', padding: 16 }
      : { position: 'fixed', left: -12000, top: 0, width: 1100, height: 800, pointerEvents: 'none' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', paddingBottom: 12 }}>
        <strong>{config.nome}</strong>
        <span role="status" style={{ flex: 1 }}>{error || (loading ? 'Abrindo sua conta…' : connected ? 'Conversa disponível' : 'Entre na sua conta nesta janela.')}</span>
        <button className="secondary-button" onClick={reload}>Recarregar</button>
        <button className="primary-button" onClick={closeAccount}>Voltar ao app</button>
      </div>
      <webview key={provider} ref={ref as any} src={config.url} partition={config.partition}
        webpreferences="contextIsolation=yes,sandbox=yes,backgroundThrottling=no"
        style={{ display: 'flex', width: '100%', height: '100%', flex: 1, borderRadius: 12 }} />
    </section>
  </Context.Provider>;
}

export function usePilotSession(): Session {
  const value = useContext(Context);
  if (!value) throw new Error('A sessão do piloto não foi iniciada.');
  return value;
}
