import { Minus, Square, X, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * Controles de janela do Electron (frameless). Usa os handlers reais já
 * existentes no preload: window.zaraIPC.window.minimize/maximize/close.
 * O botão central alterna maximizar/restaurar via isMaximized (main.ts).
 */
export function WindowControls() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    // Sem evento de resize exposto no preload: inferimos pelo tamanho da
    // janela vs viewport (barato e sem IPC novo).
    function sync() {
      setMaximized(window.outerWidth >= window.screen.availWidth - 8);
    }
    sync();
    window.addEventListener('resize', sync);
    return () => window.removeEventListener('resize', sync);
  }, []);

  const ipc = window.zaraIPC?.window;

  return (
    <div className="zh-window-controls" aria-label="Controles da janela">
      <button
        type="button"
        className="zh-window-btn"
        aria-label="Minimizar"
        disabled={!ipc?.minimize}
        onClick={() => ipc?.minimize()}
      >
        <Minus size={13} strokeWidth={2} />
      </button>
      <button
        type="button"
        className="zh-window-btn"
        aria-label={maximized ? 'Restaurar' : 'Maximizar'}
        disabled={!ipc?.maximize}
        onClick={() => ipc?.maximize()}
      >
        {maximized ? <Copy size={11} strokeWidth={2} /> : <Square size={11} strokeWidth={2} />}
      </button>
      <button
        type="button"
        className="zh-window-btn zh-window-btn--close"
        aria-label="Fechar"
        disabled={!ipc?.close}
        onClick={() => ipc?.close()}
      >
        <X size={14} strokeWidth={2} />
      </button>
    </div>
  );
}
