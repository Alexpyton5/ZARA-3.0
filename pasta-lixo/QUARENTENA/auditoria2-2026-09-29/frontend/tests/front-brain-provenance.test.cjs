const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const sourcePath = path.join(__dirname, '..', 'src', 'renderer', 'components', 'zara-home', 'frontBrainProvenance.ts');
const source = fs.readFileSync(sourcePath, 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const loaded = { exports: {} };
new Function('module', 'exports', output)(loaded, loaded.exports);
const { validateFrontBrainProvenance } = loaded.exports;

const run = (engine) => ({
  success: true,
  response_origin: 'front_brain_run',
  response: 'ok',
  engine,
  run_id: 'run_1',
  model_requested: engine,
  model_reported: null,
  provider: 'codex_cli',
  provenance_status: 'UNREPORTED',
  rerouted: false,
});

test('rejects Luna selection with unproved Astra conversational response', () => {
  assert.throws(() => validateFrontBrainProvenance({ response: 'x', engine: 'gpt-6-astra' }, 'gpt-5.6-luna'));
});

test('rejects Astra selection with unproved Luna conversational response', () => {
  assert.throws(() => validateFrontBrainProvenance({ response: 'x', engine: 'gpt-5.6-luna' }, 'gpt-6-astra'));
});

test('accepts positively identified deterministic local response without provider', () => {
  assert.doesNotThrow(() => validateFrontBrainProvenance({
    response: 'Volume verificado.', engine: 'pc_control', response_origin: 'local_deterministic',
  }, 'gpt-5.6-luna'));
});

test('rejects ambiguous response without model Run or local origin', () => {
  assert.throws(() => validateFrontBrainProvenance({ response: 'ok', engine: 'pc_control' }, 'gpt-5.6-luna'));
});

test('accepts coherent model receipt and rejects factual mismatch', () => {
  assert.doesNotThrow(() => validateFrontBrainProvenance(run('gpt-5.6-luna'), 'gpt-5.6-luna'));
  assert.throws(() => validateFrontBrainProvenance({
    ...run('gpt-5.6-luna'),
    model_reported: 'gpt-5.6-sol',
    provenance_status: 'MISMATCH_REJECTED',
    rerouted: true,
  }, 'gpt-5.6-luna'));
});
