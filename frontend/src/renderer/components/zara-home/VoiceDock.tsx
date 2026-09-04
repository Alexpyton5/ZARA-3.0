import { useEffect, useState } from 'react';
import { Grid3x3, Folder, AudioLines, HelpCircle, History, MoreHorizontal } from 'lucide-react';
import type { CoreState } from './types';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore } from '../../lib/aecAudio';

interface VoiceDockProps {
  coreState: CoreState;
}

/**
 * Botão central do dock = Modo Voz. Chama `window.zaraIPC.voice.start()` /
 * `.stop()` — os MESMOS canais que o resto da ZARA (HUD, Orb) já usa para
 * ligar o pipeline de voz real (Gemini Live). Não substitui nem duplica
 * nada da voz; só oferece outro botão para o canal existente.
 *
 * ZARA-HOME-AUDIO-BRIDGE-001: a Home nova (React) nunca chamava
 * `aecAudio.ts` nem assinava `on.voiceOutputAudio` — o botão dizia "ouvindo"
 * mas nenhum áudio de microfone saía do renderer, e a fala da Kore não tinha
 * onde tocar. `iniciarAudioAec`/`pararAudioAec`/`tocarKore`/`cortarKore` já
 * existiam prontos (mesma técnica usada pelo HUD antigo), só não estavam
 * plugados nesta árvore de componentes.
 */
export function VoiceDock({ coreState }: VoiceDockProps) {
  const [listening, setListening] = useState(false);
  const voiceAvailable = Boolean(window.zaraIPC?.voice?.start && window.zaraIPC?.voice?.stop);

  // A saída de voz (Kore) precisa estar pronta para tocar mesmo antes do
  // Alex clicar em "ouvir" — barge-in e respostas de texto também falam.
  useEffect(() => {
    const subscribe = window.zaraIPC?.on?.voiceOutputAudio;
    if (!subscribe) return;
    const unsubscribe = subscribe((data) => {
      if (data?.stop) {
        cortarKore();
        return;
      }
      if (data?.pcm) {
        tocarKore(data.pcm, data.sampleRate || 24000);
      }
    });
    return () => {
      unsubscribe?.();
      cortarKore();
    };
  }, []);

  async function toggleVoice() {
    if (!voiceAvailable) return;
    // ZARA-HOME-BARGE-IN-001: enquanto ela fala, o mesmo botao interrompe em
    // vez de alternar o microfone -- corta o audio de verdade (nao so o
    // estado visual) e avisa o backend, igual ao "Zara, pare" por voz.
    if (coreState === 'speaking') {
      cortarKore();
      try {
        await window.zaraIPC?.message?.interrupt?.();
      } catch {
        // Audio ja foi cortado no cliente; erro no aviso ao backend nao
        // precisa travar o botao.
      }
      return;
    }
    try {
      if (listening) {
        await window.zaraIPC!.voice!.stop!();
        pararAudioAec();
        setListening(false);
      } else {
        await window.zaraIPC!.voice!.start!();
        const resultado = await iniciarAudioAec((pcmBase64) => {
          window.zaraIPC?.voice?.sendMicChunk?.(pcmBase64);
        });
        if (!resultado.ok) {
          // Backend ligou o pipeline mas o navegador negou o microfone --
          // desliga dos dois lados em vez de fingir que está ouvindo.
          await window.zaraIPC!.voice!.stop!();
          setListening(false);
          return;
        }
        setListening(true);
      }
    } catch {
      pararAudioAec();
      setListening(false);
    }
  }

  const label = !voiceAvailable
    ? 'Abrir modo voz — não conectado'
    : coreState === 'speaking' ? 'Interromper'
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
          <AudioLines size={20} strokeWidth={2} />
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
