// O cliente web oficial do Muse, na janela da ZARA. A sessão é persistente.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AudioLines, Bot, LoaderCircle, RefreshCw, WifiOff } from 'lucide-react';
import { ZOE_APP_URL, ZOE_WEBVIEW_PARTITION } from '../../lib/zoeConfig';
import { useZoeVoice } from '../../lib/useZoeVoice';

// Interface mínima do <webview> do Electron (só o que este painel usa).
interface ZoeWebviewElement {
  reload(): void;
  loadURL(url: string): Promise<void>;
  executeJavaScript(code: string): Promise<unknown>;
  addEventListener(type: string, listener: (...args: any[]) => void): void;
  removeEventListener(type: string, listener: (...args: any[]) => void): void;
}

type ZoeStatus = 'loading' | 'ready' | 'offline';

const STATUS_LABEL: Record<ZoeStatus, string> = {
  loading: 'CARREGANDO…',
  ready: 'PÁGINA ABERTA',
  offline: 'OFFLINE',
};

export const ZoeAppPanel: React.FC<{ visible?: boolean }> = ({ visible = true }) => {
  const webviewRef = useRef<ZoeWebviewElement | null>(null);
  const [status, setStatus] = useState<ZoeStatus>('loading');
  const [bridgeReady, setBridgeReady] = useState<boolean | null>(null);
  const [failMessage, setFailMessage] = useState('');
  const voice = useZoeVoice(webviewRef, status === 'ready' && visible);

  const setWebviewRef = useCallback((el: HTMLElement | null) => {
    webviewRef.current = el as unknown as ZoeWebviewElement | null;
  }, []);

  useEffect(() => {
    const wv = webviewRef.current;
    if (!wv) return;
    const onStart = () => {
      setStatus('loading');
      setFailMessage('');
    };
    const onStop = () => {
      setStatus((s) => (s === 'loading' ? 'ready' : s));
    };
    const onFail = (...args: any[]) => {
      // Electron <webview> emits one event object. Ignore blocked trackers and
      // other subresources; only a failed main navigation hides the page.
      const event = args[0] || {};
      const isMainFrame = event.isMainFrame ?? args[4];
      if (isMainFrame === false) return; // ignora falha de sub-recurso
      const errorCode = Number(event.errorCode ?? args[1]);
      const failedURL = String(event.validatedURL ?? args[3] ?? '');
      if (!Number.isFinite(errorCode) || (failedURL && !failedURL.startsWith(ZOE_APP_URL))) return;
      if (errorCode === -3) return; // navigation cancelled by a redirect
      const errorDescription = String(event.errorDescription ?? args[2] ?? '');
      setStatus('offline');
      setFailMessage(
        errorCode === -106 || errorCode === -105
          ? 'Sem conexão com a internet.'
          : errorDescription || `Erro ao carregar (código ${errorCode}).`,
      );
    };
    wv.addEventListener('did-start-loading', onStart);
    wv.addEventListener('did-stop-loading', onStop);
    wv.addEventListener('did-fail-load', onFail);
    return () => {
      wv.removeEventListener('did-start-loading', onStart);
      wv.removeEventListener('did-stop-loading', onStop);
      wv.removeEventListener('did-fail-load', onFail);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      void window.zaraIPC?.zoeBridge?.status?.()
        .then((result) => { if (mounted) setBridgeReady(Boolean(result?.ready)); })
        .catch(() => { if (mounted) setBridgeReady(null); });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);


  const reload = useCallback(() => {
    const wv = webviewRef.current;
    if (!wv) return;
    setStatus('loading');
    setFailMessage('');
    try {
      wv.reload();
    } catch {
      wv.loadURL(ZOE_APP_URL).catch(() => setStatus('offline'));
    }
  }, []);

  return (
    <main className="zoe-stage">
      <section className="lab-topline">
        <div>
          <span className="lab-kicker"><Bot size={14}/> ZOE</span>
          <h1>ZOE</h1>
          <p>Entre com a mesma conta Muse que você usa no WhatsApp. O login nesta janela fica salvo.</p>
        </div>
        <div className="zoe-header-controls">
          <div className="lab-runtime-status">
            <span><Bot size={14}/> STATUS <strong>{STATUS_LABEL[status]}</strong></span>
            <button onClick={reload} title="Recarregar o app da zoe">
              <RefreshCw size={14}/>
            </button>
          </div>
          <div className="zoe-voice-toolbar" aria-label="Voz da Zoe">
            <button
              type="button"
              className={`lab-primary${voice.voiceState !== "off" && voice.voiceState !== "error" ? " zoe-voice-live" : ""}`}
              onClick={() => void voice.toggle()}
              disabled={status !== 'ready' || voice.voiceState === 'starting'}
              aria-pressed={voice.voiceState !== 'off' && voice.voiceState !== 'error'}
            >
              <AudioLines size={17}/>
              {voice.voiceState === 'off' || voice.voiceState === 'error' ? 'Falar com Zoe' : 'Parar voz'}
            </button>

          </div>
        </div>
      </section>

      <section className="zoe-frame-wrap">
        <webview
          ref={setWebviewRef}
          src={ZOE_APP_URL}
          partition={ZOE_WEBVIEW_PARTITION}
          className="zoe-webview"
        />
        {status === 'loading' && (
          <div className="zoe-overlay">
            <LoaderCircle className="spin" size={22}/>
            <p>ABRINDO O APP DA ZOE...</p>
          </div>
        )}
        {status === 'offline' && (
          <div className="zoe-overlay">
            <WifiOff size={22}/>
            <p>NÃO FOI POSSÍVEL CARREGAR O APP DA ZOE</p>
            <span>{failMessage || 'Verifique sua conexão com a internet e tente de novo.'}</span>
            <button onClick={reload} className="lab-primary" style={{ width: 'auto', padding: '0 18px' }}>
              <RefreshCw size={14}/> TENTAR DE NOVO
            </button>
          </div>
        )}
      </section>

      <p className="panel-caption zoe-caption">
        {bridgeReady === null ? '' : `Ponte local da ZARA: ${bridgeReady ? 'pronta' : 'indisponível'}. `}
        {voice.error || {
          off: 'Microfone desligado.',
          starting: 'Ligando o microfone…',
          listening: 'Ouvindo você…',
          waiting: 'Aguardando a Zoe…',
          controlling: 'Usando o computador…',
          speaking: 'Lendo a resposta da Zoe…',
          error: '',
        }[voice.voiceState]}
        {voice.museWaitMs !== null && ` Texto: ${(voice.museWaitMs / 1000).toFixed(1)} s.`}
        {voice.firstSoundMs !== null && ` Áudio: ${(voice.firstSoundMs / 1000).toFixed(1)} s.`}
      </p>
    </main>
  );
};
