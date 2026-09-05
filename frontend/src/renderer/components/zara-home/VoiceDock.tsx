import { useEffect, useRef, useState } from 'react';
import { LayoutGrid, Folder, AudioLines, HelpCircle, Clock, MoreHorizontal } from 'lucide-react';
import type { CoreState } from './types';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore } from '../../lib/aecAudio';

interface VoiceDockProps {
  coreState: CoreState;
  /** Mesma navegação da Sidebar — o dock leva para as seções que já existem. */
  onNavigate?: (section: string) => void;
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
/** Destinos do menu rápido — todos são seções que existem de verdade. */
const MENU_RAPIDO = ['Sistema', 'Projetos', 'Automações', 'ZARA Lab', 'Dispositivos', 'Configurações'];

export function VoiceDock({ coreState, onNavigate }: VoiceDockProps) {
  const [listening, setListening] = useState(false);
  const [menuAberto, setMenuAberto] = useState(false);
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

  // O `listening` era só do renderer: se o Alex fechasse e reabrisse a janela
  // com a voz já ligada, ou se o backend derrubasse o pipeline sozinho, o
  // botão continuava contando uma história própria. `voice-status` devolve o
  // `voice_active` real; ele é quem manda no estado inicial.
  useEffect(() => {
    const status = window.zaraIPC?.voice?.status;
    if (!status) return;
    let alive = true;
    status()
      .then((s: { listening?: boolean }) => {
        if (alive && typeof s?.listening === 'boolean') setListening(s.listening);
      })
      .catch(() => {
        // Sem leitura de status o botão fica como está; não vale inventar.
      });
    return () => { alive = false; };
  }, []);

  // Voz fora do ar: o microfone do renderer não pode continuar aberto nem o
  // botão continuar dizendo "ouvindo". O ajuste do estado é feito no render
  // (padrão de "corrigir estado quando a prop muda"), e o efeito cuida só do
  // que é externo — desligar a captura e cortar o áudio.
  const [viOffline, setViOffline] = useState(coreState === 'offline');
  if (coreState === 'offline' && !viOffline) {
    setViOffline(true);
    setListening(false);
  } else if (coreState !== 'offline' && viOffline) {
    setViOffline(false);
  }

  useEffect(() => {
    if (coreState !== 'offline') return;
    pararAudioAec();
    cortarKore();
  }, [coreState]);

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

  // Menu rápido do botão "mais": só destinos que EXISTEM na Sidebar. É
  // navegação, não uma gaveta de recursos futuros.
  const menuRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!menuAberto) return;
    function fora(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setMenuAberto(false);
    }
    function esc(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuAberto(false);
    }
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [menuAberto]);

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <nav className="zh-dock zh-glass-panel" aria-label="Dock ZARA">
        {/* Três grupos: o botão de voz é o do MEIO de verdade. Com todos os
          * botões como irmãos diretos e `space-between`, a lente saía do eixo
          * porque os separadores e a largura dela deslocavam a distribuição. */}
        <span className="zh-dock-side">
          <button
            className="zh-dock-btn"
            type="button"
            aria-label="Aplicativos"
            title="Aplicativos que a ZARA pode abrir"
            onClick={() => onNavigate?.('Aplicativos')}
          >
            <LayoutGrid size={21} strokeWidth={1.7} />
          </button>
          <span className="zh-dock-separator" aria-hidden="true" />
          <button
            className="zh-dock-btn"
            type="button"
            aria-label="Arquivos e memórias"
            title="Arquivos e memórias"
            onClick={() => onNavigate?.('Memórias')}
          >
            <Folder size={21} strokeWidth={1.7} />
          </button>
        </span>

        <button
          className="zh-dock-voice"
          type="button"
          aria-label={label}
          data-listening={listening}
          data-offline={!voiceAvailable}
          disabled={!voiceAvailable}
          onClick={toggleVoice}
        >
          <AudioLines size={27} strokeWidth={2} />
        </button>

        <span className="zh-dock-side">
          <button
            className="zh-dock-btn"
            type="button"
            aria-label="Ajuda — o que a ZARA sabe fazer"
            title="O que a ZARA sabe fazer"
            onClick={() => onNavigate?.('Ajuda')}
          >
            <HelpCircle size={21} strokeWidth={1.7} />
          </button>
          <span className="zh-dock-separator" aria-hidden="true" />
          <button
            className="zh-dock-btn"
            type="button"
            aria-label="Histórico de conversas"
            title="Histórico de conversas"
            onClick={() => onNavigate?.('Conversas')}
          >
            <Clock size={21} strokeWidth={1.7} />
          </button>
          <button
            className="zh-dock-btn"
            type="button"
            aria-label="Mais"
            title="Menu rápido"
            aria-expanded={menuAberto}
            onClick={() => setMenuAberto((v) => !v)}
          >
            <MoreHorizontal size={21} strokeWidth={1.7} />
          </button>
        </span>
      </nav>

      {menuAberto && (
        <div className="zh-dock-menu zh-glass-panel" ref={menuRef} role="menu" aria-label="Menu rápido">
          {MENU_RAPIDO.map((destino) => (
            <button
              key={destino}
              className="zh-dock-menu-item"
              type="button"
              role="menuitem"
              onClick={() => { setMenuAberto(false); onNavigate?.(destino); }}
            >
              {destino}
            </button>
          ))}
        </div>
      )}

      {coreState === 'offline' && (
        <span className="zh-not-connected" style={{ marginTop: 6 }}>
          Voz não conectada
        </span>
      )}
    </div>
  );
}
