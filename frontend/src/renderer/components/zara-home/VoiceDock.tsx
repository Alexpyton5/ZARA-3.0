import { useState } from 'react';
import { Grid3x3, Folder, Mic, MicOff, HelpCircle, History, MoreHorizontal } from 'lucide-react';
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
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <nav className="zh-dock zh-glass-panel" aria-label="Dock ZARA">
        <button className="zh-dock-btn" type="button" aria-label="Aplicativos">
          <Grid3x3 size={17} strokeWidth={1.7} />
        </button>
        <button className="zh-dock-btn" type="button" aria-label="Arquivos">
          <Folder size={17} strokeWidth={1.7} />
        </button>
        <span className="zh-dock-separator" aria-hidden="true" />
        <button
          className="zh-dock-voice"
          type="button"
          aria-label={label}
          data-listening={listening}
          data-offline={!voiceAvailable}
          disabled={!voiceAvailable}
          onClick={toggleVoice}
        >
          {voiceAvailable && listening
            ? <MicOff size={20} strokeWidth={2} />
            : <Mic size={20} strokeWidth={2} />}
        </button>
        <span className="zh-dock-separator" aria-hidden="true" />
        <button className="zh-dock-btn" type="button" aria-label="Ajuda">
          <HelpCircle size={17} strokeWidth={1.7} />
        </button>
        <button className="zh-dock-btn" type="button" aria-label="Histórico">
          <History size={17} strokeWidth={1.7} />
        </button>
        <button className="zh-dock-btn" type="button" aria-label="Mais opções">
          <MoreHorizontal size={17} strokeWidth={1.7} />
        </button>
      </nav>
      {coreState === 'offline' && (
        <span className="zh-not-connected" style={{ marginTop: 6 }}>
          Voz não conectada
        </span>
      )}
    </div>
  );
}
