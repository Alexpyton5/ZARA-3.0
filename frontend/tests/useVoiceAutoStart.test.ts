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
  const render = (ready: boolean, visible: boolean, state: string) => {
    index = 0;
    exports.useVoiceAutoStart(ready, visible, state, () => { starts++; });
  };
  return { render, count: () => starts };
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

test('a new login permits a new automatic start', () => {
  const h = harness();
  h.render(true, true, 'off');
  h.render(false, true, 'off');
  h.render(true, true, 'off');
  assert.equal(h.count(), 2);
});
