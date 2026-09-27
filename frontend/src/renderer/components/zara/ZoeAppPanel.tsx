// Aba "ZOE" — o app web da zoe (Muse) embutido dentro da janela da ZARA.
// É a zoe de verdade: mesma conta, mesma memória, mesmos conectores.
// A sessão é persistente (partition persist:zoe): o login é feito uma vez.
//
// Honestidade técnica: a visão embutida é visual. Por aqui a zoe NÃO enxerga
// o estado interno da ZARA e o Lab NÃO age sobre o que é dito aqui. A conexão
// nos dois sentidos acontece no painel CONSELHEIRA, pela ponte Gmail.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, LoaderCircle, RefreshCw, WifiOff } from 'lucide-react';
import { ZOE_APP_URL, ZOE_WEBVIEW_PARTITION } from '../../lib/zoeConfig';

// Interface mínima do <webview> do Electron (só o que este painel usa).
interface ZoeWebviewElement {
  reload(): void;
  loadURL(url: string): Promise<void>;
  addEventListener(type: string, listener: (...args: any[]) => void): void;
  removeEventListener(type: string, listener: (...args: any[]) => void): void;
}

type ZoeStatus = 'loading' | 'ready' | 'offline';

const STATUS_LABEL: Record<ZoeStatus, string> = {
  loading: 'CARREGANDO…',
  ready: 'ONLINE',
  offline: 'OFFLINE',
};

export const ZoeAppPanel: React.FC = () => {
  const webviewRef = useRef<ZoeWebviewElement | null>(null);
  const [status, setStatus] = useState<ZoeStatus>('loading');
  const [failMessage, setFailMessage] = useState('');

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
      // args: (event, errorCode, errorDescription, validatedURL, isMainFrame)
      const isMainFrame = args[4];
      if (isMainFrame === false) return; // ignora falha de sub-recurso
      const errorCode = Number(args[1]);
      const errorDescription = String(args[2] || '');
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
          <h1>O APP DA ZOE — DENTRO DA ZARA</h1>
          <p>É a zoe de verdade embutida no app: mesma conta, mesma memória e mesmos conectores. O login é feito uma vez e a sessão fica salva.</p>
        </div>
        <div className="lab-runtime-status">
          <span><Bot size={14}/> STATUS <strong>{STATUS_LABEL[status]}</strong></span>
          <button onClick={reload} title="Recarregar o app da zoe">
            <RefreshCw size={14}/>
          </button>
        </div>
      </section>

      <section className="zoe-frame-wrap">
        <webview
          ref={setWebviewRef}
          src={ZOE_APP_URL}
          partition={ZOE_WEBVIEW_PARTITION}
          allowpopups
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
        A zoe aqui dentro é visual: você conversa com ela com tudo o que ela já sabe sobre você.
        A conexão nos dois sentidos — ela enxergando o estado da ZARA e o Lab agindo sobre as
        respostas — acontece no painel CONSELHEIRA, pela ponte Gmail. As duas abas juntas são
        a experiência Jarvis.
      </p>
    </main>
  );
};
