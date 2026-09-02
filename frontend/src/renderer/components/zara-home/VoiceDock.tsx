import { useState } from 'react';
import type { CoreState } from './types';

interface VoiceDockProps {
  coreState: CoreState;
}

/**
 * Botão central do dock = Modo Voz. Chama `window.zaraIPC.voice.start()` /
 * `.stop()` — os MESMOS canais que o resto da ZARA (HUD, Orb) já usa para
 * ligar o pipeline de voz real (Gemini Live). Não substitui nem duplica
 * nada da voz; só oferece outro botão para o canal existente.
 */
export function VoiceDock({ coreState }: VoiceDockProps) {
  const [listening, setListening] = useState(false);
  const voiceAvailable = Boolean(window.zaraIPC?.voice?.start && window.zaraIPC?.voice?.stop);

  async function toggleVoice() {
    if (!voiceAvailable) return;
    try {
      if (listening) {
        await window.zaraIPC!.voice!.stop!();
        setListening(false);
      } else {
        await window.zaraIPC!.voice!.start!();
        setListening(true);
      }
    } catch {
      setListening(false);
    }
  }

  const label = !voiceAvailable
    ? 'Abrir modo voz — não conectado'
    : listening ? 'Parar modo voz' : 'Abrir modo voz';

  return (
    <nav className="zh-dock zh-glass-panel" aria-label="Dock ZARA">
      <button className="zh-dock-btn" type="button" aria-label="Aplicativos">▦</button>
      <button className="zh-dock-btn" type="button" aria-label="Arquivos">🗂</button>
      <button
        className="zh-dock-voice"
        type="button"
        aria-label={label}
        data-listening={listening}
        data-offline={!voiceAvailable}
        disabled={!voiceAvailable}
        onClick={toggleVoice}
      >
        {listening ? '●' : '◉'}
      </button>
      <button className="zh-dock-btn" type="button" aria-label="Ajuda">?</button>
      <button className="zh-dock-btn" type="button" aria-label="Histórico">↺</button>
      <button className="zh-dock-btn" type="button" aria-label="Mais opções">⋯</button>
      {coreState === 'offline' && (
        <span className="zh-not-connected" style={{ position: 'absolute', bottom: -18 }}>
          Voz não conectada
        </span>
      )}
    </nav>
  );
}
