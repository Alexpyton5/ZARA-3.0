import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import * as conversation from '../src/renderer/lib/pilotConversation';
import * as muse from '../src/renderer/lib/museConversation';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

// Execute the actual hook with deterministic React refs, IPC and audio doubles.
// This verifies lifecycle logic, not a physical microphone or speaker.
function voiceHarness(options: {
  command?: conversation.PilotBridge['command'];
  context?: conversation.PilotBridge['context'];
  speak?: (text: string) => Promise<any>;
  start?: () => Promise<any>;
  playback?: () => Promise<void>;
  read?: () => Promise<muse.MuseReply>;
} = {}) {
  const states: unknown[] = [];
  const calls = { commands: [] as string[], contexts: [] as string[], spoken: [] as string[], submitted: [] as string[], played: [] as string[], stops: 0, providerStops: 0 };
  const events: Record<string, (data: any) => void> = {};
  const timers: Array<{ callback: () => void; delay: number }> = [];
  let now = 0;
  let reply: muse.MuseReply = { assistantId: 'answer', text: 'Primeira frase.', busy: true };
  const webview = { executeJavaScript: async (code: string) => {
    if (code.includes('const stop = document.querySelector')) { calls.providerStops++; return; }
    calls.submitted.push(code);
    return { submitted: true, confirmed: true, userId: 'user', previousAssistantId: 'old' };
  } };
  const react = {
    useRef: (value: unknown) => ({ current: value }),
    useCallback: (fn: unknown) => fn,
    useState: (value: unknown) => {
      const index = states.push(value) - 1;
      return [value, (next: unknown) => { states[index] = next; }];
    },
    useEffect: (fn: () => unknown) => { fn(); },
  };
  const ipc = {
    pilot: {
      command: async (text: string) => { calls.commands.push(text); return options.command ? options.command(text) : { handled: false, success: true, response: '' }; },
      context: async (text: string) => { calls.contexts.push(text); return options.context ? options.context(text) : { success: true, context: `fresh:${text}` }; },
    },
    voice: {
      startZoe: options.start || (async () => ({ success: true, mode: 'local' })),
      speakZoe: async (text: string) => {
        calls.spoken.push(text);
        if (options.speak) return options.speak(text);
        events.audio({ pcm: 'test-pcm', sampleRate: 24000 });
        return { success: true };
      },
      stop: async () => { calls.stops++; },
    },
    on: {
      voiceOutputAudio: (callback: (data: any) => void) => { events.audio = callback; return () => {}; },
      zoeVoiceInput: (callback: (data: any) => void) => { events.input = callback; return () => {}; },
    },
  };
  const source = readFileSync(path.resolve(__dirname, '../../src/renderer/lib/useZoeVoice.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const exports: any = {};
  vm.runInNewContext(code, {
    exports,
    require: (name: string) => {
      if (name === 'react') return react;
      if (name === './pilotConversation') return { ...conversation, readPilotReply: async () => options.read ? options.read() : reply };
      if (name === './museConversation') return muse;
      if (name === './computerAgentTrigger') return { extractZoeComputerGoal: () => null };
      if (name.includes('computerAgentBridge')) return { getComputerAgentBridge: () => { throw new Error('Unexpected manual execution'); } };
      if (name === './aecAudio') return {
        cortarKore: () => {}, pararAudioAec: () => {}, iniciarAudioAec: async () => ({ ok: true }),
        tocarKore: (pcm: string) => calls.played.push(pcm),
        aguardarFimKore: options.playback || (async () => undefined),
      };
      throw new Error(`Unexpected import ${name}`);
    },
    window: { zaraIPC: ipc },
    Error,
    performance: { now: () => now },
    setTimeout: (callback: () => void, delay: number) => { timers.push({ callback, delay }); },
  });
  const voice = exports.useZoeVoice({ current: webview }, true, 'muse');
  const flush = async () => { for (let i = 0; i < 60; i++) await Promise.resolve(); };
  const tick = async (count = 1) => {
    for (let i = 0; i < count; i++) {
      await flush();
      const timer = timers.shift();
      if (!timer) throw new Error('Expected a reply polling timer');
      now += timer.delay;
      timer.callback();
      await flush();
    }
  };
  return { voice, states, calls, events, flush, tick, setReply: (value: muse.MuseReply) => { reply = value; }, time: () => now };
}

test('busy replies remain open through a 2.5-second plateau and speak the later continuation once', async () => {
  const h = voiceHarness();
  await h.voice.toggle();
  h.events.input({ text: 'conte algo' });
  await h.tick(20);
  assert.ok(h.time() > 2500);
  assert.notEqual(h.states[0], 'listening');
  assert.deepEqual(h.calls.spoken, ['Primeira frase.']);
  h.setReply({ assistantId: 'answer', text: 'Primeira frase. Segunda frase.', busy: false });
  await h.tick(5);
  assert.equal(h.states[0], 'listening');
  assert.deepEqual(h.calls.spoken, ['Primeira frase.', 'Segunda frase.']);
  assert.deepEqual(h.calls.commands, ['conte algo']);
  assert.deepEqual(h.calls.contexts, ['conte algo']);
  assert.match(h.calls.submitted[0], /fresh:conte algo/);
  assert.equal(h.states[4], 180); // transcribed input to first matching pilot text
  assert.equal(h.states[5], 180); // transcribed input to first mocked PCM event
  await h.voice.stop();
});

test('ordinary voice commands speak the executor result without submitting to the model', async () => {
  for (const success of [true, false]) {
    const response = success ? 'Volume confirmado em 20%.' : 'Não consegui ajustar o volume.';
    const h = voiceHarness({ command: async () => ({ handled: true, success, response }) });
    await h.voice.toggle();
    h.events.input({ text: 'diminua o volume' });
    await h.flush();
    assert.deepEqual(h.calls.spoken, [response]);
    assert.deepEqual(h.calls.contexts, []);
    assert.deepEqual(h.calls.submitted, []);
    assert.equal(h.states[0], 'listening');
    await h.voice.stop();
  }
});

test('a greeting answer plays automatically and returns to listening without a play click', async () => {
  const h = voiceHarness({ read: async () => ({ assistantId: 'reply-text', text: 'Oi, Alex!', busy: false }) });
  await h.voice.toggle();
  h.events.input({ text: 'Oi' });
  await h.tick(5);
  assert.deepEqual(h.calls.spoken, ['Oi, Alex!']);
  assert.deepEqual(h.calls.played, ['test-pcm']);
  assert.equal(h.states[0], 'listening');
  assert.equal(h.states[5], 180);
  await h.voice.stop();
});

test('the voice remains speaking until the renderer finishes scheduled playback', async () => {
  const playback = deferred<void>();
  const h = voiceHarness({ playback: () => playback.promise, read: async () => ({ assistantId: 'reply', text: 'Olá.', busy: false }) });
  await h.voice.toggle();
  h.events.input({ text: 'oi' });
  await h.tick(5);
  assert.equal(h.states[0], 'speaking');
  playback.resolve();
  await h.flush();
  assert.equal(h.states[0], 'listening');
  await h.voice.stop();
});

test('context lookup errors remain visible and never submit a context-free voice request', async () => {
  const h = voiceHarness({ context: async () => ({ success: false, context: '', error: 'Vault indisponível.' }) });
  await h.voice.toggle();
  h.events.input({ text: 'qual é meu plano?' });
  await h.flush();
  assert.equal(h.states[0], 'error');
  assert.match(String(h.states[1]), /Vault indisponível/);
  assert.equal(h.calls.submitted.length, 0);
  assert.equal(h.calls.spoken.length, 0);
});

test('stop while context is in flight suppresses submission and cannot poison a restarted session', async () => {
  const pending = deferred<{ success: boolean; context: string }>();
  let contextCalls = 0;
  const h = voiceHarness({ context: async () => ++contextCalls === 1 ? pending.promise : { success: true, context: 'new' } });
  await h.voice.toggle();
  h.events.input({ text: 'old question' });
  await h.flush();
  await h.voice.stop();
  await h.voice.toggle();
  pending.resolve({ success: true, context: 'old' });
  await h.flush();
  assert.equal(h.states[0], 'listening');
  assert.equal(h.calls.submitted.length, 0);
  h.events.input({ text: 'new question' });
  await h.tick();
  assert.equal(h.calls.submitted.length, 1);
  assert.match(h.calls.submitted[0], /Pedido do Alex:[\s\S]*new question/);
  await h.voice.stop();
});

test('stop while a reply read is in flight drops the old text and audio', async () => {
  const read = deferred<muse.MuseReply>();
  const h = voiceHarness({ read: () => read.promise });
  await h.voice.toggle();
  h.events.input({ text: 'question' });
  await h.tick();
  await h.voice.stop();
  read.resolve({ assistantId: 'old', text: 'Do not speak me.', busy: false });
  await h.flush();
  h.events.audio({ pcm: 'old-pcm' });
  assert.equal(h.states[0], 'off');
  assert.deepEqual(h.calls.spoken, []);
  assert.deepEqual(h.calls.played, []);
});

test('barge-in drops the old reply, keeps the mic open and accepts the next turn', async () => {
  const delayed = deferred<muse.MuseReply>();
  let reads = 0;
  const h = voiceHarness({ read: async () => ++reads === 1 ? delayed.promise : { assistantId: 'new', text: 'Nova resposta.', busy: false } });
  await h.voice.toggle();
  h.events.input({ text: 'primeira pergunta' });
  await h.tick();
  h.events.input({ interrupt: true, text: '' });
  await h.flush();
  assert.equal(h.states[0], 'listening');
  assert.equal(h.calls.stops, 0);
  assert.equal(h.calls.providerStops, 1);
  delayed.resolve({ assistantId: 'old', text: 'Não fale esta resposta.', busy: false });
  await h.flush();
  assert.deepEqual(h.calls.spoken, []);
  h.events.input({ text: 'segunda pergunta' });
  await h.tick(5);
  assert.deepEqual(h.calls.spoken, ['Nova resposta.']);
  await h.voice.stop();
});

test('queued speech captures its generation and cannot replay after stop and restart', async () => {
  const firstSpeech = deferred<{ success: boolean }>();
  let spoken = 0;
  const h = voiceHarness({
    command: async () => ({ handled: true, success: true, response: `${'palavra '.repeat(120)}fim.` }),
    speak: async () => ++spoken === 1 ? firstSpeech.promise : { success: true },
  });
  await h.voice.toggle();
  h.events.input({ text: 'long command' });
  await h.flush();
  assert.equal(h.calls.spoken.length, 1);
  const stopping = h.voice.stop();
  const restarting = h.voice.toggle();
  await h.flush();
  h.events.audio({ pcm: 'old-pcm' });
  assert.deepEqual(h.calls.played, []);
  firstSpeech.resolve({ success: false });
  await stopping;
  await restarting;
  await h.flush();
  assert.equal(h.calls.spoken.length, 1);
  assert.equal(h.states[0], 'listening');
  assert.equal(h.states[1], '');
  h.events.audio({ pcm: 'late-old-pcm' });
  assert.deepEqual(h.calls.played, []);
  await h.voice.stop();
});

test('stop during microphone startup prevents a delayed start from reactivating voice', async () => {
  const start = deferred<{ success: boolean; mode: string }>();
  const h = voiceHarness({ start: () => start.promise });
  const starting = h.voice.toggle();
  await h.flush();
  const stopping = h.voice.stop();
  start.resolve({ success: true, mode: 'local' });
  await starting;
  await stopping;
  await h.flush();
  assert.equal(h.states[0], 'off');
  h.events.input({ text: 'ignored' });
  await h.flush();
  assert.deepEqual(h.calls.commands, []);
});

test('assistant node replacement does not speak the same already-consumed text twice', async () => {
  const h = voiceHarness();
  await h.voice.toggle();
  h.events.input({ text: 'question' });
  await h.tick();
  h.setReply({ assistantId: 'replacement', text: 'Primeira frase.', busy: true });
  await h.tick(2);
  assert.deepEqual(h.calls.spoken, ['Primeira frase.']);
  await h.voice.stop();
});
