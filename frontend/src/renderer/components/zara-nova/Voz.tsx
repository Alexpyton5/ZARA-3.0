/** Tela Voz: órbita com o avatar, estados reais do pipeline de voz e botão de microfone.
 *  Visual fiel ao molde (voice-view).
 *
 *  PIPELINE REAL (não reinventado): `useZoeVoice` (pc-source/renderer/lib/useZoeVoice.ts)
 *  com a máquina de estados 'off' | 'starting' | 'listening' | 'waiting' |
 *  'controlling' | 'speaking' | 'error'. A conversa por voz é NATURAL e em
 *  tempo real: o Alex fala, a zoe pensa (submitToMuse) e responde FALANDO —
 *  a resposta sai em streaming por frases completas (completeSentences /
 *  stableSpeechPrefix), não é só ler texto em voz alta.
 *
 *  Cascata de TTS (Manual §4.3, decisão do Alex 2026-09-27): Kore principal →
 *  Kore principal → Edge → Kokoro (reserva local).
 *
 *  A fala contínua chega pelo evento de áudio da Kore; respostas de texto
 *  também podem solicitar TTS pelo IPC `zoe-voice-speak`, cujo handler está
 *  registrado no backend. A reprodução física ainda precisa de teste no PC.
 *
 *  Este componente só REFLETE o estado que recebe por props e devolve o clique
 *  no microfone. A fiação (useZoeVoice + webview + window.zaraIPC) é da
 *  frente FIAÇÃO. Sem fiação, os estados ficam em 'ready' e o rodapé explica —
 *  nunca se finge estado de voz. */

import { useState } from 'react';
import { Mic, MicOff } from 'lucide-react';
import type { VoiceState, AvatarInfo } from './types';
import { avatarOriginal } from './avatares';

/** Estados reais do pipeline de voz (useZoeVoice). */
export type EstadoVozReal =
  | 'off'
  | 'starting'
  | 'listening'
  | 'waiting'
  | 'controlling'
  | 'speaking'
  | 'error';

/** Mapeia o estado real do pipeline para o VoiceState do contrato de telas. */
export function mapearEstadoVoz(estado: EstadoVozReal): VoiceState {
  switch (estado) {
    case 'listening':
      return 'listening';
    case 'waiting':
    case 'starting':
      return 'thinking';
    case 'controlling':
    case 'speaking':
      return 'doing';
    case 'error':
      return 'error';
    case 'off':
    default:
      return 'ready';
  }
}

export type MotorVoz = 'kore' | 'edge' | 'kokoro';

export interface VozProps {
  state: VoiceState;
  onMicClick: () => void;
  /** Avatar exibido na órbita (padrão: LYRA, a voz da TROPA dev. — original fiel). */
  avatar?: AvatarInfo;
  /** Motor de TTS que falou por último (Kore principal; Edge/Kokoro entram sozinhos na reserva). */
  motor?: MotorVoz;
  /** Mensagem de erro real do pipeline, quando houver. */
  erro?: string;
}

const LYRA_PADRAO: AvatarInfo = {
  id: 'lyra',
  nome: 'LYRA',
  papel: 'Voz da TROPA dev.',
  imagemUrl: avatarOriginal('lyra'),
};

const COPIA: Record<VoiceState, { titulo: string; texto: string }> = {
  ready: {
    titulo: 'Vamos conversar?',
    texto: 'Toque no microfone e fale. Você fala, a Zoe responde falando — uma conversa de verdade.',
  },
  listening: {
    titulo: 'Ouvindo',
    texto: 'Pode falar. A equipe está acompanhando.',
  },
  thinking: {
    titulo: 'Pensando',
    texto: 'A Zoe está juntando o contexto para responder.',
  },
  doing: {
    titulo: 'Respondendo',
    texto: 'A resposta está saindo em voz — e, se for o caso, indo para o computador.',
  },
  error: {
    titulo: 'Algo não saiu como esperado',
    texto: 'Toque no microfone para tentar de novo.',
  },
};

const MOTOR_ROTULO: Record<MotorVoz, string> = {
  kore: 'Kore',
  edge: 'Edge',
  kokoro: 'Kokoro',
};

const ESTADOS: Array<{ key: VoiceState; rotulo: string }> = [
  { key: 'listening', rotulo: 'Ouvindo' },
  { key: 'thinking', rotulo: 'Pensando' },
  { key: 'doing', rotulo: 'Fazendo' },
];

export function Voz({ state, onMicClick, avatar = LYRA_PADRAO, motor, erro }: VozProps) {
  const [imagemFalhou, setImagemFalhou] = useState(false);
  const { titulo, texto } = COPIA[state];
  const ativo = state === 'listening' || state === 'thinking' || state === 'doing';

  return (
    <section className="voice-view" data-state={state} aria-label="Modo voz">
      <div className="voice-orbit">
        <span className="orbit-ring" aria-hidden="true" />
        <div className="voice-portrait">
          {avatar.imagemUrl && !imagemFalhou ? (
            <img src={avatar.imagemUrl} alt={`${avatar.nome}, ${avatar.papel}`} onError={() => setImagemFalhou(true)} />
          ) : (
            <span className="avatar-initial" aria-label={avatar.nome}>
              {avatar.nome.charAt(0)}
            </span>
          )}
        </div>
      </div>

      <h2>{titulo}</h2>
      <p>{erro || texto.replace(/a Zoe|A Zoe/g, avatar.nome)}</p>

      <div className="voice-states" aria-label="Estado atual da voz" role="status">
        {ESTADOS.map(({ key, rotulo }) => (
          <span
            key={key}
            className={state === key ? 'active' : ''}
            aria-current={state === key ? 'true' : undefined}
            title="O estado vem do pipeline real de voz."
          >
            {rotulo}
          </span>
        ))}
      </div>

      <button
        type="button"
        className="voice-mic"
        onClick={onMicClick}
        aria-label={ativo ? 'Encerrar a conversa por voz' : 'Começar a falar'}
        aria-pressed={ativo}
      >
        {ativo ? <MicOff size={25} aria-hidden="true" /> : <Mic size={25} aria-hidden="true" />}
      </button>

      <span className="voice-demo">{motor ? `Voz: ${MOTOR_ROTULO[motor]}` : 'Entre na sua conta para conversar.'}</span>
    </section>
  );
}
