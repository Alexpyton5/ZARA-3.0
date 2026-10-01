import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';

function harness() {
  const refs: Array<{ current: unknown }> = [];
  let index = 0;
  const exports: any = {};
  const source = readFileSync(path.resolve(__dirname, '../../src/renderer/lib/useVoiceAutoStart.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require: () => ({
    useRef: (value: unknown) => refs[index++] ||= { current: value },
    useEffect: (effect: () => void) => effect(),
  }) });
  let starts = 0;
  let markAttempted: (() => void) | undefined;
  const render = (ready: boolean, visible: boolean, state: string, intent?: any) => {
    index = 0;
    markAttempted = exports.useVoiceAutoStart(ready, visible, state, () => { starts++; }, intent);
  };
  return { render, count: () => starts, manual: () => markAttempted!() };
}

function pendingVoice(page = 'voz', provider = 'muse') {
  const consumed: boolean[] = [];
  const request = { provider, page };
  const options = { provider, page, accountOpen: true, ready: false, request,
    consume: (fulfilled: boolean) => consumed.push(fulfilled) };
  return { options, consumed };
}

test('voice starts once when a signed-in Muse conversation becomes visible', () => {
  const h = harness();
  h.render(false, true, 'off');
  h.render(true, false, 'off');
  assert.equal(h.count(), 0);
  h.render(true, true, 'off');
  h.render(true, true, 'off');
  assert.equal(h.count(), 1);
});

test('manual stop and page changes do not reopen the microphone in the same login', () => {
  const h = harness();
  h.render(true, true, 'off');
  h.render(true, true, 'listening');
  h.render(true, true, 'off');
  h.render(true, false, 'off');
  h.render(true, true, 'off');
  assert.equal(h.count(), 1);
});

test('an already active or failed voice never toggles automatically', () => {
  for (const state of ['starting', 'listening', 'waiting', 'speaking', 'controlling', 'error']) {
    const h = harness();
    h.render(true, true, state);
    h.render(true, true, 'off');
    assert.equal(h.count(), 0);
  }
});

test('readiness loss is not a new login and cannot reopen a stopped microphone', () => {
  const h = harness();
  h.render(true, true, 'off');
  h.render(false, true, 'off');
  h.render(true, true, 'off');
  assert.equal(h.count(), 1);
});

test('an explicit voice-page click waits for editable login and starts once, returning to the app', () => {
  const h = harness(), p = pendingVoice();
  h.render(false, false, 'off', p.options);
  h.render(false, false, 'off', p.options);
  assert.equal(h.count(), 0);
  assert.deepEqual(p.consumed, []);
  p.options.ready = true;
  h.render(true, false, 'off', p.options);
  h.render(true, false, 'off', p.options); // effect replay before the state update commits
  assert.equal(h.count(), 1);
  assert.deepEqual(p.consumed, [true]);
  h.render(true, true, 'off', { ...p.options, request: null, accountOpen: false });
  assert.equal(h.count(), 1);
});

test('closing the account, changing page or provider cancels intent even if login arrives together', () => {
  for (const change of [
    { accountOpen: false, ready: false },
    { page: 'conversa', ready: true },
    { provider: 'openai', ready: true },
  ]) {
    const h = harness(), p = pendingVoice();
    h.render(false, false, 'off', p.options);
    const cancelled = { ...p.options, ...change };
    h.render(cancelled.ready, true, 'off', cancelled);
    assert.equal(h.count(), 0);
    assert.deepEqual(p.consumed, [false]);
    h.render(true, true, 'off', { ...cancelled, request: null, accountOpen: false });
    assert.equal(h.count(), 0);
  }
});

test('explicit login and conversation autostart cannot toggle twice or reopen after manual stop', () => {
  const h = harness(), p = pendingVoice('conversa');
  h.render(false, true, 'off', p.options);
  p.options.ready = true;
  h.render(true, true, 'off', p.options);
  h.render(true, true, 'listening', { ...p.options, request: null, accountOpen: false });
  h.render(true, true, 'off', { ...p.options, request: null, accountOpen: false });
  assert.equal(h.count(), 1);
});

test('opening an account for inspection never starts voice behind the panel', () => {
  const h = harness();
  h.render(true, true, 'off', { provider: 'muse', page: 'conversa', accountOpen: true, ready: true });
  h.render(true, true, 'off', { provider: 'muse', page: 'conversa', accountOpen: false, ready: true });
  assert.equal(h.count(), 0);
});

test('signed-out account inspection on the voice page does not arm later conversation autostart', () => {
  const h = harness();
  h.render(false, false, 'off', { provider: 'muse', page: 'voz', accountOpen: true, ready: false });
  h.render(false, false, 'off', { provider: 'muse', page: 'voz', accountOpen: false, ready: false });
  h.render(true, true, 'off', { provider: 'muse', page: 'conversa', accountOpen: false, ready: true });
  assert.equal(h.count(), 0);
});

test('a manual start on the voice page consumes the later conversation automatic attempt', () => {
  const h = harness();
  h.render(true, false, 'off');
  h.manual();
  h.render(true, false, 'listening');
  h.render(true, true, 'off');
  assert.equal(h.count(), 0);
});

test('pending intent never toggles an active voice off; errors require a fresh explicit request', () => {
  for (const state of ['starting', 'listening', 'waiting', 'speaking', 'controlling']) {
    const h = harness(), p = pendingVoice();
    p.options.ready = true;
    h.render(true, true, state, p.options);
    assert.equal(h.count(), 0);
    assert.deepEqual(p.consumed, [true]);
  }
  const h = harness(), p = pendingVoice();
  p.options.ready = true;
  h.render(true, true, 'error', p.options);
  h.render(true, true, 'error', { ...p.options, request: null, accountOpen: false });
  h.render(true, true, 'off', { ...p.options, request: null, accountOpen: false });
  assert.equal(h.count(), 1);
  const retry = pendingVoice();
  retry.options.ready = true;
  h.render(true, true, 'error', retry.options);
  assert.equal(h.count(), 2);
});
