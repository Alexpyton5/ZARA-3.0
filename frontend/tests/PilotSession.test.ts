import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import * as conversation from '../src/renderer/lib/pilotConversation';
import * as learning from '../src/renderer/lib/pilotLearning';

function sessionHarness(options: {
  command?: conversation.PilotBridge['command'];
  context?: conversation.PilotBridge['context'];
  goal?: string;
  signedIn?: boolean;
  learn?: learning.PilotLearningBridge['learn'];
} = {}) {
  const states: any[] = [], refs: any[] = [], effects: any[] = [];
  let stateIndex = 0, refIndex = 0, effectIndex = 0;
  const calls = { commands: [] as string[], contexts: [] as string[], messages: [] as Array<{ text: string; context?: string }>, learned: [] as learning.PilotTurnObservation[], manual: 0, stops: 0 };
  const events: Record<string, () => void> = {};
  const voice = { voiceState: 'off', stop: async () => { calls.stops++; } };
  const webview = {
    executeJavaScript: async (code: string) => code.includes('signIn') ? options.signedIn !== false : undefined,
    addEventListener: (name: string, listener: () => void) => { events[name] = listener; },
    removeEventListener: (name: string) => { delete events[name]; }, reload: () => {},
  };
  const react = {
    createContext: () => ({ Provider: 'session' }), useContext: () => undefined,
    useCallback: (fn: unknown) => fn,
    useRef: (value: unknown) => { const index = refIndex++; return refs[index] ||= { current: value }; },
    useState: (value: any) => {
      const index = stateIndex++;
      if (!(index in states)) states[index] = typeof value === 'function' ? value() : value;
      return [states[index], (next: any) => { states[index] = next; }];
    },
    useEffect: (fn: () => unknown, deps: unknown[]) => {
      const index = effectIndex++;
      if (!effects[index] || deps.some((dep, i) => dep !== effects[index].deps[i])) {
        effects[index]?.cleanup?.(); effects[index] = { deps, cleanup: fn() };
      }
    },
  };
  const exports: any = {};
  const source = readFileSync(path.resolve(__dirname, '../../src/renderer/lib/PilotSession.tsx'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInNewContext(code, {
    exports, Error,
    require: (name: string) => {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx: (type: unknown, props: unknown) => ({ type, props }), jsxs: (type: unknown, props: unknown) => ({ type, props }) };
      if (name === './useZoeVoice') return { useZoeVoice: () => voice };
      if (name === './pilotLearning') return learning;
      if (name === './computerAgentTrigger') return { extractZoeComputerGoal: () => options.goal ?? null };
      if (name.includes('computerAgentBridge')) return { getComputerAgentBridge: () => ({ run: async () => { calls.manual++; return { success: true, verified: true }; } }) };
      if (name === './pilotConversation') return {
        ...conversation,
        sendPilotMessage: async (_webview: unknown, _provider: unknown, text: string, cancelled: () => boolean, context?: string, onComplete?: (submission: any, reply: any) => void) => {
          conversation.checkPilotCancellation(cancelled);
          calls.messages.push({ text, context });
          onComplete?.({ submitted: true, confirmed: true, userId: 'user', previousAssistantId: 'old' }, { assistantId: 'reply', text: 'Resposta do modelo: abra o terminal.', busy: false, correlation: 'matched' });
          return 'Resposta do modelo: abra o terminal.';
        },
      };
      throw new Error(`Unexpected import ${name}`);
    },
    localStorage: { getItem: () => 'muse', setItem: () => {} },
    window: {
      setInterval: () => 1, clearInterval: () => {},
      zaraIPC: { pilot: {
        learn: async (turn: learning.PilotTurnObservation) => { calls.learned.push(turn); return options.learn ? options.learn(turn) : { success: true, path: 'note.md' }; },
        command: async (text: string) => { calls.commands.push(text); return options.command ? options.command(text) : { handled: false, success: true, response: '' }; },
        context: async (text: string) => { calls.contexts.push(text); return options.context ? options.context(text) : { success: true, context: `revision-${calls.contexts.length}` }; },
      } },
    },
  });
  let tree: any;
  const render = () => { stateIndex = refIndex = effectIndex = 0; tree = exports.PilotSessionProvider({ children: null }); return tree.props.value; };
  const find = (node: any, type: string): any => {
    if (!node || typeof node !== 'object') return undefined;
    if (node.type === type) return node;
    for (const child of [node.props?.children].flat()) { const found = find(child, type); if (found) return found; }
  };
  render();
  const ready = async () => {
    find(tree, 'webview').props.ref(webview);
    render(); events['dom-ready']();
    for (let i = 0; i < 20; i++) await Promise.resolve();
    return render();
  };
  return { session: () => tree.props.value, render, ready, calls, voice, reload: () => find(tree, 'button').props.onClick() };
}

test('ordinary text commands return the executor reply even when the pilot account is disconnected', async () => {
  for (const success of [true, false]) {
    const response = success ? 'Volume confirmado.' : 'O executor falhou.';
    const h = sessionHarness({ signedIn: false, command: async () => ({ handled: true, success, response }) });
    assert.equal(await h.session().send('diminua o volume'), response);
    assert.deepEqual(h.calls.contexts, []);
    assert.deepEqual(h.calls.messages, []);
    assert.deepEqual(h.calls.learned, []);
  }
});

test('confirmed text replies record each actual submission, even when the same phrase is repeated', async () => {
  const h = sessionHarness();
  await h.ready();
  await h.session().send('Planeje a entrega');
  await h.session().send('Planeje a entrega');
  assert.equal(h.calls.learned.length, 2);
  assert.notEqual(h.calls.learned[0].event_id, h.calls.learned[1].event_id);
  assert.equal(h.calls.learned[0].user_text, 'Planeje a entrega');
  assert.equal(h.calls.learned[0].channel, 'text');
  assert.equal(h.calls.learned[0].assistant_text, 'Resposta do modelo: abra o terminal.');
  assert.doesNotMatch(JSON.stringify(h.calls.learned), /revision-/);
});

test('text reply returns while the memory write is pending or rejected', async () => {
  for (const learn of [async () => new Promise<learning.PilotLearningReceipt>(() => {}), async () => { throw new Error('offline'); }]) {
    const h = sessionHarness({ learn });
    await h.ready();
    assert.equal(await h.session().send('Plano'), 'Resposta do modelo: abra o terminal.');
    assert.equal(h.calls.learned.length, 1);
  }
});

test('viewing the current Muse account preserves the active voice session', async () => {
  const h = sessionHarness();
  await h.ready();
  h.voice.voiceState = 'listening';
  h.render();
  h.session().connect();
  assert.equal(h.calls.stops, 0);
  assert.equal(h.voice.voiceState, 'listening');
});

test('the account panel exposes open/close state without stopping an active voice', async () => {
  const h = sessionHarness();
  await h.ready();
  assert.equal(h.session().accountOpen, false);
  h.voice.voiceState = 'listening';
  h.render().connect();
  assert.equal(h.render().accountOpen, true);
  h.session().closeAccount();
  assert.equal(h.render().accountOpen, false);
  assert.equal(h.calls.stops, 0);
  assert.equal(h.voice.voiceState, 'listening');
});

test('closing a signed-out account exposes cancellation without pretending it is connected', async () => {
  const h = sessionHarness({ signedIn: false });
  await h.ready();
  h.session().connect();
  assert.equal(h.render().accountOpen, true);
  h.session().closeAccount();
  const session = h.render();
  assert.equal(session.accountOpen, false);
  assert.equal(session.connected, false);
  assert.equal(h.calls.stops, 0);
});

test('switching providers still stops the old voice session', async () => {
  const h = sessionHarness();
  await h.ready();
  h.voice.voiceState = 'listening';
  h.render();
  h.session().connect('openai');
  for (let index = 0; index < 20; index++) await Promise.resolve();
  assert.equal(h.calls.stops, 1);
  assert.equal(h.render().provider, 'openai');
});

test('text turns fetch a fresh context and never execute a model answer as a command', async () => {
  const h = sessionHarness();
  await h.ready();
  assert.equal(await h.session().send('meu plano'), 'Resposta do modelo: abra o terminal.');
  await h.session().send('e agora?');
  assert.deepEqual(h.calls.commands, ['meu plano', 'e agora?']);
  assert.deepEqual(h.calls.messages, [{ text: 'meu plano', context: 'revision-1' }, { text: 'e agora?', context: 'revision-2' }]);
  assert.equal(h.calls.manual, 0);
});

test('text command errors are visible without model or manual fallback', async () => {
  const h = sessionHarness({ goal: 'abrir', command: async () => ({ handled: false, success: false, response: '', error: 'Executor indisponível.' }) });
  await assert.rejects(h.session().send('use computer: abrir'), /Executor indisponível/);
  assert.deepEqual(h.calls.messages, []);
  assert.equal(h.calls.manual, 0);
});

test('the text manual path is a fallback after pilot.command only', async () => {
  for (const handled of [true, false]) {
    const h = sessionHarness({ goal: 'abrir', command: async () => ({ handled, success: true, response: handled ? 'principal' : '' }) });
    const reply = await h.session().send('use computer: abrir');
    assert.deepEqual(h.calls.commands, ['use computer: abrir']);
    assert.equal(h.calls.manual, handled ? 0 : 1);
    assert.equal(reply, handled ? 'principal' : 'Resultado confirmado.');
    assert.deepEqual(h.calls.contexts, []);
  }
});

test('session stop or provider switch invalidates a pending text executor reply', async () => {
  for (const action of ['stop', 'switch', 'reload']) {
    let resolve!: (value: any) => void;
    const pending = new Promise<any>(done => { resolve = done; });
    const h = sessionHarness({ command: () => pending });
    const reply = h.session().send('command');
    const rejection = assert.rejects(reply, /interrompida/);
    if (action === 'stop') await h.session().voice.stop();
    else if (action === 'switch') h.session().connect('openai');
    else h.reload();
    resolve({ handled: true, success: true, response: 'stale' });
    await rejection;
    assert.deepEqual(h.calls.messages, []);
  }
});

test('context failures remain visible and signed-out pages cannot receive text', async () => {
  const unavailable = sessionHarness({ context: async () => ({ success: false, context: '', error: 'Vault indisponível.' }) });
  await assert.rejects(unavailable.session().send('question'), /Vault indisponível/);
  const signedOut = sessionHarness({ signedIn: false });
  await signedOut.ready();
  await assert.rejects(signedOut.session().send('question'), /Entre na sua conta/);
  assert.deepEqual(signedOut.calls.messages, []);
});
