const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

// Execute the production form handler, extracted through the TS AST, with
// transport/state seams. This is handler coverage, not a mounted Electron UI.
const source = fs.readFileSync(path.join(__dirname,
  '../src/renderer/components/zara-lab-v2/LabRoom.tsx'), 'utf8')
const tree = ts.createSourceFile('LabRoom.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
let handler
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'submit') handler = node.getText(tree)
  ts.forEachChild(node, visit)
}
visit(tree)
assert.ok(handler, 'production submit handler exists')
const js = ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText

async function submit({ open, response }) {
  const calls = [], selections = [], texts = []
  let pending
  const execute = new Function('text', 'missionOpen', 'creating', 'sessionId', 'window', 'perform',
    'requireResult', 'runDurableLabMutation', 'select', 'setCreating', 'setText',
    `${js}; submit({preventDefault(){}});`)
  execute('A voz ainda está lenta', open, !open, 'existing-session', { zaraIPC: { labV1: {} } },
    action => { pending = action() }, result => {
      if (!result.success) throw new Error('rejected')
      return result
    }, async (_api, kind, payload) => { calls.push({ kind, payload }); return response },
    value => selections.push(value), () => {}, value => texts.push(value))
  await pending
  return { calls, selections, texts }
}

test('active mission feedback accepts confirmation without a new session id', async () => {
  const result = await submit({ open: true, response: {
    success: true, accepted: true, operation_id: 'op-feedback', state: 'QUEUED',
    session_id: 'existing-session',
  } })
  assert.deepEqual(result.calls, [{ kind: 'roomMessage', payload: {
    sessionId: 'existing-session', text: 'A voz ainda está lenta',
  } }])
  assert.deepEqual(result.selections, [])
  assert.deepEqual(result.texts, [''])
})

test('new mission requires and selects the backend-created session', async () => {
  const result = await submit({ open: false, response: { success: true, session_id: 'new-session' } })
  assert.equal(result.calls[0].kind, 'roomMessage')
  assert.deepEqual(result.selections, ['new-session'])
  await assert.rejects(submit({ open: false, response: { success: true } }), /registrou a conversa/)
})

test('rejected feedback remains visible and does not clear owner text', async () => {
  await assert.rejects(submit({ open: true, response: { success: false } }), /rejected/)
})

test('composer lets the owner submit feedback while a mission is active', () => {
  assert.match(source, /disabled=\{busy \|\| !text\.trim\(\)\}/)
  assert.doesNotMatch(source, /disabled=\{busy \|\| !text\.trim\(\) \|\| missionOpen\}/)
  assert.match(source, /if \(!busy && text\.trim\(\)\) e\.currentTarget\.form\?\.requestSubmit\(\)/)
  assert.doesNotMatch(source, /text\.trim\(\) && !missionOpen/)
})

test('saved missing session is advisory and the room recovers from backend truth', () => {
  const hookSource = fs.readFileSync(path.join(__dirname,
    '../src/renderer/components/zara-lab-v2/useLabRoom.ts'), 'utf8')
  assert.match(hookSource, /sess\[aã\]o n\[aã\]o encontrada/i)
  assert.match(hookSource, /localStorage\.removeItem\('zara\.lab\.selection\.v1'\)/)
  assert.match(hookSource, /labV1\?\.snapshot\?\.\(\)/)
})
