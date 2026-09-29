import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { cortarKore, iniciarAudioAec, pararAudioAec, tocarKore } from './aecAudio';
import { completeSentences, readMuseReply, stableSpeechPrefix, submitToMuse, type MuseWebview } from './museConversation';

type VoiceState = 'off' | 'starting' | 'listening' | 'waiting' | 'speaking' | 'error';

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

export function useZoeVoice(webviewRef: RefObject<MuseWebview | null>, pageReady: boolean) {
  const [voiceState, setVoiceState] = useState<VoiceState>('off');
  const [error, setError] = useState('');
  const [engine, setEngine] = useState<'kore' | 'omnivoice'>('kore');
  const [omnivoiceAvailable, setOmnivoiceAvailable] = useState(false);
  const [museWaitMs, setMuseWaitMs] = useState<number | null>(null);
  const [firstSoundMs, setFirstSoundMs] = useState<number | null>(null);
  const active = useRef(false);
  const busy = useRef(false);
  const pending = useRef<string[]>([]);
  const generation = useRef(0);
  const audioQueue = useRef<Promise<void>>(Promise.resolve());
  const museSubmissionAt = useRef<number | null>(null);

  const stop = useCallback(async () => {
    active.current = false;
    generation.current += 1;
    pending.current = [];
    museSubmissionAt.current = null;
    audioQueue.current = Promise.resolve();
    pararAudioAec();
    cortarKore();
    setVoiceState('off');
    await window.zaraIPC?.voice?.stop?.().catch(() => undefined);
  }, []);

  const speak = useCallback((text: string) => {
    for (const piece of speechPieces(text)) {
      audioQueue.current = audioQueue.current.then(async () => {
        if (!active.current) return;
        setVoiceState('speaking');
        const result = await window.zaraIPC?.voice?.speakZoe?.(piece);
        if (result?.success === false) throw new Error(result.error || 'A voz da ZARA não respondeu.');
      });
    }
  }, []);

  const processOne = useCallback(async (text: string, currentGeneration: number) => {
    const webview = webviewRef.current;
    if (!webview) throw new Error('A conversa da Zoe não está aberta.');
    setVoiceState('waiting');
    setMuseWaitMs(null);
    setFirstSoundMs(null);
    const started = performance.now();
    museSubmissionAt.current = started;
    const submission = await submitToMuse(webview, text);
    if (!submission.submitted) throw new Error(submission.error || 'Não consegui enviar sua fala à Zoe.');
    if (!submission.confirmed) throw new Error('O envio não foi confirmado. Confira a conversa antes de tentar de novo.');

    let previousText = '';
    let consumed = 0;
    let lastChange = performance.now();
    let sawAgent = false;
    let measuredFirst = false;
    let activeAssistantId = '';
    for (let attempt = 0; attempt < 420 && active.current && generation.current === currentGeneration; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 180));
      const reply = await readMuseReply(webview, submission);
      if (reply.assistantId && reply.text) {
        sawAgent = true;
        if (reply.assistantId !== activeAssistantId) {
          activeAssistantId = reply.assistantId;
          previousText = '';
          consumed = 0;
        }
        if (!measuredFirst) {
          measuredFirst = true;
          setMuseWaitMs(Math.round(performance.now() - started));
        }
        if (reply.text !== previousText) {
          lastChange = performance.now();
          // If Muse rewrites an earlier phrase, wait for the finished answer
          // instead of speaking text that it has already corrected.
          if (previousText && !reply.text.startsWith(previousText)) {
            consumed = reply.text.length;
          } else {
            const ready = completeSentences(reply.text, consumed);
            ready.pieces.forEach(speak);
            consumed = ready.consumed;
          }
          previousText = reply.text;
        }
        // The first audio need not wait for Muse to finish a long paragraph.
        // Use only a stable, complete-word prefix to avoid reading a word
        // while it is still being rewritten in the page.
        const prefix = stableSpeechPrefix(previousText, consumed, performance.now() - lastChange);
        if (prefix.piece) {
          speak(prefix.piece);
          consumed = prefix.consumed;
        }
      }
      if (sawAgent && performance.now() - lastChange > (reply.busy ? 2500 : 600)) {
        if (previousText.length > consumed) speak(previousText.slice(consumed));
        await audioQueue.current;
        setVoiceState('listening');
        return;
      }
    }
    if (active.current && generation.current === currentGeneration) {
      throw new Error('A Zoe demorou a responder. Confira a conversa na tela.');
    }
  }, [webviewRef, speak]);

  const drain = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    const currentGeneration = generation.current;
    try {
      while (active.current && pending.current.length && currentGeneration === generation.current) {
        const text = pending.current.shift();
        if (text) await processOne(text, currentGeneration);
      }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Falha na conversa por voz.';
      setError(message);
      await stop();
      setVoiceState('error');
    } finally {
      busy.current = false;
    }
  }, [processOne, stop]);

  useEffect(() => {
    const unAudio = window.zaraIPC?.on?.voiceOutputAudio?.((data) => {
      if (!active.current) return;
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
      const text = String(data?.text || '').trim();
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
      if (active.current) void stop();
    };
  }, [drain, stop]);

  const toggle = useCallback(async () => {
    if (active.current) { await stop(); return; }
    if (!pageReady) { setError('Abra a conversa da Zoe antes de ligar a voz.'); return; }
    setError('');
    setVoiceState('starting');
    try {
      const result = await window.zaraIPC?.voice?.startZoe?.();
      if (result?.success !== true) throw new Error(result?.error || 'O microfone da ZARA não iniciou.');
      active.current = true;
      generation.current += 1;
      if (result.mode !== 'local' && result.audio_transport !== 'local') {
        const capture = await iniciarAudioAec((pcm) => window.zaraIPC?.voice?.sendMicChunk?.(pcm));
        if (!capture.ok) throw new Error('Microfone indisponível. Verifique a permissão de áudio.');
      }
      setVoiceState('listening');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar a voz.');
      await stop();
      setVoiceState('error');
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

  return { voiceState, error, engine, omnivoiceAvailable, museWaitMs, firstSoundMs, toggle, changeEngine };
}
