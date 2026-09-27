const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

// Renderer coverage for the multi-agent room organization (Fase 1, Parte 3):
// DELEGATE / REVIEW / HANDOFF rendering plus VERIFYING/REPAIRING chips, using
// the production source through the TS AST. Pure helpers are extracted and
// executed; the JSX branches are asserted against the production source.
const source = fs.readFileSync(path.join(__dirname,
  '../src/renderer/components/zara-lab-v2/LabRoom.tsx'), 'utf8')
const types = fs.readFileSync(path.join(__dirname,
  '../src/renderer/components/zara-lab-v2/labTypes.ts'), 'utf8')
const tree = ts.createSourceFile('LabRoom.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const functions = {}
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name && ['parseReview', 'handoffStage', 'normalizeConversationContent', 'humanize_conversation_label', 'humanizeConversationValue'].includes(node.name.text)) {
    functions[node.name.text] = node.getText(tree)
  }
  ts.forEachChild(node, visit)
}
visit(tree)
assert.ok(functions.parseReview, 'production parseReview helper exists')
assert.ok(functions.handoffStage, 'production handoffStage helper exists')
assert.ok(functions.normalizeConversationContent, 'production conversation normalizer exists')

const transpiled = Object.values(functions).map(code =>
  ts.transpileModule(code.replace(/\bexport /g, ''), { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText)
const harness = [
  'const HANDOFF_STAGES = ["STRATEGIST", "EXECUTOR", "REVIEWER", "MAESTRO"];',
  'const CONVERSATION_FIELDS = ["reply_to_alex", "answer", "response", "message", "summary"];',
  ...transpiled,
  'return { parseReview, handoffStage, normalizeConversationContent };',
].join('\n')
const helpers = new Function(harness)()

test('review verdict is parsed from the backend JSON payload', () => {
  assert.deepEqual(helpers.parseReview('{"verdict":"APPROVED","notes":"cobertura ok","artifact_ref":"a1"}'),
    { verdict: 'APPROVED', notes: 'cobertura ok' })
  assert.deepEqual(helpers.parseReview('{"verdict":"CHANGES_REQUESTED","notes":"falta teste de borda"}'),
    { verdict: 'CHANGES_REQUESTED', notes: 'falta teste de borda' })
  assert.deepEqual(helpers.parseReview('{"artifact_ref":"a1"}'), { verdict: '', notes: 'Atualização registrada pela equipe.' })
  assert.deepEqual(helpers.parseReview('reprovado em prosa'), { verdict: '', notes: 'reprovado em prosa' })
})

test('baton stage comes from JSON or the plain note text', () => {
  assert.equal(helpers.handoffStage('{"stage":"REVIEWER","artifact_ref":"a1"}'), 'REVIEWER')
  assert.equal(helpers.handoffStage('bastao entregue ao executor'), 'EXECUTOR')
  assert.equal(helpers.handoffStage('contexto sem estagio nomeado'), '')
})

test('conversation envelopes become human text instead of raw JSON', () => {
  assert.equal(helpers.normalizeConversationContent('{"reply_to_alex":"A equipe concluiu a análise."}'),
    'A equipe concluiu a análise.')
  assert.equal(helpers.normalizeConversationContent('{"answer":"Resposta objetiva.","run_id":"run-1"}'),
    'Resposta objetiva.')
  assert.equal(helpers.normalizeConversationContent('{"response":{"message":"Resposta aninhada."}}'),
    'Resposta aninhada.')
  assert.equal(helpers.normalizeConversationContent('{"title":"Plano","instruction":"Executar teste"}'),
    'Plano\n\nExecutar teste')
  assert.doesNotMatch(helpers.normalizeConversationContent('{"internal":"opaque","run_id":"run-1"}'), /[{}\"]/)
  assert.deepEqual(helpers.parseReview('{"artifact_ref":"a1"}'), { verdict: '', notes: 'Atualização registrada pela equipe.' })
})

test('task and artifact inspector text uses the same human renderer', () => {
  assert.match(source, /normalizeConversationContent\(task\.instruction\)/)
  assert.match(source, /normalizeConversationContent\(task\.result\)/)
  assert.match(source, /normalizeConversationContent\(artifact\.body\)/)
})

test('participant menus are exclusive and close after a real action', () => {
  assert.match(source, /const \[openPersonMenu, setOpenPersonMenu\] = useState<string \| null>\(null\)/)
  assert.match(source, /open=\{openPersonMenu === agent\.id\}/)
  assert.match(source, /const closeMenu = \(\) => setOpenPersonMenu/)
  assert.match(source, /archiveAgent\?\.\(agent\.id\).*closeMenu\(\)/s)
})

test('capability chips only use the factual Lab snapshot', () => {
  assert.match(source, /const factualCapabilities = \[/)
  assert.match(source, /aria-label="Estado factual do ZARA Lab"/)
  assert.doesNotMatch(source, /Voz preparada/)
  assert.doesNotMatch(source, /Navegador seguro/)
})

test('DELEGATE renders a Maestro -> Executor delegation card', () => {
  assert.match(source, /message\.kind === 'DELEGATE'/)
  assert.match(source, /Delegação · \{message\.author\} → \{target\}/)
  assert.match(source, /message\.to_agent_id \? nameOf\(message\.to_agent_id\) : label\(message\.to_role\)/)
  assert.match(source, /Maestro → \{label\(message\.to_role\)/)
})

test('REVIEW renders the reviewer verdict card, including loop exhaustion', () => {
  assert.match(source, /message\.kind === 'REVIEW'/)
  assert.match(source, /const review = parseReview\(message\.content\)/)
  assert.match(source, /reviewVerdictLabel\(review\.verdict\)/)
  assert.match(source, /message\.to_role === 'OWNER'/)
  assert.match(source, /reviewVerdictLabel\('REVIEW_LOOP_EXHAUSTED'\)/)
  assert.match(source, /Rodadas de revisão esgotadas/)
})

test('HANDOFF renders the STRATEGIST -> EXECUTOR -> REVIEWER -> MAESTRO baton', () => {
  assert.match(source, /message\.kind === 'HANDOFF'/)
  assert.match(source, /HANDOFF_STAGES\.map\(\(step, index\)/)
  assert.match(source, /handoffStageLabel\(step\)/)
})

test('VERIFYING and REPAIRING session states show a visible chip', () => {
  assert.match(source, /session\.state === 'VERIFYING'/)
  assert.match(source, /missionState === 'REPAIRING'/)
  assert.match(source, /Verificando o resultado/)
  assert.match(source, /Corrigindo com o executor/)
})

test('USER/AGENT/ZARA/SYSTEM rendering stays byte-for-byte on the old path', () => {
  assert.match(source, /const mine = message\.kind === 'USER'/)
  assert.match(source, /const system = message\.kind === 'ZARA'/)
  assert.match(source, /className=\{\`zl-message \$\{mine \? 'mine' : ''\} \$\{system \? 'system' : ''\}\`\}/)
  assert.match(source, /normalizeConversationContent\(message\.content\)/)
  assert.match(source, /message\.run_id && <span>Resposta registrada<\/span>/)
  assert.match(source, /\{mine && <Check size=\{13\} \/>\}/)
  // The old fallback branch must come after the three new kinds.
  const delegateAt = source.indexOf("message.kind === 'DELEGATE'")
  const fallbackAt = source.indexOf('const mine = message.kind')
  const returnAt = source.indexOf("return <article className={`zl-message ${mine ? 'mine' : ''}")
  assert.ok(delegateAt > 0 && returnAt > delegateAt && fallbackAt < delegateAt)
})

test('owner feedback exposes a stopped executor factually', () => {
  assert.match(source, /result\.code === 'OWNER_INPUT_ACCEPTED'/)
  assert.match(source, /ownerFeedbackAccepted && !running && !supervisorLive/)
  assert.match(source, /Orientação registrada\. O executor não está ativo agora/)
})

test('labTypes carries the addressed-message fields and new kinds/states', () => {
  assert.match(types, /to_agent_id\?: string \| null; to_role\?: string \| null; reply_to\?: string \| null; correlation_id\?: string \| null/)
  assert.match(types, /HANDOFF_STAGES = \['STRATEGIST', 'EXECUTOR', 'REVIEWER', 'MAESTRO'\]/)
  assert.match(types, /REVIEW_LOOP_EXHAUSTED: 'Revisões esgotadas'/)
  assert.match(types, /VERIFYING: 'Verificando'/)
  assert.match(types, /REPAIRING: 'Corrigindo'/)
})
