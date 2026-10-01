import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { aguardarFimKore, cortarKore, iniciarAudioAec, pararAudioAec, tocarKore } from './aecAudio';
import { completeSentences, stableSpeechPrefix, type MuseWebview } from './museConversation';
import { cancelPilotReply, checkPilotCancellation, preparePilotTurn, readPilotReply, submitToPilot, type PilotProvider } from './pilotConversation';
import { extractZoeComputerGoal } from './computerAgentTrigger';
import { getComputerAgentBridge } from '../components/computer-agent/computerAgentBridge';

type VoiceState = 'off' | 'starting' | 'listening' | 'waiting' | 'controlling' | 'speaking' | 'error';

function traceVoice(stage: string, details: string) {
  console.info(`[VOICE_TRACE] stage=${stage} ${details}`);
}

function speechPieces(text: string): string[] {
  const pieces: string[] = [];
  let left = text.trim();
  while (left.length > 400) {
    const splitAt = left.lastIndexOf(' ', 380);
    const cut = splitAt > 100 ? splitAt : 380;
    pieces.push(left.slice(0, cut).trim());
    left = left.slice(cut).trim();
  }
  if (left) pieces.push(left);
  return pieces;
}

export function useZoeVoice(webviewRef: RefObject<MuseWebview | null>, pageReady: boolean, provider: PilotProvider = 'muse') {
  const [voiceState, setVoiceState] = useState<VoiceState>('off');
  const [error, setError] = useState('');
  const [engine, setEngine] = useState<'kore' | 'omnivoice'>('kore');
  const [omnivoiceAvailable, setOmnivoiceAvailable] = useState(false);
  const [museWaitMs, setMuseWaitMs] = useState<number | null>(null);
  const [firstSoundMs, setFirstSoundMs] = useState<number | null>(null);
  const active = useRef(false);
  const busy = useRef<number | null>(null);
  const starting = useRef(false);
  const startRequest = useRef<Promise<unknown> | null>(null);
  const stopTask = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef<string[]>([]);
  const generation = useRef(0);
  const audioQueue = useRef<Promise<void>>(Promise.resolve());
  const speechError = useRef<Error | null>(null);
  const museSubmissionAt = useRef<number | null>(null);
  const audioGeneration = useRef<number | null>(null);
  const interruptTask = useRef<Promise<unknown>>(Promise.resolve());

  const stop = useCallback(async () => {
    const wasBusy = busy.current !== null;
    const webview = webviewRef.current;
    const previousQueue = audioQueue.current;
    const previousStart = startRequest.current;
    const previousStop = stopTask.current;
    const stopPilot = wasBusy && webview ? cancelPilotReply(webview, provider).catch(() => undefined) : Promise.resolve();
    active.current = false;
    starting.current = false;
    generation.current += 1;
    busy.current = null;
    pending.current = [];
    museSubmissionAt.current = null;
    audioGeneration.current = null;
    audioQueue.current = Promise.resolve();
    speechError.current = null;
    pararAudioAec();
    cortarKore();
    setVoiceState('off');
    const stopping = (async () => {
      await Promise.allSettled([previousStop, ...(previousStart ? [previousStart] : [])]);
      pararAudioAec();
      await Promise.allSettled([
        Promise.resolve(window.zaraIPC?.voice?.stop?.()),
        previousQueue,
        stopPilot,
      ]);
    })();
    stopTask.current = stopping;
    await stopping;
  }, [webviewRef, provider]);

  const speak = useCallback((text: string, currentGeneration: number) => {
    for (const piece of speechPieces(text)) {
      audioQueue.current = audioQueue.current.then(async () => {
        if (!active.current || generation.current !== currentGeneration || speechError.current) return;
        setVoiceState('speaking');
        audioGeneration.current = currentGeneration;
        const speechStarted = performance.now();
        traceVoice('ZOE_TTS_REQUEST', `chars=${piece.length}`);
        const result = await window.zaraIPC?.voice?.speakZoe?.(piece);
        if (!active.current || generation.current !== currentGeneration) return;
        if (result?.success !== true) throw new Error(result?.error || 'A voz da ZARA não respondeu.');
        traceVoice('ZOE_TTS_COMPLETE', `engine=${result.engine || 'unknown'} ms=${Math.round(performance.now() - speechStarted)}`);
      }).catch((cause) => {
        if (!active.current || generation.current !== currentGeneration) return;
        speechError.current = cause instanceof Error ? cause : new Error('A voz não respondeu.');
      });
    }
  }, []);

  const processOne = useCallback(async (text: string, currentGeneration: number) => {
    const cancelled = () => !active.current || generation.current !== currentGeneration;
    await interruptTask.current;
    checkPilotCancellation(cancelled);
    speechError.current = null;
    const webview = webviewRef.current;
    setMuseWaitMs(null);
    setFirstSoundMs(null);
    const started = performance.now();
    traceVoice('ZOE_TURN_START', `chars=${text.length}`);
    museSubmissionAt.current = started;
    const computerGoal = extractZoeComputerGoal(text);
    const manualFallback = computerGoal === null ? undefined : async () => {
      if (!computerGoal) {
        return { success: false, response: 'Diga o que você quer que eu faça no computador.' };
      }
      const bridge = getComputerAgentBridge();
      if (!bridge) throw new Error('O controle do computador não está disponível nesta versão.');
      const result = await bridge.run(computerGoal) as {
        success?: boolean; verified?: boolean; refused?: boolean;
        error?: string; steps?: Array<{ outcome?: string }>;
      };
      checkPilotCancellation(cancelled);
      if (!result?.success) return { success: false, response: `Não consegui concluir no computador. ${result?.error || 'O executor não confirmou a ação.'}` };
      const count = result.steps?.length ?? 0;
      return { success: true, response: result.verified
        ? `Concluí ${count} passo${count === 1 ? '' : 's'} e confirmei o resultado na tela.`
        : `Enviei ${count} passo${count === 1 ? '' : 's'}, mas não consegui confirmar todos na tela.` };
    };
    setVoiceState('controlling');
    const turn = await preparePilotTurn(text, window.zaraIPC?.pilot, cancelled, manualFallback);
    traceVoice('ZOE_TURN_PREPARED', `handled=${turn.handled} ms=${Math.round(performance.now() - started)}`);
    if (turn.handled) {
      speak(turn.response, currentGeneration);
      await audioQueue.current;
      checkPilotCancellation(cancelled);
      if (speechError.current) throw speechError.current;
      await aguardarFimKore();
      checkPilotCancellation(cancelled);
      setVoiceState('listening');
      return;
    }
    if (!webview) throw new Error('A conversa da Zoe não está aberta.');
    setVoiceState('waiting');
    const submission = await submitToPilot(webview, provider, turn.text, turn.context, cancelled);
    traceVoice('ZOE_SUBMIT', `submitted=${submission.submitted} confirmed=${submission.confirmed} ms=${Math.round(performance.now() - started)}`);
    checkPilotCancellation(cancelled);
    if (!submission.submitted) throw new Error(submission.error || 'Não consegui enviar sua fala à Zoe.');
    if (!submission.confirmed) throw new Error('O envio não foi confirmado. Confira a conversa antes de tentar de novo.');

    let previousText = '';
    let consumed = 0;
    let lastChange = performance.now();
    let measuredFirst = false;
    let previousCorrelation = '';
    for (let attempt = 0; attempt < 420 && active.current && generation.current === currentGeneration; attempt++) {
      if (speechError.current) throw speechError.current;
      await new Promise(resolve => setTimeout(resolve, 180));
      checkPilotCancellation(cancelled);
      const reply = await readPilotReply(webview, provider, submission);
      checkPilotCancellation(cancelled);
      if (reply.correlation && reply.correlation !== previousCorrelation) {
        previousCorrelation = reply.correlation;
        traceVoice('ZOE_REPLY_CORRELATION', `result=${reply.correlation}`);
      }
      if (reply.correlation === 'superseded' || reply.correlation === 'ambiguous') {
        throw new Error('Outra conversa entrou no mesmo turno. Confira sua conta antes de continuar por voz.');
      }
      if (reply.assistantId && reply.text) {
        if (!measuredFirst) {
          measuredFirst = true;
          setMuseWaitMs(Math.round(performance.now() - started));
          traceVoice('ZOE_FIRST_REPLY_TEXT', `chars=${reply.text.length} ms=${Math.round(performance.now() - started)}`);
        }
        if (reply.text !== previousText) {
          lastChange = performance.now();
          // If Muse rewrites an earlier phrase, wait for the finished answer
          // instead of speaking text that it has already corrected.
          if (previousText && !reply.text.startsWith(previousText)) {
            consumed = reply.text.length;
          } else {
            const ready = completeSentences(reply.text, consumed);
            ready.pieces.forEach(piece => speak(piece, currentGeneration));
            consumed = ready.consumed;
          }
          previousText = reply.text;
        }
        // The first audio need not wait for Muse to finish a long paragraph.
        // Use only a stable, complete-word prefix to avoid reading a word
        // while it is still being rewritten in the page.
        const prefix = stableSpeechPrefix(previousText, consumed, performance.now() - lastChange);
        if (prefix.piece) {
          speak(prefix.piece, currentGeneration);
          consumed = prefix.consumed;
        }
      }
      if (reply.assistantId && reply.text && !reply.busy && performance.now() - lastChange > 600) {
        if (previousText.length > consumed) speak(previousText.slice(consumed), currentGeneration);
        await audioQueue.current;
        checkPilotCancellation(cancelled);
        if (speechError.current) throw speechError.current;
        await aguardarFimKore();
        checkPilotCancellation(cancelled);
        setVoiceState('listening');
        traceVoice('ZOE_TURN_COMPLETE', `ms=${Math.round(performance.now() - started)}`);
        return;
      }
    }
    if (active.current && generation.current === currentGeneration) {
      throw new Error('A Zoe demorou a responder. Confira a conversa na tela.');
    }
  }, [webviewRef, speak, provider]);

  const drain = useCallback(async () => {
    const currentGeneration = generation.current;
    if (busy.current === currentGeneration) return;
    busy.current = currentGeneration;
    try {
      while (active.current && pending.current.length && currentGeneration === generation.current) {
        const text = pending.current.shift();
        if (text) await processOne(text, currentGeneration);
      }
    } catch (cause) {
      if (!active.current || currentGeneration !== generation.current) return;
      const message = cause instanceof Error ? cause.message : 'Falha na conversa por voz.';
      traceVoice('ZOE_TURN_ERROR', `result=FAIL generation=${currentGeneration}`);
      setError(message);
      const stopping = stop();
      const errorGeneration = generation.current;
      await stopping;
      if (generation.current === errorGeneration) setVoiceState('error');
    } finally {
      if (busy.current === currentGeneration) busy.current = null;
    }
  }, [processOne, stop]);

  useEffect(() => {
    const unAudio = window.zaraIPC?.on?.voiceOutputAudio?.((data) => {
      if (!active.current || audioGeneration.current !== generation.current) return;
      if (data?.stop) cortarKore();
      else if (data?.pcm) {
        if (museSubmissionAt.current !== null) {
          setFirstSoundMs(Math.round(performance.now() - museSubmissionAt.current));
          museSubmissionAt.current = null;
        }
        tocarKore(data.pcm, data.sampleRate || 24000);
      }
    });
    const unInput = window.zaraIPC?.on?.zoeVoiceInput?.((data) => {
      if (active.current && data?.interrupt) {
        generation.current += 1;
        busy.current = null;
        pending.current = [];
        audioGeneration.current = null;
        museSubmissionAt.current = null;
        audioQueue.current = Promise.resolve();
        speechError.current = null;
        cortarKore();
        const webview = webviewRef.current;
        if (webview) interruptTask.current = cancelPilotReply(webview, provider).catch(() => undefined);
        setVoiceState('listening');
        traceVoice('ZOE_BARGE_IN', 'result=LISTENING');
        return;
      }
      const text = String(data?.text || '').trim();
      traceVoice('ZOE_INPUT', `chars=${text.length} accepted=${active.current && Boolean(text)}`);
      if (!active.current || !text) return;
      pending.current.push(text);
      void drain();
    });
    void window.zaraIPC?.voice?.getEngine?.().then((result) => {
      if (result?.success) {
        setEngine(result.engine === 'omnivoice' ? 'omnivoice' : 'kore');
        setOmnivoiceAvailable(Boolean(result.omnivoice_available));
      }
    }).catch(() => undefined);
    return () => {
      unAudio?.();
      unInput?.();
      if (active.current || starting.current) void stop();
    };
  }, [drain, stop]);

  useEffect(() => {
    if (!pageReady && (active.current || starting.current)) void stop();
  }, [pageReady, stop]);

  const toggle = useCallback(async () => {
    if (active.current || starting.current) { await stop(); return; }
    if (!pageReady) { setError('Abra sua conta e entre na conversa antes de ligar a voz.'); return; }
    setError('');
    setVoiceState('starting');
    starting.current = true;
    const currentGeneration = ++generation.current;
    const cancelled = () => currentGeneration !== generation.current;
    try {
      await stopTask.current;
      checkPilotCancellation(cancelled);
      const request = Promise.resolve(window.zaraIPC?.voice?.startZoe?.());
      startRequest.current = request;
      const result = await request;
      if (startRequest.current === request) startRequest.current = null;
      checkPilotCancellation(cancelled);
      if (result?.success !== true) throw new Error(result?.error || 'O microfone da ZARA não iniciou.');
      active.current = true;
      if (result.mode !== 'local' && result.audio_transport !== 'local') {
        const captureRequest = iniciarAudioAec((pcm) => {
          if (active.current && !cancelled()) window.zaraIPC?.voice?.sendMicChunk?.(pcm);
        });
        startRequest.current = captureRequest;
        const capture = await captureRequest;
        if (startRequest.current === captureRequest) startRequest.current = null;
        checkPilotCancellation(cancelled);
        if (!capture.ok) throw new Error('Microfone indisponível. Verifique a permissão de áudio.');
      }
      setVoiceState('listening');
    } catch (cause) {
      if (cancelled()) return;
      setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar a voz.');
      const stopping = stop();
      const errorGeneration = generation.current;
      await stopping;
      if (generation.current === errorGeneration) setVoiceState('error');
    } finally {
      if (!cancelled()) starting.current = false;
    }
  }, [pageReady, stop]);

  const changeEngine = useCallback(async (value: 'kore' | 'omnivoice') => {
    const result = await window.zaraIPC?.voice?.setEngine?.(value);
    if (result?.success !== true) {
      setError(result?.error || 'Não foi possível trocar a voz.');
      return;
    }
    setEngine(value);
  }, []);

  return { voiceState, error, engine, omnivoiceAvailable, museWaitMs, firstSoundMs, toggle, changeEngine, stop };
}
