const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

const root = path.join(__dirname, '..')
const main = fs.readFileSync(path.join(root, 'src/main.ts'), 'utf8')
const preload = fs.readFileSync(path.join(root, 'src/preload.ts'), 'utf8')
const globals = fs.readFileSync(path.join(root, 'src/renderer/types/global.d.ts'), 'utf8')
const handlers = fs.readFileSync(path.join(root, '..', 'core/ipc_handlers.py'), 'utf8')
const source = fs.readFileSync(path.join(root,
  'src/renderer/components/zara-lab-v2/ProposalEvidencePanel.tsx'), 'utf8')

test('proposal approval uses the Lab V1 IPC contract end to end', () => {
  assert.match(handlers, /'lab-v1-proposal-list':\s*self\.handle_lab_v1_proposal_list/)
  assert.match(handlers, /'lab-v1-proposal-update':\s*self\.handle_lab_v1_proposal_update/)
  assert.match(main, /ipcMain\.handle\('lab-v1-proposal-list', \(_event, payload\) => sendToPython\('lab-v1-proposal-list', payload\)\)/)
  assert.match(main, /ipcMain\.handle\('lab-v1-proposal-update', \(_event, payload\) => sendToPython\('lab-v1-proposal-update', payload\)\)/)
  assert.match(preload, /proposalList: \(\) => ipcRenderer\.invoke\('lab-v1-proposal-list', \{\}\)/)
  assert.match(preload, /proposalUpdate: \(payload: \{ proposalId: string; state: 'APPROVED' \| 'REJECTED' \}\) => ipcRenderer\.invoke\('lab-v1-proposal-update', \{ proposal_id: payload\.proposalId, state: payload\.state \}\)/)
  assert.match(globals, /proposalList\?: \(\) => Promise<any>/)
  assert.match(globals, /proposalUpdate\?: \(payload: \{ proposalId: string; state: 'APPROVED' \| 'REJECTED' \}\) => Promise<any>/)
  assert.match(source, /window\.zaraIPC\?\.labV1\?\.proposalList/)
  assert.match(source, /window\.zaraIPC\?\.labV1\?\.proposalUpdate/)
  assert.doesNotMatch(source, /window\.zaraIPC\?\.lab\?\.state/)
  assert.doesNotMatch(source, /window\.zaraIPC\?\.lab\?\.decideProposal/)
})

function loadPanel() {
  const output = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const module = { exports: {} }
  const icon = () => null
  const localRequire = (name) => {
    if (name === 'react') return React
    if (name === 'react/jsx-runtime') return require('react/jsx-runtime')
    if (name === 'lucide-react') return { AlertCircle: icon, Check: icon, FileCheck2: icon, RefreshCw: icon, ShieldCheck: icon, X: icon }
    if (name === './labTypes') return {
      asList: value => Array.isArray(value) ? value : [],
      failureText: error => error instanceof Error ? error.message : 'erro',
      label: value => value || 'Não informado',
      requireResult: value => value,
    }
    throw new Error(`unexpected import ${name}`)
  }
  new Function('require', 'exports', 'module', output)(localRequire, module.exports, module)
  return module.exports.ProposalEvidencePanel
}

test('BLOCKED_NEEDS_OWNER renders only the supplied blocker, gaps, decision and criteria', () => {
  const ProposalEvidencePanel = loadPanel()
  const html = renderToStaticMarkup(React.createElement(ProposalEvidencePanel, {
    session: {
      id: 'mission-1', team_id: 'team-1', objective: 'Melhorar o Lab', state: 'BLOCKED_NEEDS_OWNER', updated_at: 0,
      mission: { state: 'BLOCKED_NEEDS_OWNER', blocker: 'DRAFT_REJECTION_LIMIT' },
      capability_gaps: [{ id: 'gap-1', required: 'Aprovação do owner', detail: 'O rascunho excedeu o limite.' }],
      decisions: [{ id: 'decision-1', statement: 'Manter o runtime V1', rationale: 'É o caminho persistido.' }],
      acceptance_criteria: ['Mostrar o bloqueio real'],
    },
  }))

  assert.match(html, /Situação da missão/)
  assert.match(html, /Bloqueio/)
  assert.match(html, /DRAFT_REJECTION_LIMIT/)
  assert.match(html, /Lacunas/)
  assert.match(html, /Aprovação do owner/)
  assert.match(html, /Decisões registradas/)
  assert.match(html, /Manter o runtime V1/)
  assert.match(html, /Critérios de aceite/)
  assert.match(html, /Mostrar o bloqueio real/)
  assert.doesNotMatch(html, /Nenhum bloqueio|Sem lacunas|Sem decisões|Sem critérios/)
})

test('mission inspector omits absent snapshot fields instead of fabricating a status', () => {
  const ProposalEvidencePanel = loadPanel()
  const html = renderToStaticMarkup(React.createElement(ProposalEvidencePanel, {
    session: { id: 'mission-2', team_id: 'team-1', objective: 'Sem detalhes', state: 'WORKING', updated_at: 0 },
  }))

  assert.doesNotMatch(html, /Situação da missão|Bloqueio|Lacunas|Decisões registradas|Critérios de aceite/)
})
