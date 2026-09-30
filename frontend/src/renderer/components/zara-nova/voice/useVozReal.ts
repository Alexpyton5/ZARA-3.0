/**
 * useVozReal — adapta a máquina de estados real da voz (`useZoeVoice`,
 * renderer/lib/useZoeVoice.ts) para o contrato que a tela Voz da frente
 * CORE espera: `{ state: VoiceState, onMicClick }`.
 *
 * Mapa de estados (useZoeVoice -> VoiceState da interface nova):
 *   'off'         -> 'ready'      (microfone desligado, pronto p/ ligar)
 *   'starting'    -> 'thinking'   (ligando o microfone)
 *   'listening'   -> 'listening'  (ouvindo você)
 *   'waiting'     -> 'thinking'   (a mente está respondendo)
 *   'speaking'    -> 'doing'      (a voz está falando a resposta)
 *   'controlling' -> 'doing'      (o motor está operando o computador)
 *   'error'       -> 'error'
 *
 * NOTA HONESTA (p/ a frente CORE): o `useZoeVoice` conversa com a Zoe
 * através de um webview do Muse (`webviewRef` + `pageReady`). A tela Voz
 * nova precisa decidir o caminho de voz: ou mantém o webview escondido e
 * passa `pageReady=true`, ou roteia a conversa pelo IPC `message.send` +
 * o evento `voice-output-audio` (aí este adaptador precisa de revisão).
 * TODO(CORE): definir o caminho de voz da tela Voz nova.
 */

import type { RefObject } from 'react';
// DEPENDÊNCIAS EXTERNAS (código real, fora de `entrega/`): `useZoeVoice` vive
// em `frontend/src/renderer/lib/useZoeVoice.ts` e `MuseWebview` em
// `frontend/src/renderer/lib/museConversation.ts`. Na árvore real estes
// imports resolvem; em `entrega/` standalone, ainda não. O PORTÃO coloca
// este adaptador junto desses arquivos na integração — não duplicá-los aqui.
import { useZoeVoice } from '../../../lib/useZoeVoice';
import type { MuseWebview } from '../../../lib/museConversation';
import type { VoiceState } from '../types';

type ZoeVoiceState = 'off' | 'starting' | 'listening' | 'waiting' | 'controlling' | 'speaking' | 'error';

const MAPA: Record<ZoeVoiceState, VoiceState> = {
  off: 'ready',
  starting: 'thinking',
  listening: 'listening',
  waiting: 'thinking',
  speaking: 'doing',
  controlling: 'doing',
  error: 'error',
};

export interface VozReal {
  /** Estado no contrato da interface nova. */
  state: VoiceState;
  /** Clique no microfone: liga/desliga a voz (mesmo comportamento da aba Zoe). */
  onMicClick: () => void;
  /** Mensagem de erro legível ('' = sem erro). */
  error: string;
  /** Motor de TTS ativo: 'kore' (bonita, depende de internet/cota) ou 'omnivoice' (local, grátis). */
  engine: 'kore' | 'omnivoice';
  /** A reserva local está disponível? */
  omnivoiceAvailable: boolean;
  /** Troca o motor de voz. */
  trocarMotor: (engine: 'kore' | 'omnivoice') => Promise<void>;
}

export function useVozReal(webviewRef: RefObject<MuseWebview | null>, pageReady: boolean): VozReal {
  const { voiceState, error, engine, omnivoiceAvailable, toggle, changeEngine } = useZoeVoice(webviewRef, pageReady);

  return {
    state: MAPA[voiceState as ZoeVoiceState] ?? 'error',
    onMicClick: () => {
      void toggle();
    },
    error,
    engine,
    omnivoiceAvailable,
    trocarMotor: changeEngine,
  };
}
