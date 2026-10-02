const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const source = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer', 'components',
  'zara-home', 'BrainSelector.tsx'), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2020 },
}).outputText;
const loaded = { exports: {} };
const localRequire = name => name === './homeActions'
  ? { errorMessage: () => 'error' } : require(name);
new Function('require', 'module', 'exports', output)(localRequire, loaded, loaded.exports);
const { BrainSelector, canTryBrain } = loaded.exports;

test('catalog discovery permits a first attempt without claiming proof', () => {
  assert.equal(canTryBrain('DISCOVERED_UNPROVEN'), true);
  assert.equal(canTryBrain('AVAILABLE'), true);
  for (const denied of ['UNKNOWN', 'OFFLINE', 'AUTH_REQUIRED', 'QUOTA_EXHAUSTED', 'ERROR']) {
    assert.equal(canTryBrain(denied), false, denied);
  }

  global.window = { zaraIPC: { engine: { change: () => {} } } };
  try {
    const markup = renderToStaticMarkup(React.createElement(BrainSelector, {
      disabled: false,
      selection: {
        selected: 'opencode/free-one', busy: false, available: false,
        status: 'Acesso não confirmado', refresh: () => {}, select: () => {},
        options: [
          { id: 'opencode/free-one', name: 'Free One', status: 'DISCOVERED_UNPROVEN' },
          { id: 'opencode/blocked', name: 'Blocked', status: 'AUTH_REQUIRED' },
        ],
      },
    }));
    assert.match(markup, /data-available="false"/);
    assert.match(markup, /<option value="opencode\/free-one" selected="">Free One — Acesso não confirmado<\/option>/);
    assert.match(markup, /<option value="opencode\/blocked" disabled="">Blocked — Entre na conta ChatGPT<\/option>/);
    assert.match(markup, /role="status">Acesso não confirmado<\/span>/);
  } finally {
    delete global.window;
  }
});

test('successful reply refreshes observed status without a manual action', () => {
  const inputSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer',
    'components', 'zara-home', 'TextCommandInput.tsx'), 'utf8');
  const tree = ts.createSourceFile('TextCommandInput.tsx', inputSource,
    ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX);
  let refreshOnConfirmed = false;
  const visit = node => {
    if (ts.isIfStatement(node) && node.expression.getText(tree) === 'confirmed && mounted.current') {
      const calls = [];
      const collect = child => {
        if (ts.isCallExpression(child)) calls.push(child.expression.getText(tree));
        ts.forEachChild(child, collect);
      };
      collect(node.thenStatement);
      refreshOnConfirmed = calls.includes('selection.refresh');
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  assert.equal(refreshOnConfirmed, true);
});
