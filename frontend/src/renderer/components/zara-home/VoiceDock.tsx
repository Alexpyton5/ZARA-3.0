import { useEffect, useRef, useState } from 'react';
import { LayoutGrid, Folder, AudioLines, HelpCircle, Clock3, MoreHorizontal } from 'lucide-react';
import type { CoreState } from './types';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore, koreTocando, observarKore } from '../../lib/aecAudio';
import { errorMessage } from './homeActions';

interface VoiceDockProps {
  coreState: CoreState;
  onNavigate: (section: string) => void;
}

/** The Home owns one AEC capture and the existing Kore playback subscription. */
export function VoiceDock({ coreState, onNavigate }: VoiceDockProps) {
  const [listening, setListening] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [playing, setPlaying] = useState(false);
  const operation = useRef(false);
  const mounted = useRef(true);
  const ownsSession = useRef(false);
  const voiceAvailable = Boolean(window.zaraIPC?.voice?.start && window.zaraIPC?.voice?.stop);

  useEffect(() => {
    mounted.current = true;
    const unsubscribePlayback = observarKore(setPlaying);
    const unsubscribe = window.zaraIPC?.on?.voiceOutputAudio?.((data) => {
      try {
        if (data?.stop) cortarKore();
        else if (data?.pcm) tocarKore(data.pcm, data.sampleRate || 24000);
      } catch {
        if (mounted.current) setError('Não foi possível reproduzir este trecho de áudio.');
      }
    });
    const unsubscribeState = window.zaraIPC?.on?.stateChange?.((state) => {
      if (['OFFLINE', 'STOPPED', 'DISCONNECTED'].includes(state.toUpperCase())) {
        pararAudioAec();
        ownsSession.current = false;
        if (mounted.current) setListening(false);
      }
    });
    return () => {
      mounted.current = false;
      unsubscribePlayback();
      unsubscribe?.();
      unsubscribeState?.();
      pararAudioAec();
      if (ownsSession.current) void window.zaraIPC?.voice?.stop?.().catch(() => undefined);
      ownsSession.current = false;
    };
  }, []);

  async function toggleVoice() {
    if (!voiceAvailable || operation.current) return;
    operation.current = true;
    setPending(true);
    setError('');
    try {
      if (coreState === 'speaking' || koreTocando()) {
        cortarKore();
        const response = await window.zaraIPC?.message?.interrupt?.();
        if (response?.success === false) throw new Error(response.error || 'A interrupção não foi confirmada.');
      } else if (listening) {
        // Stop capture immediately, even when the backend has disconnected.
        pararAudioAec();
        setListening(false);
        const response = await window.zaraIPC!.voice!.stop!();
        if (response?.success === false) throw new Error(response.error || 'A parada da voz não foi confirmada.');
        ownsSession.current = false;
      } else {
        const response = await window.zaraIPC!.voice!.start!();
        if (response?.success !== true) throw new Error(response?.error || 'O serviço de voz não pôde iniciar.');
        ownsSession.current = true;
        if (!mounted.current) {
          await window.zaraIPC!.voice!.stop!();
          ownsSession.current = false;
          return;
        }
        // Vosk owns its microphone in Python; Gemini uses renderer AEC.
        if (response.mode !== 'local' && response.audio_transport !== 'local') {
          const result = await iniciarAudioAec((pcm) => window.zaraIPC?.voice?.sendMicChunk?.(pcm));
          if (!result.ok) throw new Error('Microfone indisponível. Verifique o dispositivo e a permissão de áudio.');
        }
        if (!mounted.current) {
          pararAudioAec();
          await window.zaraIPC!.voice!.stop!();
          ownsSession.current = false;
          return;
        }
        setListening(true);
      }
    } catch (cause) {
      pararAudioAec();
      if (ownsSession.current) {
        await window.zaraIPC?.voice?.stop?.().catch(() => undefined);
        ownsSession.current = false;
      }
      if (mounted.current) {
        setListening(false);
        setError(errorMessage(cause, 'Não foi possível iniciar a voz.'));
      }
    } finally {
      operation.current = false;
      if (mounted.current) setPending(false);
    }
  }

  const label = pending ? 'Conectando voz…' : !voiceAvailable ? 'Modo voz indisponível'
    : coreState === 'speaking' || playing ? 'Interromper fala' : listening ? 'Parar modo voz' : 'Abrir modo voz';

  return (
    <div className="zh-dock-wrap">
      <nav className="zh-dock zh-glass-panel" aria-label="Dock ZARA">
        <button className="zh-dock-btn" type="button" aria-label="Aplicativos" title="Aplicativos" onClick={() => onNavigate('Aplicativos')}><LayoutGrid size={25} strokeWidth={1.7} /></button>
        <button className="zh-dock-btn" type="button" aria-label="Arquivos" title="Arquivos e memórias" onClick={() => onNavigate('Arquivos')}><Folder size={27} strokeWidth={1.7} /></button>
        <span className="zh-dock-separator" aria-hidden="true" />
        <button className="zh-dock-voice" type="button" aria-label={label} title={label} data-listening={listening} data-state={error ? 'error' : pending ? 'connecting' : coreState} data-offline={!voiceAvailable} aria-pressed={listening} aria-busy={pending} disabled={!voiceAvailable || pending} onClick={() => void toggleVoice()}><AudioLines size={29} strokeWidth={1.7} /></button>
        <span className="zh-dock-separator" aria-hidden="true" />
        <button className="zh-dock-btn" type="button" aria-label="Ajuda" title="Ajuda" onClick={() => onNavigate('Ajuda')}><HelpCircle size={25} strokeWidth={1.7} /></button>
        <button className="zh-dock-btn" type="button" aria-label="Histórico" title="Histórico" onClick={() => onNavigate('Histórico')}><Clock3 size={25} strokeWidth={1.7} /></button>
        <button className="zh-dock-btn" type="button" aria-label="Mais opções" title="Mais opções" onClick={() => onNavigate('Mais opções')}><MoreHorizontal size={27} strokeWidth={1.7} /></button>
      </nav>
      {error && <div className="zh-dock-feedback" role="alert">{error}</div>}
    </div>
  );
}
